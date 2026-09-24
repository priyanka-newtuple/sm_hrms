"""Agent definition service for the phase-1 runtime path."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from agent.models.interface import (
    AgentConstraintContract,
    AgentDefinitionContract,
    AgentRuntimeSpec,
    AgentTemplateContract,
    RequestContext,
)
from common.logger import logger
from exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from agent.models.request import AgentDefinitionCreate, AgentDefinitionUpdate

# Allows provider-prefixed model identifiers (e.g. "gemini/gemini-1.5-flash",
# "azure/gpt-4o", "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0").
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,127}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# The single built-in agent that powers Agent Mode: hidden from the default
# definitions listing and granted every tool at runtime. It is otherwise an
# ordinary editable definition, like the other seeded system agents. Keyed by
# this reserved name (the other seeded agents are also is_system but stay
# visible). The only field that stays fixed is is_active — Agent Mode cannot be
# deactivated, because the Agent Mode UI would silently fall back to an
# arbitrary definition.
AGENT_MODE_BUILTIN_NAME = "agent_mode"


READ_ONLY_BUILTIN_TEMPLATE = AgentTemplateContract(
    name="platform_readonly_assistant",
    display_name="Platform Read-Only Assistant",
    description="Answers questions using assembled platform context without mutating records.",
    system_prompt=(
        "You are a read-only Newtuple assistant. Use only the context supplied by the "
        "platform. Do not claim to update, approve, delete, or send anything."
    ),
    allowed_tools=[],
    model_override="gpt-4.1-mini",
    is_system=True,
)


class AgentDefinitionService:
    """Own stored definitions and transform them into runtime specs."""

    def __init__(
        self,
        agent_model_service,
        *,
        builtin_templates: list[AgentTemplateContract] | None = None,
        default_model: str = "gpt-4.1-mini",
        capability_resolver=None,
        llm_service_manager=None,
    ) -> None:
        self.agent_model_service = agent_model_service
        templates_by_name = {READ_ONLY_BUILTIN_TEMPLATE.name: READ_ONLY_BUILTIN_TEMPLATE}
        for template in builtin_templates or []:
            templates_by_name.setdefault(template.name, template)
        self.builtin_templates = tuple(templates_by_name.values())
        self.default_model = default_model
        self.capability_resolver = capability_resolver
        self.llm_service_manager = llm_service_manager

    def list_definitions(
        self, context: RequestContext, active_only: bool = True, include_agent_mode: bool = False
    ) -> list[AgentDefinitionContract]:
        self.ensure_builtin_definitions(context)
        definitions = self.agent_model_service.list_definitions(
            context.organization_id, active_only=active_only
        )
        if not include_agent_mode:
            definitions = [d for d in definitions if d.name != AGENT_MODE_BUILTIN_NAME]
        return definitions

    def get_agent_mode_definition(self, context: RequestContext) -> AgentDefinitionContract:
        """Fetch the built-in Agent Mode assistant (seeding it first if needed)."""
        self.ensure_builtin_definitions(context)
        definition = self.agent_model_service.get_definition_by_name(
            context.organization_id, AGENT_MODE_BUILTIN_NAME, active_only=False
        )
        if definition is None:
            raise NotFoundError("Agent Mode assistant not found")
        return definition

    def get_definition(
        self, context: RequestContext, definition_id: str
    ) -> AgentDefinitionContract:
        self.ensure_builtin_definitions(context)
        definition = self.agent_model_service.get_definition(definition_id, context.organization_id)
        if definition is None:
            raise NotFoundError("agent definition not found")
        return definition

    def create_definition(
        self, context: RequestContext, request: AgentDefinitionCreate
    ) -> AgentDefinitionContract:
        """Create a new org-scoped agent definition.

        Validates that the name is unique within the organization and that the
        model name and tool references are well-formed before persisting.

        Args:
            context: Authenticated request context (provides the tenant).
            request: Validated creation payload.

        Returns:
            The persisted AgentDefinitionContract.

        Raises:
            ValidationError: On duplicate name, invalid model, or invalid tools.
        """
        existing = self.agent_model_service.get_definition_by_name(
            context.organization_id, request.name, active_only=False
        )
        if existing is not None:
            raise ValidationError(f"Agent with name '{request.name}' already exists")
        self._validate_model(request.model_override or self.default_model)
        allowed_tools = self._normalize_and_validate_tools(context, request.allowed_tools)
        payload = request.model_dump()
        payload["allowed_tools"] = allowed_tools
        payload["constraints"] = request.constraints.model_dump()
        payload["suggestions"] = [item.model_dump() for item in request.suggestions]
        payload["is_system"] = False
        return self.agent_model_service.create_definition(context.organization_id, payload)

    def update_definition(
        self,
        context: RequestContext,
        definition_id: str,
        request: AgentDefinitionUpdate,
    ) -> AgentDefinitionContract:
        """Apply a partial update to an existing definition.

        Validates any supplied model name and tool references. Identity fields
        (name, is_system) are not part of the update payload and stay fixed, so
        built-in definitions can be customized without losing their identity.

        Args:
            context: Authenticated request context (provides the tenant).
            definition_id: Identifier of the definition to update.
            request: Partial update payload (unset fields are ignored).

        Returns:
            The updated AgentDefinitionContract.

        Raises:
            NotFoundError: If the definition does not exist for this tenant.
            ValidationError: On invalid model or tool references, or when
                deactivating the Agent Mode assistant.
        """
        # Built-in definitions are per-org seed rows; admins may customize them.
        # (get_definition also seeds the built-in if it has not been materialized
        # yet, so there is always a row to update.) Identity fields (name,
        # is_system) are not part of AgentDefinitionUpdate and stay fixed.
        existing = self.get_definition(context, definition_id)
        # Agent Mode is editable like any other seeded agent, with one exception:
        # it must stay active. A disabled definition makes build_runtime_spec
        # raise for every Agent Mode run, while the chat UI silently falls back
        # to an arbitrary definition. Field-level guard, mirroring the roles
        # module's system-role guard.
        if request.is_active is False and existing.name == AGENT_MODE_BUILTIN_NAME:
            raise ValidationError("The Agent Mode assistant cannot be deactivated")
        if request.model_override is not None:
            self._validate_model(request.model_override)
        updates = request.model_dump(exclude_unset=True)
        if request.allowed_tools is not None:
            updates["allowed_tools"] = self._normalize_and_validate_tools(
                context, request.allowed_tools
            )
        if request.constraints is not None:
            updates["constraints"] = request.constraints.model_dump()
        if request.suggestions is not None:
            updates["suggestions"] = [item.model_dump() for item in request.suggestions]
        updated = self.agent_model_service.update_definition(
            definition_id, context.organization_id, updates
        )
        if updated is None:
            raise NotFoundError("agent definition not found")
        return updated

    def disable_definition(
        self, context: RequestContext, definition_id: str
    ) -> AgentDefinitionContract:
        existing = self.get_definition(context, definition_id)
        # Mirrors the guard in update_definition so this path can never become a
        # way around it.
        if existing.name == AGENT_MODE_BUILTIN_NAME:
            raise ValidationError("The Agent Mode assistant cannot be deactivated")
        disabled = self.agent_model_service.update_definition(
            definition_id, context.organization_id, {"is_active": False}
        )
        if disabled is None:
            raise NotFoundError("agent definition not found")
        return disabled

    def build_runtime_spec(self, context: RequestContext, definition_id: str) -> AgentRuntimeSpec:
        """Derive an SDK-ready runtime spec from a stored definition.

        The runtime spec is the platform-owned, execution-ready view of a
        definition: resolved model, instructions, and validated tool ids. It is
        built without executing the agent.

        Args:
            context: Authenticated request context (provides the tenant).
            definition_id: Identifier of the definition to resolve.

        Returns:
            An AgentRuntimeSpec ready for the runtime adapter.

        Raises:
            ValidationError: If the definition is disabled or has invalid
                model/tool references.
        """
        definition = self.get_definition(context, definition_id)
        if not definition.is_active:
            raise ValidationError("agent definition is disabled")
        constraints = AgentConstraintContract.model_validate(definition.constraints or {})
        model = definition.model_override or self.default_model
        self._validate_model(model)
        # The Agent Mode assistant gets EVERY tool at runtime (see runtime
        # all_tools expansion), bypassing the per-definition allowed_tools list
        # and the per-org enablement gate. This is a deliberate product-level
        # capability grant, not an oversight: Agent Mode is the open-ended
        # "ask the platform anything" surface, and new tools must reach it
        # without per-org curation. Because the grant short-circuits
        # allowed_tools, the editor renders that agent's tool section as locked
        # rather than as a field whose saved value would be ignored. Making the
        # list manually assignable is tracked as a follow-up: it needs runtime
        # validation to filter-and-log instead of raise (see
        # _normalize_and_validate_tools below), plus a decision on the mutating
        # capabilities that default to disabled per org.
        all_tools = definition.name == AGENT_MODE_BUILTIN_NAME
        if all_tools:
            tool_ids: list[str] = []
        else:
            tool_ids = list(definition.allowed_tools or [])
            tool_ids = self._normalize_and_validate_tools(context, tool_ids) or []
        return AgentRuntimeSpec(
            definition_id=definition.definition_id,
            key=definition.name,
            name=definition.display_name,
            description=definition.description,
            instructions=self._with_todays_date(definition.system_prompt),
            model=model,
            max_turns=constraints.max_iterations,
            tool_ids=tool_ids,
            all_tools=all_tools,
            handoff_definition_ids=[],
            is_background_enabled=False,
            temperature=self._resolve_temperature(definition.name, model, definition.constraints),
        )

    @staticmethod
    def _first_of_previous_month(today: date) -> date:
        """First day of the calendar month before `today`."""
        first_of_this_month = today.replace(day=1)
        return (first_of_this_month - timedelta(days=1)).replace(day=1)

    @staticmethod
    def _with_todays_date(system_prompt: str) -> str:
        """Tell the agent what today is, so it can work out a date range.

        Metrics accept a fixed set of window presets plus `date_from`/`date_to`.
        Anything the presets do not cover ("the last 5 days", "since last
        month") has to become real dates, and the model cannot work those out
        without knowing the current date. Dates are UTC, matching the metrics.
        """
        today = datetime.now(UTC).date()
        return (
            f"{system_prompt}\n\n"
            f"Today's date is {today.isoformat()} (UTC). Use it whenever a "
            "request refers to a relative period. Metric time windows accept "
            "time_range of all, today, this_week, this_month, last_month, or "
            "last_<N>d for any N up to 365 - so 'the last 5 days' is last_5d "
            "and 'last month' is last_month, never last_30d, which starts "
            "mid-month and misses the rest of it. For any other period work "
            "out date_from and date_to as YYYY-MM-DD from today's date. "
            f"The previous calendar month began on "
            f"{AgentDefinitionService._first_of_previous_month(today).isoformat()}. "
            "Never answer with a window that differs from the one asked for; "
            "if you cannot express it, say so."
        )

    def _resolve_temperature(
        self, definition_name: str, model: str, constraints: dict[str, Any]
    ) -> float | None:
        """Return a validated, model-supported temperature, or None.

        Only ever non-None for a definition that explicitly configures
        `constraints.temperature` (today, only `bulk_import_extractor`'s seeded
        template — nothing sets this for a definition created via the UI, so
        every other agent, including brand-new ones, is unaffected and simply
        gets `None`, the model's own default). Three independent reasons this
        falls back to None, each logged distinctly so the cause is diagnosable
        from logs alone: malformed value, out-of-range value, or (new) the
        resolved model itself doesn't accept a temperature override at all —
        this last check protects against an org admin later switching this
        definition's `model_override` to a model that doesn't support it.
        A bad value here must never break every run of an otherwise-working
        agent; it just falls back to the model's own default temperature.
        """
        raw_temperature = constraints.get("temperature")
        if raw_temperature is None:
            return None
        try:
            temperature = float(raw_temperature)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "agent definition constraints.temperature is malformed, ignoring: %s",
                exc,
                extra={"definition_name": definition_name, "raw_temperature": raw_temperature},
            )
            return None
        if not (0.0 <= temperature <= 2.0):
            logger.warning(
                "agent definition constraints.temperature out of range, ignoring",
                extra={"definition_name": definition_name, "temperature": temperature},
            )
            return None
        if self.llm_service_manager is not None and not self.llm_service_manager.supports_param(
            model, "temperature"
        ):
            logger.warning(
                "agent definition constraints.temperature is set but model does not support it, ignoring",
                extra={
                    "definition_name": definition_name,
                    "model": model,
                    "temperature": temperature,
                },
            )
            return None
        return temperature

    def ensure_builtin_definitions(self, context: RequestContext) -> None:
        """Idempotently seed the built-in definitions for an organization.

        For each registered template, a system definition is created for the
        organization if one does not already exist (matched by name). The id is
        derived deterministically from the org and template name, so repeated
        calls never create duplicates.

        Seeding is create-if-missing only. An existing row is never touched, so
        an admin's customization always survives — including for the Agent Mode
        assistant, which used to be force-resynced from the template on every
        call and so could not be edited at all. The trade-off is that template
        changes do not reach organizations that have already been seeded; that
        requires a one-off data migration, as
        ``2026_08_05_0001_resync_stale_bulk_import_extractor`` did.

        Args:
            context: Authenticated request context (provides the tenant).
        """
        for template in self.builtin_templates:
            existing = self.agent_model_service.get_definition_by_name(
                context.organization_id, template.name, active_only=False
            )
            if existing:
                continue
            definition_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"agent-definition:{context.organization_id}:{template.name}",
                )
            )
            now = datetime.now(UTC)
            self.agent_model_service.create_definition(
                context.organization_id,
                {
                    "definition_id": definition_id,
                    "name": template.name,
                    "display_name": template.display_name,
                    "description": template.description,
                    "system_prompt": template.system_prompt,
                    "allowed_tools": self._normalize_template_tools(context, template),
                    "constraints": template.constraints.model_dump(),
                    "suggestions": [item.model_dump() for item in template.suggestions],
                    "model_override": template.model_override,
                    "is_active": template.is_active,
                    "is_system": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    @staticmethod
    def _validate_model(model: str) -> None:
        if not MODEL_NAME_RE.match(model):
            raise ValidationError("Invalid agent model name")

    @staticmethod
    def _validate_tool_ids(tool_ids: list[str]) -> None:
        invalid = [tool_id for tool_id in tool_ids if not UUID_RE.match(str(tool_id))]
        if invalid:
            raise ValidationError("Agent tool references must be stable UUIDs")

    def _normalize_and_validate_tools(
        self, context: RequestContext, tool_refs: list[str] | None
    ) -> list[str] | None:
        if self.capability_resolver is not None:
            normalized = self.capability_resolver.normalize_tool_refs(context, tool_refs)
            self.capability_resolver.validate_enabled_capability_ids(context, normalized or [])
            return normalized
        self._validate_tool_ids(tool_refs or [])
        return tool_refs

    def _normalize_template_tools(
        self, context: RequestContext, template: AgentTemplateContract
    ) -> list[str] | None:
        if template.allowed_tools is None:
            return None
        if self.capability_resolver is None:
            return template.allowed_tools
        normalized: list[str] = []
        for tool_ref in template.allowed_tools:
            try:
                normalized.extend(self._normalize_and_validate_tools(context, [tool_ref]) or [])
            except ValidationError:
                continue
        return normalized
