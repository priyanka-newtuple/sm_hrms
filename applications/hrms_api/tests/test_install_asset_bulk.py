from copy import deepcopy
import pytest
from hrms_app.install_asset_bulk import migrate_method_form
from hrms_app.errors import AppError

class Api:
    def __init__(self):
        self.calls=[]
        self.drafts=[]
        self.current={'entity_type':'HRMS.Asset','is_active':True,'machine_name':'hrms_asset','definition':{'states':[{'name':'available','method_refs':[{'method_id':'m','version_id':'v1'}]}],'transitions':[]},'canvas_metadata':{'x':1}}
        self.method={'identity':{'entity_types':['HRMS.Asset']},'version':{'version_id':'v1'},'fields':[{'field_key':'asset_tag','library_field_id':'tag','field_version_id':'f1','required':True,'position':0},{'field_key':'custom','library_field_id':'custom','field_version_id':'f2','required':True,'position':1,'label':'Keep this'}]}
    def call(self,method,path,**kw):
        self.calls.append((method,path,deepcopy(kw)))
        if method=='GET' and path=='/workflow-state-machines':
            return {'published_items':[self.current]} if kw['params']['scope']=='published' else {'draft_items':self.drafts}
        if method=='GET': return deepcopy(self.method)
        if method=='PUT': return {'version':{'version_id':'v2'}}
        if path.endswith('/draft'):return {'id':'draft'}
        return {}

def test_preserves_native_fields_and_graph():
    api=Api()
    migrate_method_form(api)
    fields=next(k['json']['fields'] for m,p,k in api.calls if m=='PUT')
    assert fields[0]['required'] is False
    assert fields[1]['required'] is True and fields[1]['label']=='Keep this'
    published=api.calls[-1][2]['json']
    assert published['definition']['states'][0]['method_refs'][0]['version_id']=='v2'
    assert published['canvas_metadata']=={'x':1}
    assert api.current['definition']['states'][0]['method_refs'][0]['version_id']=='v1'

@pytest.mark.parametrize('conflict',['draft','pending_method','shared'])
def test_conflicts_fail_before_writes(conflict):
    api=Api()
    if conflict=='draft':api.drafts=[{'id':'human-draft'}]
    if conflict=='pending_method':api.method['version']['version_id']='unpublished'
    if conflict=='shared':api.method['identity']['entity_types'].append('Other')
    with pytest.raises(AppError):migrate_method_form(api)
    assert all(m=='GET' for m,p,k in api.calls)
