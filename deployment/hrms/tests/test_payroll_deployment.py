import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('configure_payroll',ROOT/'configure_payroll.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_mock_discards_live_credentials(tmp_path):
    path=tmp_path/'payroll.env'
    module.configure({'HRMS_RAZORPAY_MODE':'mock','HRMS_RAZORPAY_API_ID':'123','HRMS_RAZORPAY_API_KEY':'secret'},path)
    assert 'secret' not in path.read_text()
    assert "HRMS_RAZORPAY_MODE='mock'" in path.read_text()


@pytest.mark.parametrize('payload',[{'HRMS_RAZORPAY_MODE':'sandbox'},{'HRMS_RAZORPAY_MODE':'live'},{'HRMS_RAZORPAY_MODE':'live','HRMS_RAZORPAY_API_ID':'123','HRMS_RAZORPAY_API_KEY':'bad\nvalue'}])
def test_unsafe_configuration_creates_no_file(tmp_path,payload):
    path=tmp_path/'payroll.env'
    with pytest.raises(ValueError): module.configure(payload,path)
    assert not path.exists()


def test_live_credentials_written_without_interpolation(tmp_path):
    path=tmp_path/'payroll.env'
    module.configure({'HRMS_RAZORPAY_MODE':'live','HRMS_RAZORPAY_API_ID':'123','HRMS_RAZORPAY_API_KEY':'test-key'},path)
    assert "HRMS_RAZORPAY_API_ID='123'" in path.read_text()

def test_native_graph_has_cancel_from_every_unfinished_state():
    from test_offboarding_stage_forms import package
    release={'objects':list(package().values())}
    graph=next(x['payload']['definition'] for x in release['objects'] if x['key']=='workflow:HRMS.Employee')
    states=sorted(graph['states'],key=lambda s:s['order'])
    assert [s['name'] for s in states][-4:]==['Payroll Registration','Final HR Sign-off','Onboarding Completed','Onboarding Cancelled']
    for state in states:
        outgoing=[t for t in graph['transitions'] if t['from']==state['name']]
        if 'terminal' in state['tags']: assert not outgoing
        else: assert any(t['to_state']=='Onboarding Cancelled' and not t['required_fields'] and not t['guards'] for t in outgoing)
