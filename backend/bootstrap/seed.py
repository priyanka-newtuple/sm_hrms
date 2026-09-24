"""Seed data for modular backend."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from common.enums import DefaultRole
from common.logger import logger
from common.security import hash_password
from exceptions import PersistenceError
from filehandler.db_models import FilehandlerModelService
from permissions.db_models import PermissionsModelService
from roles.db_models import RolesModelService, UserRoleAssignment
from user.db_models import (
    AuthType,
    Organization,
    OrganizationStatus,
    Role,
    User,
    UserModelService,
    UserOrganization,
    UserRole,
    UserStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

    from database.manager import DatabaseServiceManager


def _resolve_existing_org_schema(engine: Engine, preferred_schema: str) -> str | None:
    """Return schema that currently contains organizations table.

    Resolution order:
    1) preferred schema
    2) public
    3) first available schema that has organizations
    """
    preferred_check_sql = """
    SELECT table_schema
    FROM information_schema.tables
    WHERE table_name = 'organizations'
      AND table_schema = :schema
    LIMIT 1;
    """
    any_schema_sql = """
    SELECT table_schema
    FROM information_schema.tables
    WHERE table_name = 'organizations'
    ORDER BY
      CASE WHEN table_schema = :preferred THEN 0
           WHEN table_schema = 'public' THEN 1
           ELSE 2
      END,
      table_schema
    LIMIT 1;
    """
    with engine.connect() as connection:
        preferred = connection.execute(
            text(preferred_check_sql), {"schema": preferred_schema}
        ).scalar()
        logger.info(f"Seed schema resolve: preferred={preferred_schema} preferred_hit={preferred}")
        if preferred:
            return str(preferred)
        if preferred_schema != "public":
            public = connection.execute(text(preferred_check_sql), {"schema": "public"}).scalar()
            logger.info(f"Seed schema resolve: public_hit={public}")
            if public:
                return str(public)
        fallback = connection.execute(
            text(any_schema_sql), {"preferred": preferred_schema}
        ).scalar()
        logger.info(f"Seed schema resolve: fallback_hit={fallback}")
        if fallback:
            return str(fallback)
    return None


def seed_minimum_data(
    engine: Engine,
    schema: str,
    org_id: str | None,
    org_name: str | None,
    org_slug: str | None,
) -> None:
    """Seed minimum data if bootstrap org config is provided."""
    if not (org_id and org_name and org_slug):
        logger.info("Seed skipped; bootstrap organization configuration is incomplete")
        return

    logger.info(
        f"Seed minimum data start: schema={schema} org_id={org_id} org_name={org_name} org_slug={org_slug}"
    )
    effective_schema = _resolve_existing_org_schema(engine, schema)
    if not effective_schema:
        raise RuntimeError(
            f"Bootstrap seed aborted: organizations table not found in schema '{schema}' or any fallback schema."
        )

    sql = f"""
    INSERT INTO "{effective_schema}".organizations (id, name, slug, settings, status)
    VALUES (:id, :name, :slug, '{{}}'::json, 'active')
    ON CONFLICT (id) DO NOTHING;
    """

    with engine.connect() as connection:
        connection.execute(text(sql), {"id": org_id, "name": org_name, "slug": org_slug})
        connection.commit()
    logger.info(f"Seeded bootstrap organization (org_id={org_id}, schema={effective_schema})")


def _ensure_org(
    db: Session,
    *,
    org_id: str,
    name: str,
    slug: str,
    settings: dict[str, Any] | None = None,
) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org:
        if org.status != OrganizationStatus.ACTIVE.value:
            org.status = OrganizationStatus.ACTIVE.value
            db.commit()
            db.refresh(org)
        return org

    by_slug = db.query(Organization).filter(Organization.slug == slug).first()
    if by_slug:
        logger.warning(
            f"Bootstrap org id missing but slug already exists; using existing org (requested_org_id={org_id}, existing_org_id={by_slug.id}, slug={slug})"
        )
        if by_slug.status != OrganizationStatus.ACTIVE.value:
            by_slug.status = OrganizationStatus.ACTIVE.value
            db.commit()
            db.refresh(by_slug)
        return by_slug

    org = Organization(
        id=org_id,
        name=name,
        slug=slug,
        settings=settings or {},
        status=OrganizationStatus.ACTIVE.value,
    )
    db.add(org)
    try:
        db.commit()
    except IntegrityError as exc:
        logger.warning(f"IntegrityError while creating org (org_id={org_id}), rolling back: {exc}")
        db.rollback()
        existing = db.query(Organization).filter(Organization.id == org_id).first()
        if existing:
            return existing
        raise
    db.refresh(org)
    return org


def _ensure_membership(db: Session, *, user_id: str, org_id: str, role: str) -> None:
    existing = (
        db.query(UserOrganization)
        .filter(UserOrganization.user_id == user_id, UserOrganization.organization_id == org_id)
        .first()
    )
    if existing:
        return
    db.add(
        UserOrganization(
            user_id=user_id,
            organization_id=org_id,
            role=role,
            status=UserStatus.ACTIVE.value,
        )
    )
    db.commit()


def _assign_admin_rbac_role(db: Session, *, user_id: str, org_id: str) -> None:
    admin_role = (
        db.query(Role)
        .filter(Role.organization_id == org_id, Role.name == DefaultRole.ADMIN.value)
        .first()
    )
    if not admin_role:
        return
    UserModelService().assign_role_to_user(
        db, user_id=user_id, org_id=org_id, role_id=admin_role.id
    )


def _ensure_bootstrap_user(
    db: Session,
    *,
    org_id: str,
    email: str,
    password: str,
    full_name: str,
    user_role: str,
) -> None:
    email = (email or "").strip().lower()
    if not email:
        logger.warning("Skipping bootstrap user creation: email is empty")
        return

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        logger.info(
            f"Bootstrap user already exists; skipping (email={email}, user_id={existing.id})"
        )
        if not existing.organization_id:
            existing.organization_id = org_id
            db.commit()
        _ensure_membership(db, user_id=existing.id, org_id=org_id, role=user_role)
        UserModelService().ensure_default_roles(db, org_id)
        _assign_admin_rbac_role(db, user_id=existing.id, org_id=org_id)
        return

    UserModelService().ensure_default_roles(db, org_id)

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=user_role,
        status=UserStatus.ACTIVE.value,
        auth_type=AuthType.LOCAL.value,
        organization_id=org_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        logger.warning(f"IntegrityError while creating user (email={email}), rolling back: {exc}")
        db.rollback()
        created = db.query(User).filter(User.email == email).first()
        if created:
            _ensure_membership(db, user_id=created.id, org_id=org_id, role=user_role)
            _assign_admin_rbac_role(db, user_id=created.id, org_id=org_id)
            return
        raise
    db.refresh(user)

    _ensure_membership(db, user_id=user.id, org_id=org_id, role=user_role)
    _assign_admin_rbac_role(db, user_id=user.id, org_id=org_id)
    logger.info(f"Created bootstrap user (email={email}, user_id={user.id}, org_id={org_id})")


def seed_bootstrap_admin(database_service_manager: Any, config: Any) -> None:
    """Create an initial admin (and optional super-admin) if not present."""
    cfg = config._configuration
    oauth_cfg = cfg.custom_oauth_configuration

    if not oauth_cfg.bootstrap_admin_email or not oauth_cfg.bootstrap_admin_password:
        logger.error(
            "Bootstrap admin skipped: BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be set"
        )
        raise ValueError("BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be set")
    if not oauth_cfg.bootstrap_super_admin_email or not oauth_cfg.bootstrap_super_admin_password:
        logger.error(
            "Bootstrap super admin skipped: BOOTSTRAP_SUPER_ADMIN_EMAIL and BOOTSTRAP_SUPER_ADMIN_PASSWORD must be set"
        )
        raise ValueError(
            "BOOTSTRAP_SUPER_ADMIN_EMAIL and BOOTSTRAP_SUPER_ADMIN_PASSWORD must be set"
        )

    bootstrap_cfg = cfg.bootstrap_configuration
    auth_cfg = cfg.auth_configuration

    postgres = database_service_manager.postgres_db_service()
    db = postgres.get_db_session()
    try:
        preferred_schema = (
            str(
                getattr(bootstrap_cfg, "app_schema", "")
                or os.environ.get("POSTGRES_APP_SCHEMA", "public")
            ).strip()
            or "public"
        )
        logger.info(f"Seed bootstrap admin start: preferred_schema={preferred_schema}")
        effective_schema = _resolve_existing_org_schema(postgres.engine, preferred_schema)
        if not effective_schema:
            raise RuntimeError(
                f"Bootstrap admin seed aborted: organizations table not found in schema '{preferred_schema}' or any fallback schema."
            )
        logger.info(f"Seed bootstrap admin using schema={effective_schema}")
        db.execute(text(f'SET search_path TO "{effective_schema}", public'))

        if oauth_cfg.bootstrap_super_admin_email and oauth_cfg.bootstrap_super_admin_password:
            platform_org = _ensure_org(
                db,
                org_id=auth_cfg.platform_org_id,
                name="Platform",
                slug="platform",
                settings={"is_platform": True},
            )
            _ensure_bootstrap_user(
                db,
                org_id=platform_org.id,
                email=oauth_cfg.bootstrap_super_admin_email,
                password=oauth_cfg.bootstrap_super_admin_password,
                full_name="Bootstrap Super Admin",
                user_role=UserRole.SUPERADMIN.value,
            )

        if (
            bootstrap_cfg.seed_org_id
            and bootstrap_cfg.seed_org_name
            and bootstrap_cfg.seed_org_slug
        ):
            target_org_id = bootstrap_cfg.seed_org_id
            target_org_name = bootstrap_cfg.seed_org_name
            target_org_slug = bootstrap_cfg.seed_org_slug
        else:
            target_org_id = auth_cfg.default_org_id
            target_org_name = "Default Organization"
            target_org_slug = "default"

        target_org = _ensure_org(
            db,
            org_id=target_org_id,
            name=target_org_name,
            slug=target_org_slug,
            settings={},
        )
        _ensure_bootstrap_user(
            db,
            org_id=target_org.id,
            email=oauth_cfg.bootstrap_admin_email,
            password=oauth_cfg.bootstrap_admin_password,
            full_name="Bootstrap Admin",
            user_role=UserRole.ADMIN.value,
        )
    except (SQLAlchemyError, ValueError, PersistenceError) as exc:
        logger.error(f"Bootstrap seeding failed (non-fatal): {exc}")
        return
    except Exception as exc:
        logger.error(f"Bootstrap seeding unexpected error (non-fatal): {exc}", exc_info=True)
        return
    finally:
        db.close()


def seed_default_file_types_for_active_organizations(
    database_service_manager: DatabaseServiceManager,
) -> None:
    """Idempotently provision default file types after bootstrap creates organizations."""
    db = database_service_manager.postgres_db_service().get_db_session()
    try:
        organization_ids = [
            str(row[0])
            for row in (
                db.query(Organization.id)
                .filter(Organization.status == OrganizationStatus.ACTIVE.value)
                .all()
            )
        ]
    except (SQLAlchemyError, PersistenceError) as exc:
        logger.error(
            f"Default file type bootstrap failed while listing organizations: {exc}",
            exc_info=True,
        )
        return
    finally:
        db.close()

    file_types = FilehandlerModelService(database_service_manager)
    created = 0
    for organization_id in organization_ids:
        try:
            created += file_types.seed_default_file_types(organization_id)
        except (SQLAlchemyError, PersistenceError) as exc:
            logger.error(
                f"Default file type bootstrap failed for org {organization_id}: {exc}",
                exc_info=True,
            )
    logger.info(
        "Default file type bootstrap complete: organizations=%d created=%d",
        len(organization_ids),
        created,
    )


def seed_permissions_catalog(database_service_manager: DatabaseServiceManager) -> None:
    """Idempotently seed the global permission catalog into the DB."""
    db = database_service_manager.postgres_db_service().get_db_session()
    try:
        svc = PermissionsModelService(database_service_manager)
        created = svc.ensure_default_permissions(db)
        logger.info(f"seed_permissions_catalog: {len(created)} permission(s) ensured")
    except (SQLAlchemyError, PersistenceError) as exc:
        logger.error(f"seed_permissions_catalog failed (non-fatal): {exc}", exc_info=True)
    except Exception as exc:
        logger.error(f"seed_permissions_catalog unexpected error (non-fatal): {exc}", exc_info=True)
    finally:
        db.close()


def _backfill_single_superadmin_user(db: Session, roles_svc: RolesModelService, user: User) -> bool:
    """Assign the superadmin role to a superadmin user, correcting wrong assignments."""
    org_id = str(user.organization_id)
    user_id = str(user.id)

    superadmin_role = roles_svc.get_role_by_name(db, org_id, DefaultRole.SUPERADMIN.value)
    if superadmin_role is None:
        roles = roles_svc.ensure_default_roles(db, org_id)
        superadmin_role = next((r for r in roles if r.name == DefaultRole.SUPERADMIN.value), None)
    if superadmin_role is None:
        return False

    existing = (
        db.query(UserRoleAssignment)
        .filter(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.organization_id == org_id,
        )
        .all()
    )
    if existing:
        if len(existing) == 1 and existing[0].role_id == superadmin_role.id:
            return False
        for assignment in existing:
            db.delete(assignment)
        db.flush()

    roles_svc.assign_role_to_user(db, user_id, org_id, superadmin_role.id)
    db.commit()
    return True


def _backfill_single_user(db: Session, roles_svc: RolesModelService, user: User) -> bool:
    """Assign the admin role to a single user if not already assigned.

    Returns True if assignment was made, False if skipped.
    """
    org_id = str(user.organization_id)
    user_id = str(user.id)

    existing = (
        db.query(UserRoleAssignment)
        .filter(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.organization_id == org_id,
        )
        .first()
    )
    if existing:
        return False

    admin_role = roles_svc.get_role_by_name(db, org_id, DefaultRole.ADMIN.value)
    if admin_role is None:
        roles = roles_svc.ensure_default_roles(db, org_id)
        admin_role = next((r for r in roles if r.name == DefaultRole.ADMIN.value), None)
    if admin_role is None:
        return False

    roles_svc.assign_role_to_user(db, user_id, org_id, admin_role.id)
    return True


def backfill_user_roles(database_service_manager: DatabaseServiceManager) -> None:
    """Backfill existing admin users into user_roles table.

    Idempotent — safe to run on every startup. Does nothing once all users
    are already assigned. Introduced in STAT-126 PR 3.
    """
    db = database_service_manager.postgres_db_service().get_db_session()
    try:
        roles_svc = RolesModelService()
        assigned = 0

        superadmin_users = (
            db.query(User)
            .filter(
                User.organization_id.isnot(None),
                User.role == UserRole.SUPERADMIN.value,
            )
            .all()
        )
        for user in superadmin_users:
            try:
                if _backfill_single_superadmin_user(db, roles_svc, user):
                    assigned += 1
            except (SQLAlchemyError, PersistenceError, ValueError) as exc:
                logger.error(
                    f"backfill_user_roles: failed for superadmin {user.id}: {exc}", exc_info=True
                )
                continue
            except Exception as exc:
                logger.error(
                    f"backfill_user_roles: unexpected error for superadmin {user.id}: {exc}",
                    exc_info=True,
                )
                continue

        admin_users = (
            db.query(User)
            .filter(
                User.organization_id.isnot(None),
                User.role == UserRole.ADMIN.value,
            )
            .all()
        )
        for user in admin_users:
            try:
                if _backfill_single_user(db, roles_svc, user):
                    assigned += 1
            except (SQLAlchemyError, PersistenceError, ValueError) as exc:
                logger.error(
                    f"backfill_user_roles: failed for user {user.id}: {exc}", exc_info=True
                )
                continue
            except Exception as exc:
                logger.error(
                    f"backfill_user_roles: unexpected error for user {user.id}: {exc}",
                    exc_info=True,
                )
                continue

        if assigned:
            logger.info(f"backfill_user_roles: assigned {assigned} user(s) to roles")
    except (SQLAlchemyError, PersistenceError) as exc:
        logger.error(f"backfill_user_roles failed (non-fatal): {exc}", exc_info=True)
    except Exception as exc:
        logger.error(f"backfill_user_roles unexpected error (non-fatal): {exc}", exc_info=True)
    finally:
        db.close()
