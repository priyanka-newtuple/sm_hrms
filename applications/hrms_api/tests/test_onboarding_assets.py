import pytest
from types import SimpleNamespace
from hrms_app.errors import AppError
from hrms_app.onboarding_assets import ensure_relation, issue, evidence


def test_relation_retry_is_idempotent_and_rejects_wrong_employee(monkeypatch):
    monkeypatch.setenv('HRMS_ASSET_EMPLOYEE_RELATION','ISSUED_TO')
    rows=[];writes=[]
    def call(method,path,**kw):
        if method=='GET':return {'organization_id':'org','items':rows}
        rows.append(kw['json']);writes.append(kw['json'])
        raise AppError(503,'Response lost after relationship was saved')
    p=SimpleNamespace(org='org',call=call)
    with pytest.raises(AppError):ensure_relation(p,'asset','employee')
    ensure_relation(p,'asset','employee')
    assert len(writes)==1
    with pytest.raises(AppError):ensure_relation(p,'asset','another-employee')


def test_multiple_asset_evidence_excludes_other_employee_and_unissued():
    records=[{'organization_id':'org','entity_id':key,'data':{'issued_employee_id':employee,'asset_tag':key}}
             for key,employee in [('a','employee'),('b','employee'),('c','other'),('d','employee')]]
    p=SimpleNamespace(org='org',records=lambda *_:records,states=lambda _:dict(a='issued',b='issued',c='issued',d='available'))
    assert evidence(p,'employee').splitlines()==['a |  | a','b |  | b']


def test_issue_requires_current_work_and_exact_employee(monkeypatch):
    import hrms_app.onboarding_assets as module
    from hrms_app.assets import AssetCommand
    actor=SimpleNamespace(organization_id='org',roles=set(),permissions={'tenant.org.hrms.asset:manage'},token='human')
    assets=SimpleNamespace(platform=object(),execute=lambda *a:pytest.fail('Should not issue'))
    command=AssetCommand(action='issue',idempotency_key='test-key-1',data={'issued_employee_id':'other'})
    monkeypatch.setattr(module,'context',lambda *a:({},False))
    with pytest.raises(AppError) as e:issue(assets,actor,'employee','workflow','asset',command)
    assert e.value.status==403
    monkeypatch.setattr(module,'context',lambda *a:({},True))
    with pytest.raises(AppError) as e:issue(assets,actor,'employee','workflow','asset',command)
    assert e.value.status==422
