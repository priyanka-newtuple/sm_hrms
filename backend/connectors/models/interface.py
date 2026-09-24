"""Interface models and contracts for connectors (a reusable, org-scoped outbound API call)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel

# Network behaviour — named so they are not magic numbers buried in the call.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS = 10.0
DEFAULT_SIGNATURE_HEADER = "X-Signature"
DEFAULT_TIMESTAMP_HEADER = "X-Timestamp"
RESPONSE_SUMMARY_LIMIT = 500

# HTTP success range (default 2xx) and the URL schemes a connector may target.
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_MAX = 300
SCHEME_HTTP = "http"
SCHEME_HTTPS = "https"
ALLOWED_URL_SCHEMES = (SCHEME_HTTP, SCHEME_HTTPS)

# Standard headers the connector sets on outbound calls.
HEADER_AUTHORIZATION = "Authorization"
HEADER_CONTENT_TYPE = "Content-Type"
HEADER_HOST = "Host"
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"

# Auth scheme prefixes, signing algorithm, and the default api_key header name.
BEARER_SCHEME = "Bearer"
BASIC_SCHEME = "Basic"
DEFAULT_API_KEY_HEADER = "X-API-Key"
CONTENT_TYPE_TEXT = "text/plain"


class SecretKey:
    """Keys expected in the decrypted secrets dict, per auth type."""

    TOKEN = "token"
    USERNAME = "username"
    PASSWORD = "password"
    API_KEY = "api_key"


class AuthConfigKey:
    """Non-secret auth parameters stored on the connector's auth_config."""

    LOCATION = "in"
    NAME = "name"
    SIGNATURE_HEADER = "signature_header"


class ApiKeyLocation:
    """Where an API key is placed on the outgoing request."""

    HEADER = "header"
    QUERY = "query"


class SuccessRuleKey:
    """Keys understood in a connector's success_when rule."""

    STATUS_IN = "status_in"
    JSON_PATH = "json_path"
    EQUALS = "equals"

# {{field}} and $entity.field placeholders.
CURLY_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
ENTITY_PLACEHOLDER = re.compile(r"\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)")
# A body value that is exactly one placeholder — lets its JSON type be restored.
SOLE_PLACEHOLDER = re.compile(
    r"^(?:\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}|\$entity\.([a-zA-Z_][a-zA-Z0-9_]*))$"
)


class ConnectorAuthType:
    """Supported authentication strategies for a connector call."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    CUSTOM = "custom"


class ConnectorStatus:
    """Lifecycle status for a connector record."""

    CONFIGURED = "configured"
    DISABLED = "disabled"


class HttpMethod:
    """HTTP methods a connector is allowed to use."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ContentType:
    """How the request body is encoded on the wire."""

    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    RAW = "raw"


_VALID_AUTH_TYPES = frozenset(
    {
        ConnectorAuthType.NONE,
        ConnectorAuthType.API_KEY,
        ConnectorAuthType.BEARER,
        ConnectorAuthType.BASIC,
        ConnectorAuthType.CUSTOM,
    }
)

_VALID_METHODS = frozenset(
    {HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH, HttpMethod.DELETE}
)

_VALID_CONTENT_TYPES = frozenset({ContentType.JSON, ContentType.FORM, ContentType.RAW})


class ConnectorContract(PydanticBaseModel):
    """Immutable view of a stored connector. Never carries the raw secret — only masked hints."""

    model_config = ConfigDict(frozen=True)

    id: str
    organization_id: str
    name: str
    entity_types: list[str] = Field(default_factory=list)
    base_url: str
    method: str = HttpMethod.POST
    path: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    content_type: str = ContentType.JSON
    # dict or list for JSON/form bodies, str for raw bodies, None when there is no
    # body. A list is the top level for batch endpoints that take an array of
    # objects (inriver's entities:upsert, Elasticsearch _bulk, and so on).
    body_template: dict[str, Any] | list[Any] | str | None = None
    auth_type: str = ConnectorAuthType.NONE
    # Non-secret auth parameters (e.g. header name for api_key, signature header for hmac).
    auth_config: dict[str, Any] = Field(default_factory=dict)
    secret_hints: dict[str, str] = Field(default_factory=dict)
    # entity field -> dotted path in the response JSON.
    response_mapping: dict[str, str] = Field(default_factory=dict)
    # Optional rule deciding success beyond the default 2xx (see executor for interpretation).
    success_when: dict[str, Any] = Field(default_factory=dict)
    expose_as_tool: bool = False
    status: str = ConnectorStatus.CONFIGURED
    validation_status: str | None = None
    last_validated_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def normalize_method(method: str) -> str:
    """Return the upper-cased HTTP method, raising ValueError if unsupported."""
    normalized = str(method or "").strip().upper()
    if normalized not in _VALID_METHODS:
        raise ValueError(f"method must be one of {sorted(_VALID_METHODS)}")
    return normalized


def normalize_auth_type(auth_type: str) -> str:
    """Return the lower-cased auth type, raising ValueError if unsupported."""
    normalized = str(auth_type or ConnectorAuthType.NONE).strip().lower()
    if normalized not in _VALID_AUTH_TYPES:
        raise ValueError(f"auth_type must be one of {sorted(_VALID_AUTH_TYPES)}")
    return normalized


def normalize_content_type(content_type: str) -> str:
    """Return a supported content type, raising ValueError if unsupported."""
    normalized = str(content_type or ContentType.JSON).strip().lower()
    if normalized not in _VALID_CONTENT_TYPES:
        raise ValueError(f"content_type must be one of {sorted(_VALID_CONTENT_TYPES)}")
    return normalized
