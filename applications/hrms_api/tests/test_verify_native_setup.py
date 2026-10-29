import pytest

from hrms_app.verify_native_setup import verify_workflow_methods


def test_shared_native_form_is_valid_when_workflow_references_it():
    verify_workflow_methods([{'method_id': 'shared', 'entity_types': []}], [
        {'definition': {'states': [{'method_refs': [{'method_id': 'shared'}]}]}}])


@pytest.mark.parametrize('refs', [[], [{'method_id': 'missing'}]])
def test_missing_native_workflow_forms_are_rejected(refs):
    with pytest.raises(AssertionError):
        verify_workflow_methods([{'method_id': 'shared'}], [{'definition': {'states': [{'method_refs': refs}]}}])


def test_private_native_notification_workflow_needs_mail_action_not_user_form():
    from hrms_app.offboarding_notifications import ENTITY, definition
    graph=definition()
    verify_workflow_methods([], [{'entity_type':ENTITY,'definition':graph}])
    graph['states'][0]['on_state_actions']=[]
    with pytest.raises(AssertionError,match='mail action'):verify_workflow_methods([], [{'entity_type':ENTITY,'definition':graph}])
