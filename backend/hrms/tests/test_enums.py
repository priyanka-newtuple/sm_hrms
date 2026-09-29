from hrms.authz.enums import Action, RecordScope, expand_actions, scope_at_least


def test_manage_expands_to_view_create_edit_but_not_approve_or_delete():
    expanded = expand_actions([Action.MANAGE])
    assert expanded == {Action.VIEW, Action.CREATE, Action.EDIT, Action.MANAGE}
    assert Action.APPROVE not in expanded
    assert Action.DELETE not in expanded


def test_full_expands_to_everything_except_none():
    expanded = expand_actions([Action.FULL])
    assert expanded == {a for a in Action if a != Action.NONE}


def test_plain_action_does_not_expand():
    assert expand_actions([Action.VIEW]) == {Action.VIEW}


def test_scope_ordering():
    assert scope_at_least(RecordScope.ALL, RecordScope.SELF)
    assert not scope_at_least(RecordScope.SELF, RecordScope.ALL)
    assert scope_at_least(RecordScope.TEAM, RecordScope.TEAM)
