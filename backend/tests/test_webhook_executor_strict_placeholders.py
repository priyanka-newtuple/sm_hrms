"""HttpWebhookExecutor blocks a state-entry action instead of writing blank data.

Live-verified against a real inriver tenant (see FT-0218): a state-entry action
referencing a field the entity does not have recorded ACTION_FAILED with
status_code None, and inriver's product count did not move. This locks that
behaviour down with a unit test, since nothing exercised the executor before.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from connectors.models.interface import ConnectorContract, ConnectorStatus
from executor.executors.http_webhook import HttpWebhookExecutor
from executor.models.interface import ExecutorInput, ExecutorValue, ValueKind


def _contract(**overrides: object) -> ConnectorContract:
    base: dict[str, object] = {
        "id": "conn-1",
        "organization_id": "org-1",
        "name": "inriver-upsert",
        "base_url": "https://example.test",
        "method": "POST",
        "path": "/entities:upsert",
        "content_type": "application/json",
        "headers": {},
        "query_params": {},
        "status": ConnectorStatus.CONFIGURED,
        "entity_types": ["product"],
    }
    base.update(overrides)
    return ConnectorContract(**base)


def _executor(
    contract: ConnectorContract, secrets: dict[str, str] | None = None
) -> HttpWebhookExecutor:
    """Build the executor with its model-service dependencies stubbed, no real DB."""
    executor = HttpWebhookExecutor()
    executor._connectors = SimpleNamespace(
        get_connector=lambda connector_id, org_id: contract,
        get_decrypted_secrets=lambda connector_id, org_id: secrets or {},
    )
    executor._audit = MagicMock()
    executor._roles = None
    executor._notifications = None
    return executor


def _input(fields: dict[str, str]) -> ExecutorInput:
    return ExecutorInput(
        entity_id="entity-1",
        entity_type="product",
        current_state="SYNCED",
        fields={
            key: ExecutorValue(kind=ValueKind.TEXT, value=value) for key, value in fields.items()
        },
    )


def test_a_state_entry_action_blocks_on_a_field_the_entity_does_not_have() -> None:
    """The exact case proven live: a placeholder naming an absent field must fail,
    not silently upsert a blank value and record success."""
    contract = _contract(body_template={"name": "$entity.product_name"})
    executor = _executor(contract)

    response = executor.execute(
        _input({"org_id": "org-1", "connector_id": "conn-1", "run_id": "run-1"})
    )

    assert response.success is False
    assert "product_name" in response.message
    assert response.data.meta["status_code"] is None


def test_a_state_entry_action_still_fires_when_every_placeholder_resolves() -> None:
    """The strict check must not block a well-formed call."""
    contract = _contract(body_template={"code": "$entity.sku"})
    executor = _executor(contract)

    response = executor.execute(
        _input({"org_id": "org-1", "connector_id": "conn-1", "run_id": "run-1", "sku": "ABC-1"})
    )

    # It reaches the network (and fails there, since example.test resolves
    # nowhere in this sandbox) - the point is it is not blocked pre-flight.
    assert "unresolved placeholders" not in (response.message or "")
