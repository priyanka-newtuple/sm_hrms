import pytest

from hrms.core.exceptions import ValidationFailed
from hrms.workflows.platform import DEFINITIONS, validate_transition


@pytest.mark.parametrize("kind,source,target", [
    ("timesheet", "draft", "submitted"),
    ("timesheet", "submitted", "approved"),
    ("onboarding", "not_started", "in_progress"),
    ("project_approval", "pending", "changes_requested"),
    ("published_content", "pending_approval", "published"),
    ("published_content", "pending_approval", "approved"),
    ("published_content", "approved", "published"),
])
def test_declared_legacy_moves_use_platform_definition(kind, source, target):
    assert DEFINITIONS[kind].entity_type.startswith("HRMS.")
    validate_transition(kind, source, target)


@pytest.mark.parametrize("kind,source,target", [
    ("timesheet", "draft", "approved"),
    ("onboarding", "completed", "in_progress"),
    ("published_content", "draft", "published"),
    ("project_approval", "draft", "approved"),
])
def test_undeclared_moves_fail_closed(kind, source, target):
    with pytest.raises(ValidationFailed):
        validate_transition(kind, source, target)
