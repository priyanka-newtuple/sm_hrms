"""Read-only aggregate queries for organization usage analytics.

Receives a per-request Session — no session management of its own, mirroring
``organizations/db_models.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import case, func

from analytics.models.interface import LOGIN_EVENT_TYPES, AnalyticsGroupBy
from common.enums import AuditMetadataType
from common.logger import logger
from exceptions import PersistenceError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AuditModelProvider(Protocol):
    """Injected service exposing the unified ``audit_events`` ORM model."""

    audit_event_model: Any


class UserModelProvider(Protocol):
    """Injected service exposing the ``users`` ORM model."""

    user_model: Any


class AnalyticsModelService:
    """Executes tenant-scoped aggregate queries against unified audit events."""

    def __init__(self, database_service_manager: Any = None) -> None:
        """Stateless — each method receives the per-request DB session as a parameter."""
        _ = database_service_manager

    @staticmethod
    def _audit_model(audit_model_service: AuditModelProvider):
        """Resolve the audit ORM model from the service injected through the manager."""
        audit_model = getattr(audit_model_service, "audit_event_model", None)
        if audit_model is None:
            raise RuntimeError("Audit event model service unavailable")
        return audit_model

    @staticmethod
    def _window(
        query,
        audit_model,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
    ):
        """Limit a query to one organization and a half-open UTC time window."""
        return query.filter(
            audit_model.organization_id == organization_id,
            audit_model.event_timestamp >= date_from,
            audit_model.event_timestamp < date_to,
        )

    @staticmethod
    def _utc_bucket(unit: str, audit_model):
        """Create a PostgreSQL expression that groups timestamps in UTC."""
        return func.date_trunc(unit, func.timezone("UTC", audit_model.event_timestamp))

    @staticmethod
    def _list_users_by_ids(
        db: Session, user_ids: list[str], user_model_service: UserModelProvider
    ) -> list[Any]:
        """Load users by ID through the user model service injected from ``main.py``."""
        if not user_ids:
            return []
        user_model = getattr(user_model_service, "user_model", None)
        if user_model is None:
            raise RuntimeError("User model service unavailable")
        return db.query(user_model).filter(user_model.id.in_(user_ids)).all()

    def _login_buckets(
        self,
        db: Session,
        audit_model: Any,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        login_filter: tuple[Any, ...],
        unit: str,
    ) -> list[tuple[Any, int]]:
        """Count successful login events for one time-bucket size (day/week)."""
        bucket = self._utc_bucket(unit, audit_model)
        return (
            self._window(
                db.query(bucket.label("bucket"), func.count().label("count")),
                audit_model,
                organization_id,
                date_from,
                date_to,
            )
            .filter(*login_filter)
            .group_by(bucket)
            .order_by(bucket.asc())
            .all()
        )

    def login_activity(
        self,
        db: Session,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        *,
        audit_model_service: AuditModelProvider,
    ) -> dict[str, Any]:
        """Count successful logins, active users, and daily or weekly buckets."""
        try:
            audit_model = self._audit_model(audit_model_service)
            login_filter = (
                audit_model.event_type.in_(LOGIN_EVENT_TYPES),
                audit_model.user_id.isnot(None),
            )
            base = self._window(
                db.query(audit_model), audit_model, organization_id, date_from, date_to
            ).filter(*login_filter)
            total_logins = int(base.count())
            active_users = int(
                self._window(
                    db.query(func.count(func.distinct(audit_model.user_id))),
                    audit_model,
                    organization_id,
                    date_from,
                    date_to,
                )
                .filter(*login_filter)
                .scalar()
                or 0
            )
            args = (db, audit_model, organization_id, date_from, date_to, login_filter)
            return {
                "total_logins": total_logins,
                "active_users": active_users,
                "daily": self._login_buckets(*args, "day"),
                "weekly": self._login_buckets(*args, "week"),
            }
        except Exception as exc:
            logger.exception(f"Analytics login aggregation failed for org {organization_id} from {date_from} to {date_to}: {exc}")  # fmt: skip
            raise PersistenceError(f"Unable to aggregate login activity: {exc}") from exc

    def action_breakdown(
        self,
        db: Session,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        *,
        audit_model_service: AuditModelProvider,
    ) -> list[dict[str, Any]]:
        """Count non-authentication events by action type and category."""
        try:
            audit_model = self._audit_model(audit_model_service)
            rows = (
                self._window(
                    db.query(
                        audit_model.event_type,
                        audit_model.metadata_type,
                        func.count().label("count"),
                    ),
                    audit_model,
                    organization_id,
                    date_from,
                    date_to,
                )
                .filter(audit_model.metadata_type != AuditMetadataType.AUTH.value)
                .group_by(audit_model.event_type, audit_model.metadata_type)
                .order_by(func.count().desc(), audit_model.event_type.asc())
                .all()
            )
            return [
                {"action": action, "category": category, "count": int(count)}
                for action, category, count in rows
            ]
        except Exception as exc:
            logger.exception(f"Analytics action aggregation failed for org {organization_id} from {date_from} to {date_to}: {exc}")  # fmt: skip
            raise PersistenceError(f"Unable to aggregate action breakdown: {exc}") from exc

    def _user_page(
        self,
        db: Session,
        audit_model: Any,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        limit: int,
        offset: int,
    ) -> tuple[list[Any], int]:
        """One page of per-user login/action aggregates, most active first."""
        is_login = audit_model.event_type.in_(LOGIN_EVENT_TYPES)
        is_action = audit_model.metadata_type != AuditMetadataType.AUTH.value
        total_actions = func.sum(case((is_action, 1), else_=0))
        query = (
            self._window(
                db.query(
                    audit_model.user_id.label("user_id"),
                    func.max(case((is_login, audit_model.event_timestamp), else_=None)).label(
                        "last_login_at"
                    ),
                    func.sum(case((is_login, 1), else_=0)).label("login_count"),
                    total_actions.label("total_actions"),
                    func.max(audit_model.actor_name).label("actor_name"),
                ),
                audit_model,
                organization_id,
                date_from,
                date_to,
            )
            .filter(audit_model.user_id.isnot(None))
            .group_by(audit_model.user_id)
        )
        total = int(query.count())
        rows = (
            query.order_by(total_actions.desc(), audit_model.user_id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, total

    def _actions_by_user(
        self,
        db: Session,
        audit_model: Any,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        user_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Per-user action-type/category counts for the given users."""
        action_rows = (
            self._window(
                db.query(
                    audit_model.user_id,
                    audit_model.event_type,
                    audit_model.metadata_type,
                    func.count().label("count"),
                ),
                audit_model,
                organization_id,
                date_from,
                date_to,
            )
            .filter(
                audit_model.user_id.in_(user_ids),
                audit_model.metadata_type != AuditMetadataType.AUTH.value,
            )
            .group_by(
                audit_model.user_id,
                audit_model.event_type,
                audit_model.metadata_type,
            )
            .order_by(
                audit_model.user_id.asc(),
                func.count().desc(),
                audit_model.event_type.asc(),
            )
            .all()
        )
        actions_by_user: dict[str, list[dict[str, Any]]] = {}
        for action_row in action_rows:
            actions_by_user.setdefault(str(action_row.user_id), []).append(
                {
                    "action": action_row.event_type,
                    "category": action_row.metadata_type,
                    "count": int(action_row.count),
                }
            )
        return actions_by_user

    @staticmethod
    def _assemble_user_rows(
        rows: list[Any],
        users_by_id: dict[str, Any],
        actions_by_user: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Merge aggregates with user records into response rows."""
        result = []
        for row in rows:
            user_id = str(row.user_id)
            user = users_by_id.get(user_id)
            # Auth rows are written by the auth service with actor_type="system"
            # even for real humans, so actor_type cannot distinguish people from
            # automation — only the literal "system" user id (no users row) is.
            is_system = user is None and user_id.lower() == "system"
            result.append(
                {
                    "user_id": user_id,
                    "name": (
                        user.full_name
                        if user
                        else "System"
                        if is_system
                        else row.actor_name or "Deleted user"
                    ),
                    "email": user.email if user else None,
                    "actor_type": "system" if is_system else "user",
                    "last_login_at": row.last_login_at,
                    "login_count": int(row.login_count or 0),
                    "total_actions": int(row.total_actions or 0),
                    "actions": actions_by_user.get(user_id, []),
                }
            )
        return result

    def user_activity(
        self,
        db: Session,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        *,
        limit: int,
        offset: int,
        audit_model_service: AuditModelProvider,
        user_model_service: UserModelProvider,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of login and action aggregates per actor.

        Current users are enriched from the users table. Missing users fall
        back to their recorded audit name, while system events are labeled as
        automated activity.
        """
        try:
            audit_model = self._audit_model(audit_model_service)
            rows, total = self._user_page(
                db, audit_model, organization_id, date_from, date_to, limit, offset
            )
            user_ids = [str(row.user_id) for row in rows]
            users = self._list_users_by_ids(db, user_ids, user_model_service)
            users_by_id = {str(user.id): user for user in users}
            actions_by_user = self._actions_by_user(
                db, audit_model, organization_id, date_from, date_to, user_ids
            )
            return self._assemble_user_rows(rows, users_by_id, actions_by_user), total
        except Exception as exc:
            logger.exception(f"Analytics user aggregation failed for org {organization_id} from {date_from} to {date_to}: {exc}")  # fmt: skip
            raise PersistenceError(f"Unable to aggregate user activity: {exc}") from exc

    def _dimension_map(self, audit_model: Any) -> dict[AnalyticsGroupBy, Any]:
        """Map each approved group-by dimension to its SQL expression."""
        return {
            AnalyticsGroupBy.DAY: self._utc_bucket("day", audit_model),
            AnalyticsGroupBy.WEEK: self._utc_bucket("week", audit_model),
            AnalyticsGroupBy.USER: audit_model.user_id,
            AnalyticsGroupBy.ACTION: audit_model.event_type,
            AnalyticsGroupBy.CATEGORY: audit_model.metadata_type,
        }

    def _resolve_user_labels(
        self, db: Session, rows: list[dict[str, Any]], user_model_service: UserModelProvider
    ) -> None:
        """Replace raw user ids in the 'user' column with display names, in place."""
        ids = {str(row["user"]) for row in rows if row.get("user")}
        users = self._list_users_by_ids(db, list(ids), user_model_service)
        labels = {str(user.id): user.full_name for user in users}
        for row in rows:
            raw_user = row.get("user")
            if raw_user:
                uid = str(raw_user)
                row["user"] = labels.get(
                    uid,
                    "System" if uid.lower() == "system" else f"Deleted user ({uid})",
                )

    @staticmethod
    def _normalize_rows(rows: list[dict[str, Any]]) -> None:
        """Coerce day/week buckets to ISO dates and counts to int, in place."""
        for row in rows:
            for dimension in ("day", "week"):
                value = row.get(dimension)
                if isinstance(value, datetime):
                    row[dimension] = value.date().isoformat()
            row["count"] = int(row["count"])

    def flexible(
        self,
        db: Session,
        organization_id: str,
        date_from: datetime,
        date_to: datetime,
        *,
        group_by: list[AnalyticsGroupBy],
        include_auth: bool,
        event_type: str | None,
        user_id: str | None,
        limit: int,
        offset: int,
        audit_model_service: AuditModelProvider,
        user_model_service: UserModelProvider,
    ) -> tuple[list[dict[str, Any]], int]:
        """Run one page of an aggregate query using approved dimensions only."""
        try:
            audit_model = self._audit_model(audit_model_service)
            dimensions = self._dimension_map(audit_model)
            expressions = [dimensions[dimension].label(dimension.value) for dimension in group_by]
            query = self._window(
                db.query(*expressions, func.count().label("count")),
                audit_model,
                organization_id,
                date_from,
                date_to,
            )
            if not include_auth:
                query = query.filter(audit_model.metadata_type != AuditMetadataType.AUTH.value)
            if event_type:
                query = query.filter(audit_model.event_type == event_type)
            if user_id:
                query = query.filter(audit_model.user_id == user_id)
            if AnalyticsGroupBy.USER in group_by:
                query = query.filter(audit_model.user_id.isnot(None))
            query = query.group_by(*[dimensions[dimension] for dimension in group_by])
            total = int(query.count())
            query = query.order_by(*[dimensions[dimension].asc() for dimension in group_by])
            rows = [dict(row._mapping) for row in query.offset(offset).limit(limit).all()]
            if AnalyticsGroupBy.USER in group_by:
                self._resolve_user_labels(db, rows, user_model_service)
            self._normalize_rows(rows)
            return rows, total
        except Exception as exc:
            logger.exception(f"Flexible analytics query failed for org {organization_id} from {date_from} to {date_to}: {exc}")  # fmt: skip
            raise PersistenceError(f"Unable to run flexible analytics query: {exc}") from exc
