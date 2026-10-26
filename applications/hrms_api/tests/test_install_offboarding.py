"""Installer upgrade order, permission revocations and failed-publish recovery."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from hrms_app import install_offboarding as base
from hrms_app import install_offboarding_participation as participation
from hrms_app.offboarding_catalog import ENTITY, definition
from hrms_app.errors import AppError

class DB:
    def __init__(self): self.markers=set()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=()):
        if sql.startswith('INSERT'): self.markers.add(params[1])
        return SimpleNamespace(fetchone=lambda: (1,) if sql.startswith('SELECT') and params[1] in self.markers else None)

class API:
    org='org'
    def __init__(self):
        self.workflow={'id':'workflow-id','machine_name':'tenant_custom_offboarding','definition':definition(),'entity_type':ENTITY,'is_active':True}
        self.fields={}; self.methods=[]; self.templates=[]; self.publishes=0; self.fail_role=False
        self.roles={name:dict(id=name,name=name,workflow_permissions=[],transition_permissions=[],field_permissions=[],entity_permissions=[]) for name in ('superadmin','hrms_hr_full','hrms_application_service')}
    def call(self, method, path, **kw):
        data=kw.get('json',{})
        if path.startswith('/entity-types/'): return {}
        if path=='/roles': return list(self.roles.values())
        if path.startswith('/roles/'):
            role=self.roles[path.split('/')[-1]]
            if method=='GET': return deepcopy(role)
            workflows={p['machine_name'] for p in data.get('workflow_permissions',role['workflow_permissions'])}
            assert all(t['machine_name'] in workflows for t in data.get('transition_permissions',[])), 'Transition permissions require workflow access'
            if self.fail_role and self.publishes:
                self.fail_role=False
                raise AppError(503,'Role update failed after publishing')
            role.update(deepcopy(data)); return role
        if path=='/workflow-state-machines':
            return {'published_items':[deepcopy(self.workflow)],'draft_items':[]}
        if path=='/workflow-state-machines/workflow-id': return deepcopy(self.workflow)
        if path=='/workflow-state-machines/validate': return {'can_publish':True}
        if path.endswith('/draft'): return {'id':'draft'}
        if path.endswith('/publish'):
            self.publishes+=1; self.workflow['definition']=deepcopy(data['definition'])
            return {'state_machine':deepcopy(self.workflow)}
        if path=='/field-library/field-types':
            return {'items':[dict(code=t,engine_type=t,selectable=True) for t in ('string','text','enum','boolean','date','email')]}
        if path=='/field-library/fields':
            if method=='GET': return {'items':list(self.fields.values())}
            key=data['field_key']; self.fields[key]={'identity':{'field_key':key,'library_field_id':key},'version':{'version_id':key}}
            return self.fields[key]
        if path=='/method-library/methods':
            if method=='GET': return {'items':self.methods}
            row={'method_id':data['name'],'name':data['name']}; self.methods.append(row)
            return {'identity':row}
        if path=='/email-templates':
            if method=='GET': return {'items':self.templates}
            row={**data,'template_id':data['name']};self.templates.append(row);return row
        raise AssertionError((method,path))

@pytest.fixture
def system(monkeypatch):
    db=DB();api=API()
    monkeypatch.setattr(base.psycopg,'connect',lambda *a,**kw:db)
    return api,db

def test_fresh_install_grants_workflow_before_participation(system):
    api,db=system
    base.install(api,'unused')
    assert db.markers=={'offboarding-v1','offboarding-participation-v1'}
    assert api.publishes==1
    for name,role in api.roles.items():
        keys={p['transition_key'] for p in role['transition_permissions']}
        assert 'employee_handover_return' in keys
        assert ('employee_handover_submit' in keys)==(name=='hrms_application_service')
    base.install(api,'unused')
    assert api.publishes==1

def test_upgrade_preserves_revoked_human_workflow_access(system):
    api,db=system
    db.markers.add('offboarding-v1')
    base.install(api,'unused')
    assert api.roles['hrms_hr_full']['workflow_permissions']==[]
    assert api.roles['hrms_hr_full']['transition_permissions']==[]
    assert api.roles['hrms_application_service']['workflow_permissions']

def test_retry_after_publish_finishes_roles_without_duplicate_version(system):
    api,db=system;api.fail_role=True
    with pytest.raises(AppError):base.install(api,'unused')
    assert api.publishes==1
    assert 'offboarding-participation-v1' not in db.markers
    base.install(api,'unused')
    assert api.publishes==1
    assert 'offboarding-participation-v1' in db.markers
