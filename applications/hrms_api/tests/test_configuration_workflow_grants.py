from types import SimpleNamespace
from copy import deepcopy
import pytest
from hrms_app.configuration_package import ConfigurationError
from hrms_app.configuration_workflow_grants import capture, restore, projected_grants


def test_old_case_permissions_restored_after_native_publish_pruning():
    role={'id':'hr','workflow_permissions':[{'machine_name':'exit'}], 'transition_permissions':[{'machine_name':'exit','transition_key':'approve_old'}, {'machine_name':'other','transition_key':'keep'}]}
    writes=[]
    native=SimpleNamespace(listing=lambda _: [role], get=lambda _:deepcopy(role), api=SimpleNamespace(call=lambda *a,**kw:writes.append(kw['json'])))
    old={'transitions':[{'key':'approve_old','from':'Approval','to_state':'Handover'}]}
    new={'transitions':[{'key':'submit','from':'In Progress','to_state':'Submitted'},{'key':'verify','from':'Submitted','to_state':'Completed'}]}
    snapshots=capture(native,'exit',old,new)
    role['transition_permissions']=[{'machine_name':'other','transition_key':'keep'}]
    restore(native,snapshots)
    assert writes==[{'transition_permissions':[{'machine_name':'exit','transition_key':'approve_old'}, {'machine_name':'other','transition_key':'keep'}]}]
    # Unrelated concurrent revocation must never be reversed.
    role['transition_permissions']=[]
    with pytest.raises(ConfigurationError,match='changed'):restore(native,snapshots)
    assert len(writes)==1


def test_native_rename_projection_is_exact_and_keeps_other_workflows():
    old={'transitions':[{'key':'before','from_state':'A','to_state':'B'}]}
    new={'transitions':[{'key':'after','from':'A','to_state':'B'}]}
    assert projected_grants({('wf','before'),('other','read')},'wf',old,new)=={('wf','after'),('other','read')}


def test_append_only_workflow_does_not_touch_role_grants():
    native=SimpleNamespace(listing=lambda _:(_ for _ in ()).throw(AssertionError('unnecessary read')))
    assert capture(native,'wf',{'transitions':[{'key':'old'}]}, {'transitions':[{'key':'old'},{'key':'new'}]})==[]
