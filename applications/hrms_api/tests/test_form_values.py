import pytest
from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.form_values import editable_values, record_input
from hrms_app.project_contracts import CustomerInput
from hrms_app.performance_contracts import GoalInput

@pytest.mark.parametrize('kind',['Employee','Customer','Project','Allocation','LeaveRequest','PerformanceCycle','PerformanceGoal','ProjectFeedback','WorkFromHomeRequest','WorkFromHomePolicy','Asset','Policy','LearningEvent','HolidayCalendar','JobDescription','JobOpening'])
def test_native_changes_are_enforced_for_each_kind(monkeypatch,kind):
    fields=[{'field':'reference','type':'enum','enum_values':['new'],'required':True}, {'field':'locked','type':'string','read_only':True}]
    monkeypatch.setattr('hrms_app.form_values.configured_form',lambda *a:{'fields':fields})
    def validate(data,current=None): return editable_values(None,'HRMS.'+kind,data,current=current)
    assert validate({'reference':'new'})=={'reference':'new'}
    for data in ({'retired':5,'reference':'new'}, {}, {'reference':'old'}, {'reference':'new','locked':'injected'}):
        with pytest.raises(AppError) as error: validate(data)
        assert error.value.status==422
    fields[0]['required']=False
    assert validate({})=={}
    assert validate({'reference':'new'}, {'locked':'original'})=={'reference':'new'}


def test_removed_defaults_do_not_reappear_and_protected_fields_are_rejected(monkeypatch):
    fields=[{'field':'name','type':'string'},{'field':'created_by','type':'string'},{'field':'reference','type':'integer'}]
    monkeypatch.setattr('hrms_app.form_values.configured_form',lambda *a:{'fields':fields})
    assert record_input(None,'HRMS.Customer',CustomerInput,{'name':'Acme','reference':12})=={'name':'Acme','reference':12}
    with pytest.raises(AppError): record_input(None,'HRMS.Customer',CustomerInput,{'name':'Acme','created_by':'attacker'})


def test_configured_enum_can_extend_seeded_choices(monkeypatch):
    fields=[dict(f) for f in pack_by_type('HRMS.PerformanceGoal').fields]
    next(f for f in fields if f['field']=='category').update(type='enum',enum_values=['mentoring'])
    monkeypatch.setattr('hrms_app.form_values.configured_form',lambda *a:{'fields':fields})
    data=dict(title='Coach',category='mentoring',measurement='Two sessions',weight=20,target_date='2030-01-01')
    assert record_input(None,'HRMS.PerformanceGoal',GoalInput,data)['category']=='mentoring'
