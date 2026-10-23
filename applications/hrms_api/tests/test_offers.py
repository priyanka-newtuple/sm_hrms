import pytest
from hrms_app.offers import authorize_offer_request, offer_metadata_access
from hrms_app.platform import Actor
from hrms_app.errors import AppError
from hrms_app.policy import permission_key

ORG='org'
ID='00000000-0000-0000-0000-000000000001'

def actor(caps=True):
    return Actor('hr',ORG,'human-token',frozenset(),frozenset({permission_key(ORG,'cockpit:view')} if caps else set()))

class Platform:
    def __init__(self, foreign=False): self.calls=[]; self.foreign=foreign
    def request(self, method, path, token):
        assert method=='GET' and token=='human-token'
        self.calls.append(path)
        if path=='/entity-types': return {'items':[{'entity_type_id':'offer','name':'hrms_offer'},{'entity_type_id':'employee','name':'HRMS.Employee'}]}
        if path.endswith('/active'): return {'entity_type':'hrms_offer','is_active':True}
        return {'organization_id':'other' if self.foreign else ORG,'entity_type_id':'offer'}

def test_offer_creation_uses_human_metadata():
    p=Platform();authorize_offer_request(p,actor(),'entity-records',{'entity_type_id':'offer','data':{}})
    assert p.calls==['/entity-types']

@pytest.mark.parametrize('payload',[{'entity_type_id':'employee'},{'entity_type_id':'offer','organization_id':'other'}])
def test_no_employee_or_cross_tenant_creation(payload):
    with pytest.raises(AppError): authorize_offer_request(Platform(),actor(),'entity-records',payload)

def test_requires_cockpit_permission():
    p=Platform()
    with pytest.raises(AppError): authorize_offer_request(p,actor(False),'entity-records',{'entity_type_id':'offer'})
    assert not p.calls

def test_native_offer_enrollment():
    authorize_offer_request(Platform(),actor(),'workflow-state-machines/offers/enrollments',{'entity_id':ID})

def test_cross_tenant_enrollment_denied():
    with pytest.raises(AppError): authorize_offer_request(Platform(True),actor(),'workflow-state-machines/offers/enrollments',{'entity_id':ID})

def test_metadata_requires_native_grants_and_excludes_other_settings():
    a=actor();assert not offer_metadata_access(a,'forms/config')
    a=Actor(a.user_id,a.organization_id,a.token,a.roles,a.permissions|{'entity_record:write','workflow:read','form:read'})
    assert offer_metadata_access(a,'forms/config')
    assert not offer_metadata_access(a,'users')
    assert not offer_metadata_access(a,'workflow-state-machines/offers/enrollments')

def test_offer_board_reads_human_scoped_enrollments():
    from hrms_app.offers import offer_workflow_rows
    a=actor();a=Actor(a.user_id,a.organization_id,a.token,a.roles,a.permissions|{'workflow:read'})
    class Board:
        def request(self, method, path, token, **kwargs):
            assert token=='human-token'
            if path=='/workflow-state-machines':
                return {'published_items':[{'machine_name':'offers','entity_type':'hrms_offer','is_active':True,'version':1,'name':'Offers','definition':{'states':[{'name':'Draft','tags':['initial']}]}}]}
            assert kwargs['params']['machine_name']=='offers'
            return {'items':[{'entity_id':ID,'entity_type':'hrms_offer','organization_id':ORG,'machine_name':'offers','machine_version':1,'current_state':'Draft','summary_fields':{'identifier':'Offer 1'}}],'has_more':False}
    rows=offer_workflow_rows(Board(),a)
    assert len(rows)==1 and rows[0]['title']=='Offer 1'
    assert rows[0]['workflow_configuration']['machine_name']=='offers'
    assert not rows[0]['is_terminal']
