"""Read the workflow-enrollment board: which rows, what they show, and what they total.

This is one endpoint, `GET /workflow-enrollments`, and the most performance-sensitive read in
the module. It answers several questions at once — a page of rows, per-state counts, a total
count, numeric column totals, identifier options — over a set the caller may only partly be
allowed to see.

Two things shape the code:

**A read policy is the authority, not the query.** Some of it pushes down into SQL; the rest can
only be answered from a loaded row. Every row that reaches a response is policy-projected and
masked regardless of what SQL managed to filter, so a value the actor may not read cannot leak
through a totals column or a facet count.

**Scans are bounded.** A row-level condition that SQL cannot express forces a scan, and a scan
stops at a configured cap rather than reading a table. A response built from a truncated scan
understates its counts, which the caller is told about rather than left to infer.

The typed shapes this works with — the parsed request, the read access split, the scan limit,
the totals accumulator and the per-page context — are contracts rather than mechanics, so they
live in `workflow/models/interface.py` alongside the module's other typed records.

What stays in `workflow/manager.py` is the use case: it resolves the context once, then asks
this service for each section of the response.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from common.configuration import get_configuration
from common.logger import logger
from entities.models.interface import (
    DISPLAY_NAME_FIELD_KEYS,
    IDENTIFIER_FIELD_KEY,
    EntityRecord,
)
from exceptions import ValidationError
from workflow.models.interface import (
    ENROLLMENT_PAGE_SIZE_CAP,
    IDENTIFIER_OPTION_CAP,
    UNASSIGNED_FILTER_SENTINEL,
    EnrollmentAggregateFilters,
    EnrollmentAggregates,
    EnrollmentSortDirection,
    EnrollmentSortField,
    EnrollmentSummaryContext,
    EnrollmentSummaryPageData,
    EnrollmentSummaryRequest,
    EntityReadAccess,
    FieldNumericAggregate,
    FieldTotalAccumulator,
    FieldTotalErrorCode,
    ScanLimit,
)
from workflow.models.response import (
    FieldTotalError,
    FieldTotalValue,
    WorkflowEnrollmentSummary,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from blob_storage.service import BlobStorageService
    from common.protocols import EntityConditionSpec, EntityReadPolicy
    from entities.manager import EntitiesServiceManager
    from filehandler.manager import FilehandlerServiceManager
    from workflow.db_models import WorkflowEnrollmentSummaryRow, WorkflowModelService
    from workflow.services.transition_evaluation import TransitionEvaluationService


class EnrollmentSummaryService:
    """Owns the enrollment-board read: request shaping, read policy, and totals."""

    def __init__(
        self,
        workflow_db: WorkflowModelService,
        entities_service_manager: EntitiesServiceManager,
        transition_evaluation: TransitionEvaluationService,
        blob_storage_service: BlobStorageService | None,
        filehandler_service_manager: FilehandlerServiceManager | None,
    ) -> None:
        """Take the stores and the guard evaluator this read needs.

        `transition_evaluation` is handed in by the manager rather than built here, the same way
        simulation receives it: a capability service does not construct another. It is used only
        to work out which transitions a row may offer.
        """
        self.workflow_db = workflow_db
        self.entities_service_manager = entities_service_manager
        self.transition_evaluation = transition_evaluation
        self.blob_storage_service = blob_storage_service
        self.filehandler_service_manager = filehandler_service_manager

    @staticmethod
    def scan_bounds() -> tuple[int, int]:
        """Rows read per chunk, and in total, by any bounded row-policy scan."""
        workflow_config = get_configuration().workflow_configuration
        return (
            workflow_config.row_condition_scan_chunk,
            workflow_config.row_condition_scan_cap,
        )

    @staticmethod
    def build_request(
        machine_name: str | None,
        current_state: str | None,
        entity_type_name: str | None,
        entity_type_id: str | None,
        include_archived: bool,
        anchor_entity_id: str | None,
        fields: set[str] | None,
        thumbnail_field: str | None,
        limit: int,
        machine_names: set[str] | None = None,
        exclude_states: set[str] | None = None,
        assignee_ids: set[str] | None = None,
        search: str | None = None,
        field_filters: dict[str, str | list[str]] | None = None,
        identifier: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = EnrollmentSortDirection.ASC.value,
        offset: int | None = None,
        include_total_count: bool = False,
        include_identifier_options: bool = False,
    ) -> EnrollmentSummaryRequest:
        """Parse and check one board request, returning it as a single frozen value.

        Everything caller-supplied is settled here — the sort whitelists, the fields the
        response will need, the unassigned sentinel, the page-size clamp — so no part of the
        read downstream has to re-interpret a query parameter or disagree about what was asked.
        """
        EnrollmentSummaryService._validate_sort(sort_by, sort_dir)
        requested_fields = EnrollmentSummaryService._fields_to_project(fields, thumbnail_field)
        assignee_ids, include_unassigned = EnrollmentSummaryService._split_assignee_filter(
            assignee_ids
        )
        frozen_exclude_states = frozenset(exclude_states) if exclude_states else None
        return EnrollmentSummaryRequest(
            machine_name=machine_name,
            machine_names=machine_names,
            current_state=current_state,
            exclude_states=frozen_exclude_states,
            entity_type_name=entity_type_name,
            entity_type_id=entity_type_id,
            include_archived=include_archived,
            anchor_entity_id=anchor_entity_id,
            requested_fields=requested_fields,
            thumbnail_field=thumbnail_field,
            assignee_ids=assignee_ids,
            include_unassigned=include_unassigned,
            search=search,
            field_filters=dict(field_filters) if field_filters else None,
            identifier=identifier,
            sort_by=sort_by,
            sort_dir=sort_dir,
            offset=offset,
            include_total_count=include_total_count,
            include_identifier_options=include_identifier_options,
            page_size=max(1, min(limit, ENROLLMENT_PAGE_SIZE_CAP)),
        )

    @staticmethod
    def _validate_sort(sort_by: str | None, sort_dir: str) -> None:
        """Refuse a sort the board does not offer.

        Both values reach SQL, so they are checked against the whitelists rather than passed
        through. `sort_by=None` means unsorted and is allowed.
        """
        if sort_by is not None and sort_by not in EnrollmentSortField:
            raise ValidationError(f"unsupported sort_by '{sort_by}'")
        if sort_dir not in EnrollmentSortDirection:
            raise ValidationError(f"unsupported sort_dir '{sort_dir}'")

    @staticmethod
    def _fields_to_project(fields: set[str] | None, thumbnail_field: str | None) -> set[str]:
        """The fields to read, widened past what the caller asked for.

        The display name and the thumbnail are resolved from entity data, so their source fields
        have to be projected even when unrequested, or every row comes back unnamed. The read
        policy still filters the result, so widening cannot expose a field the actor may not see.
        """
        requested = set(fields or ()) | {IDENTIFIER_FIELD_KEY, *DISPLAY_NAME_FIELD_KEYS}
        if thumbnail_field:
            requested.add(thumbnail_field.split(".", 1)[0])
        return requested

    @staticmethod
    def _split_assignee_filter(
        assignee_ids: set[str] | None,
    ) -> tuple[frozenset[str] | None, bool]:
        """Separate "assigned to nobody" from the real assignee ids.

        The sentinel arrives mixed in with user ids because it is one query parameter, but it
        means the opposite of a match on an id, so SQL needs the two apart.
        """
        if not assignee_ids:
            return None, False
        include_unassigned = UNASSIGNED_FILTER_SENTINEL in assignee_ids
        real_ids = frozenset(a for a in assignee_ids if a != UNASSIGNED_FILTER_SENTINEL) or None
        return real_ids, include_unassigned

    @staticmethod
    def entity_records_for_rows(
        rows: list[WorkflowEnrollmentSummaryRow],
    ) -> list[EntityRecord]:
        """Re-shape enrollment rows as entity records.

        The read-policy and relation-walk helpers on the entities manager take records, so the
        board's joined rows are adapted to that shape rather than duplicating those helpers here.
        """
        return [
            EntityRecord(
                entity_id=row.entity_id,
                organization_id=row.organization_id,
                entity_type_id=row.entity_type_id,
                data=row.entity_data,
                owner_id=row.owner_id,
                assignee_id=row.assignee_id,
                due_date=row.due_date,
                created_at=row.entity_created_at,
                updated_at=row.entity_updated_at,
                archived_at=row.archived_at,
            )
            for row in rows
        ]

    @staticmethod
    def searchable_fields_by_type(
        policies: dict[str, EntityReadPolicy],
    ) -> dict[str, set[str] | None]:
        """Per-type entity-data keys the `search` filter is allowed to match on.

        `search` is a SQL predicate, evaluated before `apply_read_policy_to_data`
        strips invisible fields and masks the rest — so matching the whole JSONB
        blob would let an actor confirm the contents of fields their role cannot
        view. `None` = no field restriction (system roles). The identifier is
        always included: the read policy exempts it from both rules.
        """
        return {
            type_id: (
                None
                if policy.visible_fields is None
                else (policy.visible_fields - policy.masked_fields) | {IDENTIFIER_FIELD_KEY}
            )
            for type_id, policy in policies.items()
        }

    @staticmethod
    def summable_fields_by_type(
        policies: dict[str, EntityReadPolicy], sum_fields: set[str]
    ) -> dict[str, set[str] | None]:
        """Per requested field, the entity type ids allowed to contribute to it.

        A field permission is per entity type, so the same column can be
        summable on one type's rows and hidden on another's. `None` means every
        type in the result set allows it; a field no type allows is dropped
        entirely rather than reported as a total of zero, since an actor who
        cannot read a column should not learn anything about its values.

        Masked fields are excluded alongside invisible ones: a masked value is
        deliberately unreadable, and an exact sum of masked numbers would hand
        back precisely what the mask withholds.
        """
        summable: dict[str, set[str] | None] = {}
        unrestricted = all(policy.visible_fields is None for policy in policies.values())
        for field in sum_fields:
            if unrestricted:
                summable[field] = None
                continue
            allowed = {
                type_id
                for type_id, policy in policies.items()
                if policy.visible_fields is None
                or (field in policy.visible_fields and field not in policy.masked_fields)
            }
            if allowed:
                summable[field] = allowed
        return summable

    @staticmethod
    def accumulate_field_totals(
        into: dict[str, FieldTotalAccumulator],
        row: WorkflowEnrollmentSummaryRow,
        visible: dict[str, object],
        summable_fields: dict[str, set[str] | None],
    ) -> None:
        """Add one already-masked row's numeric values to the running totals.

        Reads only from `visible` — the policy-projected, policy-masked copy —
        never `row.entity_data`, so a value this actor may not see can never
        reach a total.
        """
        for field, allowed_type_ids in summable_fields.items():
            # Seeded even when this row's type can't contribute, so a column
            # visible on no matching row still totals 0 rather than vanishing.
            accumulator = into.setdefault(field, FieldTotalAccumulator(field=field))
            if allowed_type_ids is not None and row.entity_type_id not in allowed_type_ids:
                continue
            accumulator.add(visible.get(field), entity_id=row.entity_id)

    @staticmethod
    def field_totals_response(
        totals: dict[str, FieldNumericAggregate],
    ) -> dict[str, FieldTotalValue | FieldTotalError]:
        """Render each field's aggregate as a number, or say why it isn't one.

        A field whose rows carry more than one currency code returns a message
        naming them instead: adding amounts in different currencies produces a
        figure that means nothing, and no conversion infrastructure exists to
        make one. Re-derived per request, so normalizing the records to a
        single currency shows a real total on the very next call.
        """
        response: dict[str, FieldTotalValue | FieldTotalError] = {}
        for field, aggregate in totals.items():
            codes = sorted(aggregate.currency_codes)
            if len(codes) > 1:
                response[field] = FieldTotalError(
                    error=FieldTotalErrorCode.MIXED_CURRENCY,
                    currency_codes=codes,
                    message=(
                        f"This column has {', '.join(codes)} currency codes. "
                        "Update these records to a single currency to see a total."
                    ),
                )
            else:
                response[field] = FieldTotalValue(
                    total=float(aggregate.total),
                    currency_code=codes[0] if codes else None,
                )
        return response

    def readable_entity_policies(
        self,
        actor: dict[str, object],
        organization_id: str,
        services: EntitiesServiceManager,
    ) -> EntityReadAccess:
        """Resolve this actor's read access, and decide how much of it is SQL.

        Resolved from the org's entity-type registry — a small table — rather
        than from the rows being read, so an aggregate never has to materialise
        the rows it is aggregating.

        A row-level read condition is evaluated against a record's own JSONB
        *merged with* fields inherited through entity relations, and the
        inherited half wins. A condition on an inherited key therefore cannot
        be a predicate on `runtime_entities` — those actors still pay the row
        walk. Every other condition can, which is the common case and skips
        the walk entirely.
        """
        type_names_by_id = {
            record.entity_type_id: record.name
            for record in services.list_entity_type_records(organization_id=organization_id)
        }
        policies = services.resolve_read_policies(actor, organization_id, type_names_by_id)
        conditioned = {
            type_id: policy.conditions
            for type_id, policy in policies.items()
            if policy.conditions
        }
        if not conditioned:
            return EntityReadAccess(
                policies=policies,
                sql_conditions={},
                scan_type_ids=frozenset(),
                needs_row_scan=False,
            )
        sql_conditions, scan_type_ids = self._split_conditions_by_enforceability(
            organization_id, conditioned, services
        )
        return EntityReadAccess(
            policies=policies,
            # Pushed even on the scan path: there the predicate only narrows
            # what gets loaded — `apply_read_policy_to_data` still decides.
            sql_conditions=sql_conditions,
            scan_type_ids=frozenset(scan_type_ids),
            needs_row_scan=bool(scan_type_ids),
        )

    def _split_conditions_by_enforceability(
        self,
        organization_id: str,
        conditioned: dict[str, list[EntityConditionSpec]],
        services: EntitiesServiceManager,
    ) -> tuple[dict[str, list[EntityConditionSpec]], set[str]]:
        """Split conditioned entity types into the SQL-enforceable and the scan-only.

        A type is SQL-enforceable only if *every* one of its conditions is: one condition that
        needs a loaded row puts the whole type on the scan path, because a partial predicate
        would filter on some conditions and silently ignore the rest.
        """
        inheritable = services.db_model_service.inheritable_field_names_by_type(
            organization_id=organization_id, entity_type_ids=set(conditioned)
        )
        sql_conditions: dict[str, list[EntityConditionSpec]] = {}
        scan_type_ids: set[str] = set()
        for type_id, conditions in conditioned.items():
            inherited_keys = inheritable.get(type_id, frozenset())
            if all(
                condition.field_names.isdisjoint(inherited_keys)
                and self.workflow_db.read_condition_expression(condition) is not None
                for condition in conditions
            ):
                sql_conditions[type_id] = conditions
            else:
                scan_type_ids.add(type_id)
        return sql_conditions, scan_type_ids

    def global_filter_entity_ids(
        self,
        *,
        actor: dict[str, object],
        organization_id: str,
        anchor_entity_id: str | None,
        include_archived: bool = False,
    ) -> set[str] | None:
        """Return the anchor entity plus directly related runtime entities.

        The UI decides whether the org-level filter is enabled and passes an
        anchor id only when active. The server owns relation expansion so the
        client never fetches all workflow rows just to filter locally.
        """
        if not anchor_entity_id:
            return None

        return self.entities_service_manager.global_filter_entity_ids(
            actor=actor,
            organization_id=organization_id,
            anchor_entity_id=anchor_entity_id,
            include_archived=include_archived,
        )

    @staticmethod
    def _report_scan_capped(
        scan_limit: ScanLimit, organization_id: str, machine_name: str | None, scanned: int
    ) -> None:
        """Record that a bounded scan stopped on its cap rather than on the data.

        Both scans need this and neither can return it: they are generators, and a caller that
        stops early never resumes them. An aggregate built from a capped scan understates its
        counts, so the response says so rather than leaving the caller to infer it.
        """
        scan_limit.exhausted = True
        logger.warning(
            "workflow enrollment scan hit its row cap",
            extra={
                "organization_id": organization_id,
                "machine_name": machine_name,
                "scanned": scanned,
            },
        )

    def _shared_row_filters(
        self,
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
    ) -> dict[str, Any]:
        """The filters every read of this row set applies identically.

        Four reads narrow the same rows — the page, the reachability probe, the facet scan and
        the identifier options. What differs between them is deliberate: which entity types are
        in scope, and what each one leaves out so its answer can span more than the page does.
        Those stay spelled out at each call site. Everything returned here is the same in all
        four, so a filter added to the board cannot reach three of them and miss the fourth.
        """
        return {
            "organization_id": organization_id,
            "machine_name": request.machine_name,
            "machine_names": request.machine_names,
            "exclude_states": request.exclude_states,
            "entity_type_name": request.entity_type_name,
            "entity_type_id": request.entity_type_id,
            "include_archived": request.include_archived,
            "entity_ids": allowed_ids,
            "assignee_ids": request.assignee_ids,
            "include_unassigned": request.include_unassigned,
            "search": request.search,
            "field_filters": request.field_filters,
            "searchable_fields_by_type": self.searchable_fields_by_type(access.policies),
        }

    def _query_enrollment_rows(
        self,
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
        *,
        current_state: str | None,
        identifier: str | None,
        sort_by: str | None,
        offset: int | None,
        limit: int,
    ) -> list[WorkflowEnrollmentSummaryRow]:
        """Read one batch of raw rows for any read of the board.

        The last three are passed rather than taken off `request`, because the facet scans
        deliberately differ: they drop the narrowing that would stop their answer spanning the
        whole board, and they pass `sort_by=None` to keep the default total ordering, which is
        what makes their chunked paging sound. Requiring them keyword-only means a new caller
        has to state its choice rather than inherit the page's by accident.
        """
        return self.workflow_db.list_enrollment_summary_rows(
            **self._shared_row_filters(organization_id, request, allowed_ids, access),
            entity_type_ids=access.type_ids,
            read_conditions_by_type=access.sql_conditions,
            current_state=current_state,
            identifier=identifier,
            sort_by=sort_by,
            sort_dir=request.sort_dir,
            offset=offset,
            limit=limit,
        )

    def narrow_row_scan_to_reachable_types(
        self,
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
    ) -> EntityReadAccess:
        """Drop the row scan when no reachable row belongs to a scan-only type.

        `scan_type_ids` is a property of the actor's roles across the whole org,
        so without this one entity type carrying an inherited-field condition
        would put *every* query in that org on the scan path — including a board
        that cannot return a single row of that type.

        The probe runs the same filter chain as the real query, minus
        `current_state` and `identifier`: the state counts drop the first and
        the identifier options drop the second, so this is the union of what
        all three surfaces can reach. Empty there means empty for each of them.
        """
        if not access.needs_row_scan:
            return access
        reachable = self.workflow_db.enrollment_rows_exist(
            **self._shared_row_filters(organization_id, request, allowed_ids, access),
            # Only the scan-only types: this asks whether the scan could return anything,
            # not whether the board has rows.
            entity_type_ids=set(access.scan_type_ids),
        )
        return access if reachable else replace(access, needs_row_scan=False)

    def _sql_enrollment_aggregates(
        self,
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
        summable: dict[str, set[str] | None],
    ) -> EnrollmentAggregates:
        """Counts and totals as SQL aggregates, for actors needing no row scan."""
        filters = EnrollmentAggregateFilters(
            organization_id=organization_id,
            machine_name=request.machine_name,
            machine_names=request.machine_names,
            exclude_states=request.exclude_states,
            entity_type_name=request.entity_type_name,
            entity_type_id=request.entity_type_id,
            entity_type_ids=access.type_ids,
            include_archived=request.include_archived,
            entity_ids=allowed_ids,
            assignee_ids=request.assignee_ids,
            include_unassigned=request.include_unassigned,
            search=request.search,
            field_filters=request.field_filters,
            searchable_fields_by_type=self.searchable_fields_by_type(access.policies),
            read_conditions_by_type=access.sql_conditions,
            identifier=request.identifier,
        )
        return EnrollmentAggregates(
            state_counts=self.workflow_db.count_enrollment_rows_by_state(filters),
            field_totals=(
                self.workflow_db.sum_enrollment_fields(
                    filters, sum_fields=summable, current_state=request.current_state
                )
                if summable
                else {}
            ),
        )

    def _resolve_summary_policies_and_inherited(
        self,
        actor: dict[str, object],
        organization_id: str,
        rows: list[WorkflowEnrollmentSummaryRow],
        requested_fields: set[str],
        services: EntitiesServiceManager,
        *,
        include_transition_fields: bool,
    ) -> tuple[dict[str, EntityReadPolicy], dict[str, dict[str, object]]]:
        """The read policies for a page's entity types, and the fields inherited by its rows.

        Resolved together because the inherited fields that must be fetched depend on what the
        policies condition on: a condition on an inherited key can only be evaluated once that
        key has been walked. `include_transition_fields` widens the walk for the page, which
        also has to offer transition options, but not for the facets, which do not.
        """
        type_names = {row.entity_type_id: row.entity_type for row in rows}
        policies = services.resolve_read_policies(actor, organization_id, type_names)
        condition_fields = {
            name
            for policy in policies.values()
            for condition in policy.conditions
            for name in condition.field_names
        }
        transition_fields = (
            {
                field_name
                for row in rows
                for transition in self.transition_evaluation.transitions_from(
                    row.machine_definition, row.current_state
                )
                for field_name in self.transition_evaluation.transition_field_names(transition)
            }
            if include_transition_fields
            else set()
        )
        inherited = services.db_model_service.resolve_inherited_fields_for_records(
            organization_id=organization_id,
            records=self.entity_records_for_rows(rows),
            field_names=requested_fields | condition_fields | transition_fields,
        )
        return policies, inherited

    def _visible_facet_rows(
        self,
        actor: dict[str, object],
        organization_id: str,
        rows: list[WorkflowEnrollmentSummaryRow],
        services: EntitiesServiceManager,
        projected_fields: set[str] | None = None,
    ) -> Iterator[tuple[WorkflowEnrollmentSummaryRow, dict[str, object]]]:
        """Yield (row, projected data) for the rows this actor may actually read.

        The facets can't take a shortcut the page doesn't: any aggregate built
        over raw rows reports — or, for identifier options, hands back — values
        from records the read policy hides.

        `projected_fields` widens the projection beyond the identifier for a
        caller that has to read real values (the field totals); the read policy
        still decides what survives, so widening it cannot expose a field the
        actor's role hides or unmask one it masks.
        """
        requested = {IDENTIFIER_FIELD_KEY} | (projected_fields or set())
        policies, inherited = self._resolve_summary_policies_and_inherited(
            actor,
            organization_id,
            rows,
            requested,
            services,
            include_transition_fields=False,
        )
        for row in rows:
            policy = policies.get(row.entity_type_id)
            if policy is None:
                continue
            visible = services.apply_read_policy_to_data(
                policy,
                entity_id=row.entity_id,
                data={**row.entity_data, **inherited.get(row.entity_id, {})},
                projected_fields=requested,
            )
            if visible is not None:
                yield row, visible

    def _resolve_enrollment_summary_context(
        self,
        actor: dict[str, object],
        organization_id: str,
        rows: list[WorkflowEnrollmentSummaryRow],
        request: EnrollmentSummaryRequest,
        services: EntitiesServiceManager,
    ) -> EnrollmentSummaryContext:
        """Everything a page of rows needs resolved once: policies, inherited fields, thumbnails."""
        policies, inherited = self._resolve_summary_policies_and_inherited(
            actor,
            organization_id,
            rows,
            request.requested_fields,
            services,
            include_transition_fields=True,
        )
        preview_urls: dict[str, str] = {}
        if self.filehandler_service_manager is not None:
            # Same degradation contract as `_with_refreshed_thumbnail`: broad on purpose, so a
            # thumbnail lookup failing costs the page its images and not its rows. Logged with
            # the exception and the row count, so a systematic failure shows up.
            try:
                preview_urls = (
                    self.filehandler_service_manager.get_entity_preview_thumbnail_urls(
                        organization_id, {row.entity_id for row in rows}
                    )
                )
            except Exception as exc:
                logger.warning(
                    "could not resolve summary thumbnails; the page is served without them: %s",
                    exc,
                    extra={"organization_id": organization_id, "rows": len(rows)},
                    exc_info=True,
                )
        return EnrollmentSummaryContext(
            policies=policies,
            inherited=inherited,
            preview_urls=preview_urls,
        )

    def load_page(
        self,
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
    ) -> EnrollmentSummaryPageData:
        """One page of rows, and whether anything follows it.

        Reads one row more than the page holds and reports the surplus as `has_more`, so the
        caller learns there is a next page without paying for a second count query.
        """
        rows = self._query_enrollment_rows(
            organization_id,
            request,
            allowed_ids,
            access,
            current_state=request.current_state,
            identifier=request.identifier,
            sort_by=request.sort_by,
            offset=request.offset,
            limit=request.page_size + 1,
        )
        return EnrollmentSummaryPageData(
            rows=rows[:request.page_size],
            has_more=len(rows) > request.page_size,
        )

    def _scan_visible_facet_rows(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
        services: EntitiesServiceManager,
        scan_limit: ScanLimit,
        *,
        current_state: str | None,
        identifier: str | None,
        projected_fields: set[str] | None = None,
    ) -> Iterator[tuple[WorkflowEnrollmentSummaryRow, dict[str, object]]]:
        """Chunked walk over the policy-visible rows an aggregate must cover.

        Yields lazily, a chunk at a time: peak memory is one chunk rather than the whole matched
        set, and a consumer that stops early (the identifier cap) stops the reads too. See
        `_query_enrollment_rows` for why the narrowing and ordering are passed in.
        """
        scanned = 0
        scan_chunk, scan_cap = self.scan_bounds()
        while scanned < scan_cap:
            chunk = min(scan_chunk, scan_cap - scanned)
            rows = self._query_enrollment_rows(
                organization_id,
                request,
                allowed_ids,
                access,
                current_state=current_state,
                identifier=identifier,
                sort_by=None,
                offset=scanned,
                limit=chunk,
            )
            if not rows:
                return
            scanned += len(rows)
            yield from self._visible_facet_rows(
                actor, organization_id, rows, services, projected_fields
            )
            if len(rows) < chunk:
                return
        # Fell out of the loop rather than returning from inside it: the cap
        # stopped the walk, so whatever aggregate the caller built is low.
        self._report_scan_capped(scan_limit, organization_id, request.machine_name, scanned)

    def _with_refreshed_thumbnail(
        self, projected: dict[str, object], thumbnail_field: str | None
    ) -> dict[str, object]:
        """Re-sign the thumbnail's URL, keeping the stored value if that fails.

        The catch is broad deliberately, and this is the degradation contract: a thumbnail is
        decoration served from a network dependency, so a signing failure costs the caller one
        missing image rather than the whole board. It is not silent — the exception and the
        field are logged, so a systematic failure is visible rather than merely invisible.
        """
        if not thumbnail_field or self.blob_storage_service is None:
            return projected
        try:
            refreshed = self.blob_storage_service.refresh_field(projected, thumbnail_field)
        except Exception as exc:
            logger.warning(
                "could not refresh a summary thumbnail; keeping the stored value: %s",
                exc,
                extra={"thumbnail_field": thumbnail_field},
                exc_info=True,
            )
            return projected
        return refreshed if refreshed is not None else projected

    def _build_enrollment_summary_item(
        self,
        row: WorkflowEnrollmentSummaryRow,
        policy: EntityReadPolicy,
        context: EnrollmentSummaryContext,
        request: EnrollmentSummaryRequest,
        services: EntitiesServiceManager,
    ) -> WorkflowEnrollmentSummary | None:
        """One board row as a response item, or None when the policy hides the record."""
        combined = {**row.entity_data, **context.inherited.get(row.entity_id, {})}
        projected = services.apply_read_policy_to_data(
            policy,
            entity_id=row.entity_id,
            data=combined,
            projected_fields=request.requested_fields,
        )
        if projected is None:
            return None
        projected = self._with_refreshed_thumbnail(projected, request.thumbnail_field)
        return WorkflowEnrollmentSummary(
            state_id=row.state_id,
            entity_id=row.entity_id,
            entity_type_id=row.entity_type_id,
            entity_type=row.entity_type,
            organization_id=row.organization_id,
            workflow_id=row.workflow_id,
            machine_name=row.machine_name,
            machine_display_name=row.machine_display_name,
            machine_version=row.machine_version,
            current_state=row.current_state,
            state_version=row.state_version,
            display_name=services.summary_display_name(projected, row.entity_id),
            summary_fields=projected,
            transition_options=self.transition_evaluation.summary_options(
                row.machine_definition, row.current_state, combined, policy
            ),
            owner_id=row.owner_id,
            assignee_id=row.assignee_id,
            due_date=row.due_date,
            state_entered_at=row.state_entered_at,
            last_transition_at=row.last_transition_at,
            sla_due_at=row.sla_due_at,
            entity_created_at=row.entity_created_at,
            entity_updated_at=row.entity_updated_at,
            archived_at=row.archived_at,
            preview_thumbnail_url=context.preview_urls.get(row.entity_id),
        )

    def build_items(
        self,
        actor: dict[str, object],
        organization_id: str,
        rows: list[WorkflowEnrollmentSummaryRow],
        request: EnrollmentSummaryRequest,
        services: EntitiesServiceManager,
    ) -> list[WorkflowEnrollmentSummary]:
        """Turn a page of rows into response items, dropping those the policy hides.

        The per-page context is resolved once for the whole page rather than per row, so the
        relation walk and the thumbnail lookup each cost one call instead of one per record.
        """
        context = self._resolve_enrollment_summary_context(
            actor, organization_id, rows, request, services
        )
        items: list[WorkflowEnrollmentSummary] = []
        for row in rows:
            policy = context.policies.get(row.entity_type_id)
            if policy is None:
                continue
            item = self._build_enrollment_summary_item(
                row, policy, context, request, services
            )
            if item is not None:
                items.append(item)
        return items

    def visible_identifier_options(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        services: EntitiesServiceManager,
        access: EntityReadAccess,
        scan_limit: ScanLimit,
    ) -> list[str]:
        """Distinct identifiers for the table's filter, policy-visible ones only.

        No `identifier` filter: the dropdown must keep offering the values you
        did not pick. Type-level access is an `IN (...)` predicate the DISTINCT
        query already carries, but a row-level condition can only be evaluated
        on a loaded row — so those actors get the same scan the state counts
        use, or the dropdown would list identifiers of records they cannot open.
        """
        if not access.needs_row_scan:
            return self.workflow_db.list_enrollment_summary_identifier_options(
                **self._shared_row_filters(organization_id, request, allowed_ids, access),
                entity_type_ids=access.type_ids,
                read_conditions_by_type=access.sql_conditions,
                current_state=request.current_state,
                # No `identifier`: the dropdown must keep offering what you did not pick.
                limit=IDENTIFIER_OPTION_CAP,
            )
        options: set[str] = set()
        for _, visible in self._scan_visible_facet_rows(
            actor,
            organization_id,
            request,
            allowed_ids,
            access,
            services,
            scan_limit,
            current_state=request.current_state,
            identifier=None,
        ):
            value = visible.get(IDENTIFIER_FIELD_KEY)
            if value:
                options.add(str(value))
            if len(options) >= IDENTIFIER_OPTION_CAP:
                break
        return sorted(options)

    def _compute_enrollment_aggregates(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
        services: EntitiesServiceManager,
        scan_limit: ScanLimit,
        summable_fields: dict[str, set[str] | None],
    ) -> EnrollmentAggregates:
        """Counts and field totals from a single chunked walk of visible rows."""
        state_counts: dict[str, int] = {}
        totals: dict[str, FieldTotalAccumulator] = {}
        # Every active filter EXCEPT `current_state` — the counts must span all
        # states (that's the point), but they have to agree with the filtered
        # rows the caller is actually showing, or a board's column badges tally
        # records its own columns deliberately hide.
        for row, visible in self._scan_visible_facet_rows(
            actor,
            organization_id,
            request,
            allowed_ids,
            access,
            services,
            scan_limit,
            current_state=None,
            identifier=request.identifier,
            projected_fields=set(summable_fields),
        ):
            state_counts[row.current_state] = state_counts.get(row.current_state, 0) + 1
            # The counts span every state; a total describes only the rows on
            # screen, so a pinned state filters here rather than in the scan.
            if summable_fields and request.current_state in (None, row.current_state):
                self.accumulate_field_totals(totals, row, visible, summable_fields)
        return EnrollmentAggregates(
            state_counts=state_counts,
            field_totals={field: acc.to_aggregate() for field, acc in totals.items()},
        )

    def _collect_visible_rows(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
        services: EntitiesServiceManager,
        wanted: int,
    ) -> tuple[list[WorkflowEnrollmentSummaryRow], int, bool]:
        """Scan from the top until `wanted` visible rows are found or the cap stops it.

        Returns the visible rows, how many raw rows were read, and whether the data ran out —
        as opposed to the cap cutting the scan short, which the caller has to report.
        """
        visible: list[WorkflowEnrollmentSummaryRow] = []
        scanned = 0
        scan_chunk, scan_cap = self.scan_bounds()
        while len(visible) < wanted and scanned < scan_cap:
            chunk = min(scan_chunk, scan_cap - scanned)
            rows = self._query_enrollment_rows(
                organization_id,
                request,
                allowed_ids,
                access,
                current_state=request.current_state,
                identifier=request.identifier,
                sort_by=request.sort_by,
                offset=scanned,
                limit=chunk,
            )
            if not rows:
                return visible, scanned, True
            scanned += len(rows)
            # Visibility only — the scan decides *which* rows the page holds, so
            # it must not pay for hydration (inherited projection fields,
            # transition options, signed thumbnail URLs) on rows it discards.
            # Minting preview URLs for records that never reach the response
            # would be wrong as well as wasteful.
            visible.extend(
                row for row, _ in self._visible_facet_rows(actor, organization_id, rows, services)
            )
            if len(rows) < chunk:
                return visible, scanned, True
        return visible, scanned, False

    def scan_visible_enrollment_page(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        access: EntityReadAccess,
        services: EntitiesServiceManager,
        scan_limit: ScanLimit,
    ) -> tuple[list[WorkflowEnrollmentSummary], bool]:
        """Page over policy-visible rows when row-level read conditions apply.

        A read condition can match an inherited (relation-walked) field that
        isn't in the row's own JSONB, so it can't be pushed into SQL — the row
        is only droppable once loaded. Paging with a SQL OFFSET therefore skips
        over rows the actor never sees, and since `total_count` counts only
        visible rows the trailing visible records sit past the last reachable
        offset. So scan raw rows from the top in chunks, apply the policy, and
        slice the *filtered* list — offsets then mean the same thing on both
        sides.

        ponytail: bounded by `workflow_configuration.row_condition_scan_cap`
        raw rows; push the conditions into SQL if a tenant outgrows that.
        """
        start = request.offset or 0
        wanted = start + request.page_size + 1
        visible, scanned, drained = self._collect_visible_rows(
            actor, organization_id, request, allowed_ids, access, services, wanted
        )
        if not drained and len(visible) < wanted:
            # Stopped on the cap while still short of a full page: `has_more`
            # below is a false negative, so say so rather than let the caller
            # read it as the end of the list.
            self._report_scan_capped(scan_limit, organization_id, request.machine_name, scanned)
        page_rows = visible[start:start + request.page_size]
        items = self.build_items(
            actor, organization_id, page_rows, request, services
        )
        return items, len(visible) > start + request.page_size

    def visible_enrollment_aggregates(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: EnrollmentSummaryRequest,
        allowed_ids: set[str] | None,
        services: EntitiesServiceManager,
        access: EntityReadAccess,
        scan_limit: ScanLimit,
        sum_fields: set[str] | None = None,
    ) -> EnrollmentAggregates:
        """Per-state row counts, and field totals, over the rows this actor sees.

        Type-level read access is an `entity_type_id IN (...)` filter, so the
        common case is one GROUP BY that never loads a row. Row-level read
        conditions can match on inherited (relation-walked) fields that aren't
        in the row's own JSONB, so those can't be pushed into SQL — only actors
        who hold such a condition pay for the row walk.

        Counts and totals resolve together rather than through two entry
        points: on the scan path a second pass would mean walking every
        matching row twice to fill one response.
        """
        summable = self.summable_fields_by_type(access.policies, sum_fields or set())
        if access.needs_row_scan:
            return self._compute_enrollment_aggregates(
                actor, organization_id, request, allowed_ids, access, services,
                scan_limit, summable,
            )
        return self._sql_enrollment_aggregates(
            organization_id, request, allowed_ids, access, summable
        )
