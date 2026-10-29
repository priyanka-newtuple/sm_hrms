from copy import deepcopy
from types import SimpleNamespace
import pytest
from hrms_app import install_offboarding_checklist as installer
from hrms_app.offboarding_catalog import FIELDS
from hrms_app.errors import AppError
from test_install_offboarding import API, DB


class ChecklistAPI(API):
    def __init__(self):
        super().__init__()
        self.workflow=deepcopy(self.workflow)
        self.entity={'schema_definition':{'fields':deepcopy(FIELDS),'identifier_template':'EXT-{{seq}}'}}
        self.writes=[]
        for r in self.roles.values():r['workflow_permissions']=[{'machine_name':self.workflow['machine_name']}]
        self.roles['office_admin']=dict(id='office_admin',name='office_admin',field_permissions=[],workflow_permissions=[],transition_permissions=[],entity_permissions=[])
    def call(self,method,path,**kwargs):
        if method!='GET':self.writes.append((method,path,deepcopy(kwargs)))
        if path.startswith('/entity-types/'):
            if method=='PUT': self.entity.update(kwargs['json'])
            return deepcopy(self.entity)
        if path=='/field-library/field-types':return {'items':[dict(code=t,engine_type=t,selectable=True) for t in ('string','text','enum','boolean','datetime','email','document')]}
        return super().call(method,path,**kwargs)


@pytest.fixture
def system(monkeypatch):
    from hrms_app import install_offboarding_notifications
    monkeypatch.setattr(install_offboarding_notifications, 'install', lambda api: None)
    api=ChecklistAPI(); db=DB(); old=db.execute
    db.execute=lambda sql,params=():SimpleNamespace(fetchone=lambda:None) if 'pg_advisory_lock' in sql else old(sql,params)
    monkeypatch.setattr(installer.psycopg,'connect',lambda *a,**kw:db)
    monkeypatch.setenv('HRMS_PUBLIC_URL','https://hrms.example.com')
    return api,db


def test_installs_native_forms_and_preserves_versions(system):
    api,db=system
    installer.install(api,'unused',api.workflow)
    assert api.publishes==1 and len(api.methods)==8
    assert len(api.templates)==5
    assert not any('/enrollments' in path for _,path,_ in api.writes)
    assert all('{{workspace_url}}' in t['body_html'] and 'https://' not in t['body_html'] for t in api.templates)
    hr=api.roles['hrms_hr_full']
    assert not any(p['can_edit'] for p in hr['field_permissions'] if p['field_name']=='exit_acknowledgment')
    assert not any(p['can_view'] for p in api.roles['office_admin']['field_permissions'])
    count=len(api.writes)
    installer.install(api,'unused',api.workflow)
    assert len(api.writes)==count


def test_permission_failure_after_publish_resumes_without_republishing(system):
    api,db=system;api.fail_role=True
    with pytest.raises(AppError):installer.install(api,'unused',api.workflow)
    assert api.publishes==1 and not db.markers
    installer.install(api,'unused',api.workflow)
    assert api.publishes==1 and db.markers


def test_custom_workflow_is_not_overwritten(system):
    api,db=system
    api.workflow['definition']['entity_schema']['fields'].append({'field':'custom_legal_check','type':'string'})
    with pytest.raises(AppError,match='reviewed migration'):installer.install(api,'unused',api.workflow)
    assert not api.writes


def test_revoked_hr_workflow_access_is_preserved(system):
    api,db=system
    api.roles['hrms_hr_full']['workflow_permissions']=[]
    installer.install(api,'unused',api.workflow)
    assert api.roles['hrms_hr_full']['workflow_permissions']==[]
    assert api.roles['hrms_hr_full']['transition_permissions']==[]


def test_unchanged_native_draft_alias_is_reused(system):
    api,db=system
    draft=deepcopy(api.workflow)
    draft['id']='existing-draft'
    for t in draft['definition']['transitions']:
        t['from_state']=t.pop('from')
    old=api.call
    def call(method,path,**kwargs):
        if path=='/workflow-state-machines':
            return {'draft_items':[{'id':'existing-draft'}]}
        if path=='/workflow-state-machines/existing-draft':return draft
        if path.endswith('/draft'):raise AssertionError('Must reuse unchanged draft')
        return old(method,path,**kwargs)
    api.call=call
    installer.install(api,'unused',api.workflow)
    assert api.publishes==1


def test_changed_draft_is_preserved(system):
    api,db=system
    draft=deepcopy(api.workflow)
    draft['definition']['states'][0]['description']='User draft changes'
    old=api.call
    def call(method,path,**kwargs):
        if path=='/workflow-state-machines':return {'draft_items':[{'id':'existing-draft'}]}
        if path=='/workflow-state-machines/existing-draft':return draft
        return old(method,path,**kwargs)
    api.call=call
    with pytest.raises(AppError,match='existing offboarding draft'):
        installer.install(api,'unused',api.workflow)
    assert not api.writes
