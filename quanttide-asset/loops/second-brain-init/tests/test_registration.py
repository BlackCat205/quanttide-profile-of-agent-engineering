import copy,json,subprocess
from unittest.mock import patch
import unittest
from test_ui import UITests,ui,BASE

class ReportCompatibilityTests(unittest.TestCase):
    def test_legacy_read_failures_are_unknown_without_rewriting_original(self):
        old={'checked_at':'original-time','failures':[{'repo':'quanttide','reason':'工作区不干净'}]+[{'repo':'sample','reason':'git ls-remote 失败（退出码 128）。'} for _ in range(11)],'rows':[],'repositories':[],'technical_passed':False}
        original=copy.deepcopy(old);result=ui.readable_report(old)
        self.assertEqual(sum(x['status']=='unknown' for x in result['failures']),11)
        self.assertEqual(sum(x['status']=='failed' for x in result['failures']),1)
        self.assertEqual(old,original);self.assertTrue(result['historical']);self.assertFalse(result['technical_passed']);self.assertEqual(result['checked_at'],'original-time')
    def test_current_classification_is_not_overridden(self):
        report={'failures':[{'status':'failed','reason':'git ls-remote 失败'}]}
        self.assertEqual(ui.readable_report(report),report)

class OrganizationUITests(UITests):
    def test_nonowner_organization_blocks_before_plan(self):
        self.studio.enable_github=True
        identity={'owner_type':'Organization','owner':'TestOrg','owner_id':2,'id':1,'login':'Tester'}
        with patch.object(ui.e,'github_identity',return_value=identity),patch.object(ui.e,'command',return_value=subprocess.CompletedProcess([],0,json.dumps({'state':'active','role':'member'}),'')):
            code,_=self.request('/api/plan',dict(BASE,provider='github',test_organization='TestOrg'))
            self.assertEqual(code,400)
        self.assertFalse((self.studio.storage/'runs').exists())
    def test_owned_organization_is_recorded_but_rule_failure_blocks_creation(self):
        self.studio.enable_github=True
        identity={'owner_type':'Organization','owner':'TestOrg','owner_id':2,'id':1,'login':'Tester'}
        with patch.object(ui.e,'github_identity',return_value=identity),patch.object(ui.e,'command',return_value=subprocess.CompletedProcess([],0,json.dumps({'state':'active','role':'admin'}),'')),patch.object(ui.survey,'inspect',return_value={'rules':{'status':'changed'}}),patch.object(ui.e,'make_plan') as make:
            key=self.json('/api/plan',dict(BASE,provider='github',test_organization='TestOrg'))['id'];view=self.wait(key)
            self.assertEqual(view['organization'],'TestOrg');self.assertEqual(view['status'],'paused');make.assert_not_called()
for name in list(UITests.__dict__):
    if name.startswith('test_'):setattr(OrganizationUITests,name,None)
del UITests
