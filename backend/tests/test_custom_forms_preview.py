"""Previewing a connector-backed form before any record exists.

`resolve_connector_form_for_actor` backs
`POST /custom-forms/methods/{method_version_id}/preview`. It is keyed by the
method version rather than a raw connector id — the same
`_connector_id_for_version` check `connector_ids_for_state` already applies
on read — so a caller with only `entity_record:write` can preview a form
but cannot point it at an arbitrary connector the way a raw connector id
would let them. Fakes mirror `test_custom_forms.py`'s `_manager` factory.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from custom_forms.manager import CustomFormsServiceManager
from custom_forms.models.response import ConnectorFormPreviewResponse
from exceptions import AuthorizationError, NotFoundError

ORG = "org-1"
OTHER_ORG = "org-2"
DYNAMIC_VERSION = "version-dynamic"
PLAIN_VERSION = "version-plain"
CONNECTOR = "connector-1"

FORM = {
    "sections": [
        {
            "id": "s1",
            "title": "Certificate",
            "cells": [
                {"id": "cert_id", "label": "Certificate ID", "type": "text", "value": "CPCN-1"}
            ],
        }
    ],
    "calculations": {},
}


def _manager(
    *,
    fields_by_version: dict[str, list],
    connector_by_version: dict[str, str | None],
    call_result=None,
) -> CustomFormsServiceManager:
    return CustomFormsServiceManager(
        method_library_db_model_service=NS(
            list_version_fields=lambda **kw: fields_by_version.get(kw["method_version_id"], []),
            get_version=lambda **kw: NS(connector_id=connector_by_version.get(kw["version_id"])),
        ),
        connectors_service_manager=NS(run_for_entity=lambda **kw: call_result),
    )


def _ok(payload) -> NS:
    return NS(ok=True, response_json=payload, error=None)


def test_preview_returns_the_form_with_cell_values_stripped() -> None:
    manager = _manager(
        fields_by_version={DYNAMIC_VERSION: []},
        connector_by_version={DYNAMIC_VERSION: CONNECTOR},
        call_result=_ok(FORM),
    )

    result = manager.resolve_connector_form_for_actor(
        {"organization_id": ORG}, ORG, DYNAMIC_VERSION, {"account": "A-1"}
    )

    assert isinstance(result, ConnectorFormPreviewResponse)
    cell = result.form["sections"][0]["cells"][0]
    assert cell["id"] == "cert_id"
    assert "value" not in cell


def test_preview_rejects_an_actor_from_a_different_organization() -> None:
    manager = _manager(
        fields_by_version={DYNAMIC_VERSION: []},
        connector_by_version={DYNAMIC_VERSION: CONNECTOR},
        call_result=_ok(FORM),
    )

    with pytest.raises(AuthorizationError):
        manager.resolve_connector_form_for_actor(
            {"organization_id": OTHER_ORG}, ORG, DYNAMIC_VERSION, {}
        )


def test_preview_raises_not_found_when_the_connector_returns_nothing_usable() -> None:
    manager = _manager(
        fields_by_version={DYNAMIC_VERSION: []},
        connector_by_version={DYNAMIC_VERSION: CONNECTOR},
        call_result=NS(ok=False, response_json=None, error="boom"),
    )

    with pytest.raises(NotFoundError):
        manager.resolve_connector_form_for_actor({"organization_id": ORG}, ORG, DYNAMIC_VERSION, {})


def test_preview_rejects_a_method_version_that_is_not_a_dynamic_form() -> None:
    """A version with fields (or no connector) is not previewable at all —
    the connector is never even called, unlike the old raw-connector-id shape."""
    manager = _manager(
        fields_by_version={PLAIN_VERSION: [NS(field_key="notes")]},
        connector_by_version={PLAIN_VERSION: CONNECTOR},
        call_result=_ok(FORM),
    )

    with pytest.raises(NotFoundError):
        manager.resolve_connector_form_for_actor({"organization_id": ORG}, ORG, PLAIN_VERSION, {})
