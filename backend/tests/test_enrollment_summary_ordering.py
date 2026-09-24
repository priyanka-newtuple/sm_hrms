"""Default ordering of the Pipeline board's enrollment summary page."""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import pytest

from entities.db_models import EntityRecordModel, EntityStateRuntimeModel, EntityTypeModel
from workflow.db_models import WorkflowModelService, WorkflowStateMachineModel


def _db_is_reachable() -> bool:
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    parsed = urlparse(url)
    try:
        socket.getaddrinfo(parsed.hostname or "localhost", parsed.port or 5432)
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")
def test_board_orders_by_most_recent_state_entry_not_enrollment_date(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    """Cards in a state come back most-recently-entered first.

    The board sends no sort, so it lands on this default. It used to order by
    enrollment date, burying an entity that had just moved in.
    """
    org_id = "test-org-1"
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    workflow_db = WorkflowModelService(entities_db_service_manager)

    type_id = str(uuid.uuid4())
    type_name = f"board_order_{uuid.uuid4().hex[:8]}"
    machine_name = f"board_order_wf_{uuid.uuid4().hex[:8]}"
    workflow_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    # Deliberately opposed so the two candidate orderings disagree, otherwise
    # this test would pass on the old `created_at` ordering too:
    #   "parked"     enrolled 2 days ago  and has sat in REVIEW since
    #   "just_moved" enrolled 30 days ago but entered REVIEW 5 minutes ago
    # By enrollment date parked is newest and would come first; by state entry
    # just_moved must come first.
    parked_entity, just_moved_entity = str(uuid.uuid4()), str(uuid.uuid4())
    rows = [
        # (identifier, entity_id, enrolled/created_at, state_entered_at)
        ("A-parked", parked_entity, now - timedelta(days=2), now - timedelta(days=2)),
        ("B-moved", just_moved_entity, now - timedelta(days=30), now - timedelta(minutes=5)),
    ]
    try:
        session.add(
            EntityTypeModel(
                entity_type_id=type_id,
                organization_id=org_id,
                name=type_name,
                schema={},
                version=1,
                is_active=True,
            )
        )
        session.add(
            WorkflowStateMachineModel(
                id=workflow_id,
                organization_id=org_id,
                machine_key=machine_name,
                machine_name=machine_name,
                entity_type=type_name,
                version=1,
                is_active=True,
                definition_json=json.dumps(
                    {
                        "machine_key": machine_name,
                        "name": machine_name,
                        "entity_type": type_name,
                        "entity_schema": {"entity_type": type_name, "fields": []},
                        "initial_state": "REVIEW",
                        "states": [{"name": "REVIEW"}],
                        "transitions": [],
                    }
                ),
            )
        )
        session.commit()

        for identifier, entity_id, created_at, state_entered_at in rows:
            session.add(
                EntityRecordModel(
                    entity_id=entity_id,
                    organization_id=org_id,
                    entity_type_id=type_id,
                    data={"identifier": identifier},
                )
            )
            session.add(
                EntityStateRuntimeModel(
                    state_id=str(uuid.uuid4()),
                    organization_id=org_id,
                    entity_id=entity_id,
                    workflow_id=workflow_id,
                    current_state="REVIEW",
                    state_version=0,
                    state_entered_at=state_entered_at,
                    created_at=created_at,
                )
            )
        session.commit()

        summaries = workflow_db.list_enrollment_summary_rows(
            organization_id=org_id,
            machine_name=machine_name,
            current_state="REVIEW",
        )
        ordered = [row.entity_id for row in summaries]
        assert ordered == [just_moved_entity, parked_entity], (
            "the entity that most recently entered the state must come first"
        )

        # An explicit sort still wins over the default (the list view's column
        # sort), so this default does not take that control away.
        by_identifier = workflow_db.list_enrollment_summary_rows(
            organization_id=org_id,
            machine_name=machine_name,
            current_state="REVIEW",
            sort_by="identifier",
            sort_dir="asc",
        )
        assert [row.entity_id for row in by_identifier] == [parked_entity, just_moved_entity]
    finally:
        session.query(EntityStateRuntimeModel).filter(
            EntityStateRuntimeModel.workflow_id == workflow_id
        ).delete(synchronize_session=False)
        session.query(EntityRecordModel).filter(
            EntityRecordModel.entity_type_id == type_id
        ).delete(synchronize_session=False)
        session.query(WorkflowStateMachineModel).filter(
            WorkflowStateMachineModel.id == workflow_id
        ).delete(synchronize_session=False)
        session.query(EntityTypeModel).filter(
            EntityTypeModel.entity_type_id == type_id
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
