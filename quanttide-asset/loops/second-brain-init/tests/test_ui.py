"""HTTP boundary + real Git UI tests. All recorded feedback is explicitly simulated."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('brain_ui',ROOT/'ui/app.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
BASE={'chinese_name':'示例工程','short_name':'sample','english_name':'sample-engineering','overview':'测试领域。','boundary':'包含演示资料。','neighbors':'正式资料属于业务领域。','provider':'local'}

class UITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='second-brain-ui-test-')
        self.studio=ui.Studio(self.temp.name,test_mode=True)
        self.server=ui.ThreadingHTTPServer(('127.0.0.1',0),ui.Handler)
        self.server.studio=self.studio;self.server.token='test-session-token'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,payload=None,headers=None):
        h={'X-Session-Token':self.server.token,'Content-Type':'application/json'};h.update(headers or {})
        request=Request(self.url+path,data=json.dumps(payload).encode() if payload is not None else None,headers=h)
        try:
            with urlopen(request,timeout=10) as r:return r.status,r.read()
        except HTTPError as exc:return exc.code,exc.read()
    def json(self,path,payload=None):
        code,raw=self.request(path,payload);self.assertEqual(code,200,raw);return json.loads(raw)
    def wait(self,key):
        until=time.monotonic()+120
        while time.monotonic()<until:
            result=self.json('/api/runs/'+key)
            if key not in self.studio.active:return self.json('/api/runs/'+key)
            time.sleep(.03)
        self.fail('worker timed out')
    def plan(self,values=None):
        key=self.json('/api/plan',values or BASE)['id'];v=self.wait(key);self.assertEqual(v['status'],'review',v);return key,v
    def execute(self,values=None):
        key,v=self.plan(values);self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'automated-ui-test'})
        v=self.wait(key);self.assertEqual(v['status'],'completed',v);return key,v
    def accept(self,key,v):
        return self.json('/api/runs/'+key+'/acceptance',{'signature':v['report']['signature'],'reviewer':'automated-ui-test','meaning':'passed','navigation':'passed','usability':'improve','notes':'模拟测试，需要更清楚的示例。'})
    def test_cross_origin_missing_token_and_foreign_host_blocked(self):
        self.assertEqual(self.request('/api/info',headers={'X-Session-Token':''})[0],400)
        self.assertEqual(self.request('/api/plan',BASE,{'Origin':'https://foreign.example'})[0],400)
        self.assertEqual(self.request('/api/info',headers={'Host':'foreign.example'})[0],400)
        self.assertFalse((Path(self.temp.name)/'runs').exists())
    def test_invalid_input_and_github_disabled_before_plan(self):
        for data in [{},dict(BASE,short_name='../escape'),dict(BASE,provider='github')]:self.assertEqual(self.request('/api/plan',data)[0],400)
        self.assertFalse((Path(self.temp.name)/'runs').exists())
    def test_naming_rules_and_direct_request_rejection(self):
        rules=self.json('/api/naming-rules')
        self.assertIn('journal',rules['reserved'])
        cases=[('short_name','My Project','小写'),('short_name','sample_name','下划线'),('short_name','-sample','开头'),('short_name','a--b','单个'),('short_name','journal','资产类别'),('short_name',42,'文字'),('english_name','x'*73,'72'),('overview','   ','领域用途')]
        for key,value,expected in cases:
            with self.subTest(key=key,value=value):
                code,raw=self.request('/api/plan',dict(BASE,**{key:value}))
                self.assertEqual(code,400);self.assertIn(expected,json.loads(raw)['error'])
        self.assertFalse((Path(self.temp.name)/'runs').exists())
        good=dict(BASE,english_name='x'*72,short_name='x'*60)
        self.assertTrue(ui.validate_request(good)['valid'])
        for repo in ui.e.asset_map(ui.validate_request(good)['domain'],ui.e.read_yaml(ui.e.SPEC)).values():
            ui.e.slug(repo['repo'])

    def test_confirm_real_execution_report_and_feedback(self):
        key,v=self.plan();work=Path(v['plan']['workspace']);self.assertFalse(work.exists())
        for data in [{'plan_id':v['plan']['id'],'reviewer':'tester'}, {'plan_id':'wrong','confirmed':True,'reviewer':'tester'}]:
            self.assertEqual(self.request('/api/runs/'+key+'/execute',data)[0],400);self.assertFalse(work.exists())
        self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'automated-test'})
        v=self.wait(key);self.assertEqual(v['status'],'completed',v)
        self.assertEqual(v['completed'],27);self.assertTrue(v['report']['technical_passed']);self.assertEqual(len(v['report']['rows']),7)
        self.assertEqual(len(list((work/'repositories').iterdir())),8)
        self.assertTrue(v['report']['simulated']);self.assertIsNone(v['acceptance'])
        result=self.accept(key,v);self.assertEqual(result['overall'],'needs-improvement');self.assertTrue(result['simulated'])
        code,html=self.request('/api/runs/'+key+'/export');self.assertEqual(code,200);self.assertIn('模拟反馈'.encode(),html);self.assertIn('需改进'.encode(),html)
        self.assertEqual(self.request('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'x'})[0],400)
    def test_changed_files_invalidate_acceptance(self):
        key,v=self.execute();self.accept(key,v)
        path=Path(v['plan']['workspace'])/'repositories/quanttide-sample/README.md'
        path.write_text(path.read_text()+'\n人工改动。\n')
        self.json('/api/runs/'+key+'/verify',{});fresh=self.wait(key)
        self.assertEqual(fresh['status'],'paused');self.assertFalse(fresh['report']['technical_passed']);self.assertTrue(fresh['acceptance']['stale'])
        self.assertEqual(self.request('/api/runs/'+key+'/acceptance',{'signature':v['report']['signature'],'reviewer':'x'})[0],400)
    def test_document_allowlist_and_export_escape(self):
        key,v=self.execute(dict(BASE,chinese_name='<script>alert(1)</script>'))
        doc=self.json('/api/runs/'+key+'/document',{'name':'quanttide-sample/README.md'});self.assertIn('<script>',doc['text'])
        for path in ['../../etc/passwd','quanttide-sample/.git/config','quanttide-sample/../README.md']:
            self.assertEqual(self.request('/api/runs/'+key+'/document',{'name':path})[0],400)
        code,data=self.request('/api/runs/'+key+'/export');self.assertEqual(code,200);self.assertNotIn(b'<script>',data);self.assertIn(b'&lt;script&gt;',data)
    def test_failed_final_verification_still_exposes_readable_report(self):
        key,v=self.plan()
        original=ui.e.verify
        def fail(plan,approval=None):
            report=original(plan,approval)
            report['status']='failed'
            report['details'][0].update(passed=False,reason='模拟发现文档格式问题')
            return report
        with patch.object(ui.e,'verify',fail):
            self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'automated-test'})
            result=self.wait(key)
        self.assertEqual(result['status'],'paused')
        self.assertFalse(result['report']['technical_passed'])
        self.assertEqual(result['report']['failures'][0]['reason'],'模拟发现文档格式问题')
    def test_restart_marks_inflight_run_paused(self):
        key,v=self.plan();folder=self.studio.folder(key);self.studio.set_meta(folder,status='running')
        restarted=ui.Studio(self.temp.name,test_mode=True)
        self.assertEqual(restarted.view(key)['status'],'paused')
        self.assertIn('上次窗口服务',restarted.view(key)['error'])
    def test_request_log_file_busy_does_not_pause_creation(self):
        original=ui.e.save
        def save(path,value):
            if Path(path).name=='requests.json':raise PermissionError(5,'simulated Windows file busy')
            return original(path,value)
        with patch.object(ui.e,'save',side_effect=save):
            key,v=self.plan()
            self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'automated-test'})
            result=self.wait(key)
        self.assertEqual(result['status'],'completed',result.get('error'))
        self.assertEqual(self.studio.request_log_errors[key]['category'],'local-file-busy')

if __name__=='__main__':unittest.main()
