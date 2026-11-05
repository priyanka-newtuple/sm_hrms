from contextlib import nullcontext
from types import SimpleNamespace
import httpx
import pytest
from hrms_app import onboarding_payroll as payroll
from hrms_app.errors import AppError


class Database:
    def __init__(self): self.row = None
    def execute(self, sql, args=()):
        if sql.startswith('SELECT'): return SimpleNamespace(fetchone=lambda: self.row)
        if sql.startswith('INSERT'):
            self.row = (1, args[2], args[3], None)
            return SimpleNamespace(fetchone=lambda: (1,))
        if sql.startswith('UPDATE'): self.row = (*self.row[:3], args[0].obj)
        return SimpleNamespace(fetchone=lambda: None)


def fixture(monkeypatch):
    monkeypatch.setenv('HRMS_RAZORPAY_MODE', 'mock')
    db = Database()
    record = {'organization_id':'org', 'data':{'first_name':'Test','last_name':'Employee','work_email':'employee@example.com','employment_type':'fte'}}
    writes = []
    def request(method, path, **kwargs):
        assert kwargs['token']=='human'
        if method=='GET': return record
        writes.append(kwargs['json']['data'])
    platform=SimpleNamespace(request=request)
    actor=SimpleNamespace(organization_id='org',token='human')
    journal=SimpleNamespace(lock=lambda org:nullcontext(db),audit=lambda *args:None)
    return platform,journal,actor,record,writes,db


def test_mock_and_retry_reuse_one_receipt(monkeypatch):
    p,j,a,r,w,db=fixture(monkeypatch)
    monkeypatch.setattr(httpx,'post',lambda *a,**k:pytest.fail('mock must not contact provider'))
    first=payroll.register(p,j,a,'employee')
    monkeypatch.setattr(payroll,'create_person',lambda *a:pytest.fail('retry must not recreate'))
    assert payroll.register(p,j,a,'employee')==first
    assert first=={'razorpay_employee_id':'1','razorpay_people_id':'1','razorpay_mode':'mock'}
    assert 'employee_code' not in first and 'platform_user_id' not in first


def test_ambiguous_failure_blocks_duplicate(monkeypatch):
    p,j,a,r,w,db=fixture(monkeypatch)
    def timeout(*args): raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(payroll,'create_person',timeout)
    with pytest.raises(AppError,match='could not be confirmed'): payroll.register(p,j,a,'employee')
    monkeypatch.setattr(payroll,'create_person',lambda *a:pytest.fail('must reconcile'))
    with pytest.raises(AppError,match='uncertain'): payroll.register(p,j,a,'employee')
    assert not w


@pytest.mark.parametrize('change',['tenant','payload','mode'])
def test_receipt_isolation(monkeypatch,change):
    p,j,a,r,w,db=fixture(monkeypatch)
    payroll.register(p,j,a,'employee')
    if change=='tenant': r['organization_id']='another'
    if change=='payload': r['data']['work_email']='different@example.com'
    if change=='mode':
        monkeypatch.setenv('HRMS_RAZORPAY_MODE','live')
        monkeypatch.setenv('HRMS_RAZORPAY_API_ID','123')
        monkeypatch.setenv('HRMS_RAZORPAY_API_KEY','test-key')
    monkeypatch.setattr(payroll,'create_person',lambda *a:pytest.fail('must not create'))
    with pytest.raises(AppError): payroll.register(p,j,a,'employee')


def test_live_exact_payroll_contract(monkeypatch):
    monkeypatch.setenv('HRMS_RAZORPAY_API_ID','2631')
    monkeypatch.setenv('HRMS_RAZORPAY_API_KEY','test-key')
    data={'email':'employee@example.com','name':'Test Employee','type':'employee'}
    def post(url,**kw):
        assert url=='https://payroll.razorpay.com/api/people'
        assert kw['follow_redirects'] is False
        assert kw['json']=={'auth':{'id':2631,'key':'test-key'},'request':{'type':'people','sub-type':'create'},'data':data}
        return httpx.Response(200,json={'status':'ok','people-id':36286,'employee-id':4},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',post)
    assert payroll.create_person('live',data,1)['employee-id']==4


@pytest.mark.parametrize('mode',['disabled','sandbox','anything'])
def test_unsafe_modes_fail_closed(monkeypatch,mode):
    p,j,a,r,w,db=fixture(monkeypatch)
    monkeypatch.setenv('HRMS_RAZORPAY_MODE',mode)
    with pytest.raises(AppError): payroll.register(p,j,a,'employee')
    assert db.row is None



def test_writeback_denial_preserves_receipt_and_retries_without_recreating(monkeypatch):
    p,j,a,r,w,db=fixture(monkeypatch)
    original=p.request
    def denied(method, path, **kwargs):
        if method == 'PUT':
            raise AppError(403, 'Not allowed to edit read-only fields')
        return original(method, path, **kwargs)
    p.request=denied
    with pytest.raises(AppError, match='existing registration will be reused') as error:
        payroll.register(p,j,a,'employee')
    assert error.value.status == 403
    assert db.row[3]['employee-id'] == 1
    assert not w
    p.request=original
    monkeypatch.setattr(payroll,'create_person',lambda *args:pytest.fail('must reuse receipt'))
    assert payroll.register(p,j,a,'employee')['razorpay_employee_id'] == '1'
    assert len(w) == 1


def test_release_does_not_globally_lock_integration_result_fields():
    import json
    from pathlib import Path
    package=next((parent / 'configuration/hrms/release.json' for parent in Path(__file__).resolve().parents if (parent / 'configuration/hrms/release.json').is_file()), None)
    if package is None:
        pytest.skip('Release configuration is validated separately outside the application image')
    release=json.loads(package.read_text(encoding='utf-8'))
    fields={obj['match']:obj['payload'] for obj in release['objects'] if obj['kind']=='field'}
    for key in payroll.FIELDS:
        assert fields[key]['settings']['read_only'] is False
