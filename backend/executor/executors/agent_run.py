"""Executor: run a configured AI agent on state entry and map its output to entity fields.

Generic and domain-agnostic. It resolves the entity's inputs (scalar fields, plus
optionally its attached files' text and linked-entity data), calls any configured
agent through the existing agent runtime, parses the agent's JSON reply, and returns
the mapped values as output fields for the workflow to write back. The binding routes
the outcome to the next transition — either a fixed ``success`` or, when ``outcome_field``
is configured, the agent's own decision value (e.g. ``advance``/``reject``).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from agent.models.request import AgentRunRequest
from common.logger import logger
from entities.db_models import EntityRecordModel, EntityRelationModel
from executor.executors.base import fail, get_field
from executor.models.interface import (
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
    ExecutorValue,
    ValueKind,
)
from filehandler.db_models import FileModel

if TYPE_CHECKING:
    from agent.manager import AgentServiceManager
    from filehandler.manager import FilehandlerServiceManager

# Keep the executor aligned with the agent runtime request contract rather than
# duplicating its current max_length value here.
_DEFAULT_AGENT_INPUT_MAX_CHARS = 10_000
# Per-file cap so one large text file cannot crowd out the rest of the prompt.
_MAX_FILE_TEXT_CHARS = 2000
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _agent_input_max_chars() -> int:
    """Return the max request size enforced by AgentRunRequest.input."""
    field = AgentRunRequest.model_fields["input"]
    max_length = getattr(field, "max_length", None)
    if isinstance(max_length, int) and max_length > 0:
        return max_length
    for metadata in getattr(field, "metadata", ()):
        candidate = getattr(metadata, "max_length", None)
        if isinstance(candidate, int) and candidate > 0:
            return candidate
    return _DEFAULT_AGENT_INPUT_MAX_CHARS


def _is_text_content_type(content_type: str) -> bool:
    """Return True when a file's bytes can be inlined as UTF-8 text in the prompt."""
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized.startswith("text/"):
        return True
    return normalized in {"application/json", "application/xml", "application/csv"}


class AgentExecutor(BaseExecutor):
    """Run any configured AI agent generically and route its outcome to a trigger."""

    def __init__(
        self,
        mail_service: object | None = None,
        database_service_manager: object | None = None,
        config: object | None = None,
        notifications_service: object | None = None,
        filehandler_service: FilehandlerServiceManager | None = None,
        agent_service: AgentServiceManager | None = None,
    ) -> None:
        """Store dependencies.

        The executor manager instantiates all executors through a shared constructor
        shape, so some parameters are accepted here for parity even though this
        executor only actively uses ``filehandler_service`` and ``agent_service``.

        Runtime entity/file/relation reads depend on the per-execution ``db``
        session passed into ``execute()``, not on ``database_service_manager``.
        ``agent_service`` is late-bound after construction.
        """
        _ = mail_service, notifications_service
        self._database_service_manager = database_service_manager
        self._config = config
        self._filehandler = filehandler_service
        # Bound in main.py after the agent service manager is constructed.
        self.agent_service = agent_service

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="agent_run",
            description=(
                "Run a configured AI agent on state entry and map its structured "
                "output back to entity fields."
            ),
            supported_outcomes=["success", "failed"],
            # The agent's decision (via outcome_field) can route the workflow, so the
            # returned outcome is not restricted to the declared list.
            dynamic_outcomes=True,
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        """Resolve inputs, run the agent, parse its JSON reply, and return mapped fields."""
        org_id = ""
        agent_id = ""
        try:
            validation_error, org_id, config, agent_id, output_mapping = self._validate_request(
                input_payload.fields
            )
            if validation_error is not None:
                return validation_error

            entity_id = input_payload.entity_id
            entity_data = self._load_entity_data(db, org_id, entity_id)
            prompt = self._build_prompt(
                config=config,
                entity_data=entity_data,
                input_payload=input_payload,
                org_id=org_id,
                entity_id=entity_id,
                output_mapping=output_mapping,
                db=db,
            )

            request = AgentRunRequest(definition_id=agent_id, input=prompt)
            response = self.agent_service.run_agent_for_actor(
                self._build_actor(org_id), request
            )
            return self._process_agent_response(
                response=response,
                config=config,
                agent_id=agent_id,
                output_mapping=output_mapping,
            )
        except Exception as exc:
            logger.exception(
                "agent_run executor failed",
                extra={
                    "executor": "agent_run",
                    "entity_id": input_payload.entity_id,
                    "entity_type": input_payload.entity_type,
                    "current_state": input_payload.current_state,
                    "organization_id": org_id or None,
                    "agent_id": agent_id or None,
                    "exc_type": type(exc).__name__,
                },
            )
            return fail("agent run failed")

    # ── Config ────────────────────────────────────────────────────────────────

    def _parse_config(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Parse the resolved action config from the raw config field."""
        raw = get_field(fields, "_raw_config") or "{}"
        try:
            config = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("agent_run: failed to parse config_json: %s", exc)
            return {}
        return config if isinstance(config, dict) else {}

    def _validate_request(
        self, fields: dict[str, Any]
    ) -> tuple[ExecutorResponse | None, str, dict[str, Any], str, dict[str, Any]]:
        """Validate resolved fields and return the normalized executor config."""
        org_id = get_field(fields, "org_id") or ""
        if not org_id:
            return fail("missing required field: org_id"), "", {}, "", {}
        if self.agent_service is None:
            return fail("agent runtime is not available"), org_id, {}, "", {}

        config = self._parse_config(fields)
        agent_id = str(config.get("agent_id") or "").strip()
        if not agent_id:
            return fail("missing required config: agent_id"), org_id, config, "", {}
        output_mapping = dict(config.get("output_mapping") or {})
        if not output_mapping:
            return (
                fail("missing required config: output_mapping"),
                org_id,
                config,
                agent_id,
                {},
            )
        return None, org_id, config, agent_id, output_mapping

    @staticmethod
    def _build_actor(org_id: str) -> dict[str, object]:
        """Return the system actor used for background workflow agent runs."""
        return {"organization_id": org_id, "user_id": None, "roles": []}

    def _process_agent_response(
        self,
        *,
        response: Any,
        config: dict[str, Any],
        agent_id: str,
        output_mapping: dict[str, Any],
    ) -> ExecutorResponse:
        """Validate the agent response, map its JSON payload, and resolve outcome."""
        if response.status == "waiting_for_approval":
            return fail("agent paused for human approval; workflow agents must run autonomously")
        if response.status != "completed" or not response.output:
            return fail(response.error or f"agent run did not complete (status={response.status})")

        parsed = self._parse_json_output(response.output)
        if parsed is None:
            return fail("agent output was not valid JSON")

        outcome = self._resolve_outcome(config, parsed)
        if outcome is None:
            outcome_field = str(config.get("outcome_field") or "").strip()
            return fail(f"agent output missing outcome field '{outcome_field}'")

        mapped = self._map_output(parsed, output_mapping)
        return ExecutorResponse(
            success=True,
            message="Agent run completed",
            data=ExecutorData(
                outcome=outcome,
                fields=mapped,
                meta={"agent_id": agent_id, "run_id": response.run_id},
            ),
        )

    # ── Input resolution ────────────────────────────────────────────────────────

    def _load_entity_data(self, db: Any, org_id: str, entity_id: str) -> dict[str, Any]:
        """Return the entity's data dict, or empty when unavailable."""
        if db is None:
            return {}
        entity = (
            db.query(EntityRecordModel)
            .filter_by(entity_id=entity_id, organization_id=org_id)
            .first()
        )
        return dict(entity.data or {}) if entity is not None else {}

    def _build_prompt(
        self,
        *,
        config: dict[str, Any],
        entity_data: dict[str, Any],
        input_payload: ExecutorInput,
        org_id: str,
        entity_id: str,
        output_mapping: dict[str, Any],
        db: Any,
    ) -> str:
        """Assemble the agent prompt from resolved inputs plus a strict JSON instruction."""
        parts = [
            self._build_prompt_header(input_payload),
            self._build_instruction_section(config),
            self._build_scalar_section(entity_data, config.get("input_fields")),
            self._build_files_section(config, org_id, entity_id, db),
            self._build_relations_section(config, org_id, entity_id, db),
            self._build_json_instruction(config, output_mapping),
        ]
        prompt = "\n".join(part for part in parts if part)
        max_prompt_chars = _agent_input_max_chars()
        if len(prompt) > max_prompt_chars:
            prompt = prompt[:max_prompt_chars]
        return prompt

    @staticmethod
    def _build_prompt_header(input_payload: ExecutorInput) -> str:
        """Return the fixed prompt header describing the current workflow context."""
        return (
            f"You are an automated workflow step acting on a '{input_payload.entity_type}' "
            f"record currently in state '{input_payload.current_state}'."
        )

    @staticmethod
    def _build_instruction_section(config: dict[str, Any]) -> str:
        """Return optional free-form prompt instructions from the action config."""
        return str(config.get("prompt_instructions") or "").strip()

    def _build_scalar_section(self, entity_data: dict[str, Any], input_fields: Any) -> str:
        """Render selected scalar entity fields for prompt inclusion."""
        scalars = self._select_scalar_fields(entity_data, input_fields)
        if not scalars:
            return ""
        lines = ["Record fields:"]
        lines.extend(f"- {key}: {value}" for key, value in scalars.items())
        return "\n".join(lines)

    def _build_files_section(
        self, config: dict[str, Any], org_id: str, entity_id: str, db: Any
    ) -> str:
        """Render the optional attached-files prompt section."""
        if not config.get("include_files"):
            return ""
        return self._render_files(org_id, entity_id, db)

    def _build_relations_section(
        self, config: dict[str, Any], org_id: str, entity_id: str, db: Any
    ) -> str:
        """Render the optional linked-records prompt section."""
        include_relations = [str(r) for r in (config.get("include_relations") or [])]
        if not include_relations or db is None:
            return ""
        return self._render_relations(db, org_id, entity_id, include_relations)

    @staticmethod
    def _build_json_instruction(
        config: dict[str, Any], output_mapping: dict[str, Any]
    ) -> str:
        """Render the strict JSON-response instructions, including optional outcome constraints."""
        key_names = list(output_mapping.keys())
        outcome_field = str(config.get("outcome_field") or "").strip()
        if outcome_field and outcome_field not in key_names:
            key_names.append(outcome_field)
        keys = ", ".join(f'"{key}"' for key in key_names)
        lines = [
            "Respond with ONLY a valid JSON object — no markdown, no code fences, no prose — "
            f"containing exactly these keys: {keys}."
        ]
        if outcome_field:
            allowed = [str(value) for value in (config.get("outcome_triggers") or {}).keys()]
            if allowed:
                lines.append(
                    f'The "{outcome_field}" value must be exactly one of: {", ".join(allowed)}.'
                )
        return "\n".join(lines)

    @staticmethod
    def _select_scalar_fields(
        entity_data: dict[str, Any], input_fields: Any
    ) -> dict[str, Any]:
        """Pick scalar values from entity data (named fields, or all when unspecified)."""
        if input_fields:
            names = [str(name) for name in input_fields]
        else:
            names = list(entity_data.keys())
        selected: dict[str, Any] = {}
        for name in names:
            if name not in entity_data:
                continue
            value = entity_data[name]
            if value is None or isinstance(value, (str, int, float, bool)):
                selected[name] = value
        return selected

    def _render_files(self, org_id: str, entity_id: str, db: Any) -> str:
        """Render attached files: inline text for text files, list binaries as references."""
        if db is None:
            return ""
        try:
            files = (
                db.query(FileModel)
                .filter_by(organization_id=org_id, owner_entity_id=entity_id)
                .all()
            )
        except Exception as exc:
            logger.warning("agent_run: file lookup failed entity=%s: %s", entity_id, exc)
            return ""
        if not files:
            return ""

        lines = ["Attached files:"]
        for file_row in files:
            if _is_text_content_type(file_row.content_type):
                text = self._read_text_file(org_id, str(file_row.file_id))
                if text is not None:
                    lines.append(f"- {file_row.filename} ({file_row.content_type}):\n{text}")
                    continue
            # Binary docs (PDF, docx, images): text extraction is a follow-up — list as reference.
            lines.append(
                f"- {file_row.filename} ({file_row.content_type}) — content not inlined"
            )
        return "\n".join(lines)

    def _read_text_file(self, org_id: str, file_id: str) -> str | None:
        """Fetch a text file's content via the filehandler, truncated. None on failure."""
        if self._filehandler is None:
            return None
        try:
            raw = self._filehandler.get_file_bytes(org_id, file_id)
        except Exception as exc:
            logger.warning("agent_run: get_file_bytes failed file=%s: %s", file_id, exc)
            return None
        if not raw:
            return None
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            return None
        return text[:_MAX_FILE_TEXT_CHARS]

    def _render_relations(
        self, db: Any, org_id: str, entity_id: str, relation_types: list[str]
    ) -> str:
        """Render linked entities' data for the requested relation types."""
        try:
            edges = (
                db.query(EntityRelationModel)
                .filter(
                    EntityRelationModel.organization_id == org_id,
                    EntityRelationModel.from_entity_id == entity_id,
                    EntityRelationModel.relation_type.in_(relation_types),
                )
                .all()
            )
        except Exception as exc:
            logger.warning("agent_run: relation lookup failed entity=%s: %s", entity_id, exc)
            return ""
        if not edges:
            return ""

        linked_entity_ids = [edge.to_entity_id for edge in edges]
        linked_records_by_id: dict[str, EntityRecordModel] = {}
        try:
            linked_records = (
                db.query(EntityRecordModel)
                .filter(
                    EntityRecordModel.organization_id == org_id,
                    EntityRecordModel.entity_id.in_(linked_entity_ids),
                )
                .all()
            )
            linked_records_by_id = {
                str(record.entity_id): record for record in linked_records if record is not None
            }
        except Exception as exc:
            logger.warning("agent_run: linked entity lookup failed entity=%s: %s", entity_id, exc)
            return ""

        lines = ["Linked records:"]
        for edge in edges:
            linked = linked_records_by_id.get(str(edge.to_entity_id))
            if linked is None:
                continue
            data = dict(linked.data or {})
            summary = ", ".join(
                f"{key}: {value}"
                for key, value in data.items()
                if value is None or isinstance(value, (str, int, float, bool))
            )
            lines.append(f"- [{edge.relation_type}] {summary}")
        return "\n".join(lines) if len(lines) > 1 else ""

    # ── Output parsing ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_output(output: str) -> dict[str, Any] | None:
        """Parse the agent's reply as a JSON object, tolerating fences/preamble."""
        text = output.strip()
        # Strip a leading ```json / ``` fence if present.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            match = _JSON_BLOCK_RE.search(output)
            if match is None:
                return None
            try:
                parsed = json.loads(match.group(0))
            except (json.JSONDecodeError, TypeError):
                return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _resolve_outcome(config: dict[str, Any], parsed: dict[str, Any]) -> str | None:
        """Return the routing outcome: the decision value when outcome_field is set, else 'success'.

        Returns None when a configured outcome_field is missing/empty in the reply.
        """
        outcome_field = str(config.get("outcome_field") or "").strip()
        if not outcome_field:
            return "success"
        decision = parsed.get(outcome_field)
        if decision is None:
            return None
        outcome = str(decision).strip()
        return outcome or None

    @staticmethod
    def _map_output(
        parsed: dict[str, Any], output_mapping: dict[str, Any]
    ) -> dict[str, ExecutorValue]:
        """Map agent output keys onto entity field names as typed executor values."""
        mapped: dict[str, ExecutorValue] = {}
        for agent_key, entity_field in output_mapping.items():
            if agent_key not in parsed:
                continue
            mapped[str(entity_field)] = _to_executor_value(parsed[agent_key])
        return mapped


def _to_executor_value(value: Any) -> ExecutorValue:
    """Wrap a parsed JSON value in the typed ExecutorValue matching its Python type."""
    if value is None:
        return ExecutorValue(kind=ValueKind.NULL, value=None)
    if isinstance(value, bool):
        return ExecutorValue(kind=ValueKind.BOOLEAN, value=value)
    if isinstance(value, (int, float)):
        return ExecutorValue(kind=ValueKind.NUMBER, value=value)
    if isinstance(value, dict):
        return ExecutorValue(kind=ValueKind.JSON, value=value)
    if isinstance(value, list):
        return ExecutorValue(kind=ValueKind.LIST, value=value)
    return ExecutorValue(kind=ValueKind.TEXT, value=str(value))
