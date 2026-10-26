import pytest

from hrms_app.verify_native_setup import verify_workflow_methods


def test_shared_native_form_is_valid_when_workflow_references_it():
    verify_workflow_methods([{'method_id': 'shared', 'entity_types': []}], [
        {'definition': {'states': [{'method_refs': [{'method_id': 'shared'}]}]}}])


@pytest.mark.parametrize('refs', [[], [{'method_id': 'missing'}]])
def test_missing_native_workflow_forms_are_rejected(refs):
    with pytest.raises(AssertionError):
        verify_workflow_methods([{'method_id': 'shared'}], [{'definition': {'states': [{'method_refs': refs}]}}])
