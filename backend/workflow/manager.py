"""Compact workflow manager.

This module implements the same generic state machine behavior as `workflow`,
but with a denser design:

- one local `models.py` instead of a models package
- one unified definition-report store
- one unified activity log
- one candidate-finalization flow for all workflow modifications

A state machine is a versioned workflow definition for one primary entity. The
entity carries mutable runtime state, while the workflow version carries the
allowed states, transitions, schema, guards, tasks, and timing rules.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from background_jobs.models.interface import ActionRunStatus
from common.auth import actor_str, build_system_actor
from common.enums import AuditMetadataType, ModuleStatus, WorkflowPermissionKey
from common.logger import logger
from entities.models.request import (
    EntityRecordUpdateRequest,
    EntityRelationDeclarationUpdateRequest,
)
from exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from field_library.models.interface import FieldTypeConfigKind
from workflow.models import (
    ActivityRecord,
    ActivityType,
    AvailableTransitionsResponse,
    DefinitionReport,
    EntityDryRunRequest,
    EntityDryRunResponse,
    PICKLIST_MULTI_COPY_FIELDS,
    EntityField,
    EntityFieldType,
    EntitySchema,
    EntityState,
    EventHistoryResponse,
    MethodRef,
    ReportType,
    ResolvedMethodSchema,
    RunFactsItem,
    RunFactsRequest,
    RunFactsResponse,
    State,
    StateActionRerunResponse,
    StateMachineCreateRequest,
    StateMachineDefinition,
    StateMachineListResponse,
    StateMachinePublishResponse,
    StateMachineRecord,
    StateMachineValidateRequest,
    StateMachineValidationResponse,
    StateMachineVersionCompareResponse,
    StateTag,
    Transition,
    TransitionExecutionResponse,
    TransitionHistoryResponse,
    TransitionPreflightResponse,
    TransitionStatus,
    ValidationIssue,
    ValidationIssueCode,
    WorkflowBoardDisplayFieldsRecord,
    WorkflowBoardDisplayFieldsUpdateRequest,
    WorkflowDraftCreateRequest,
    WorkflowDraftRecord,
    WorkflowDraftSaveResponse,
    WorkflowDraftUpdateRequest,
    WorkflowDraftSeedRequest,
    WorkflowDryRunSummary,
    WorkflowListResponse,
    WorkflowEnrollmentSummaryPage,
    WorkflowListScopeRequest,
    WorkflowPathsResponse,
    WorkflowPublishRequest,
    WorkflowRowLookupRequest,
    WorkflowScope,
    WorkflowService,
    WorkflowServiceWithWorkflows,
    WorkflowServiceCreateRequest,
    WorkflowServiceRenameRequest,
    WorkflowStatusResponse,
)
from workflow.models.interface import (
    FIELD_FILTERS_MAX_KEY_LENGTH,
    FIELD_FILTERS_MAX_KEYS,
    FIELD_FILTERS_MAX_VALUE_LENGTH,
    FIELD_FILTERS_MAX_VALUES,
    RUN_FACTS_DEVIATION_HISTORY_PAGE_SIZE,
    EnrollmentInclude,
    ENROLLMENT_TRANSITION_KEY,
    STATE_VERSION_CONFLICT_REASON,
    EntityTypeSentinel,
    FieldOwnership,
    ScanLimit,
    StateAction,
    TransitionAuditEventType,
    TransitionAuditMetadataKey,
    WorkflowEventType,
    not_enrolled_message,
)
from workflow.models.request import TransitionExecuteRequest
from workflow.models.response import EventRecord
from workflow.db_models import (
    SERVICE_PAGE_LIMIT,
    DuplicateWorkflowServiceNameError,
    UnknownWorkflowServiceError,
    WorkflowEnrollmentSummaryRow,
    WorkflowModelService,
    WorkflowServiceInUseError,
)
from workflow.services import (
    DefinitionAnalysisService,
    EnrollmentSummaryService,
    EntitySchemaService,
    RuntimeResolutionService,
    SimulationService,
    StateActionSchedulingService,
    TransitionAuditService,
    TransitionEvaluationService,
)

if TYPE_CHECKING:
    from audit.db_models import AuditEventsModelService
    from blob_storage.service import BlobStorageService
    from common.configuration import Configuration
    from database.manager import DatabaseServiceManager
    from entities.manager import EntitiesServiceManager
    from executor.manager import ExecutorServiceManager
    from filehandler.manager import FilehandlerServiceManager
    from forms.manager import FormsServiceManager
    from forms.models.interface import EntityTypeSchemaContract
    from method_library.db_models import MethodLibraryModelService
    from method_library.models.interface import (
        MethodIdentity,
        MethodVersion,
        MethodVersionField,
    )
    from roles.manager import RolesServiceManager
    from user.manager import UserServiceManager


# Page size when walking a method's version history to confirm a pinned version
# belongs to it. Methods carry few versions; this only bounds the walk.
_METHOD_VERSION_PAGE = 100
# Raw rows read per round, and in total, when an actor's read policy carries
# row-level conditions and enrollment pages must be sliced after filtering
# (`_scan_visible_enrollment_page`). The cap is the same order as the existing
# state-count scan, so it adds no new worst case.
# Distinct values offered by the table's identifier filter dropdown.
_METHOD_ATTRIBUTION_KEY = "_method_attribution"

# One state's pin on one method version, as `(method_id, version_id)`. Diffing
# method_refs on this rather than on method_id alone is what makes a repin to
# another version count as a change.
_MethodPin = tuple[str, str | None]


@dataclass(frozen=True)
class _PendingMethodRelationWrite:
    """One method field's source-intent mapping, validated and ready to merge
    into its relation's `relation_metadata`."""

    from_entity_type_id: str
    to_entity_type_id: str
    source_key: str
    target_key: str
    method_id: str
    field_key: str


@dataclass(frozen=True)
class _PendingMethodRelationRemoval:
    """One method field's attributed entry to remove from a relation's
    `relation_metadata`, because the method was detached from a state."""

    from_entity_type_id: str
    to_entity_type_id: str
    method_id: str
    field_key: str


class WorkflowServiceManager:
    """Compact orchestration manager for workflow."""

    _MODULE_NAME = "workflow"
    _READ_ACTION = "read"
    _WRITE_ACTION = "write"

    def __init__(
        self,
        *,
        workflow_db_model_service: WorkflowModelService,
        database_service_manager: DatabaseServiceManager,
        config: Configuration,
        entities_service_manager: EntitiesServiceManager,
        roles_manager: RolesServiceManager,
        audit_events_service: AuditEventsModelService,
        forms_service_manager: FormsServiceManager,
        method_library_db_model_service: MethodLibraryModelService | None = None,
        filehandler_service_manager: FilehandlerServiceManager,
        user_service_manager: UserServiceManager,
        blob_storage_service: BlobStorageService,
        executor_service_manager: ExecutorServiceManager | None = None,
    ) -> None:
        """Initialize the manager.

        `entities_service_manager` carries the new state-machine model
        (runtime.entities, runtime.entity_state, audit.entity_events,
        audit.transition_attempts). All entity create/transition flows now
        write through it; legacy `workflow_db.entity_state` writes are gone.

        `method_library_db_model_service` is read at publish time to resolve the
        methods a state pins.

        `audit_events_service` is the unified `audit_events` writer
        (`AuditEventsModelService`, owned by the audit module). Transition
        attempts (succeeded/blocked/conflict) are emitted through it instead
        of `workflow_db.record_transition_attempt`. It is handed to
        `TransitionAuditService` and not kept here, so there is one holder of
        the writer rather than two that can drift apart.
        """
        self.workflow_db = workflow_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.entities_service_manager = entities_service_manager
        self.method_library_db_model_service = method_library_db_model_service
        self.roles_manager = roles_manager
        self.filehandler_service_manager = filehandler_service_manager
        self.user_service_manager = user_service_manager
        self.blob_storage_service = blob_storage_service
        # Read only to validate that a configured action kind can actually run;
        # the workflow engine never executes actions itself, the worker does.
        self.executor_service_manager = executor_service_manager
        # The manager owns the wiring between capabilities: Stage 3.5 §9 forbids a workflow
        # service from holding or constructing another one, so simulation is handed the guard
        # evaluator rather than building its own.
        self.transition_evaluation = TransitionEvaluationService()
        self.definition_analysis = DefinitionAnalysisService()
        self.simulation = SimulationService(self.transition_evaluation, self.definition_analysis)
        self.entity_schema = EntitySchemaService(forms_service_manager)
        self.runtime_resolution = RuntimeResolutionService(
            workflow_db_model_service, entities_service_manager
        )
        self.transition_audit = TransitionAuditService(audit_events_service, user_service_manager)
        self.state_action_scheduling = StateActionSchedulingService(workflow_db_model_service)
        self.enrollment_summary = EnrollmentSummaryService(
            workflow_db_model_service,
            entities_service_manager,
            self.transition_evaluation,
            blob_storage_service,
            filehandler_service_manager,
        )
        self._started = False

    def start(self) -> None:
        """Mark the module as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the module as stopped."""
        self._started = False

    def get_status(self) -> WorkflowStatusResponse:
        """Return the module's lifecycle status (`started` flips on start/stop).

        Used by the platform's per-module health probe to verify the
        workflow runtime is wired up before traffic is routed to it."""
        return WorkflowStatusResponse(
            module=self._MODULE_NAME, status=ModuleStatus.READY.value, started=self._started
        )

    def _authorize_workflow_access(self, actor: dict[str, object], machine_name: str) -> None:
        self._deny_out_of_scope_workflow(
            actor, machine_name, self.roles_manager.get_workflow_access_scope(actor)
        )

    def _deny_out_of_scope_workflow(
        self, actor: dict[str, object], machine_name: str, scope: set[str] | None
    ) -> None:
        """Enforce an already-fetched workflow read scope against one machine name.

        Split out of `_authorize_workflow_access` so a caller that has already
        paid for `get_workflow_access_scope` can enforce it without a second
        round trip, while the rule itself stays defined in exactly one place.
        `scope is None` means unrestricted (system role, or no scoping rows).

        Raises `NotFoundError`, not an authorization error, deliberately: a 403
        would confirm the workflow exists to an actor who may not see it.
        """
        if scope is not None and machine_name not in scope:
            logger.warning(
                "workflow access denied: %s",
                machine_name,
                extra={"machine_name": machine_name, "user_id": actor_str(actor, "user_id")},
            )
            raise NotFoundError(f"workflow '{machine_name}' was not found")

    @classmethod
    def build_reference_definition(cls) -> StateMachineDefinition:
        """Build the Phase 1 starter workflow definition."""
        return StateMachineDefinition(
            machine_key="generic_workflow",
            name="Generic Workflow",
            description="Starter template for the workflow builder",
            entity_type="generic_entity",
            entity_schema=EntitySchema(
                entity_type="generic_entity",
                fields=[],
            ),
            states=[
                State(name="start", tags=["initial"], order=1),
                State(name="end", tags=["terminal"], order=2),
            ],
            initial_state="start",
            transitions=[
                Transition(
                    key="start_to_end",
                    trigger="complete",
                    label="Complete",
                    from_state="start",
                    to_state="end",
                    required_fields=[],
                    guards=[],
                    pre_transition_tasks=[],
                    post_transition_tasks=[],
                    auto_transition=None,
                    description="Minimal working transition from start to end",
                )
            ],
        )

    def get_default_template_for_actor(self, actor: dict[str, object]) -> StateMachineDefinition:
        """Return the canonical default state machine definition template."""
        return self.build_reference_definition()

    def validate_candidate_workflow_for_actor(
        self, actor: dict[str, object], payload: StateMachineValidateRequest
    ) -> StateMachineValidationResponse:
        """Validate one candidate definition and persist both reports."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, payload.machine_name)

        candidate_version = self.workflow_db.get_next_version(
            organization_id=organization_id, machine_name=payload.machine_name
        )
        base_version = (
            payload.base_version
            if payload.base_version is not None
            else self._current_base_version(organization_id, payload.machine_name)
        )
        # Evaluate what publishing would actually evaluate. Publish merges each
        # state's pinned method fields into the entity schema before validating
        # and dry-running (see `_prepare_publishable_definition`); without the
        # same merge here, Validate reports a guard on a method-contributed
        # field as unsatisfiable and refuses to publish a definition that
        # publishes cleanly.
        candidate_definition, pin_issues = self._definition_with_method_fields(
            organization_id, payload.definition
        )
        validation, dry_run_report, dry_run_summary, can_publish = (
            self._evaluate_candidate_definition(
                organization_id=organization_id,
                machine_name=payload.machine_name,
                definition=candidate_definition,
                candidate_version=candidate_version,
                persist_validation_report=True,
                extra_issues=pin_issues,
            )
        )
        if not validation.valid:
            return StateMachineValidationResponse(
                machine_name=payload.machine_name,
                base_version=base_version,
                candidate_version=candidate_version,
                can_dry_run=False,
                can_publish=False,
                validation_report_id=validation.report_id,
                validation_report=validation,
                dry_run_report=None,
                dry_run_summary=None,
            )
        return StateMachineValidationResponse(
            machine_name=payload.machine_name,
            base_version=base_version,
            candidate_version=candidate_version,
            can_dry_run=True,
            can_publish=can_publish,
            validation_report_id=validation.report_id,
            validation_report=validation,
            dry_run_report=dry_run_report,
            dry_run_summary=dry_run_summary,
        )

    def publish_workflow_for_actor(
        self,
        actor: dict[str, object],
        row_id: str,
        payload: WorkflowPublishRequest,
    ) -> StateMachinePublishResponse:
        """Validate and publish a workflow definition as a new persisted version row."""
        organization_id = self._organization_id(actor)
        draft = self.workflow_db.get_state_machine_by_row_id(
            organization_id=organization_id,
            row_id=row_id,
        )
        if draft is None or getattr(draft, "version", None) != 0:
            raise NotFoundError(f"workflow draft with row_id '{row_id}' was not found")
        machine_name = draft.machine_name
        self._authorize_workflow_access(actor, machine_name)
        candidate_version = self.workflow_db.get_next_version(
            organization_id=organization_id,
            machine_name=machine_name,
        )
        (
            definition,
            method_pins,
            relation_writes,
            validation_report,
            dry_run_report,
            dry_run_summary,
        ) = self._prepare_publishable_definition(
            organization_id=organization_id,
            machine_name=machine_name,
            definition=payload.definition,
            candidate_version=candidate_version,
        )

        previous_active = self.workflow_db.get_active_state_machine(
            organization_id=organization_id, machine_name=machine_name
        )

        # The pins go in with the row, in one transaction. Recording them after
        # the fact would let a concurrent method delete fail the pin insert while
        # the new version was already active, leaving method-derived fields with
        # nothing protecting their source method. They hang off the published row,
        # so each version keeps the pins it was built with and a republish never
        # rewrites the previous version's.
        try:
            created = self.workflow_db.create_state_machine_published(
                StateMachineCreateRequest(
                    machine_name=machine_name,
                    version=candidate_version,
                    is_active=True,
                    definition=definition,
                ),
                organization_id=organization_id,
                created_by=getattr(draft, "created_by", None)
                or getattr(previous_active, "created_by", None)
                or actor_str(actor, "user_id")
                or None,
                method_pins=method_pins,
            )
        except UnknownWorkflowServiceError as exc:
            raise ValidationError(str(exc)) from exc
        updated = self._machine(created)

        # Applied only now that the row and its pins are committed — everything
        # upstream (relation-exists, field-exists, remap-conflict) has already
        # passed, so this is recording the outcome of checks already made, not
        # making a new decision. The update replaces relation_metadata
        # wholesale, so each write merges into the declaration's CURRENT
        # metadata — a bare key/value payload would wipe every other mapping
        # (and the request model would silently drop the keys anyway).
        if relation_writes:
            entities_db = self.entities_service_manager.db_model_service
            declarations = {
                declaration.relation_def_id: declaration
                for declaration in entities_db.get_active_relation_declarations_by_to_type(
                    organization_id=organization_id,
                    to_entity_type_id=self.runtime_resolution.resolve_entity_type_id(
                        organization_id, definition.entity_type
                    ),
                )
            }
            merged_metadata: dict[str, dict[str, object]] = {}
            for relation_def_id, key, value in relation_writes:
                metadata = merged_metadata.get(relation_def_id)
                if metadata is None:
                    declaration = declarations.get(relation_def_id)
                    metadata = dict(declaration.relation_metadata or {}) if declaration else {}
                metadata[key] = value
                merged_metadata[relation_def_id] = metadata
            for relation_def_id, metadata in merged_metadata.items():
                entities_db.update_entity_relation_declaration_metadata(
                    organization_id=organization_id,
                    relation_def_id=relation_def_id,
                    request=EntityRelationDeclarationUpdateRequest(relation_metadata=metadata),
                )

        draft_update_kwargs: dict[str, object] = {
            "organization_id": organization_id,
            "row_id": row_id,
            "definition": definition.model_dump(mode="json"),
        }
        if "canvas_metadata" in payload.model_fields_set:
            draft_update_kwargs["canvas_metadata"] = payload.canvas_metadata
        self.workflow_db.update_state_machine_draft(**draft_update_kwargs)

        logger.info(
            f"workflow published row_id={row_id} machine={updated.machine_name} "
            f"version={updated.version} org={organization_id}"
        )
        # The version above is already committed. The cascade commits separately, so a failure
        # here leaves the new version live with permissions still on the old transition keys.
        # Reporting that as a 500 would tell the caller the publish failed when it did not, and
        # send them to republish - which cannot repair it, because there is no longer a key
        # change to detect. Log everything needed to replay it by hand and flag the response.
        permission_sync_failed = False
        if previous_active is not None:
            try:
                self.roles_manager.cascade_workflow_publish(
                    org_id=organization_id,
                    machine_name=machine_name,
                    old_definition=previous_active.definition,
                    new_definition=definition,
                )
            except Exception as exc:
                permission_sync_failed = True
                logger.error(
                    "workflow publish succeeded but the transition permission cascade failed: "
                    f"{exc}",
                    exc_info=True,
                    extra={
                        "organization_id": organization_id,
                        "machine_name": machine_name,
                        "published_version": updated.version,
                        "previous_transition_keys": sorted(
                            t.key for t in previous_active.definition.transitions
                        ),
                        "new_transition_keys": sorted(t.key for t in definition.transitions),
                    },
                )
        return StateMachinePublishResponse(
            state_machine=updated,
            validation_report_id=validation_report.report_id,
            validation_report=validation_report,
            dry_run_report=dry_run_report,
            dry_run_summary=dry_run_summary,
            permission_sync_failed=permission_sync_failed,
        )

    def _prepare_publishable_definition(
        self,
        *,
        organization_id: str,
        machine_name: str,
        definition: StateMachineDefinition,
        candidate_version: int,
    ) -> tuple[
        StateMachineDefinition,
        list[tuple[str, str, str]],
        list[tuple[str, str, str]],
        DefinitionReport,
        DefinitionReport,
        WorkflowDryRunSummary,
    ]:
        """Settle the definition to publish, or refuse to publish it.

        Two things reshape it before validation: the entity schema is resynced
        from the live forms, and any pinned method fields are merged in. Both
        happen before evaluation so the reports describe what actually gets
        published rather than what was submitted. The returned relation_metadata
        writes are pending only — the caller applies them after this whole
        method returns without raising, i.e. after every check here has passed.
        """
        active_schemas = self.entity_schema.resolve_active_schemas(
            organization_id, definition.entity_type
        )
        resynced_schema = self.entity_schema._resync_entity_schema_field_metadata(
            organization_id, definition.entity_schema, active_schemas
        )
        if resynced_schema is not definition.entity_schema:
            definition = definition.model_copy(update={"entity_schema": resynced_schema})
        definition, method_pins, relation_writes, pin_issues = self._resolve_pinned_method_fields(
            organization_id, definition
        )
        validation_report, dry_run_report, dry_run_summary, can_publish = (
            self._evaluate_candidate_definition(
                organization_id=organization_id,
                machine_name=machine_name,
                definition=definition,
                candidate_version=candidate_version,
                active_schemas=active_schemas,
                persist_validation_report=True,
                extra_issues=pin_issues,
            )
        )
        if pin_issues:
            # Raised separately from the generic failure below so the caller is
            # told which field disagrees and which sources disagree about it.
            raise ValidationError(
                "state machine definition cannot be published: "
                + " ".join(issue.message for issue in pin_issues)
            )
        if not can_publish or dry_run_report is None or dry_run_summary is None:
            raise ValidationError(
                "state machine definition failed validation or dry-run checks and cannot be published"
            )
        return (
            definition,
            method_pins,
            relation_writes,
            validation_report,
            dry_run_report,
            dry_run_summary,
        )

    def create_workflow_draft_for_actor(
        self,
        actor: dict[str, object],
        payload: WorkflowDraftCreateRequest,
    ) -> WorkflowDraftRecord:
        """Create one empty workflow draft at version 0 with no validation."""
        organization_id = self._organization_id(actor)
        if self.roles_manager.get_workflow_access_scope(actor) is not None:
            raise AuthorizationError("Restricted roles cannot create workflows")
        machine_name = self._generate_machine_name()
        definition = self._blank_draft_definition(
            machine_name,
            name=payload.name,
            description=payload.description,
        )
        created = self.workflow_db.create_state_machine_draft(
            organization_id=organization_id,
            machine_key=machine_name,
            machine_name=machine_name,
            definition=definition.model_dump(mode="json"),
            created_by=actor_str(actor, "user_id") or None,
        )
        logger.info(f"workflow draft created machine={machine_name} org={organization_id}")
        return created

    def seed_workflow_draft_for_actor(
        self,
        actor: dict[str, object],
        machine_name: str,
        payload: WorkflowDraftSeedRequest,
    ) -> WorkflowDraftRecord:
        """Find or create a version-0 draft for an existing published workflow family."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)
        drafts = self.workflow_db.list_state_machines(
            organization_id=organization_id,
            machine_name=machine_name,
            scope="draft",
        )
        existing_drafts = [d for d in drafts if isinstance(d, WorkflowDraftRecord)]
        if existing_drafts:
            logger.info(
                f"workflow seed_draft found existing draft machine={machine_name} org={organization_id}"
            )
            return existing_drafts[0]
        published = self.workflow_db.get_active_state_machine(
            organization_id=organization_id,
            machine_name=machine_name,
        )
        if published is None:
            raise NotFoundError(
                f"No active published version found for workflow '{machine_name}'. Cannot seed draft."
            )
        definition = (
            payload.definition
            if payload.definition is not None
            else published.definition.model_dump(mode="json")
        )
        created = self.workflow_db.create_state_machine_draft(
            organization_id=organization_id,
            machine_key=machine_name,
            machine_name=machine_name,
            definition=definition,
            canvas_metadata=payload.canvas_metadata,
            created_by=getattr(published, "created_by", None)
            or actor_str(actor, "user_id")
            or None,
        )
        logger.info(f"workflow seed_draft created machine={machine_name} org={organization_id}")
        return created

    def update_workflow_draft_for_actor(
        self,
        actor: dict[str, object],
        row_id: str,
        payload: WorkflowDraftUpdateRequest,
    ) -> WorkflowDraftSaveResponse:
        """Persist one in-progress workflow draft definition with structural validation."""
        organization_id = self._organization_id(actor)
        existing = self.workflow_db.get_state_machine_by_row_id(
            organization_id=organization_id,
            row_id=row_id,
        )
        if existing is None:
            raise NotFoundError(f"workflow with row_id '{row_id}' was not found")
        self._authorize_workflow_access(actor, existing.machine_name)
        if getattr(existing, "version", None) != 0:
            raise ValidationError(
                f"row_id '{row_id}' points to a published version ({existing.version}) and cannot be edited directly. "
                "Only draft rows (version 0) can be updated."
            )

        parsed: StateMachineDefinition | None = None
        try:
            parsed = StateMachineDefinition.model_validate(payload.definition)
            active_schemas = self.entity_schema.resolve_active_schemas(
                organization_id, parsed.entity_type
            )
            resynced_schema = self.entity_schema._resync_entity_schema_field_metadata(
                organization_id, parsed.entity_schema, active_schemas
            )
            if resynced_schema is not parsed.entity_schema:
                # `parsed` (validated model, used below for issue-checking) and
                # `payload.definition` (raw dict, what actually gets persisted)
                # are two representations of the same definition kept in sync
                # deliberately — model_copy assigns `resynced_schema` directly
                # (no deep-copy), so `parsed.entity_schema` and this dump are
                # the same data, not divergent copies. We patch only the
                # entity_schema key of the raw dict rather than replacing it
                # with `parsed.model_dump()` wholesale, so nothing else in the
                # definition is touched by Pydantic's own normalization.
                parsed = parsed.model_copy(update={"entity_schema": resynced_schema})
                payload.definition = {
                    **payload.definition,
                    "entity_schema": resynced_schema.model_dump(mode="json"),
                }
            issues = self._definition_preview_issues(parsed)
            issues.extend(
                self.entity_schema._validate_entity_schema_against_active_forms(
                    organization_id, parsed, active_schemas
                )
            )
            issues.extend(self._validate_transition_field_references(organization_id, parsed))
        except Exception as exc:
            logger.exception(
                "workflow save_workflow_draft definition parse failed "
                f"row_id={row_id} org={organization_id}"
            )
            issues = [
                ValidationIssue(
                    code=ValidationIssueCode.INVALID_DEFINITION,
                    message=self._simple_validation_message(exc),
                )
            ]

        # Method-attach/detach relation sync only runs once the incoming definition
        # actually parsed — an unparseable definition has no method_refs worth
        # diffing, and is already reported via the INVALID_DEFINITION issue above.
        # Unlike the permissive issue-collection above, a failure here raises
        # uncaught: no method_refs write and no relation_metadata write happen
        # together, or neither does.
        if parsed is not None:
            self._sync_method_source_intent_relations(
                organization_id=organization_id,
                previous_definition=existing.definition,
                new_definition=parsed,
            )

        is_valid = not self.definition_analysis.has_blocking_issues(issues)
        should_deactivate = False

        update_kwargs = {
            "organization_id": organization_id,
            "row_id": row_id,
            "definition": payload.definition,
        }
        if "canvas_metadata" in payload.model_fields_set:
            update_kwargs["canvas_metadata"] = payload.canvas_metadata
        try:
            updated = self.workflow_db.update_state_machine_draft(**update_kwargs)
        except UnknownWorkflowServiceError as exc:
            raise ValidationError(str(exc)) from exc
        if updated is None:
            raise NotFoundError(f"workflow with row_id '{row_id}' was not found")

        logger.info(
            f"workflow draft saved row_id={row_id} machine={existing.machine_name} "
            f"org={organization_id} is_valid={is_valid}"
        )
        return WorkflowDraftSaveResponse(
            record=updated,
            validation_issues=issues,
            is_valid=is_valid,
            deactivated=should_deactivate,
        )

    def create_service_for_actor(
        self, actor: dict[str, object], request: WorkflowServiceCreateRequest
    ) -> WorkflowService:
        """Create a service in the actor's organization.

        A name already taken in this organization is a 400, the same way the
        method library treats a duplicate category name, rather than a 409.
        """
        organization_id = self._organization_id(actor)
        name = request.name.strip()
        if not name:
            raise ValidationError("service name is required")
        try:
            return self.workflow_db.create_service(organization_id=organization_id, name=name)
        except DuplicateWorkflowServiceNameError as exc:
            raise ValidationError(str(exc)) from exc

    def list_services_for_actor(self, actor: dict[str, object]) -> list[WorkflowService]:
        """Every service in the actor's organization, ordered by name."""
        organization_id = self._organization_id(actor)
        return self.workflow_db.list_services(organization_id=organization_id)

    def list_services_with_workflows_for_actor(
        self,
        actor: dict[str, object],
        *,
        limit: int = SERVICE_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[WorkflowServiceWithWorkflows], int]:
        """A page of services with the workflows filed under each, plus the total.

        The workflow lists respect the actor's workflow access scope, the same
        way `list_state_machines_scoped_for_actor` does: a scoped actor sees the
        org's services but only the workflows they are allowed to see under
        each. `total` still counts services, not workflows, so page controls
        stay stable regardless of scope.
        """
        organization_id = self._organization_id(actor)
        services, total = self.workflow_db.list_services_with_workflows(
            organization_id=organization_id, limit=limit, offset=offset
        )
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        if access_scope is None:
            return services, total
        scoped: list[WorkflowServiceWithWorkflows] = []
        for service in services:
            allowed = [
                workflow for workflow in service.workflows if workflow.machine_name in access_scope
            ]
            scoped.append(
                service.model_copy(update={"workflows": allowed, "workflow_count": len(allowed)})
            )
        return scoped, total

    def rename_service_for_actor(
        self,
        actor: dict[str, object],
        service_id: str,
        request: WorkflowServiceRenameRequest,
    ) -> WorkflowService:
        """Rename a service in place, keeping its workflows where they are."""
        organization_id = self._organization_id(actor)
        name = request.name.strip()
        if not name:
            raise ValidationError("service name is required")
        try:
            service = self.workflow_db.rename_service(
                organization_id=organization_id, service_id=service_id, name=name
            )
        except DuplicateWorkflowServiceNameError as exc:
            raise ValidationError(str(exc)) from exc
        if service is None:
            raise NotFoundError(f"service '{service_id}' was not found")
        return service

    def delete_service_for_actor(self, actor: dict[str, object], service_id: str) -> None:
        """Delete a service that no workflow is filed under.

        Refusing while workflows still reference it is the database's own
        guarantee; it surfaces as a 400 rather than a 500.
        """
        organization_id = self._organization_id(actor)
        try:
            deleted = self.workflow_db.delete_service(
                organization_id=organization_id, service_id=service_id
            )
        except WorkflowServiceInUseError as exc:
            raise ValidationError(str(exc)) from exc
        if not deleted:
            raise NotFoundError(f"service '{service_id}' was not found")

    def _assert_workflow_exists(self, organization_id: str, machine_name: str) -> None:
        """Raise NotFoundError unless `machine_name` has an active published version."""
        if (
            self.workflow_db.get_active_state_machine(
                organization_id=organization_id, machine_name=machine_name
            )
            is None
        ):
            raise NotFoundError(f"active workflow '{machine_name}' was not found")

    def get_board_display_fields_for_actor(
        self, actor: dict[str, object], machine_name: str
    ) -> WorkflowBoardDisplayFieldsRecord:
        """Get the configured extra Kanban card fields for one workflow."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)
        self._assert_workflow_exists(organization_id, machine_name)
        return self.workflow_db.get_board_display_fields(
            organization_id=organization_id,
            machine_name=machine_name,
        )

    def update_board_display_fields_for_actor(
        self,
        actor: dict[str, object],
        payload: WorkflowBoardDisplayFieldsUpdateRequest,
    ) -> WorkflowBoardDisplayFieldsRecord:
        """Replace the configured extra Kanban card fields for one workflow."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, payload.machine_name)
        self._assert_workflow_exists(organization_id, payload.machine_name)
        updated = self.workflow_db.upsert_board_display_fields(
            organization_id=organization_id,
            machine_name=payload.machine_name,
            fields=payload.fields,
            updated_by=actor_str(actor, "user_id") or None,
        )
        logger.info(
            f"workflow board_display_fields saved machine={payload.machine_name} "
            f"org={organization_id} fields={payload.fields}"
        )
        return updated

    @staticmethod
    def _blank_draft_definition(
        machine_name: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> StateMachineDefinition:
        """Return a minimal blank draft definition for a given machine_name family."""
        return StateMachineDefinition(
            machine_key=machine_name,
            name=name or "New Workflow",
            description=description or "",
            entity_type=EntityTypeSentinel.UNASSIGNED,
            entity_schema=EntitySchema(entity_type=EntityTypeSentinel.UNASSIGNED, fields=[]),
            states=[
                State(
                    name="INITIAL",
                    description="Initial state.",
                    tags=[StateTag.INITIAL],
                    order=1,
                )
            ],
            initial_state="INITIAL",
            transitions=[],
        )

    @staticmethod
    def _generate_machine_name() -> str:
        """Generate one random workflow-family identifier."""
        alphabet = string.ascii_lowercase + string.digits
        head = "".join(secrets.choice(alphabet) for _ in range(8))
        tail = "".join(secrets.choice(alphabet) for _ in range(6))
        return f"workflow_{head}_{tail}"

    @staticmethod
    def _simple_validation_message(exc: Exception) -> str:
        """Extract a concise validation message from parser exceptions."""
        if hasattr(exc, "errors"):
            messages: list[str] = []
            for error in exc.errors():  # type: ignore[attr-defined]
                message = str(error.get("msg") or "Invalid definition").strip()
                if message.startswith("Value error, "):
                    message = message[len("Value error, ") :]
                if message and message not in messages:
                    messages.append(message)
            if messages:
                return "; ".join(messages)
        return str(exc)

    def list_workflow_paths_for_actor(
        self, actor: dict[str, object], payload: StateMachineValidateRequest
    ) -> WorkflowPathsResponse:
        """Render all currently discoverable workflow paths for a candidate definition."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, payload.machine_name)

        candidate_version = self.workflow_db.get_next_version(
            organization_id=organization_id, machine_name=payload.machine_name
        )
        validation, dry_run_report, dry_run_summary, _ = self._evaluate_candidate_definition(
            organization_id=organization_id,
            machine_name=payload.machine_name,
            definition=payload.definition,
            candidate_version=candidate_version,
            persist_validation_report=False,
        )
        if not validation.valid:
            return WorkflowPathsResponse(
                machine_name=payload.machine_name,
                candidate_version=candidate_version,
                validation_report=validation,
                dry_run_report=None,
                paths=[],
            )
        return WorkflowPathsResponse(
            machine_name=payload.machine_name,
            candidate_version=candidate_version,
            validation_report=validation,
            dry_run_report=dry_run_report,
            paths=self.simulation.render_workflow_paths(dry_run_summary),
        )

    def list_workflows_for_actor(
        self, actor: dict[str, object], machine_name: str | None = None
    ) -> StateMachineListResponse:
        """List every persisted workflow version for the actor's org.

        Pass `machine_name` to scope to one workflow's version history;
        omit it to see every workflow the org has published. Results are
        ordered by the underlying DB's natural insert order (typically
        ascending version per machine)."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name) if machine_name else None
        scope = self.roles_manager.get_workflow_access_scope(actor)
        rows = self.workflow_db.list_state_machines(
            organization_id=organization_id,
            machine_name=machine_name,
            scope=WorkflowScope.PUBLISHED.value,
        )
        return StateMachineListResponse(
            items=[
                self._machine(item) for item in rows if scope is None or item.machine_name in scope
            ]
        )

    def get_workflow_by_row_id_for_actor(
        self,
        actor: dict[str, object],
        payload: WorkflowRowLookupRequest,
    ) -> WorkflowDraftRecord | StateMachineRecord:
        """Resolve one exact workflow row by `row_id`."""
        organization_id = self._organization_id(actor)
        machine = self.workflow_db.get_state_machine_by_row_id(
            organization_id=organization_id,
            row_id=payload.row_id,
        )
        if machine is None:
            raise NotFoundError(f"workflow with row_id '{payload.row_id}' was not found")
        self._authorize_workflow_access(actor, machine.machine_name)
        if getattr(machine, "version", None) == 0:
            return machine
        return self._machine_with_method_schemas(machine)

    def list_state_machines_scoped_for_actor(
        self,
        actor: dict[str, object],
        payload: WorkflowListScopeRequest,
        include_archived: bool = False,
    ) -> WorkflowListResponse:
        """Return published/draft/all workflow lists for one scope."""
        organization_id = self._organization_id(actor)
        rows = self.workflow_db.list_state_machines(
            organization_id=organization_id,
            machine_name=payload.machine_name,
            scope=payload.scope.value,
            include_archived=include_archived,
        )
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        published_items: list[StateMachineRecord] = []
        draft_items: list[WorkflowDraftRecord] = []
        for row in rows:
            if access_scope is not None and row.machine_name not in access_scope:
                continue
            if getattr(row, "version", None) == 0:
                draft_items.append(row)
            else:
                published_items.append(self._machine(row))
        self._attach_creator_names(published_items, draft_items)
        return WorkflowListResponse(
            scope=payload.scope.value,
            published_items=published_items,
            draft_items=draft_items,
        )

    def _resolve_user_names(self, user_ids: set[str]) -> dict[str, str | None]:
        """Map user ids to display names. Empty if the lookup fails.

        The catch is broad on purpose: the user service is duck-typed, so we
        can't know what it throws. A missing name must never break the list.
        """
        if not user_ids or self.user_service_manager is None:
            return {}
        try:
            return {
                user_id: self.user_service_manager.get_user_display_info(user_id)[0]
                for user_id in user_ids
            }
        except Exception:
            logger.warning("Failed to resolve user display names", exc_info=True)
            return {}

    def _attach_creator_names(
        self,
        published_items: list[StateMachineRecord],
        draft_items: list[WorkflowDraftRecord],
    ) -> None:
        """Resolve and stamp `created_by_name` for a batch of workflow rows in-place."""
        rows = (*published_items, *draft_items)
        names = self._resolve_user_names({row.created_by for row in rows if row.created_by})
        for row in rows:
            if row.created_by:
                row.created_by_name = names.get(row.created_by)

    def _attach_assignee_owner_names(self, items: list[WorkflowEnrollmentSummary]) -> None:
        """Fill in `owner_name`/`assignee_name` on a page of rows, in place.

        Rows only carry user ids. The UI looked these up itself, so anything
        server-side (Agent Mode) was stuck with raw ids.
        """
        names = self._resolve_user_names(
            {user_id for row in items for user_id in (row.owner_id, row.assignee_id) if user_id}
        )
        for row in items:
            if row.owner_id:
                row.owner_name = names.get(row.owner_id)
            if row.assignee_id:
                row.assignee_name = names.get(row.assignee_id)

    def delete_workflow_for_actor(
        self,
        actor: dict[str, object],
        row_id: str,
    ) -> WorkflowDraftRecord | StateMachineRecord:
        """Soft-delete one workflow row by its row ID.

        Sets archived_at to the current timestamp without removing the row.
        Works for both draft and published versions. Raises ValidationError if
        any entities are still active (non-terminal) in this workflow version.
        """
        organization_id = self._organization_id(actor)
        row = self.workflow_db.get_state_machine_by_row_id(
            organization_id=organization_id,
            row_id=row_id,
        )
        if row is None:
            logger.warning(f"workflow not found for archive row_id={row_id} org={organization_id}")
            raise NotFoundError(f"workflow with row_id '{row_id}' was not found")
        self._authorize_workflow_access(actor, row.machine_name)

        if self.entities_service_manager is not None:
            definition = getattr(row, "definition", None)
            terminal_states: list[str] = []
            if definition is not None:
                if isinstance(definition, dict):
                    states = definition.get("states", [])
                    terminal_states = [
                        s["name"]
                        for s in states
                        if isinstance(s, dict) and "terminal" in (s.get("tags") or [])
                    ]
                else:
                    terminal_states = [
                        s.name
                        for s in getattr(definition, "states", [])
                        if "terminal" in (s.tags or [])
                    ]
            has_active = self.entities_service_manager.db_model_service.has_non_terminal_entities_for_workflow(
                organization_id=organization_id,
                workflow_ids=[row_id],
                terminal_states=terminal_states,
            )
            if has_active:
                logger.warning(
                    f"archive blocked row_id={row_id} machine={row.machine_name} org={organization_id}"
                )
                raise ValidationError(
                    "Cannot archive: one or more entities are still active in this workflow"
                )

        deleted = self.workflow_db.delete_state_machine_by_row_id(
            organization_id=organization_id,
            row_id=row_id,
        )
        if deleted is None:
            logger.warning(f"workflow not found for archive row_id={row_id} org={organization_id}")
            raise NotFoundError(f"workflow with row_id '{row_id}' was not found")
        logger.info(
            f"workflow soft-deleted row_id={row_id} "
            f"machine={deleted.machine_name} org={organization_id}"
        )
        return deleted

    def get_state_machine_by_name(
        self, org_id: str, machine_name: str
    ) -> StateMachineRecord | None:
        """Return the active workflow version by machine_name, or None if not found."""
        return self.workflow_db.get_active_state_machine(
            organization_id=org_id, machine_name=machine_name
        )

    def get_active_state_machine_for_actor(
        self, actor: dict[str, object], machine_name: str
    ) -> StateMachineRecord:
        """Load the active workflow version."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)

        machine = self.workflow_db.get_active_state_machine(
            organization_id=organization_id, machine_name=machine_name
        )
        if machine is None:
            raise NotFoundError(f"active workflow '{machine_name}' was not found")
        return self._machine_with_method_schemas(machine)

    def get_state_machine_for_actor(
        self, actor: dict[str, object], machine_name: str, version: int
    ) -> StateMachineRecord:
        """Load one workflow version."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)
        return self._machine_with_method_schemas(
            self._machine_or_raise(organization_id, machine_name, version)
        )

    def compare_state_machine_versions_for_actor(
        self, actor: dict[str, object], machine_name: str, from_version: int, to_version: int
    ) -> StateMachineVersionCompareResponse:
        """Compare two versions of the same workflow."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)

        if from_version == to_version:
            raise ValidationError("from_version and to_version must be different")
        left = self._machine_or_raise(organization_id, machine_name, from_version)
        right = self._machine_or_raise(organization_id, machine_name, to_version)
        return self.definition_analysis.compare_definitions(
            machine_name, from_version, to_version, left.definition, right.definition
        )

    def validate_workflow_version_for_actor(
        self, actor: dict[str, object], machine_name: str, version: int
    ) -> DefinitionReport:
        """Validate and persist one workflow version."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)

        return self._persist_validation_report(
            organization_id, self._machine_or_raise(organization_id, machine_name, version)
        )

    def activate_workflow_for_actor(
        self, actor: dict[str, object], machine_name: str, version: int
    ) -> StateMachineRecord:
        """Activate a safe workflow version."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)

        report = self.workflow_db.get_latest_validation_report(
            organization_id=organization_id, machine_name=machine_name, version=version
        )
        if report is None or report.valid is not True:
            machine = self._machine_or_raise(organization_id, machine_name, version)
            report = self._persist_validation_report(organization_id, machine)
            if report.valid is not True:
                raise ValidationError("workflow version failed validation and cannot be activated")
        result = self._machine_with_method_schemas(
            self.workflow_db.activate_state_machine(
                organization_id=organization_id, machine_name=machine_name, version=version
            )
        )
        logger.info(
            f"workflow activated machine={machine_name} version={version} org={organization_id}"
        )
        return result

    def revert_workflow_version_for_actor(
        self, actor: dict[str, object], machine_name: str, version: int
    ) -> StateMachineRecord:
        """Re-activate a safe historical workflow version."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)

        machine = self._machine_or_raise(organization_id, machine_name, version)
        validation = self._persist_validation_report(organization_id, machine)
        if validation.valid is not True:
            raise ValidationError("workflow version failed validation and cannot be re-activated")
        return self._machine_with_method_schemas(
            self.workflow_db.activate_state_machine(
                organization_id=organization_id, machine_name=machine_name, version=version
            )
        )

    def dry_run_entity_for_actor(
        self,
        actor: dict[str, object],
        machine_name: str,
        version: int,
        payload: EntityDryRunRequest,
    ) -> EntityDryRunResponse:
        """Dry-run one entity snapshot against a full workflow version."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)

        machine = self._machine_or_raise(organization_id, machine_name, version)
        if payload.entity_type != machine.definition.entity_type:
            raise ValidationError("entity_type must match the workflow definition entity_type")
        known_states = {state.name for state in machine.definition.states}
        if payload.current_state not in known_states:
            # The simulator starts its walk from this state and looks it up with next(), which
            # raises StopIteration for an unknown name and surfaces as a 500. Reject it here.
            raise ValidationError(
                f"current_state '{payload.current_state}' is not a state in workflow "
                f"'{machine_name}' version {version}"
            )
        # No schema_fields argument: EntityDryRunRequest does not carry one, and for a dry run
        # against a pinned workflow version the definition's own schema is the correct source.
        self.entity_schema._validate_entity_data(
            organization_id, machine.definition, dict(payload.data)
        )
        return EntityDryRunResponse(
            machine_name=machine_name,
            version=version,
            definition=machine.definition,
            validation_report=self._build_validation_preview(
                machine_name, version, machine.definition
            ),
            dry_run_summary=self.simulation.simulate_definition(
                machine.definition,
                start_states=[payload.current_state],
                seed_data=dict(payload.data),
            ),
        )

    def _evaluate_candidate_definition(
        self,
        *,
        organization_id: str,
        machine_name: str,
        definition: StateMachineDefinition,
        candidate_version: int,
        persist_validation_report: bool,
        extra_issues: list[ValidationIssue] | None = None,
        active_schemas: list[EntityTypeSchemaContract] | None = None,
    ) -> tuple[DefinitionReport, DefinitionReport | None, WorkflowDryRunSummary | None, bool]:
        """Validate definition and optionally run dry-run preview in one reusable path.

        `extra_issues` carries issues found before this point, so they land in the
        persisted report and count towards whether the definition can publish.
        """
        issues = self._definition_preview_issues(definition)
        issues.extend(
            self.entity_schema._validate_entity_schema_against_active_forms(
                organization_id, definition, active_schemas
            )
        )
        issues.extend(self._validate_document_fields(organization_id, definition))
        issues.extend(self._validate_transition_field_references(organization_id, definition))
        issues.extend(extra_issues or [])
        validation = (
            self._create_validation_report(
                organization_id=organization_id,
                machine_name=machine_name,
                version=candidate_version,
                issues=issues,
            )
            if persist_validation_report
            else self.definition_analysis.build_preview_report(
                machine_name, candidate_version, ReportType.VALIDATION, issues
            )
        )
        if validation.valid is not True:
            return validation, None, None, False
        dry_run_summary = self.simulation.simulate_definition(definition)
        dry_run_report = self._build_dry_run_preview(
            machine_name, candidate_version, definition, dry_run_summary
        )
        return validation, dry_run_report, dry_run_summary, dry_run_report.valid is True

    def list_available_transitions_for_actor(
        self,
        actor: dict[str, object],
        machine_name: str | None,
        current_state: str | None,
        entity_id: str,
        inputs: dict[str, object] | None = None,
        workflow_id: str | None = None,
    ) -> AvailableTransitionsResponse:
        """List available transitions from the entity's current state."""
        organization_id = self._organization_id(actor)

        entity_state, _, _, enrolled_machine = self._hydrate_state_with_id(
            organization_id, entity_id, workflow_id=workflow_id
        )
        state_name = (entity_state.current_state if entity_state else None) or current_state or ""
        resolved_machine_name = (
            (entity_state.machine_name if entity_state else None) or machine_name or ""
        )
        self._authorize_workflow_access(actor, resolved_machine_name)
        if entity_state is not None and not entity_state.workflow_id:
            raise NotFoundError(not_enrolled_message(entity_id, resolved_machine_name))
        machine = self._runtime_machine(
            organization_id, resolved_machine_name, entity_state, enrolled_machine
        )
        resolved_inputs = dict(inputs or {})
        transitions = self.transition_evaluation.available_options(
            machine.definition,
            state_name,
            dict(entity_state.data) if entity_state else {},
            resolved_inputs,
        )
        return AvailableTransitionsResponse(
            entity_id=entity_id, current_state=state_name, available_transitions=transitions
        )

    def preflight_transition_for_actor(
        self,
        actor: dict[str, object],
        machine_name: str,
        current_state: str,
        entity_id: str,
        trigger: str,
        inputs: dict[str, object] | None = None,
        workflow_id: str | None = None,
    ) -> TransitionPreflightResponse:
        """Run non-mutating transition checks."""
        organization_id = self._organization_id(actor)
        # One scope read serves both enforcements: the actor's workflow scope does not depend on
        # which workflow is being checked. Both checks still run - the first covers the workflow the
        # caller named, the second covers the workflow the entity is actually enrolled in, which can
        # differ.
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        self._deny_out_of_scope_workflow(actor, machine_name, access_scope)

        entity_state, _, _, enrolled_machine = self._hydrate_state_with_id(
            organization_id, entity_id, workflow_id=workflow_id
        )
        resolved_machine_name = (
            entity_state.machine_name if entity_state else None
        ) or machine_name
        self._deny_out_of_scope_workflow(actor, resolved_machine_name, access_scope)
        if entity_state is not None and not entity_state.workflow_id:
            raise NotFoundError(not_enrolled_message(entity_id, resolved_machine_name))
        state_name = entity_state.current_state if entity_state else current_state
        machine = self._runtime_machine(
            organization_id, resolved_machine_name, entity_state, enrolled_machine
        )
        transition = self.transition_evaluation.require_transition(
            machine.definition, state_name, trigger
        )
        blocked, guards, missing = self.transition_evaluation.evaluate(
            transition,
            dict(entity_state.data) if entity_state else {},
            dict(inputs or {}),
        )
        return TransitionPreflightResponse(
            entity_id=entity_id,
            trigger=transition.trigger,
            to_state=transition.to_state,
            label=transition.label,
            allowed=not blocked,
            missing_required_fields=missing,
            guard_results=guards,
            blocked_reasons=blocked,
            needs_dialog=bool(
                transition.required_fields or transition.guards or transition.post_transition_tasks
            ),
        )

    def _authorize_transition(
        self,
        actor: dict[str, object],
        machine_name: str,
        transition_key: str,
        organization_id: str,
    ) -> None:
        """Raise AuthorizationError if actor's role is not allowed to execute this transition."""
        user_id = actor_str(actor, "user_id")
        if not user_id:
            raise ValidationError("Cannot authorize transition: actor is missing user_id")
        scope = self.roles_manager.get_workflow_access_scope(actor)
        if scope is not None and machine_name not in scope:
            raise AuthorizationError(f"Not allowed to access workflow '{machine_name}'")
        allowed = self.roles_manager.db_model_service.check_transition_permission(
            user_id, organization_id, machine_name, transition_key
        )
        if not allowed:
            raise AuthorizationError(
                f"Not allowed to execute transition '{transition_key}' on workflow '{machine_name}'"
            )

    def rerun_state_action_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        action_index: int | None = None,
        *,
        workflow_id: str | None = None,
    ) -> StateActionRerunResponse:
        """Re-run the whole chain (action_index=None) or one isolated action."""
        organization_id = self._organization_id(actor)
        actor_id = actor_str(actor, "user_id") or None
        current_state, actions, state_version, machine_name = self._resolve_rerun_state_action(
            organization_id, entity_id, workflow_id=workflow_id
        )
        self._authorize_workflow_access(actor, machine_name)
        isolated = action_index is not None
        index = action_index if action_index is not None else 0
        if not (0 <= index < len(actions)):
            raise ValidationError(
                f"action_index {index} is out of range for state '{current_state}' "
                f"({len(actions)} action(s) configured)"
            )
        run_id = self.state_action_scheduling.enqueue_rerun(
            organization_id=organization_id,
            entity_id=entity_id,
            current_state=current_state,
            state_version=state_version,
            action=actions[index],
            action_index=index,
            action_total=len(actions),
            isolated=isolated,
            actor_id=actor_id,
        )
        return StateActionRerunResponse(
            run_id=run_id,
            entity_id=entity_id,
            state=current_state,
            action_kinds=[actions[index].kind] if isolated else [a.kind for a in actions],
            status=ActionRunStatus.PENDING.value,
        )

    def _resolve_rerun_state_action(
        self,
        organization_id: str,
        entity_id: str,
        *,
        workflow_id: str | None = None,
    ) -> tuple[str, list[StateAction], int, str]:
        """Resolve the current-state action chain for a manual re-run, or raise.

        Raises NotFoundError (no workflow state), ValidationError (state has no
        action), or ConflictError (a run is already in flight)."""
        entity_state, state_id, _workflow_id, _enrolled_machine = self._hydrate_state_with_id(
            organization_id, entity_id, workflow_id=workflow_id
        )
        if entity_state is None or state_id is None:
            logger.warning(
                f"action rerun rejected: entity workflow state not found entity={entity_id} org={organization_id}"
            )
            raise NotFoundError(f"entity '{entity_id}' workflow state was not found")
        machine = self._runtime_machine(organization_id, entity_state.machine_name, entity_state)
        current_state = entity_state.current_state
        actions = self.state_action_scheduling.rerun_actions_for_state(
            machine.definition,
            current_state,
            entity_id=entity_id,
            machine_name=entity_state.machine_name,
        )
        self.state_action_scheduling.ensure_rerun_allowed(organization_id, entity_id, current_state)
        return (
            current_state,
            actions,
            entity_state.state_version,
            entity_state.machine_name,
        )

    def execute_transition_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        payload: TransitionExecuteRequest,
        *,
        _system_initiated: bool = False,
    ) -> TransitionExecutionResponse:
        """Execute one transition against the entity's runtime workflow version.

        No session parameter: the roles model service opens its own for the transition-permission
        check, so HTTP and non-HTTP callers (the agent tool) reach this the same way.
        """
        organization_id = self._organization_id(actor)

        actor_id = actor_str(actor, "user_id") or None
        if entity_id != payload.entity_id:
            raise ValidationError("entity_id in path must match request payload")
        entity_state, state_id, workflow_id, enrolled_machine = self._hydrate_state_with_id(
            organization_id, entity_id, workflow_id=payload.workflow_id
        )
        if entity_state is None:
            raise NotFoundError(f"entity '{entity_id}' workflow state was not found")
        if not entity_state.workflow_id:
            raise NotFoundError(not_enrolled_message(entity_id, entity_state.machine_name))
        if state_id is None or workflow_id is None:
            raise NotFoundError(f"entity '{entity_id}' workflow state was not found")
        if payload.idempotency_key:
            replay = self.transition_audit.find_successful_replay(
                organization_id, entity_id, payload.idempotency_key
            )
            if replay is not None:
                return replay
        machine = self._runtime_machine(
            organization_id, entity_state.machine_name, entity_state, enrolled_machine
        )
        transition = self.transition_evaluation.require_transition(
            machine.definition, entity_state.current_state, payload.trigger
        )
        blocked, guard_results, missing = self.transition_evaluation.evaluate(
            transition, dict(entity_state.data), payload.inputs
        )
        if blocked:
            self.transition_audit.emit_outcome(
                organization_id=organization_id,
                entity_state=entity_state,
                transition=transition,
                workflow_id=workflow_id,
                machine_version=machine.version,
                actor_id=actor_id,
                idempotency_key=payload.idempotency_key,
                is_system=_system_initiated,
                status=TransitionStatus.BLOCKED,
                inputs=dict(payload.inputs) if payload.inputs else None,
                guard_evaluations={"results": [item.model_dump() for item in guard_results]}
                if guard_results
                else None,
                blocked_reasons=blocked,
            )
            if missing or any(not item.passed for item in guard_results):
                raise ValidationError("; ".join(blocked))
            raise ValidationError("; ".join(blocked))
        if not _system_initiated:
            self._authorize_transition(
                actor, entity_state.machine_name, transition.key, organization_id
            )
        transitioned_at = datetime.now(UTC)
        state_duration_seconds = self._state_duration(
            entity_state.state_entered_at, transitioned_at
        )
        merged_data = {**entity_state.data, **payload.inputs}
        self.entities_service_manager.update_entity_record(
            organization_id=organization_id,
            entity_id=entity_id,
            request=EntityRecordUpdateRequest(data=merged_data),
        )
        target_state = next(
            (s for s in machine.definition.states if s.name == transition.to_state), None
        )
        sla_due = self.state_action_scheduling.calculate_sla_due(
            transitioned_at,
            target_state.sla_seconds if target_state else None,
        )
        updated_state = self.entities_service_manager._transition_entity_state(
            organization_id=organization_id,
            state_id=state_id,
            expected_state_version=entity_state.state_version,
            next_state=transition.to_state,
            state_entered_at=transitioned_at,
            last_transition_at=transitioned_at,
            sla_due_at=sla_due,
        )
        if updated_state is None:
            logger.warning(
                f"workflow transition conflict entity={entity_id} trigger={payload.trigger} expected_version={entity_state.state_version}"
            )
            self.transition_audit.emit_outcome(
                organization_id=organization_id,
                entity_state=entity_state,
                transition=transition,
                workflow_id=workflow_id,
                machine_version=machine.version,
                actor_id=actor_id,
                idempotency_key=payload.idempotency_key,
                is_system=_system_initiated,
                status=TransitionStatus.CONFLICT,
                inputs=dict(payload.inputs) if payload.inputs else None,
                blocked_reasons=[STATE_VERSION_CONFLICT_REASON],
            )
            raise ConflictError(STATE_VERSION_CONFLICT_REASON)
        transition_id = str(uuid4())
        event_id = str(uuid4())
        committed = TransitionExecutionResponse(
            transition_id=transition_id,
            event_id=event_id,
            entity_id=entity_id,
            from_state=entity_state.current_state,
            to_state=transition.to_state,
            state_version=updated_state.state_version,
            executed_tasks=[],
            idempotent=False,
            sla_due_at=updated_state.sla_due_at,
            state_duration_seconds=state_duration_seconds,
        )
        post_state = EntityState.model_validate(
            {
                **entity_state.model_dump(),
                "current_state": transition.to_state,
                "state_version": updated_state.state_version,
                "data": merged_data,
                "state_entered_at": transitioned_at,
                "last_transition_at": transitioned_at,
                "sla_due_at": updated_state.sla_due_at,
            }
        )
        logger.info(
            f"workflow transition executed entity={entity_id} trigger={payload.trigger} from={entity_state.current_state} to={transition.to_state}"
        )
        self.state_action_scheduling.apply_entry_effects(
            organization_id=organization_id,
            entity_id=entity_id,
            state=transition.to_state,
            machine_definition=machine.definition,
            entry_key=transition.key,
            state_version=updated_state.state_version,
            entered_at=transitioned_at,
            workflow_id=machine.id,
        )
        committed.executed_tasks = self._execute_post_tasks(
            organization_id, post_state, transition, transition_id
        )
        transition_outputs = committed.model_dump(mode="json")
        if _system_initiated:
            transition_outputs.setdefault("metadata", {})["system_initiated"] = True
        self.transition_audit.emit_outcome(
            organization_id=organization_id,
            entity_state=entity_state,
            transition=transition,
            workflow_id=workflow_id,
            machine_version=machine.version,
            actor_id=actor_id,
            idempotency_key=payload.idempotency_key,
            is_system=_system_initiated,
            status=TransitionStatus.SUCCEEDED,
            inputs=dict(payload.inputs) if payload.inputs else None,
            outputs=transition_outputs,
        )
        return committed

    def execute_transition_system(
        self,
        organization_id: str,
        entity_id: str,
        trigger: str,
    ) -> TransitionExecutionResponse:
        """Execute a transition in system context — bypasses role-based transition checks."""
        payload = TransitionExecuteRequest(
            entity_id=entity_id,
            trigger=trigger,
            idempotency_key=f"system:{entity_id}:{trigger}",
            inputs={},
        )
        return self.execute_transition_for_actor(
            actor={"organization_id": organization_id, "user_id": "system"},
            entity_id=entity_id,
            payload=payload,
            _system_initiated=True,
        )

    def list_transition_history_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> TransitionHistoryResponse:
        """List transition attempts for one entity, newest-first, with pagination."""
        organization_id = self._organization_id(actor)
        entity = self.entities_service_manager.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        if entity is None:
            raise NotFoundError(f"Entity '{entity_id}' not found")

        if self.roles_manager is not None:
            self.entities_service_manager.verify_entity_type_view_permission(
                actor, organization_id, entity.entity_type_id
            )

        attempts, total = self.workflow_db.list_transition_attempts_for_entity(
            organization_id=organization_id,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

        workflow_ids = list({r.workflow_id for r in attempts})
        machine_map: dict[str, object] = {}
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        for wid in workflow_ids:
            machine = self.workflow_db.get_state_machine_by_row_id(
                organization_id=organization_id, row_id=wid
            )
            if machine is not None and (
                access_scope is None or machine.machine_name in access_scope
            ):
                machine_map[wid] = machine

        items: list[ActivityRecord] = []
        for record in attempts:
            machine = machine_map.get(record.workflow_id)
            if machine is None and access_scope is not None:
                continue
            items.append(
                ActivityRecord(
                    activity_id=record.transition_attempt_id,
                    activity_type=ActivityType.TRANSITION_ATTEMPT,
                    entity_id=record.entity_id,
                    machine_name=machine.machine_name if machine else "",
                    machine_version=machine.version if machine else 0,
                    trigger=record.trigger,
                    from_state=record.from_state,
                    to_state=record.to_state,
                    actor_id=record.actor_id,
                    actor_name=record.actor_name,
                    actor_role=record.actor_role,
                    status=record.status,
                    idempotency_key=record.idempotency_key,
                    blocked_reasons=list((record.outputs or {}).get("blocked_reasons", []))
                    if record.outputs
                    else [],
                    committed_response=dict(record.outputs) if record.outputs else None,
                    payload=dict(record.inputs) if record.inputs else {},
                    created_at=record.occurred_at,
                )
            )
        return TransitionHistoryResponse(
            total=len(items) if access_scope is not None else total,
            items=items,
        )

    def list_event_history_for_actor(
        self, actor: dict[str, object], entity_id: str
    ) -> EventHistoryResponse:
        """List projected event history for one entity from `audit.entity_events`."""
        organization_id = self._organization_id(actor)
        events = self.entities_service_manager.db_model_service.list_entity_events_for_entity(
            organization_id=organization_id, entity_id=entity_id
        )
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        items: list[EventRecord] = []
        for record in events:
            machine_name = ""
            machine_version = 0
            payload = dict(record.payload) if record.payload else {}
            mn = payload.get("machine_name")
            mv = payload.get("machine_version")
            if isinstance(mn, str):
                machine_name = mn
                if access_scope is not None and machine_name not in access_scope:
                    continue
            if isinstance(mv, int):
                machine_version = mv
            items.append(
                EventRecord(
                    event_id=record.event_id,
                    entity_id=record.entity_id,
                    machine_name=machine_name,
                    machine_version=machine_version,
                    event_type=record.event_type,
                    payload=payload,
                    created_at=record.occurred_at,
                )
            )
        return EventHistoryResponse(items=items)

    def enroll_entity_for_actor(
        self,
        actor: dict[str, object],
        machine_name: str,
        entity_id: str,
    ) -> EntityState:
        """Enroll an existing entity in the active version of `machine_name`.

        The entity record must already exist (live, not archived) and its
        entity_type must match the workflow's declared entity_type. Writes
        one row to `runtime.entity_state` at the workflow's `initial_state`
        and emits one ENTITY_ENROLLED event."""
        organization_id = self._organization_id(actor)
        self._authorize_workflow_access(actor, machine_name)
        write_check = self.roles_manager.check_permission_for_actor(
            actor, WorkflowPermissionKey.WRITE
        )
        if not write_check.allowed:
            logger.warning(
                "enrollment denied: actor lacks workflow:write: %s",
                write_check.reason,
                extra={
                    "organization_id": organization_id,
                    "machine_name": machine_name,
                    "user_id": actor_str(actor, "user_id"),
                },
            )
            raise AuthorizationError(
                write_check.reason or f"Not allowed to write to workflow '{machine_name}'"
            )

        record = self.entities_service_manager.get_entity_record(
            organization_id=organization_id,
            entity_id=entity_id,
            include_archived=False,
        )
        if record is None:
            logger.warning(
                "enrollment rejected: entity not found: %s",
                entity_id,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            raise NotFoundError(f"entity '{entity_id}' was not found")

        machine = self._runtime_machine(organization_id, machine_name, None)
        expected_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
            organization_id, machine.definition.entity_type
        )
        if not expected_entity_type_id:
            raise ValidationError(
                f"workflow '{machine_name}' has no entity type configured — "
                "open it in Edit and select an entity type before enrolling"
            )
        if record.entity_type_id != expected_entity_type_id:
            raise ValidationError(
                f"entity_type does not match workflow entity_type "
                f"'{machine.definition.entity_type}'"
            )
        if not machine.id:
            raise ServiceError(f"workflow '{machine_name}' has no active version")

        enrollment = self.entities_service_manager._enroll_entity(
            organization_id=organization_id,
            entity_id=entity_id,
            workflow_id=machine.id,
            current_state=machine.definition.initial_state,
        )
        actor_user_id = actor_str(actor, "user_id") or None
        if actor_user_id and not record.owner_id:
            self.entities_service_manager.update_entity_record(
                organization_id=organization_id,
                entity_id=entity_id,
                request=EntityRecordUpdateRequest(owner_id=actor_user_id),
            )
        try:
            self.entities_service_manager._try_emit_audit_event(
                actor=actor,
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type_id=record.entity_type_id,
                event_type=WorkflowEventType.ENTITY_ENROLLED,
                payload={"machine_name": machine_name, "workflow_id": machine.id},
            )
        except Exception as exc:
            logger.warning(
                "entity enrolled audit emit failed",
                extra={"entity_id": entity_id, "machine_name": machine_name, "error": str(exc)},
                exc_info=True,
            )
        self.state_action_scheduling.apply_entry_effects(
            organization_id=organization_id,
            entity_id=entity_id,
            state=machine.definition.initial_state,
            machine_definition=machine.definition,
            entry_key=ENROLLMENT_TRANSITION_KEY,
            state_version=enrollment.state_version,
            entered_at=datetime.now(UTC),
            workflow_id=machine.id,
        )
        # Build the response from the just-created enrollment, not from
        # `_hydrate_entity_state` — that helper picks `states[0]` (oldest by
        # state_entered_at), so when an entity is already enrolled in another
        # workflow it would return that older enrollment's machine_name and
        # current_state instead of the one we just created.
        return EntityState(
            entity_id=record.entity_id,
            entity_type=machine.definition.entity_type,
            organization_id=organization_id,
            machine_name=machine.machine_name,
            machine_version=machine.version,
            workflow_id=machine.id,
            current_state=enrollment.current_state,
            state_version=enrollment.state_version,
            due_date=record.due_date,
            data=dict(record.data),
            state_entered_at=enrollment.state_entered_at,
            last_transition_at=enrollment.last_transition_at,
            sla_due_at=enrollment.sla_due_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            archived_at=record.archived_at,
        )

    @staticmethod
    def _csv_values(raw: str | None) -> set[str]:
        """Split a comma-separated query parameter into its non-empty values."""
        return {value.strip() for value in (raw or "").split(",") if value.strip()}

    @staticmethod
    def _normalize_field_filter_scalar(raw: object) -> str:
        """Normalize one filter value into the string form SQL matches against."""
        if isinstance(raw, (dict, list)) or raw is None:
            raise ValidationError("field filter values must be strings, numbers, or booleans")
        normalized = json.dumps(raw) if isinstance(raw, bool) else str(raw)
        if len(normalized) > FIELD_FILTERS_MAX_VALUE_LENGTH:
            raise ValidationError(
                f"field filter values must be at most {FIELD_FILTERS_MAX_VALUE_LENGTH} characters"
            )
        return normalized

    @classmethod
    def _parse_field_filters(cls, raw: str | None) -> dict[str, str | list[str]] | None:
        """Parse and bound the `field_filters` JSON object.

        Every key reaches SQL as a match predicate on entity data, so this
        validates shape and size rather than trusting well-formed JSON. A value
        may be a scalar (exact match) or a list (match any of), and booleans
        normalize to their JSON spelling so they match how they are stored.
        """
        if not raw:
            return None
        try:
            decoded = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValidationError("field_filters must be a JSON object") from exc
        if not isinstance(decoded, dict) or len(decoded) > FIELD_FILTERS_MAX_KEYS:
            raise ValidationError(
                f"field_filters must be an object with at most {FIELD_FILTERS_MAX_KEYS} fields"
            )
        parsed: dict[str, str | list[str]] = {}
        for key, value in decoded.items():
            if not isinstance(key, str) or not key or len(key) > FIELD_FILTERS_MAX_KEY_LENGTH:
                raise ValidationError("field_filters contains an invalid field name")
            if isinstance(value, list):
                if not value or len(value) > FIELD_FILTERS_MAX_VALUES:
                    raise ValidationError(
                        "field_filters list values must have between 1 and "
                        f"{FIELD_FILTERS_MAX_VALUES} entries"
                    )
                parsed[key] = [cls._normalize_field_filter_scalar(item) for item in value]
            else:
                parsed[key] = cls._normalize_field_filter_scalar(value)
        return parsed

    def list_enrollment_summaries_for_actor(
        self,
        actor: dict[str, object],
        *,
        machine_name: str | None = None,
        current_state: str | None = None,
        exclude_states: str | None = None,
        entity_type_name: str | None = None,
        entity_type_id: str | None = None,
        include_archived: bool = False,
        anchor_entity_id: str | None = None,
        fields: str | None = None,
        sum_fields: str | None = None,
        thumbnail_field: str | None = None,
        include: str | None = None,
        assignee_ids: str | None = None,
        search: str | None = None,
        field_filters: str | None = None,
        identifier: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        limit: int = 50,
        offset: int | None = None,
    ) -> WorkflowEnrollmentSummaryPage:
        """Canonical bounded workflow-enrollment summary query.

        Takes the filters in their wire form — comma-separated lists and the
        `field_filters` JSON blob — and parses them here rather than in the
        controller, so the request format is owned by one layer and any caller
        (REST today, an agent tool tomorrow) gets the same validation.

        Paged by `offset`/`limit` only. Keyset cursors were removed: the sole
        consumers (per-column kanban scroll, the calendar's full drain) page
        strictly forward over a `enrollment_created_at DESC` ordering, so
        dropping it removed both the cursor-vs-sort_by ordering hazard and the
        "cursor does not match the active filters" failure that a mid-scroll
        filter change used to raise.

        `offset` counts rows this actor can *see*, not raw rows — read policies
        drop rows, and `total_count` counts only survivors, so the two have to
        agree or the trailing visible rows sit past the last reachable page."""
        organization_id = self._organization_id(actor)
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        # `access_scope` rides along as `machine_names`, which the filter chain
        # ignores whenever a single `machine_name` is set — so check it here.
        if machine_name:
            self._deny_out_of_scope_workflow(actor, machine_name, access_scope)
        includes = self._csv_values(include)
        requested_sum_fields = self._csv_values(sum_fields)
        include_state_counts = EnrollmentInclude.STATE_COUNTS in includes
        request = self.enrollment_summary.build_request(
            machine_name,
            current_state,
            entity_type_name,
            entity_type_id,
            include_archived,
            anchor_entity_id,
            self._csv_values(fields),
            thumbnail_field,
            limit,
            access_scope,
            exclude_states=self._csv_values(exclude_states) or None,
            assignee_ids=self._csv_values(assignee_ids) or None,
            search=search,
            field_filters=self._parse_field_filters(field_filters),
            identifier=identifier,
            sort_by=sort_by,
            sort_dir=sort_dir,
            offset=offset,
            include_total_count=EnrollmentInclude.TOTAL_COUNT in includes,
            include_identifier_options=(EnrollmentInclude.IDENTIFIER_OPTIONS in includes),
        )
        # Resolved before paging, not after: both halves of the read policy
        # decide which rows exist for this actor, and a page whose OFFSET runs
        # over rows the actor cannot see leaves visible records unreachable.
        # The type half is a plain `entity_type_id IN (...)` predicate, so it
        # goes into SQL; the row half cannot (see `_scan_visible_enrollment_page`).
        access = self.enrollment_summary.readable_entity_policies(
            actor, organization_id, self.entities_service_manager
        )
        allowed_ids = self.enrollment_summary.global_filter_entity_ids(
            actor=actor,
            organization_id=organization_id,
            anchor_entity_id=request.anchor_entity_id,
            include_archived=request.include_archived,
        )
        access = self.enrollment_summary.narrow_row_scan_to_reachable_types(
            organization_id, request, allowed_ids, access
        )
        scan_limit = ScanLimit()
        if access.needs_row_scan:
            items, has_more = self.enrollment_summary.scan_visible_enrollment_page(
                actor,
                organization_id,
                request,
                allowed_ids,
                access,
                self.entities_service_manager,
                scan_limit,
            )
        else:
            page = self.enrollment_summary.load_page(organization_id, request, allowed_ids, access)
            items = self.enrollment_summary.build_items(
                actor, organization_id, page.rows, request, self.entities_service_manager
            )
            has_more = page.has_more
        self._attach_assignee_owner_names(items)
        # One aggregate feeds both facets: `state_counts` is the whole map,
        # `total_count` is that map read at the requested state (or summed when
        # no state is pinned). Both therefore count exactly the rows this actor
        # can see, which a raw SQL count over the unrestricted filter set did
        # not — it ignored the read-policy drops `_build_enrollment_summary_items`
        # applies, so the table's page count overstated and its trailing pages
        # came back empty.
        aggregates = (
            self.enrollment_summary.visible_enrollment_aggregates(
                actor,
                organization_id,
                request,
                allowed_ids,
                self.entities_service_manager,
                access,
                scan_limit,
                requested_sum_fields,
            )
            if include_state_counts or request.include_total_count or requested_sum_fields
            else None
        )
        state_count_map = None if aggregates is None else aggregates.state_counts
        field_totals = (
            None
            if aggregates is None or not requested_sum_fields
            else self.enrollment_summary.field_totals_response(aggregates.field_totals)
        )
        total_count = (
            None
            if state_count_map is None or not request.include_total_count
            else (
                state_count_map.get(request.current_state, 0)
                if request.current_state
                else sum(state_count_map.values())
            )
        )
        identifier_options = (
            self.enrollment_summary.visible_identifier_options(
                actor,
                organization_id,
                request,
                allowed_ids,
                self.entities_service_manager,
                access,
                scan_limit,
            )
            if request.include_identifier_options
            else None
        )
        return WorkflowEnrollmentSummaryPage(
            items=items,
            has_more=has_more,
            state_counts=state_count_map if include_state_counts else None,
            total_count=total_count,
            identifier_options=identifier_options,
            field_totals=field_totals,
            scan_truncated=scan_limit.exhausted,
        )

    def run_facts_for_actor(
        self, actor: dict[str, object], payload: RunFactsRequest
    ) -> RunFactsResponse:
        """Batched state/timestamp/assignee/deviation facts for a set of entity ids, for analytics.

        No entity_data and no read-policy projection — this is state metadata only, not
        record content. An id outside the actor's organization or workflow access scope is
        silently omitted rather than raising, the same as the enrollment board's own rows.
        """
        organization_id = self._organization_id(actor)
        access_scope = self.roles_manager.get_workflow_access_scope(actor)
        rows = self.workflow_db.list_enrollment_summary_rows(
            organization_id=organization_id,
            entity_ids=set(payload.entity_ids),
            machine_names=access_scope,
            limit=len(payload.entity_ids),
        )
        visited_states = self._visited_states_by_enrollment(organization_id, rows)
        return RunFactsResponse(
            items=[
                self._run_facts_item(
                    row, visited_states.get((row.entity_id, row.workflow_id), set())
                )
                for row in rows
            ]
        )

    def _visited_states_by_enrollment(
        self, organization_id: str, rows: list[WorkflowEnrollmentSummaryRow]
    ) -> dict[tuple[str, str], set[str]]:
        """Map each visible enrollment to its visited states from successful audit rows.

        Audit history belongs to an enrollment, not just an entity: one entity can
        participate in several workflows.  Initial state is included explicitly
        because enrollment itself does not emit a successful transition audit row.
        Pages continue until every enrollment with no known deviation has exhausted
        its history, avoiding a false negative from a batch-wide row cap.
        """
        if not rows:
            return {}

        enrollment_rows = {(row.entity_id, row.workflow_id): row for row in rows}
        visited = {
            key: {row.machine_definition.initial_state} for key, row in enrollment_rows.items()
        }
        deviation_states = {
            key: {state.name for state in row.machine_definition.states if state.deviation}
            for key, row in enrollment_rows.items()
        }
        unresolved = {
            key
            for key, row in enrollment_rows.items()
            if not ((visited[key] | {row.current_state}) & deviation_states[key])
        }
        offset = 0
        entity_ids = list({row.entity_id for row in rows})

        while unresolved:
            events, total = self.transition_audit.audit_events_service.list_for_org_paginated(
                organization_id=organization_id,
                metadata_type=AuditMetadataType.TRANSITION,
                event_type=TransitionAuditEventType.SUCCEEDED,
                entity_ids=entity_ids,
                limit=RUN_FACTS_DEVIATION_HISTORY_PAGE_SIZE,
                offset=offset,
            )
            if not events:
                break
            for event in events:
                workflow_id = event.metadata.get(TransitionAuditMetadataKey.WORKFLOW_ID)
                if not event.entity_id or not workflow_id:
                    continue
                key = (event.entity_id, str(workflow_id))
                if key not in unresolved:
                    continue
                if event.before_state:
                    visited[key].add(event.before_state)
                if event.after_state:
                    visited[key].add(event.after_state)
                if visited[key] & deviation_states[key]:
                    unresolved.remove(key)
            offset += len(events)
            if offset >= total:
                break
        return visited

    @staticmethod
    def _run_facts_item(
        row: WorkflowEnrollmentSummaryRow, visited_states: set[str] | None = None
    ) -> RunFactsItem:
        """One enrollment row reshaped into a lean run fact for analytics."""
        state = next(
            (s for s in row.machine_definition.states if s.name == row.current_state), None
        )
        tags = state.tags if state is not None else []
        is_terminal = state.terminal if state is not None else False
        deviation_states = {s.name for s in row.machine_definition.states if s.deviation}
        visited = (visited_states or set()) | {row.current_state}
        return RunFactsItem(
            entity_id=row.entity_id,
            machine_name=row.machine_name,
            machine_display_name=row.machine_display_name,
            current_state=row.current_state,
            current_state_tags=tags,
            created_at=row.entity_created_at,
            state_entered_at=row.state_entered_at,
            terminal_transition_at=row.last_transition_at if is_terminal else None,
            assignee_id=row.assignee_id,
            due_at=row.sla_due_at,
            has_deviation=bool(visited & deviation_states),
        )

    @staticmethod
    def _state_descriptions(machine: StateMachineRecord | None) -> dict[str, str]:
        """Map state name -> description for a machine, real descriptions only.

        Handles a definition stored as either a dict or a parsed object, and
        skips states with no (or blank) description so callers can treat a
        present key as "has a real description".
        """
        if machine is None:
            return {}
        definition = machine.definition
        states = (
            definition.get("states", [])
            if isinstance(definition, dict)
            else getattr(definition, "states", [])
        )
        descriptions: dict[str, str] = {}
        for state in states or []:
            if isinstance(state, dict):
                name, desc = state.get("name"), state.get("description")
            else:
                name, desc = getattr(state, "name", None), getattr(state, "description", None)
            if name and desc and str(desc).strip():
                descriptions[str(name)] = str(desc).strip()
        return descriptions

    @staticmethod
    def _organization_id(actor: dict[str, object]) -> str:
        """Extract actor organization id."""
        organization_id = actor_str(actor, "organization_id")
        if not organization_id:
            raise ValidationError("actor organization_id is required")
        return organization_id

    def _machine_or_raise(
        self, organization_id: str, machine_name: str, version: int
    ) -> StateMachineRecord:
        """Load one workflow version or fail."""
        machine = self.workflow_db.get_state_machine(
            organization_id=organization_id, machine_name=machine_name, version=version
        )
        if machine is None:
            raise NotFoundError(f"workflow '{machine_name}' version {version} was not found")
        return machine

    def _runtime_machine(
        self,
        organization_id: str,
        machine_name: str,
        entity_state: EntityState | None,
        enrolled_machine: StateMachineRecord | None = None,
    ) -> StateMachineRecord:
        """Resolve which workflow version this request executes against.

        An enrolled entity runs the exact definition it was enrolled into, even after a newer
        version is activated; the active version is only used when there is no usable enrolled
        row. Pass `enrolled_machine` if the caller already loaded that row, to avoid re-reading
        it. Raises `NotFoundError` when no active workflow exists under the resolved name.
        """
        return self.runtime_resolution.resolve_runtime_workflow(
            organization_id, machine_name, entity_state, enrolled_machine
        )

    # ── Runtime adapter (new state-machine model) ───────────────────────────
    #
    # The workflow manager keeps the legacy `EntityState` Pydantic shape as
    # an internal hydrated view. Reads and writes go through the entities
    # service manager (runtime.entities + runtime.entity_state +
    # audit.entity_events + audit.transition_attempts), but transition logic
    # still consumes the denormalized view. The wire-shape switch to
    # `EntityWithStatesResponse` is tracked as a follow-up.

    def _hydrate_entity_state(
        self,
        organization_id: str,
        entity_id: str,
        *,
        include_archived: bool = False,
    ) -> EntityState | None:
        """Build a denormalized `EntityState` view of an entity's current workflow state.

        Returns None when the entity does not exist, or when it is archived and
        `include_archived` is False. An entity that exists but is enrolled in no workflow comes
        back as a placeholder with `machine_name=""` and `current_state="CREATED"`.
        """
        return self.runtime_resolution.hydrate_entity_state(
            organization_id, entity_id, include_archived=include_archived
        )

    def _hydrate_state_with_id(
        self,
        organization_id: str,
        entity_id: str,
        *,
        workflow_id: str | None = None,
    ) -> tuple[EntityState | None, str | None, str | None, StateMachineRecord | None]:
        """Hydrate an entity's state along with the identifiers a transition write needs.

        Returns `(view, state_id, workflow_id, enrolled_machine)`. `state_id` drives the
        optimistic-lock UPDATE on the state row, and the enrolled workflow record is handed back
        so the caller does not read it again. All three are None when the entity is enrolled
        nowhere. `workflow_id` selects one enrollment when an entity sits in several.
        """
        return self.runtime_resolution.hydrate_transition_context(
            organization_id, entity_id, workflow_id=workflow_id
        )

    def _persist_validation_report(
        self, organization_id: str, machine: StateMachineRecord
    ) -> DefinitionReport:
        """Persist a validation report."""
        issues = self._definition_preview_issues(machine.definition)
        return self._create_validation_report(
            organization_id=organization_id,
            machine_name=machine.machine_name,
            version=machine.version,
            issues=issues,
        )

    def _build_validation_preview(
        self, machine_name: str, version: int, definition: StateMachineDefinition
    ) -> DefinitionReport:
        """Build a non-persisted validation report."""
        issues = self._definition_preview_issues(definition)
        return self.definition_analysis.build_preview_report(
            machine_name, version, ReportType.VALIDATION, issues
        )

    @staticmethod
    def _entity_schema_content_hash(entity_type: str, fields: list[EntityField]) -> str:
        """Build deterministic content hash for schema dedupe."""
        payload = {
            "entity_type": entity_type,
            "fields": [
                {
                    "field": item.field,
                    "type": item.type,
                    "required": item.required,
                    "nullable": item.nullable,
                    "default": item.default,
                    "enum_values": item.enum_values,
                    "description": item.description,
                }
                for item in fields
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _current_base_version(self, organization_id: str, machine_name: str) -> int | None:
        """Return the active version for compatibility checks, if any."""
        active = self.workflow_db.get_active_state_machine(
            organization_id=organization_id, machine_name=machine_name
        )
        if active is not None:
            return active.version
        items = self.workflow_db.list_state_machines(
            organization_id=organization_id, machine_name=machine_name
        )
        return items[0].version if items else None

    def _build_dry_run_preview(
        self,
        machine_name: str,
        version: int,
        definition: StateMachineDefinition,
        summary: WorkflowDryRunSummary,
    ) -> DefinitionReport:
        """Build a non-persisted dry-run report for the whole definition."""
        issues = self.simulation.dry_run_issues(definition, summary)
        return self.definition_analysis.build_preview_report(
            machine_name, version, ReportType.DRY_RUN, issues
        )

    def _create_validation_report(
        self,
        *,
        organization_id: str,
        machine_name: str,
        version: int,
        issues: list[ValidationIssue],
    ) -> DefinitionReport:
        """Persist a normalized validation report."""
        normalized = self.definition_analysis.normalize_issues(issues, ReportType.VALIDATION)
        return self.workflow_db.create_validation_report(
            organization_id=organization_id,
            machine_name=machine_name,
            version=version,
            valid=not self.definition_analysis.has_blocking_issues(normalized),
            issues=normalized,
        )

    def _require_valid_validation_report(
        self, organization_id: str, machine_name: str, version: int
    ) -> None:
        """Require a valid persisted validation report."""
        report = self.workflow_db.get_latest_validation_report(
            organization_id=organization_id, machine_name=machine_name, version=version
        )
        if report is None or report.valid is not True:
            raise ValidationError(
                "workflow version must have a valid persisted validation report before activation"
            )

    def _validate_definition_or_raise(self, definition: StateMachineDefinition) -> None:
        """Raise on definition validation issues."""
        issues = self._definition_preview_issues(definition)
        if issues:
            raise ValidationError("; ".join(item.message for item in issues))

    def _definition_with_method_fields(
        self, organization_id: str, definition: StateMachineDefinition
    ) -> tuple[StateMachineDefinition, list[ValidationIssue]]:
        """The definition as publish would evaluate it, with method fields merged.

        Never raises: an unresolvable pin is reported as an issue so a preview
        can still render the rest of the report, where publish would refuse
        outright.
        """
        if self.method_library_db_model_service is None:
            return definition, []
        try:
            merged, _pins, _relation_writes, issues = self._resolve_pinned_method_fields(
                organization_id, definition
            )
            return merged, issues
        except Exception as exc:
            logger.debug("validate: could not resolve pinned method fields: %s", exc)
            return definition, [
                ValidationIssue(
                    code=ValidationIssueCode.INVALID_DEFINITION,
                    message=self._simple_validation_message(exc),
                    severity="error",
                )
            ]

    def _validate_transition_field_references(
        self, organization_id: str, definition: StateMachineDefinition
    ) -> list[ValidationIssue]:
        """Check a transition's field references resolve, counting the source
        state's Methods — both its guards and its `required_fields`.

        `StateMachineDefinition` performs this check itself, but can only see
        `entity_schema.fields`; a field contributed by an attached Method is
        only knowable by resolving that Method's pinned version here. It
        therefore defers to this check for any transition whose source state
        pins a method, and this is the only place such a reference is
        validated.

        Scoped per transition, matching the field picker the reference was
        built in: a transition leaving state A may use A's method fields, not
        those of an unrelated state in the same workflow.
        """
        if self.method_library_db_model_service is None:
            return []
        # A schema field with no `source_states` is the workflow's own and is
        # available in every state. One carrying them was contributed by a
        # Method pinned to those states, so it only resolves for a transition
        # leaving one of them — the merged schema is flat, and treating it as
        # uniformly available would let a guard on any state reference a field
        # collected somewhere else entirely.
        schema_by_name = {field.field: field for field in definition.entity_schema.fields}
        states = {state.name: state for state in definition.states}
        # Resolved once per state, not per guard — several guards on several
        # transitions commonly leave the same state.
        method_fields_by_state: dict[str, set[str]] = {}

        def fields_for_state(state_name: str) -> set[str]:
            if state_name in method_fields_by_state:
                return method_fields_by_state[state_name]
            resolved: set[str] = set()
            state = states.get(state_name)
            for ref in state.method_refs if state else []:
                try:
                    version_id = self._resolve_method_version_id(organization_id, ref)
                    resolved.update(
                        field.field_key
                        for field in self.method_library_db_model_service.list_version_fields(
                            organization_id=organization_id, method_version_id=version_id
                        )
                    )
                except Exception:
                    # An unresolvable pin is reported by the pin resolution
                    # itself; failing to read it here must not turn into a
                    # spurious "undefined field" against the transition.
                    logger.debug(
                        "transition field validation: could not resolve method %s on state %s",
                        ref.method_id,
                        state_name,
                        exc_info=True,
                    )
            method_fields_by_state[state_name] = resolved
            return resolved

        issues: list[ValidationIssue] = []
        for transition in definition.transitions:
            known: set[str] | None = None

            def _resolves(field_name: str, _t=transition) -> bool:
                """Whether the schema, or a Method on the state this transition
                leaves, provides `field_name`. Methods are resolved at most once
                per transition, and only if the schema does not already cover it."""
                nonlocal known
                schema_field = schema_by_name.get(field_name)
                if schema_field is not None:
                    if not schema_field.source_states:
                        return True
                    if any(src in schema_field.source_states for src in _t.source_states):
                        return True
                if known is None:
                    known = (
                        set().union(*(fields_for_state(source) for source in _t.source_states))
                        if _t.source_states
                        else set()
                    )
                return field_name in known

            # `references` (required_fields) and `guard references` keep the
            # wording the definition contract uses for each, so an operator sees
            # the same phrasing whichever layer rejected it.
            for required_field in transition.required_fields:
                if _resolves(required_field.field):
                    continue
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.INVALID_DEFINITION,
                        message=(
                            f"transition '{transition.trigger}' references undefined "
                            f"entity field '{required_field.field}' — it is not on the entity "
                            "schema, and no Method attached to the state this transition "
                            "leaves contributes it."
                        ),
                        severity="error",
                    )
                )
            for guard in transition.guards:
                if guard.field is None or _resolves(guard.field):
                    continue
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.INVALID_DEFINITION,
                        message=(
                            f"transition '{transition.trigger}' guard references undefined "
                            f"entity field '{guard.field}' — it is not on the entity schema, "
                            "and no Method attached to the state this transition leaves "
                            "contributes it."
                        ),
                        severity="error",
                    )
                )
        return issues

    def _validate_document_fields(
        self, organization_id: str, definition: StateMachineDefinition
    ) -> list[ValidationIssue]:
        """Check every file a document field points at exists in this organization.

        Done here rather than on EntityField, which is a contract with no
        organization and no services in scope. The shape of the value is settled
        there; whether the files are real is only answerable with both.

        Blocking: a workflow published against a file that is missing, or that
        belongs to another tenant, would hand the runtime a reference it can
        never resolve.
        """
        if self.filehandler_service_manager is None:
            return []
        issues: list[ValidationIssue] = []
        for field in definition.entity_schema.fields:
            if field.type != EntityFieldType.DOCUMENT or not field.default:
                continue
            missing = [
                file_id
                for file_id in field.default
                if not self._file_exists(organization_id, file_id)
            ]
            if missing:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.UNKNOWN_DOCUMENT_FILE,
                        message=(
                            f"Document field '{field.field}' points at files that do not "
                            f"exist in this organization: {', '.join(sorted(missing))}."
                        ),
                        severity="error",
                    )
                )
        return issues

    def _file_exists(self, organization_id: str, file_id: str) -> bool:
        """Whether one file id resolves inside this organization.

        `get_file` raises rather than returning None, and it filters by
        organization, so a file belonging to another tenant is indistinguishable
        from one that was never there. Both are equally unusable here.
        """
        try:
            self.filehandler_service_manager.get_file(organization_id, file_id)
        except NotFoundError:
            return False
        return True

    # ── Pinned method resolution (publish time) ───────────────────────────────

    def _resolve_pinned_method_fields(
        self, organization_id: str, definition: StateMachineDefinition
    ) -> tuple[
        StateMachineDefinition,
        list[tuple[str, str, str]],
        list[tuple[str, str, str]],
        list[ValidationIssue],
    ]:
        """Merge every state's pinned method fields into the entity schema.

        Returns the definition to publish, the pins to record as
        (state_key, method_id, method_version_id), the relation_metadata writes
        to apply as (relation_def_id, key, value), and any blocking issues.
        Both write lists are pending only: the caller applies them after every
        other publish check has passed, in the same commit as everything else
        this resolves — nothing here writes anything itself.

        A state's `method_refs` are resolved here and only here: a ref with no
        version_id captures the method's current latest version at this moment,
        and from then on the published workflow reads that version even after the
        method moves on. Nothing re-resolves on its own.
        """
        states_with_refs = [state for state in definition.states if state.method_refs]
        if not states_with_refs:
            # No pin can contribute a field any more, so a leftover derived field
            # goes with the pins that produced it rather than lingering in the
            # schema (and in every record form built from it).
            kept = [f for f in definition.entity_schema.fields if not f.source_states]
            dropped = [f.field for f in definition.entity_schema.fields if f.source_states]
            if dropped:
                logger.warning(
                    f"workflow '{definition.name}' has no method pins left: dropping "
                    f"{len(dropped)} method-derived field(s) from entity_schema "
                    f"(org_id={organization_id}, fields={', '.join(dropped)}). Record "
                    "data stored under them is left in place and no longer rendered "
                    "or validated."
                )
            entity_schema = definition.entity_schema.model_copy(update={"fields": kept})
            return (
                definition.model_copy(
                    update={"entity_schema": entity_schema, "method_schemas": []}
                ),
                [],
                [],
                [],
            )
        if self.method_library_db_model_service is None:
            raise ServiceError(
                "method library service is required to resolve workflow method references"
            )

        catalogue = self.workflow_db.list_engine_field_types()
        # Only the workflow's *own* fields seed the merge. A field carrying
        # `source_states` was written into `entity_schema` by an earlier run of
        # this resolver, and the client echoes it back verbatim on the next
        # publish — comparing this pass's resolution against that stale copy
        # reported the field as disagreeing with itself the moment the pinned
        # library field changed shape, which nothing in the builder can fix by
        # hand. Derived fields are rebuilt below instead.
        merged: dict[str, tuple[EntityField, str]] = {
            field.field: (field, "the workflow's own fields")
            for field in definition.entity_schema.fields
            if not field.source_states
        }
        pins: list[tuple[str, str, str]] = []
        method_schemas: list[ResolvedMethodSchema] = []
        issues: list[ValidationIssue] = []
        pending_relation_writes: dict[tuple[str, str], tuple[str, str]] = {}

        for state in states_with_refs:
            for method_order, ref in enumerate(state.method_refs):
                identity, version = self._resolve_method_pin(organization_id, ref)
                version_id = version.version_id
                pins.append((state.name, ref.method_id, version_id))
                source = f"method '{ref.method_id}' (version {version_id})"
                snapshot, method_fields = self._method_schema_snapshot(
                    organization_id=organization_id,
                    identity=identity,
                    version=version,
                    state=state,
                    method_order=method_order,
                    catalogue=catalogue,
                )
                for method_field, candidate in zip(method_fields, snapshot.fields, strict=True):
                    issue = self._merge_pinned_field(merged, candidate, source, state.name)
                    if issue is not None:
                        issues.append(issue)
                    inherit_issue = self._check_inherited_field_pin(
                        organization_id=organization_id,
                        definition=definition,
                        method_field=method_field,
                        source=source,
                        state_key=state.name,
                        pending_writes=pending_relation_writes,
                    )
                    if inherit_issue is not None:
                        issues.append(inherit_issue)
                    ownership_issue = self._check_owned_inheritance_pin(
                        organization_id=organization_id,
                        definition=definition,
                        method_field=method_field,
                        source=source,
                        state_key=state.name,
                    )
                    if ownership_issue is not None:
                        issues.append(ownership_issue)
                method_schemas.append(snapshot)

        if issues:
            return definition, pins, [], issues
        entity_schema = definition.entity_schema.model_copy(
            update={"fields": [field for field, _source in merged.values()]}
        )
        relation_writes = [
            (relation_def_id, key, value)
            for (relation_def_id, key), (value, _source) in pending_relation_writes.items()
        ]
        return (
            definition.model_copy(
                update={"entity_schema": entity_schema, "method_schemas": method_schemas}
            ),
            pins,
            relation_writes,
            issues,
        )

    def _method_schema_snapshot(
        self,
        *,
        organization_id: str,
        identity: MethodIdentity,
        version: MethodVersion,
        state: State,
        method_order: int,
        catalogue: dict[str, tuple[str | None, str]],
    ) -> tuple[ResolvedMethodSchema, list[MethodVersionField]]:
        """Build the canonical ordered presentation snapshot for one Method pin."""
        service = self.method_library_db_model_service
        if service is None:
            raise ServiceError(
                "method library service is required to resolve workflow method references"
            )
        method_fields = service.list_version_fields(
            organization_id=organization_id,
            method_version_id=version.version_id,
        )
        fields = [
            self._entity_field_from_method_field(method_field, catalogue).model_copy(
                update={"source_states": [state.name]}
            )
            for method_field in method_fields
        ]
        return (
            ResolvedMethodSchema(
                method_id=identity.method_id,
                method_name=identity.name,
                version_id=version.version_id,
                version=version.version,
                state_name=state.name,
                state_order=state.order,
                method_order=method_order,
                fields=fields,
            ),
            method_fields,
        )

    def _check_inherited_field_pin(
        self,
        *,
        organization_id: str,
        definition: StateMachineDefinition,
        method_field: MethodVersionField,
        source: str,
        state_key: str,
        pending_writes: dict[tuple[str, str], tuple[str, str]],
    ) -> ValidationIssue | None:
        """Validate one pinned field's `inherit_from`, and queue its write.

        Checked in order: a relation must already exist from the field's
        source entity type to this workflow's own entity type, the named
        source field must exist on that entity type today, and mapping it
        must not remap a source field something else already maps to a
        different target. `pending_writes` accumulates across every pinned
        field in this publish, so two pins in the same publish are checked
        against each other too, not only against what is already persisted.
        """
        inherit_from = method_field.inherit_from
        if not inherit_from:
            return None
        if self.entities_service_manager is None:
            raise ServiceError("entities service is required to resolve inherited method fields")

        source_entity_type_name, _, source_field = inherit_from.partition(".")
        try:
            to_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                organization_id, definition.entity_type
            )
        except ValidationError:
            to_entity_type_id = ""
        try:
            from_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                organization_id, source_entity_type_name
            )
        except ValidationError:
            from_entity_type_id = ""

        declaration = (
            self.entities_service_manager.db_model_service.get_active_relation_declaration_for_pair(
                organization_id=organization_id,
                from_entity_type_id=from_entity_type_id,
                to_entity_type_id=to_entity_type_id,
            )
            if from_entity_type_id and to_entity_type_id
            else None
        )
        if declaration is None:
            return ValidationIssue(
                code=ValidationIssueCode.PINNED_METHOD_FIELD_UNRELATED_SOURCE,
                message=(
                    f"state '{state_key}' pins {source}'s field '{method_field.field_key}' "
                    f"to inherit from '{inherit_from}', but no relation is declared from "
                    f"'{source_entity_type_name}' to '{definition.entity_type}'. Declare "
                    "that relation first."
                ),
                severity="error",
            )

        if source_field not in self._source_entity_type_field_names(
            organization_id, source_entity_type_name
        ):
            return ValidationIssue(
                code=ValidationIssueCode.PINNED_METHOD_FIELD_UNKNOWN_SOURCE_FIELD,
                message=(
                    f"state '{state_key}' pins {source}'s field '{method_field.field_key}' "
                    f"to inherit from '{inherit_from}', but '{source_field}' is not a "
                    f"field on '{source_entity_type_name}' today."
                ),
                severity="error",
            )

        target_value = f"{definition.entity_type}.{method_field.field_key}"
        accumulator_key = (declaration.relation_def_id, inherit_from)
        existing_value, existing_source = pending_writes.get(accumulator_key, (None, None))
        if existing_value is None:
            persisted = declaration.relation_metadata.get(inherit_from)
            if isinstance(persisted, str):
                existing_value, existing_source = persisted, "the relation's existing mapping"
        if existing_value is not None and existing_value != target_value:
            return ValidationIssue(
                code=ValidationIssueCode.PINNED_METHOD_FIELD_SOURCE_REMAPPED,
                message=(
                    f"state '{state_key}' pins {source}'s field '{method_field.field_key}' "
                    f"to inherit from '{inherit_from}', mapping it to '{target_value}', "
                    f"but {existing_source} already maps it to '{existing_value}'. Make "
                    "the two mappings identical, or stop one of them from remapping it."
                ),
                severity="error",
            )
        pending_writes[accumulator_key] = (target_value, source)
        return None

    def _check_owned_inheritance_pin(
        self,
        *,
        organization_id: str,
        definition: StateMachineDefinition,
        method_field: MethodVersionField,
        source: str,
        state_key: str,
    ) -> ValidationIssue | None:
        """Validate one pinned field's `ownership='inherited'`.

        The method-block-level counterpart of `_check_inherited_field_pin`. Same
        first check — a relation must already be declared from the field's source
        entity type to this workflow's entity type, or the field could never
        resolve and publishing it would only produce a permanently blank value.

        Deliberately NOT the same afterwards. This takes no `pending_writes` and
        queues nothing: an `ownership='inherited'` field is never projected into
        `entity_type_relations.relation_metadata`. That projection is what turns
        a block-level declaration into a rule for every record of the entity
        type, and avoiding it is the reason this mechanism exists. The value is
        resolved at read time from the record's own pinned schema instead
        (`EntitiesDBModelService._resolve_pinned_inherited_fields`).

        The two mechanisms cannot meet on one field: `MethodFieldInput` refuses
        `inherit_from` together with `ownership='inherited'`, so a field reaches
        exactly one of these two checks with something to do.

        No source-field-exists check here on purpose. The check `inherit_from`
        uses reads the source type's Forms only, and the types this is built for
        (client, site) have none, so it would reject every valid pin.
        """
        if method_field.ownership != FieldOwnership.INHERITED:
            return None
        if self.entities_service_manager is None:
            raise ServiceError("entities service is required to resolve inherited method fields")

        source_entity_type_name = (method_field.source_entity_type or "").strip()
        source_field = (method_field.source_field_key or "").strip()
        if not source_entity_type_name or not source_field:
            # The request model forbids this, but a row could predate it. Fail
            # closed: a field with nowhere to inherit from must not be pinned.
            return ValidationIssue(
                code=ValidationIssueCode.PINNED_METHOD_FIELD_UNRELATED_SOURCE,
                message=(
                    f"state '{state_key}' pins {source}'s field '{method_field.field_key}' "
                    "as inherited, but it names no source entity type and field to "
                    "inherit from. Set source_entity_type and source_field_key on the "
                    "method field."
                ),
                severity="error",
            )

        try:
            to_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                organization_id, definition.entity_type
            )
        except ValidationError:
            to_entity_type_id = ""
        try:
            from_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                organization_id, source_entity_type_name
            )
        except ValidationError:
            from_entity_type_id = ""

        declaration = (
            self.entities_service_manager.db_model_service.get_active_relation_declaration_for_pair(
                organization_id=organization_id,
                from_entity_type_id=from_entity_type_id,
                to_entity_type_id=to_entity_type_id,
            )
            if from_entity_type_id and to_entity_type_id
            else None
        )
        if declaration is None:
            return ValidationIssue(
                code=ValidationIssueCode.PINNED_METHOD_FIELD_UNRELATED_SOURCE,
                message=(
                    f"state '{state_key}' pins {source}'s field '{method_field.field_key}' "
                    f"as inherited from '{source_entity_type_name}.{source_field}', but no "
                    f"relation is declared from '{source_entity_type_name}' to "
                    f"'{definition.entity_type}'. Declare that relation first."
                ),
                severity="error",
            )
        return None

    def _source_entity_type_field_names(
        self, organization_id: str, entity_type_name: str
    ) -> set[str]:
        """Real field names on an entity type's active form(s), today.

        Goes through `EntitySchemaService`, which reads the active schemas via
        the forms manager and owns its own session. Before the main merge this
        reached into `forms_db_model_service` with a hand-rolled session,
        because the old `_active_forms_schemas` helper read `current_db`, which
        production never sets; `resolve_active_schemas` has no such hole, and
        `forms_db_model_service` is no longer held by this manager at all.
        """
        return {
            field.field
            for schema in self.entity_schema.resolve_active_schemas(
                organization_id, entity_type_name
            )
            for field in schema.fields
            if field.field
        }

    @staticmethod
    def _merge_pinned_field(
        merged: dict[str, tuple[EntityField, str]],
        candidate: EntityField,
        source: str,
        state_key: str,
    ) -> ValidationIssue | None:
        """Add one resolved method field, or report the clash it caused.

        Two sources defining the same key is fine while they define it
        identically, which is the ordinary case of two methods sharing a field.
        Any difference is a real disagreement about what the field is, and is
        never resolved by picking a side.
        """
        existing = merged.get(candidate.field)
        if existing is None:
            merged[candidate.field] = (candidate, source)
            return None
        held, held_source = existing
        # `source_states` records where a field came from, not what it is, so it
        # is excluded from the comparison: the same field pinned on two states
        # is agreement, not a clash. The states are unioned instead.
        comparable = {"exclude": {"source_states"}, "mode": "json"}
        if held.model_dump(**comparable) == candidate.model_dump(**comparable):
            combined = list(dict.fromkeys([*held.source_states, *candidate.source_states]))
            if combined != held.source_states:
                merged[candidate.field] = (
                    held.model_copy(update={"source_states": combined}),
                    held_source,
                )
            return None
        return ValidationIssue(
            code=ValidationIssueCode.PINNED_METHOD_FIELD_CONFLICT,
            message=(
                f"state '{state_key}' pins a method that defines field "
                f"'{candidate.field}' differently from {held_source}: {source} disagrees. "
                "Make the two definitions identical, or stop one of them from "
                "contributing the field."
            ),
            severity="error",
        )

    def _resolve_method_pin(
        self, organization_id: str, ref: MethodRef
    ) -> tuple[MethodIdentity, MethodVersion]:
        """Resolve one ref to its Method identity and exact immutable version.

        An explicit version_id is checked against the method's own history rather
        than trusted, so a version belonging to a different method, or to another
        tenant, is refused instead of silently pinned.
        """
        service = self.method_library_db_model_service
        if service is None:
            raise ServiceError(
                "method library service is required to resolve workflow method references"
            )
        identity = service.get_method(organization_id=organization_id, method_id=ref.method_id)
        if identity is None:
            raise ValidationError(f"method '{ref.method_id}' was not found")
        if ref.version_id is None:
            latest = service.get_latest_version(
                organization_id=organization_id, method_id=ref.method_id
            )
            if latest is None:
                raise ValidationError(f"method '{ref.method_id}' has no current version")
            return identity, latest
        offset = 0
        while True:
            page, total = service.list_method_versions(
                organization_id=organization_id,
                method_id=ref.method_id,
                limit=_METHOD_VERSION_PAGE,
                offset=offset,
            )
            matched = next(
                (version for version in page if version.version_id == ref.version_id), None
            )
            if matched is not None:
                return identity, matched
            offset += len(page)
            if not page or offset >= total:
                raise ValidationError(
                    f"version '{ref.version_id}' does not belong to method '{ref.method_id}'"
                )

    def _resolve_method_version_id(self, organization_id: str, ref: MethodRef) -> str:
        """Compatibility helper for validation paths that only need the version id."""
        _identity, version = self._resolve_method_pin(organization_id, ref)
        return version.version_id

    def _sync_method_source_intent_relations(
        self,
        *,
        organization_id: str,
        previous_definition: dict[str, Any],
        new_definition: StateMachineDefinition,
    ) -> None:
        """Attach/detach side effects for a state's `method_refs` changing on save.

        Diffs the previously-persisted draft's method_refs against the incoming
        ones, per state — only methods newly added or newly removed from a state
        are touched; a method that was already attached and stays attached is
        left alone, so an unrelated relation disappearing later never breaks a
        draft save that isn't touching that method this time.

        Every newly-attached method's source-intent fields are checked against
        Entity Types -> Relations first, for every state, before anything is
        written: the first missing relation raises immediately, so a save
        either writes nothing new or writes every validated entry — never a
        partial set. Newly-detached methods' attributed entries are then best-
        effort removed; that cleanup never blocks the save.
        """
        try:
            previous_parsed: StateMachineDefinition | None = StateMachineDefinition.model_validate(
                previous_definition
            )
        except Exception:
            # Permissive drafts can be persisted in a shape that no longer
            # parses; nothing to diff against in that case.
            previous_parsed = None

        # Diff on the whole pin, not just its method_id: a state that keeps
        # method M but repins it to a different version can carry a different
        # field set, and those fields' source intents have never been checked.
        def _by_pin(definition: StateMachineDefinition) -> dict[str, dict[_MethodPin, MethodRef]]:
            return {
                state.name: {(ref.method_id, ref.version_id): ref for ref in state.method_refs}
                for state in definition.states
            }

        previous_refs_by_state: dict[str, dict[_MethodPin, MethodRef]] = (
            _by_pin(previous_parsed) if previous_parsed is not None else {}
        )
        new_refs_by_state: dict[str, dict[_MethodPin, MethodRef]] = _by_pin(new_definition)

        # The target half of every mapping is `<entity_type>.<field_key>`, and
        # whether a relation exists at all depends on the receiving type. So a
        # workflow changing its entity type invalidates every pin it holds,
        # even the ones that did not move: re-check them all against the new
        # type, and clean the old type's entries up.
        previous_entity_type = previous_parsed.entity_type if previous_parsed is not None else None
        entity_type_changed = (
            previous_parsed is not None and previous_entity_type != new_definition.entity_type
        )

        state_names = set(previous_refs_by_state) | set(new_refs_by_state)
        if entity_type_changed:
            added = {
                state_name: set(new_refs_by_state.get(state_name, {})) for state_name in state_names
            }
            removed = {
                state_name: set(previous_refs_by_state.get(state_name, {}))
                for state_name in state_names
            }
        else:
            added = {
                state_name: set(new_refs_by_state.get(state_name, {}))
                - set(previous_refs_by_state.get(state_name, {}))
                for state_name in state_names
            }
            removed = {
                state_name: set(previous_refs_by_state.get(state_name, {}))
                - set(new_refs_by_state.get(state_name, {}))
                for state_name in state_names
            }
        if not any(added.values()) and not any(removed.values()):
            return

        pending_writes: list[_PendingMethodRelationWrite] = []
        pending_removals: list[_PendingMethodRelationRemoval] = []

        for state_name in set(added) | set(removed):
            for pin in added.get(state_name, set()):
                pending_writes.extend(
                    self._check_method_source_intent_fields(
                        organization_id=organization_id,
                        to_entity_type_name=new_definition.entity_type,
                        state_name=state_name,
                        ref=new_refs_by_state[state_name][pin],
                    )
                )
            for pin in removed.get(state_name, set()):
                pending_removals.extend(
                    self._collect_method_source_intent_removals(
                        organization_id=organization_id,
                        to_entity_type_name=previous_entity_type,
                        ref=previous_refs_by_state[state_name][pin],
                    )
                )

        # Every newly-attached field validated above without raising — apply
        # every removal and write now, none of it conditional on the rest.
        #
        # Removals go first, and must: attribution is keyed on
        # (method_id, field_key) with no version in it, so a method that is
        # both detached and re-attached in one save (repinned to another
        # version, or moved between states) collects a removal and a write for
        # the same key. Writing first would let the removal delete what the
        # write just put back.
        for removal in pending_removals:
            self._apply_method_relation_removal(organization_id=organization_id, removal=removal)
        for write in pending_writes:
            self._apply_method_relation_write(organization_id=organization_id, write=write)

    def _check_method_source_intent_fields(
        self,
        *,
        organization_id: str,
        to_entity_type_name: str,
        state_name: str,
        ref: MethodRef,
    ) -> list[_PendingMethodRelationWrite]:
        """Validate one newly-attached method's source-intent fields.

        Raises `ValidationError` — nothing written yet at this point in the
        overall sync — the moment any field's declared source has no matching
        relation. Returns the writes to apply once every field across the
        whole save has validated clean.

        The workflow's own entity type is resolved lazily, only once a field
        actually carries a source intent: a method with no source-intent
        fields must save exactly as it did before this feature existed, even
        on a workflow whose entity_type isn't in the registry.
        """
        version_id = self._resolve_method_version_id(organization_id, ref)
        fields = self.method_library_db_model_service.list_version_fields(
            organization_id=organization_id, method_version_id=version_id
        )
        pending: list[_PendingMethodRelationWrite] = []
        to_entity_type_id: str | None = None
        for method_field in fields:
            if not method_field.source_entity_type or not method_field.source_field_key:
                continue
            if to_entity_type_id is None:
                if not to_entity_type_name or to_entity_type_name == EntityTypeSentinel.UNASSIGNED:
                    raise ValidationError(
                        f"state '{state_name}' pins method '{ref.method_id}' whose field "
                        f"'{method_field.field_key}' declares a source of "
                        f"'{method_field.source_entity_type}.{method_field.source_field_key}', but "
                        "this workflow has no entity type configured to receive it."
                    )
                to_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                    organization_id, to_entity_type_name
                )
            from_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                organization_id, method_field.source_entity_type
            )
            relation = self.entities_service_manager.db_model_service.get_active_relation_declaration_for_pair(
                organization_id=organization_id,
                from_entity_type_id=from_entity_type_id,
                to_entity_type_id=to_entity_type_id,
            )
            if relation is None:
                raise ValidationError(
                    f"state '{state_name}' pins method '{ref.method_id}' whose field "
                    f"'{method_field.field_key}' declares a source of "
                    f"'{method_field.source_entity_type}.{method_field.source_field_key}', but no "
                    f"relation exists from entity type '{method_field.source_entity_type}' to "
                    f"'{to_entity_type_name}'. Create that relation under Entity Types -> "
                    "Relations before attaching this method."
                )
            pending.append(
                _PendingMethodRelationWrite(
                    from_entity_type_id=from_entity_type_id,
                    to_entity_type_id=to_entity_type_id,
                    source_key=f"{method_field.source_entity_type}.{method_field.source_field_key}",
                    target_key=f"{to_entity_type_name}.{method_field.field_key}",
                    method_id=ref.method_id,
                    field_key=method_field.field_key,
                )
            )
        return pending

    def _collect_method_source_intent_removals(
        self,
        *,
        organization_id: str,
        to_entity_type_name: str | None,
        ref: MethodRef,
    ) -> list[_PendingMethodRelationRemoval]:
        """Best-effort: find one newly-detached method's attributed entries.

        Never raises — detach cleanup does not block a save. A method or
        version that can no longer be resolved just leaves its attribution
        behind rather than aborting the save that is removing it.
        """
        if not to_entity_type_name or to_entity_type_name == EntityTypeSentinel.UNASSIGNED:
            return []
        try:
            version_id = self._resolve_method_version_id(organization_id, ref)
            fields = self.method_library_db_model_service.list_version_fields(
                organization_id=organization_id, method_version_id=version_id
            )
        except Exception:
            logger.debug(
                "method source-intent detach: could not resolve method %s",
                ref.method_id,
                exc_info=True,
            )
            return []
        removals: list[_PendingMethodRelationRemoval] = []
        to_entity_type_id: str | None = None
        for method_field in fields:
            if not method_field.source_entity_type or not method_field.source_field_key:
                continue
            try:
                if to_entity_type_id is None:
                    to_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                        organization_id, to_entity_type_name
                    )
                from_entity_type_id = self.runtime_resolution.resolve_entity_type_id(
                    organization_id, method_field.source_entity_type
                )
                relation = self.entities_service_manager.db_model_service.get_active_relation_declaration_for_pair(
                    organization_id=organization_id,
                    from_entity_type_id=from_entity_type_id,
                    to_entity_type_id=to_entity_type_id,
                )
            except Exception:
                continue
            if relation is None:
                continue
            removals.append(
                _PendingMethodRelationRemoval(
                    from_entity_type_id=from_entity_type_id,
                    to_entity_type_id=to_entity_type_id,
                    method_id=ref.method_id,
                    field_key=method_field.field_key,
                )
            )
        return removals

    def _apply_method_relation_write(
        self, *, organization_id: str, write: _PendingMethodRelationWrite
    ) -> None:
        """Merge one attributed source->target entry into a relation's
        `relation_metadata`. Idempotent: re-attaching the same method+field to
        the same relation never duplicates the entry."""
        db = self.entities_service_manager.db_model_service
        relation = db.get_active_relation_declaration_for_pair(
            organization_id=organization_id,
            from_entity_type_id=write.from_entity_type_id,
            to_entity_type_id=write.to_entity_type_id,
        )
        if relation is None:
            return
        metadata = dict(relation.relation_metadata or {})
        attribution = list(metadata.get(_METHOD_ATTRIBUTION_KEY, []))
        already_present = any(
            isinstance(entry, dict)
            and entry.get("method_id") == write.method_id
            and entry.get("field_key") == write.field_key
            for entry in attribution
        )
        if not already_present:
            metadata[write.source_key] = write.target_key
            attribution.append(
                {
                    "method_id": write.method_id,
                    "field_key": write.field_key,
                    "source_key": write.source_key,
                    "target_key": write.target_key,
                }
            )
            metadata[_METHOD_ATTRIBUTION_KEY] = attribution
            db.update_entity_relation_declaration_metadata(
                organization_id=organization_id,
                relation_def_id=relation.relation_def_id,
                request=EntityRelationDeclarationUpdateRequest(relation_metadata=metadata),
            )

    def _apply_method_relation_removal(
        self, *, organization_id: str, removal: _PendingMethodRelationRemoval
    ) -> None:
        """Remove exactly this method+field's attributed entry from a
        relation's `relation_metadata`. A mapping entry is only dropped once no
        remaining attribution still claims it — legacy manual entries and
        other methods' attributions are never touched."""
        db = self.entities_service_manager.db_model_service
        relation = db.get_active_relation_declaration_for_pair(
            organization_id=organization_id,
            from_entity_type_id=removal.from_entity_type_id,
            to_entity_type_id=removal.to_entity_type_id,
        )
        if relation is None:
            return
        metadata = dict(relation.relation_metadata or {})
        attribution = list(metadata.get(_METHOD_ATTRIBUTION_KEY, []))
        keep: list[Any] = []
        removed_source_keys: set[str] = set()
        for entry in attribution:
            if (
                isinstance(entry, dict)
                and entry.get("method_id") == removal.method_id
                and entry.get("field_key") == removal.field_key
            ):
                source_key = entry.get("source_key")
                if isinstance(source_key, str):
                    removed_source_keys.add(source_key)
                continue
            keep.append(entry)
        if len(keep) == len(attribution):
            return
        still_claimed = {
            entry.get("source_key")
            for entry in keep
            if isinstance(entry, dict) and isinstance(entry.get("source_key"), str)
        }
        for source_key in removed_source_keys - still_claimed:
            metadata.pop(source_key, None)
        metadata[_METHOD_ATTRIBUTION_KEY] = keep
        db.update_entity_relation_declaration_metadata(
            organization_id=organization_id,
            relation_def_id=relation.relation_def_id,
            request=EntityRelationDeclarationUpdateRequest(relation_metadata=metadata),
        )

    @staticmethod
    def _entity_field_from_method_field(
        method_field: MethodVersionField, catalogue: dict[str, tuple[str | None, str]]
    ) -> EntityField:
        """Translate one pinned method field into an entity schema field.

        The field library type is a catalogue code; `engine_type` from that same
        catalogue is what the engine stores it as. A type the engine cannot store
        yet has no engine_type, and pinning it is refused rather than guessed at.
        """
        engine_type, config_kind = catalogue.get(method_field.field_type, (None, "none"))
        if not engine_type:
            raise ValidationError(
                f"field '{method_field.field_key}' has type '{method_field.field_type}', "
                "which the engine cannot store yet, so it cannot be pinned to a workflow"
            )
        settings = dict(method_field.settings or {})
        attributes: dict[str, Any] = {
            "field": method_field.field_key,
            "type": engine_type,
            "required": bool(method_field.required),
            "description": method_field.label,
            "placeholder": method_field.placeholder,
        }
        # Method-block-level inheritance rides through to the entity schema in
        # the shape EntityField already validates: `source` is the
        # context_entity_type/context_field pair, and an inherited field is
        # read-only, which EntityField enforces by forcing editable=False. This
        # is what lets the resolver see, per record, that THIS pinned field is
        # inherited, without anything being written to the entity type's
        # relation metadata.
        if method_field.ownership == FieldOwnership.INHERITED:
            attributes["ownership"] = FieldOwnership.INHERITED.value
            attributes["source"] = {
                "context_entity_type": method_field.source_entity_type,
                "context_field": method_field.source_field_key,
            }
            attributes["editable"] = False
        if config_kind == FieldTypeConfigKind.ENUM_VALUES:
            attributes["enum_values"] = list(settings.get("enum_values") or [])
        elif config_kind == FieldTypeConfigKind.PICKLIST:
            attributes["picklist_id"] = settings.get("picklist_id")
            attributes["enum_values"] = list(settings.get("enum_values") or [])
            # A "Picklist Multi (Dropdown Add)" field carries a second picklist
            # and, optionally, the Field Library fields each of its options
            # reveals. Dropping them here left a pinned field rendering as a
            # flat multi-select of the first picklist alone.
            attributes["picklist_id_2"] = settings.get("picklist_id_2")
            attributes["enum_values_2"] = list(settings.get("enum_values_2") or [])
            attributes["enum_labels_2"] = list(settings.get("enum_labels_2") or [])
            extensions = settings.get("extensions")
            attributes["extensions"] = extensions if isinstance(extensions, dict) else None
            # Every admin-supplied string the wizard renders, by one list, so a
            # new one cannot reach the schema through some paths and not others.
            for copy_name in PICKLIST_MULTI_COPY_FIELDS:
                attributes[copy_name] = settings.get(copy_name)
        elif config_kind == FieldTypeConfigKind.CURRENCY:
            attributes["currency_config"] = settings or None
        elif config_kind == FieldTypeConfigKind.TABLE:
            # The Field Library keeps a table field's settings as
            # `{required, table_config: {...}}`, so the config the renderer
            # wants sits one level in. Taking `settings` wholesale produced
            # `table_config.table_config` and a grid with no columns at all.
            # A plain JSON field (no grid) shares this catalogue code; its settings
            # hold only usage keys like `required`, and turning those into a
            # column-less table_config made every save fail "expects table rows".
            nested_table = settings.get("table_config")
            if isinstance(nested_table, dict) and nested_table:
                attributes["table_config"] = nested_table
            elif settings.get("columns"):
                attributes["table_config"] = settings
            else:
                attributes["table_config"] = None
        elif config_kind == FieldTypeConfigKind.AUTO_NUMBER:
            attributes["auto_number_config"] = settings or None
        # Presentation settings that belong to no single type: a field's colour
        # overrides and its value-level read-only lock. Copied regardless of
        # config_kind, since the branches above are keyed to the type's own
        # config and would otherwise drop these for every type.
        style_config = settings.get("style_config")
        if isinstance(style_config, dict) and style_config:
            attributes["style_config"] = style_config
        if settings.get("read_only"):
            attributes["read_only"] = True
        try:
            return EntityField.model_validate(attributes)
        except PydanticValidationError as exc:
            raise ValidationError(
                f"field '{method_field.field_key}' cannot be pinned to a workflow: {exc}"
            ) from exc

    def _definition_issues(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Compose structural and entity-schema issue sources in their contractual order.

        The entity-schema block sits deliberately between the two structural blocks: the
        emitted order is part of the response contract because the builder UI renders
        issues in sequence. Structural rules belong to `definition_analysis`; field rules
        remain manager-composed until the entity-schema capability is extracted.
        """
        issues: list[ValidationIssue] = []
        issues.extend(
            self.definition_analysis.validate_states(
                definition, known_action_kinds=self._known_action_kinds()
            )
        )
        issues.extend(self.entity_schema._validate_schema_fields(definition))
        issues.extend(self.definition_analysis.validate_transitions(definition))
        return issues

    def _known_action_kinds(self) -> frozenset[str]:
        """Action kinds the executor runtime can run, for publish-time validation.

        Empty when no executor runtime is wired in, which skips the existence
        check rather than declaring every action unknown — a validator must not
        turn its own missing dependency into "this workflow is broken".
        """
        if self.executor_service_manager is None:
            logger.warning(
                "workflow validation running without an executor runtime — "
                "action kinds will not be checked against the registry"
            )
            return frozenset()
        return self.executor_service_manager.registered_action_kinds()

    def _definition_preview_issues(
        self, definition: StateMachineDefinition
    ) -> list[ValidationIssue]:
        """Collect full definition preview issues."""
        try:
            validated = StateMachineDefinition.model_validate(definition.model_dump(by_alias=True))
        except Exception as exc:
            logger.warning(
                f"workflow definition parse failed machine={definition.name} error={exc}"
            )
            return [ValidationIssue(code=ValidationIssueCode.INVALID_DEFINITION, message=str(exc))]
        return self._definition_issues(validated)

    @staticmethod
    def _state_duration(state_entered_at: datetime | None, transitioned_at: datetime) -> int | None:
        """Compute duration spent in the source state."""
        if state_entered_at is None:
            return None
        return max(int((transitioned_at - state_entered_at).total_seconds()), 0)

    def _append_transition_attempt(
        self,
        organization_id: str,
        entity_state: EntityState,
        machine_version: int,
        transition: Transition,
        actor_id: str | None,
        idempotency_key: str | None,
        blocked_reasons: list[str],
        status: str,
        *,
        workflow_id: str | None = None,
        is_system: bool = False,
    ) -> None:
        """Append one transition-attempt audit row to `audit.transition_attempts`."""
        resolved_workflow_id = workflow_id
        if resolved_workflow_id is None and entity_state.machine_name:
            machine = self.workflow_db.get_active_state_machine(
                organization_id=organization_id, machine_name=entity_state.machine_name
            )
            if machine is not None:
                resolved_workflow_id = machine.id
        if not resolved_workflow_id:
            logger.warning(
                f"workflow attempt audit skipped: no workflow_id resolvable for entity={entity_state.entity_id}"
            )
            return
        actor_name, actor_role = self.transition_audit.resolve_actor(actor_id, is_system)
        self.workflow_db.record_transition_attempt(
            organization_id=organization_id,
            entity_id=entity_state.entity_id,
            workflow_id=resolved_workflow_id,
            status=status,
            from_state=entity_state.current_state,
            to_state=transition.to_state,
            trigger=transition.trigger,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            outputs={"blocked_reasons": list(blocked_reasons)} if blocked_reasons else None,
        )

    def _execute_post_tasks(
        self,
        organization_id: str,
        entity_state: EntityState,
        transition: Transition,
        transition_id: str,
    ) -> list[str]:
        """Execute built-in post-transition tasks and append a TASK_EXECUTED row
        to `audit.entity_events` for each successful task."""
        entity_type_id = self.runtime_resolution.resolve_entity_type_id(
            organization_id, entity_state.entity_type
        )
        executed: list[str] = []
        for task in sorted(transition.post_transition_tasks, key=lambda item: item.order):
            try:
                message = f"{task.task} completed"
                logger.info(
                    f"workflow post-task executed task={task.task} entity={entity_state.entity_id}"
                )
                executed.append(task.task)
                if entity_type_id:
                    try:
                        self.entities_service_manager._try_emit_audit_event(
                            actor=build_system_actor(organization_id),
                            organization_id=organization_id,
                            entity_id=entity_state.entity_id,
                            entity_type_id=entity_type_id,
                            event_type=WorkflowEventType.TASK_EXECUTED,
                            payload={
                                "transition_id": transition_id,
                                "task": task.task,
                                "order": task.order,
                                "status": "completed",
                                "message": message,
                                "machine_name": entity_state.machine_name,
                                "machine_version": entity_state.machine_version,
                            },
                        )
                    except Exception as audit_exc:
                        logger.warning(
                            "task executed audit emit failed",
                            extra={
                                "task": task.task,
                                "entity_id": entity_state.entity_id,
                                "error": str(audit_exc),
                            },
                            exc_info=True,
                        )
            except Exception as exc:
                logger.error(
                    f"workflow post-task failed task={task.task} entity={entity_state.entity_id} error={exc}"
                )
                if task.required and task.on_failure == "stop":
                    raise ServiceError(f"post-transition task '{task.task}' failed: {exc}") from exc
        return executed

    def _machine_with_method_schemas(
        self, machine: StateMachineRecord | None
    ) -> StateMachineRecord:
        """Hydrate legacy published rows that predate Method snapshots.

        New publishes persist ``definition.method_schemas`` directly. Exact
        workflow reads also support older published rows by rebuilding the same
        presentation shape from their immutable pin rows. This is deliberately
        not used by bulk list endpoints, avoiding an N+1 expansion there; the
        Pipeline loads its selected workflow through an exact read.
        """
        result = self._machine(machine)
        definition = result.definition
        refs = [
            (state, method_order, ref)
            for state in definition.states
            for method_order, ref in enumerate(state.method_refs)
        ]
        if definition.method_schemas or not refs:
            return result
        if self.method_library_db_model_service is None or not result.id:
            return result

        try:
            pinned_versions = {
                (state_name, method_id): version_id
                for state_name, method_id, version_id in self.workflow_db.list_method_pins(
                    organization_id=result.organization_id,
                    workflow_state_machine_id=result.id,
                )
            }
            # A missing pin means the legacy data is incomplete. Returning the
            # untouched definition keeps the existing single-schema fallback
            # instead of exposing a misleading partial set of Method tabs.
            if any(
                (state.name, ref.method_id) not in pinned_versions
                for state, _method_order, ref in refs
            ):
                return result

            catalogue = self.workflow_db.list_engine_field_types()
            snapshots: list[ResolvedMethodSchema] = []
            for state, method_order, ref in refs:
                pinned_version_id = pinned_versions[(state.name, ref.method_id)]
                identity, version = self._resolve_method_pin(
                    result.organization_id,
                    MethodRef(method_id=ref.method_id, version_id=pinned_version_id),
                )
                snapshot, _method_fields = self._method_schema_snapshot(
                    organization_id=result.organization_id,
                    identity=identity,
                    version=version,
                    state=state,
                    method_order=method_order,
                    catalogue=catalogue,
                )
                snapshots.append(snapshot)
        except (ValidationError, NotFoundError, ServiceError) as exc:
            logger.warning(
                "workflow Method schema hydration failed; using legacy fallback",
                extra={"workflow_id": result.id, "error": str(exc)},
            )
            return result

        return result.model_copy(
            update={"definition": definition.model_copy(update={"method_schemas": snapshots})}
        )

    @staticmethod
    def _machine(machine: StateMachineRecord | None) -> StateMachineRecord:
        """Convert internal record to read response."""
        if machine is None:
            raise NotFoundError("workflow was not found")
        return StateMachineRecord.model_validate(machine.model_dump())
