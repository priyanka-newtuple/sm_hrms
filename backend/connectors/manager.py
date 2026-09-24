"""Connectors manager: CRUD, authorization, and the outbound HTTP call logic (run_connector_call)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx

from common.auth import actor_str
from common.enums import ModuleStatus
from common.logger import logger
from common.outbound_http import PinTarget, SsrfError, resolve_safe_target
from exceptions import AuthorizationError, ConflictError, NotFoundError, ServiceError, ValidationError

from connectors.models.interface import (
    BASIC_SCHEME,
    BEARER_SCHEME,
    CONTENT_TYPE_TEXT,
    CURLY_PLACEHOLDER,
    DEFAULT_API_KEY_HEADER,
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_READ_TIMEOUT_SECONDS,
    ENTITY_PLACEHOLDER,
    HEADER_AUTHORIZATION,
    HEADER_CONTENT_TYPE,
    HEADER_HOST,
    HEADER_IDEMPOTENCY_KEY,
    HTTP_SUCCESS_MAX,
    HTTP_SUCCESS_MIN,
    RESPONSE_SUMMARY_LIMIT,
    SOLE_PLACEHOLDER,
    ApiKeyLocation,
    AuthConfigKey,
    ConnectorAuthType,
    ConnectorContract,
    ContentType,
    HttpMethod,
    SecretKey,
    SuccessRuleKey,
)
from connectors.models.request import ConnectorCreateRequest, ConnectorInlineTestRequest, ConnectorTestRequest, ConnectorUpdateRequest
from connectors.models.response import (
    ConnectorListResponse,
    ConnectorReadResponse,
    ConnectorsStatusResponse,
    ConnectorTestResponse,
)

TABLE_MERGE_MATCH_KEY = "__match__"
TABLE_MERGE_INSTRUCTION_KEY = "__table_merge__"
# `*.column` targets every table field on the record; expanded at write-back.
TABLE_WILDCARD_FIELD = "*"
# Merge-instruction keys.
TABLE_MERGE_MATCH_INSTRUCTION_KEY = "match"
TABLE_MERGE_ROWS_KEY = "rows"
# Carried when the response says nothing about which rows exist.
TABLE_MERGE_LOOKUPS_KEY = "lookups"
TABLE_MERGE_RESPONSE_KEY = "response"
FILTER_PREDICATE_PREFIX = "?"
# Placeholder in a column path that is substituted, per built row, with that
# row's match-column value — turning the column into a per-row lookup/join.
# e.g. lineage path `results[?fcc_line=$match].lineage.source_rows.0.calculation`
# resolves each row's lineage from a *different* array keyed on the row's line.
LOOKUP_MATCH_TOKEN = "$match"

if TYPE_CHECKING:
    from connectors.db_models import ConnectorsModelService
    from database.manager import DatabaseServiceManager


class ConnectorsServiceManager:
    """Orchestrates connector CRUD, authorization, and connectivity testing."""

    def __init__(
        self,
        connectors_db_model_service: ConnectorsModelService,
        database_service_manager: DatabaseServiceManager | None,
        config: object | None,
        *dependencies: object,
    ) -> None:
        self.db_model_service = connectors_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "connectors"
        self._started = False
        # Exposed so dependents (e.g. tools) access connector behaviour via the injected manager,
        # not by importing from the connectors module directly.
        self.curly_placeholder = CURLY_PLACEHOLDER
        self.entity_placeholder = ENTITY_PLACEHOLDER

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> ConnectorsStatusResponse:
        """Return module health information."""
        return ConnectorsStatusResponse(
            module=self.module_name, status=ModuleStatus.READY.value, started=self._started
        )

    def list_connectors_for_actor(
        self, actor: dict[str, object], organization_id: str, entity_type: str | None = None
    ) -> ConnectorListResponse:
        """List active connectors for the actor's organization, optionally by entity type."""
        self._authorize(actor, organization_id)
        rows = self.db_model_service.list_connectors(organization_id, entity_type)
        items = [self._to_read_response(row) for row in rows]
        return ConnectorListResponse(items=items, total=len(items))

    def get_connector_for_actor(
        self, actor: dict[str, object], organization_id: str, connector_id: str
    ) -> ConnectorReadResponse:
        """Return one connector or raise NotFoundError."""
        self._authorize(actor, organization_id)
        row = self.db_model_service.get_connector(connector_id, organization_id)
        if row is None:
            logger.error(f"connector not found id={connector_id} org={organization_id}")
            raise NotFoundError("Connector not found")
        return self._to_read_response(row)

    def create_connector_for_actor(
        self, actor: dict[str, object], organization_id: str, request: ConnectorCreateRequest
    ) -> ConnectorReadResponse:
        """Create a connector, rejecting a duplicate active name in the same organization."""
        self._authorize(actor, organization_id)
        try:
            if self.db_model_service.name_exists(organization_id, request.name):
                raise ConflictError(f"A connector named '{request.name}' already exists")
            row = self.db_model_service.create_connector(
                organization_id=organization_id, request=request
            )
            return self._to_read_response(row)
        except (ValidationError, AuthorizationError, ConflictError, NotFoundError) as exc:
            logger.error(f"create connector rejected org={organization_id} name={request.name}: {exc}")
            raise
        except Exception as exc:
            logger.exception(f"create connector failed org={organization_id} name={request.name}")
            raise ServiceError(f"Unable to create connector: {exc}") from exc

    def update_connector_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        connector_id: str,
        request: ConnectorUpdateRequest,
    ) -> ConnectorReadResponse:
        """Update a connector or raise NotFoundError if it does not exist."""
        self._authorize(actor, organization_id)
        try:
            row = self.db_model_service.update_connector(
                connector_id=connector_id, organization_id=organization_id, request=request
            )
            if row is None:
                raise NotFoundError("Connector not found")
            return self._to_read_response(row)
        except (ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.error(f"update connector rejected id={connector_id} org={organization_id}: {exc}")
            raise
        except Exception as exc:
            logger.exception(f"update connector failed id={connector_id} org={organization_id}")
            raise ServiceError(f"Unable to update connector: {exc}") from exc

    def delete_connector_for_actor(
        self, actor: dict[str, object], organization_id: str, connector_id: str
    ) -> bool:
        """Soft-delete a connector. Returns True if a connector was archived."""
        self._authorize(actor, organization_id)
        return self.db_model_service.delete_connector(connector_id, organization_id)

    def test_connector_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        connector_id: str,
        request: ConnectorTestRequest,
    ) -> ConnectorTestResponse:
        """Fire the connector against sample field values and record the validation result."""
        self._authorize(actor, organization_id)
        contract = self.db_model_service.get_connector(connector_id, organization_id)
        if contract is None:
            logger.error(f"test connector: not found id={connector_id} org={organization_id}")
            raise NotFoundError("Connector not found")
        secrets = self.db_model_service.get_decrypted_secrets(connector_id, organization_id)
        field_values = {key: str(value) for key, value in request.sample_fields.items()}
        result = run_connector_call(
            contract=contract,
            secrets=secrets,
            field_values=field_values,
            strict_placeholders=False,
        )
        self.db_model_service.record_validation(
            connector_id=connector_id, organization_id=organization_id,
            ok=result.ok, error=result.error,
        )
        return self._test_response(result)

    def test_connector_inline_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        request: ConnectorInlineTestRequest,
    ) -> ConnectorTestResponse:
        """Test a connector definition immediately without saving it first."""
        self._authorize(actor, organization_id)
        c = request.connector
        contract = ConnectorContract(
            id="inline-test",
            organization_id=organization_id,
            name=c.name,
            entity_types=list(c.entity_types),
            base_url=c.base_url,
            method=c.method,
            path=c.path,
            headers=c.headers,
            query_params=c.query_params,
            content_type=c.content_type,
            body_template=c.body_template,
            auth_type=c.auth_type,
            auth_config=c.auth_config,
            response_mapping=c.response_mapping,
            success_when=c.success_when,
        )
        secrets = self._merge_test_secrets(organization_id, request)
        field_values = {key: str(value) for key, value in request.sample_fields.items()}
        result = run_connector_call(
            contract=contract,
            secrets=secrets,
            field_values=field_values,
            strict_placeholders=False,
        )
        return self._test_response(result)

    def run_for_entity(
        self,
        *,
        organization_id: str,
        connector_id: str,
        entity_values: dict[str, str] | None = None,
    ) -> ConnectorCallResult:
        """Call one connector for a record, for callers that already checked access.

        Secrets are decrypted and used here, never returned.
        """
        contract = self.db_model_service.get_connector(connector_id, organization_id)
        if contract is None:
            logger.error(
                f"run connector for entity: not found id={connector_id} org={organization_id}"
            )
            raise NotFoundError("Connector not found")
        secrets = self.db_model_service.get_decrypted_secrets(connector_id, organization_id)
        values = entity_values or {}
        # Both placeholder styles read the record: {{field}} as well as
        # $entity.field.
        return run_connector_call(
            contract=contract, secrets=secrets, field_values=values, entity_values=values
        )

    @staticmethod
    def _test_response(result: ConnectorCallResult) -> ConnectorTestResponse:
        return ConnectorTestResponse(
            success=result.ok,
            status_code=result.status_code,
            message=result.error or "OK",
            response_json=result.response_json,
        )

    def _merge_test_secrets(
        self, organization_id: str, request: ConnectorInlineTestRequest
    ) -> dict[str, str]:
        """Combine the secrets typed in the form with those stored on a saved connector.

        Secrets are write-only, so editing an existing connector leaves the credential
        fields blank. Without this, an inline test would send empty credentials and fail
        auth. Any secret the user did type wins; blank ones fall back to the stored value.
        """
        supplied = {key: value for key, value in (request.connector.secrets or {}).items() if value}
        if not request.connector_id:
            return supplied
        stored = self.db_model_service.get_decrypted_secrets(request.connector_id, organization_id)
        merged = dict(stored)
        merged.update(supplied)
        return merged

    def _authorize(self, actor: dict[str, object], organization_id: str) -> None:
        """Ensure the actor may operate within the requested organization scope."""
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            logger.error(
                f"connector org scope mismatch actor_org={actor_organization_id} requested_org={organization_id}"
            )
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            logger.error(f"actor missing required field: {field_name}")
            raise AuthorizationError(f"Actor missing required field: {field_name}")
        return value

    @staticmethod
    def _to_read_response(contract: ConnectorContract) -> ConnectorReadResponse:
        return ConnectorReadResponse(
            id=contract.id,
            organization_id=contract.organization_id,
            name=contract.name,
            entity_types=list(contract.entity_types),
            base_url=contract.base_url,
            method=contract.method,
            path=contract.path,
            headers=dict(contract.headers),
            query_params=dict(contract.query_params),
            content_type=contract.content_type,
            body_template=contract.body_template,
            auth_type=contract.auth_type,
            auth_config=dict(contract.auth_config),
            secret_hints=dict(contract.secret_hints),
            response_mapping=dict(contract.response_mapping),
            success_when=dict(contract.success_when),
            expose_as_tool=bool(contract.expose_as_tool),
            status=contract.status,
            validation_status=contract.validation_status,
            last_validated_at=contract.last_validated_at,
            last_error=contract.last_error,
            created_at=contract.created_at,
            updated_at=contract.updated_at,
        )


# ── Outbound HTTP call logic ────────────────────────────────────────────────────

@dataclass
class ConnectorCallResult:
    """Outcome of one connector call."""

    ok: bool
    status_code: int | None = None
    error: str | None = None
    mapped_fields: dict[str, Any] = field(default_factory=dict)
    response_summary: str = ""
    response_json: Any = None


def run_connector_call(
    *,
    contract: ConnectorContract,
    secrets: dict[str, str],
    field_values: dict[str, str],
    entity_values: dict[str, str] | None = None,
    allow_private_hosts: bool = False,
    idempotency_key: str | None = None,
    strict_placeholders: bool = True,
) -> ConnectorCallResult:
    """Build, guard, send, and interpret one connector HTTP call.

    ``field_values`` fills ``{{input}}`` placeholders — values supplied by the
    caller (an agent argument or a workflow input). ``entity_values`` fills
    ``$entity.field`` placeholders from the bound entity's record. When
    ``entity_values`` is omitted, entity placeholders fall back to
    ``field_values`` so the inline-test and workflow paths keep working.

    ``strict_placeholders`` fails the call when a placeholder names something its
    source does not have. Those used to resolve to an empty string, so a
    misspelt field sent blank data, the API answered 200, and the run was
    recorded as a success. Interactive testing passes False, because sample
    values are deliberately partial there.
    """
    resolver = _PlaceholderResolver(
        field_values, field_values if entity_values is None else entity_values
    )
    try:
        url = resolver.resolve_text(_join_url(contract.base_url, contract.path))
        query = resolver.resolve_mapping(contract.query_params)
        body, headers = _build_body_and_headers(contract, resolver)
        _apply_auth(headers, query, contract, secrets, body)
        if idempotency_key:
            headers.setdefault(HEADER_IDEMPOTENCY_KEY, idempotency_key)
        # After the whole request is built, so one failure names every unresolved
        # placeholder rather than only the first, and before DNS, so a
        # misconfigured connector never reaches the network.
        if strict_placeholders and resolver.missing:
            names = ", ".join(sorted(resolver.missing))
            logger.error(
                f"connector call blocked, unresolved placeholders connector={contract.id}: {names}"
            )
            return ConnectorCallResult(
                ok=False,
                error=(
                    f"unresolved placeholders: {names}. "
                    "Each must name a field on the entity, or an input supplied by the caller."
                ),
            )
        target = resolve_safe_target(url, allow_private_hosts)
        return _send(contract, target, query, headers, body)
    except SsrfError as exc:
        logger.error(f"connector call blocked by SSRF guard: {exc}")
        return ConnectorCallResult(ok=False, error=str(exc))
    except Exception as exc:
        logger.exception(f"connector call build failed for connector={contract.id}")
        return ConnectorCallResult(ok=False, error=f"request build failed: {exc}")


def _send(
    contract: ConnectorContract, target: PinTarget, query: dict, headers: dict, body: Any
) -> ConnectorCallResult:
    """Perform the HTTP request against the pinned IP and interpret the response."""
    timeout = httpx.Timeout(
        connect=DEFAULT_CONNECT_TIMEOUT_SECONDS, read=DEFAULT_READ_TIMEOUT_SECONDS,
        write=DEFAULT_READ_TIMEOUT_SECONDS, pool=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    send_headers = dict(headers)
    if target.host_header:
        send_headers[HEADER_HOST] = target.host_header
    try:
        # No redirects: a 3xx must not bounce us to an unvalidated host.
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            request = client.build_request(
                contract.method, target.request_url, params=query or None,
                headers=send_headers or None,
                content=body if isinstance(body, (bytes, str)) else None,
            )
            if target.sni_hostname:
                # TLS SNI + cert verification use the hostname, not the pinned IP.
                request.extensions["sni_hostname"] = target.sni_hostname
            response = client.send(request)
    except httpx.TimeoutException as exc:
        logger.error(f"connector={contract.id} call timed out: {exc}")
        return ConnectorCallResult(ok=False, error="request timed out")
    except httpx.HTTPError as exc:
        logger.error(f"connector={contract.id} call failed: {exc}")
        return ConnectorCallResult(ok=False, error=f"request failed: {exc}")

    parsed = _safe_json(response)
    ok = _evaluate_success(response.status_code, parsed, dict(contract.success_when or {}))
    mapped = _extract_mapped_fields(parsed, dict(contract.response_mapping or {})) if ok else {}
    return ConnectorCallResult(
        ok=ok,
        status_code=response.status_code,
        error=None if ok else f"non-success response: HTTP {response.status_code}",
        mapped_fields=mapped,
        response_summary=response.text[:RESPONSE_SUMMARY_LIMIT],
        response_json=parsed,
    )


def _build_body_and_headers(
    contract: ConnectorContract, resolver: _PlaceholderResolver
) -> tuple[Any, dict[str, str]]:
    """Return the encoded request body and the base headers (incl. content-type)."""
    headers = resolver.resolve_mapping(contract.headers)
    template = contract.body_template
    if template is None or contract.method == HttpMethod.GET:
        return None, headers

    if contract.content_type == ContentType.RAW:
        headers.setdefault(HEADER_CONTENT_TYPE, CONTENT_TYPE_TEXT)
        return resolver.resolve_text(str(template)), headers

    resolved = resolver.resolve_value(template)
    if contract.content_type == ContentType.FORM:
        headers.setdefault(HEADER_CONTENT_TYPE, ContentType.FORM)
        return _encode_form(resolved), headers
    headers.setdefault(HEADER_CONTENT_TYPE, ContentType.JSON)
    return json.dumps(resolved), headers


def _apply_auth(
    headers: dict[str, str], query: dict[str, str], contract: ConnectorContract,
    secrets: dict[str, str], body: Any,
) -> None:
    """Attach the connector's auth credentials to the outgoing request in place."""
    auth_type = contract.auth_type
    auth_config = dict(contract.auth_config or {})
    if auth_type == ConnectorAuthType.BEARER:
        headers[HEADER_AUTHORIZATION] = f"{BEARER_SCHEME} {secrets.get(SecretKey.TOKEN, '')}"
    elif auth_type == ConnectorAuthType.BASIC:
        raw = f"{secrets.get(SecretKey.USERNAME, '')}:{secrets.get(SecretKey.PASSWORD, '')}".encode()
        headers[HEADER_AUTHORIZATION] = f"{BASIC_SCHEME} {base64.b64encode(raw).decode()}"
    elif auth_type == ConnectorAuthType.API_KEY:
        _apply_api_key(headers, query, auth_config, secrets.get(SecretKey.API_KEY, ""))
    # NONE and CUSTOM need no computed credentials (CUSTOM uses static headers on the connector).


def _apply_api_key(
    headers: dict[str, str], query: dict[str, str], auth_config: dict[str, Any], api_key: str
) -> None:
    location = str(auth_config.get(AuthConfigKey.LOCATION) or ApiKeyLocation.HEADER).strip().lower()
    name = str(auth_config.get(AuthConfigKey.NAME) or DEFAULT_API_KEY_HEADER).strip()
    if location == ApiKeyLocation.QUERY:
        query[name] = api_key
    else:
        headers[name] = api_key



class _PlaceholderResolver:
    """Resolve placeholders against two distinct sources.

    ``{{input}}`` is filled from caller-supplied inputs (an agent argument or a
    workflow input); ``$entity.field`` is filled from the bound entity's record.
    Keeping the two sources separate means a caller input and an entity field
    may share a name without colliding.
    """

    def __init__(self, input_values: dict[str, str], entity_values: dict[str, str]) -> None:
        """Store the input and entity value sources for placeholder resolution."""
        self._inputs = dict(input_values or {})
        self._entities = dict(entity_values or {})
        # Placeholders naming something absent from their source. A field that
        # exists but is empty is not recorded: an optional field left blank is a
        # real value, a misspelt field name is not.
        self.missing: set[str] = set()

    def _input(self, name: str) -> str:
        if name not in self._inputs:
            self.missing.add(f"{{{{{name}}}}}")
            return ""
        return str(self._inputs[name])

    def _entity(self, name: str) -> str:
        if name not in self._entities:
            self.missing.add(f"$entity.{name}")
            return ""
        return str(self._entities[name])

    def resolve_text(self, text: str) -> str:
        """Replace every {{input}} and $entity.field placeholder in a string."""
        with_inputs = CURLY_PLACEHOLDER.sub(
            lambda match: self._input(match.group(1)), text
        )
        return ENTITY_PLACEHOLDER.sub(
            lambda match: self._entity(match.group(1)), with_inputs
        )

    def resolve_mapping(self, mapping: dict[str, str]) -> dict[str, str]:
        """Resolve placeholders in every value of a string mapping."""
        return {key: self.resolve_text(str(value)) for key, value in (mapping or {}).items()}

    def resolve_value(self, value: Any) -> Any:
        """Resolve placeholders in strings/dicts/lists; a sole placeholder keeps its JSON type."""
        if isinstance(value, str):
            sole = SOLE_PLACEHOLDER.match(value.strip())
            if sole:
                # group(1) is the {{input}} capture; group(2) is the $entity.field capture.
                if sole.group(1) is not None:
                    return _coerce_scalar(self._input(sole.group(1)))
                return _coerce_scalar(self._entity(sole.group(2)))
            return self.resolve_text(value)
        if isinstance(value, dict):
            return {key: self.resolve_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        return value


def _coerce_scalar(raw: str) -> Any:
    """Restore a value to its JSON type (number/bool/null), or keep the string if ambiguous."""
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    return raw if isinstance(parsed, str) else parsed


def _evaluate_success(status_code: int, parsed: Any, success_when: dict[str, Any]) -> bool:
    """Decide success: default is 2xx; an optional rule can also check a JSON value."""
    status_ok = HTTP_SUCCESS_MIN <= status_code < HTTP_SUCCESS_MAX
    if not success_when:
        return status_ok
    allowed = success_when.get(SuccessRuleKey.STATUS_IN)
    if isinstance(allowed, list) and allowed:
        status_ok = status_code in allowed
    json_path = success_when.get(SuccessRuleKey.JSON_PATH)
    if json_path:
        actual = _dotted_get(parsed, str(json_path))
        return status_ok and str(actual) == str(success_when.get(SuccessRuleKey.EQUALS))
    return status_ok


def _extract_mapped_fields(parsed: Any, response_mapping: dict[str, str]) -> dict[str, Any]:
    """Build {entity_field: value} by reading nested paths out of the parsed response.

    A mapping key of the form ``table_field.column_id`` targets one column of a
    table field: its response path (typically a wildcard like ``results[].value``)
    is read, and the per-column values are zipped by index into table rows. Plain
    keys write the extracted value straight onto the entity field.

    A special key ``table_field.__match__`` (whose value is a column id, not a
    response path) switches that table to *merge* mode: instead of replacing the
    field, the write-back matches each built row to an existing row by that column
    and updates only the mapped cells — leaving all other rows/cells intact.

    A mapping value that begins with ``=`` is a *literal*: the text after ``=`` is
    used verbatim (parsed as JSON when possible, e.g. ``=["a","b"]`` or ``=42``),
    instead of being read from the API response. Useful for hardcoding values.
    """
    if not response_mapping:
        return {}
    mapped: dict[str, Any] = {}
    table_columns: dict[str, dict[str, Any]] = {}
    table_match: dict[str, str] = {}
    # Columns whose path contains LOOKUP_MATCH_TOKEN — resolved per row after the
    # base rows are assembled, so a column can be joined from a different source
    # keyed on each row's match value (e.g. lineage from results[] by fcc_line).
    table_lookups: dict[str, dict[str, str]] = {}
    for entity_field, response_path in response_mapping.items():
        if "." in entity_field:
            table_field, column_id = entity_field.split(".", 1)
            if column_id == TABLE_MERGE_MATCH_KEY:
                # Value is the column to match existing rows on — a literal id, not a path.
                table_match[table_field] = str(response_path)
                continue
            path = str(response_path)
            if LOOKUP_MATCH_TOKEN in path:
                table_lookups.setdefault(table_field, {})[column_id] = path
            else:
                table_columns.setdefault(table_field, {})[column_id] = _resolve_value(parsed, path)
            continue
        value = _resolve_value(parsed, str(response_path))
        if value is not None:
            mapped[entity_field] = value
    for table_field in set(table_columns) | set(table_lookups):
        columns = table_columns.get(table_field, {})
        match_col = table_match.get(table_field)
        lookups = table_lookups.get(table_field)
        if match_col and lookups and not columns:
            # All columns are per-row lookups, so the record supplies the rows.
            mapped[table_field] = {
                TABLE_MERGE_INSTRUCTION_KEY: {
                    TABLE_MERGE_MATCH_INSTRUCTION_KEY: match_col,
                    TABLE_MERGE_LOOKUPS_KEY: lookups,
                    TABLE_MERGE_RESPONSE_KEY: prune_response_for_lookups(parsed, lookups),
                }
            }
            continue
        rows = _assemble_table_rows(columns)
        if lookups and match_col:
            fill_lookup_columns(rows, match_col, lookups, parsed)
        if match_col:
            # Merge instruction — resolved against existing rows at write-back time.
            mapped[table_field] = {
                TABLE_MERGE_INSTRUCTION_KEY: {
                    TABLE_MERGE_MATCH_INSTRUCTION_KEY: match_col,
                    TABLE_MERGE_ROWS_KEY: rows,
                }
            }
        else:
            mapped[table_field] = rows
    return mapped


def prune_response_for_lookups(parsed: Any, lookups: dict[str, str]) -> Any:
    """The parts of the response the lookups read, in their original shape.

    A deferred instruction travels to write-back, so carrying the whole external
    response would keep data nobody asked for alive far past the call. Each
    lookup path is static up to the segment holding LOOKUP_MATCH_TOKEN; only
    that prefix is kept, which is enough for every row to resolve later.

    Falls back to the full response when a prefix is not plain object access —
    an index or wildcard cannot be rebuilt as a dict, and a correct merge
    matters more than a smaller payload.
    """
    pruned: dict[str, Any] = {}
    for path in lookups.values():
        tokens = _parse_response_path(str(path))
        cut = next(
            (i for i, token in enumerate(tokens) if LOOKUP_MATCH_TOKEN in token), len(tokens)
        )
        prefix = tokens[:cut]
        if not prefix or any(
            token == "*" or token.startswith(FILTER_PREDICATE_PREFIX) or token.isdigit()
            for token in prefix
        ):
            return parsed
        value = _dotted_get(parsed, ".".join(prefix))
        if value is None:
            continue
        branch = pruned
        for token in prefix[:-1]:
            nxt = branch.get(token)
            if not isinstance(nxt, dict):
                nxt = {}
                branch[token] = nxt
            branch = nxt
        branch[prefix[-1]] = value
    return pruned


def fill_lookup_columns(
    rows: list[dict[str, Any]], match_col: str, lookups: dict[str, str], parsed: Any
) -> None:
    """Resolve per-row lookup columns in place.

    For each row, substitute ``LOOKUP_MATCH_TOKEN`` in each lookup path with the
    row's match-column value, resolve it against the response, and store the first
    result (lookups are expected to identify a single matching item).

    Public because write-back calls it too, on the record's own rows.
    """
    for row in rows:
        key_value = row.get(match_col)
        if key_value is None:
            continue
        for column_id, path in lookups.items():
            resolved = _resolve_value(parsed, path.replace(LOOKUP_MATCH_TOKEN, str(key_value)))
            if isinstance(resolved, list):
                resolved = resolved[0] if resolved else None
            row[column_id] = resolved


def _assemble_table_rows(columns: dict[str, Any]) -> list[dict[str, Any]]:
    """Zip per-column values into table rows.

    Each column value is a list (from a wildcard path like ``results[].value``) or a
    scalar; row ``i`` takes each column's ``i``-th value, missing values become None.
    """
    normalized: dict[str, list[Any]] = {}
    length = 0
    for column_id, value in columns.items():
        values = value if isinstance(value, list) else [value]
        normalized[column_id] = values
        length = max(length, len(values))
    rows: list[dict[str, Any]] = []
    for index in range(length):
        rows.append(
            {
                column_id: (values[index] if index < len(values) else None)
                for column_id, values in normalized.items()
            }
        )
    return rows


def _resolve_value(parsed: Any, response_path: str) -> Any:
    """Resolve a mapping value: a ``=``-prefixed literal, or a response path.

    ``=`` prefix -> the remaining text is used verbatim (parsed as JSON when
    possible, e.g. ``=["a","b"]`` or ``=42``), instead of reading the response.
    Otherwise the value is read from ``parsed`` via :func:`_dotted_get`.
    """
    raw = str(response_path)
    if raw.startswith("="):
        literal = raw[1:]
        try:
            return json.loads(literal)
        except (ValueError, TypeError):
            return literal
    return _dotted_get(parsed, raw)


def _dotted_get(obj: Any, path: str) -> Any:
    """Read a nested value by path.

    Supported forms:
    - dotted object access: ``data.status``
    - numeric list indexes: ``items.0.id`` or ``items[0].id``
    - wildcard list expansion: ``items[].id`` or ``items[*].id``
    """
    tokens = _parse_response_path(path)
    if not tokens:
        return obj
    if any(token == "*" or token.startswith(FILTER_PREDICATE_PREFIX) for token in tokens):
        values = _path_collect(obj, tokens)
        return values if values else None
    current = obj
    for segment in tokens:
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and str(segment).isdigit():
            index = int(segment)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _parse_response_path(path: str) -> list[str]:
    """Split response paths into object keys, list indexes, and wildcard markers."""
    raw = str(path or "").strip()
    if not raw:
        return []
    tokens: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == ".":
            index += 1
            continue
        if char == "[":
            end = raw.find("]", index)
            if end == -1:
                return []
            bracket_value = raw[index + 1 : end].strip()
            if bracket_value in {"", "*"}:
                tokens.append("*")
            elif "=" in bracket_value:
                # Filter predicate, e.g. results[column_indicator=a] -> keep matching items.
                tokens.append(FILTER_PREDICATE_PREFIX + bracket_value)
            else:
                tokens.append(bracket_value)
            index = end + 1
            continue
        end = index
        while end < len(raw) and raw[end] not in ".[":
            end += 1
        tokens.append(raw[index:end])
        index = end
    return [token for token in tokens if token != ""]


def _path_collect(current: Any, tokens: list[str]) -> list[Any]:
    """Collect all values that match a path containing one or more wildcards."""
    if not tokens:
        return [current]
    head, tail = tokens[0], tokens[1:]
    if head == "*":
        # Wildcard over a list expands its items; over a dict it expands into
        # {"key", "value"} pseudo-rows so a mapping can read `obj[].key` /
        # `obj[].value` (e.g. turn {"115a": 1.0, "116a": 2.0} into table rows).
        if isinstance(current, dict):
            items: list[Any] = [{"key": key, "value": value} for key, value in current.items()]
        elif isinstance(current, list):
            items = current
        else:
            return []
        collected: list[Any] = []
        for item in items:
            collected.extend(_path_collect(item, tail))
        return collected
    if head.startswith(FILTER_PREDICATE_PREFIX):
        # Filter predicate "field=value": keep only list items whose field equals value.
        field_name, _, expected = head[len(FILTER_PREDICATE_PREFIX):].partition("=")
        if not isinstance(current, list):
            return []
        matched: list[Any] = []
        for item in current:
            if isinstance(item, dict) and str(item.get(field_name)) == expected:
                matched.extend(_path_collect(item, tail))
        return matched
    if isinstance(current, dict):
        next_value = current.get(head)
        return [] if next_value is None else _path_collect(next_value, tail)
    if isinstance(current, list) and str(head).isdigit():
        item_index = int(head)
        if item_index >= len(current):
            return []
        return _path_collect(current[item_index], tail)
    return []


def _join_url(base_url: str, path: str) -> str:
    if not path:
        return base_url
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _encode_form(value: Any) -> str:
    if isinstance(value, dict):
        return urlencode({key: str(item) for key, item in value.items()})
    return str(value)


def _safe_json(response: httpx.Response) -> Any:
    """Parse response as JSON, returning None on any parse failure."""
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return None


# Wire run_connector_call onto the manager after the function is defined.
ConnectorsServiceManager.run_connector_call = staticmethod(run_connector_call)
