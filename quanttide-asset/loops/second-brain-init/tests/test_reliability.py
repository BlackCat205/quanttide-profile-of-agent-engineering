"""Failure-oriented checks; public API failures are simulated, local Git is real."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ui'))
import survey
from test_ui import UITests, BASE, ui

class SurveyTests(unittest.TestCase):
    def test_http_failures_are_unknown_not_available(self):
        for code in [401,403,404,429,500]:
            with self.subTest(code=code),patch.object(survey,'urlopen',side_effect=HTTPError('https://api.github.com',code,'error',{},None)):
                result=survey.get('repos/example/test');self.assertEqual(result['status'],'unknown');self.assertEqual(result['http_status'],code)
        with patch.object(survey,'urlopen',side_effect=URLError('offline')):
            self.assertEqual(survey.get('repos/example/test')['status'],'unknown')

    def test_root_documents_are_pinned_and_rule_change_is_visible(self):
        calls=[]
        def fake(path):
            calls.append(path)
            if '/contents/' in path:
                return {'status':'ok','data':{'sha':'old' if 'ref=pinned-rule' in path else 'new','encoding':'base64','content':base64.b64encode(b'# actual directory').decode()}}
            if '/commits/' in path:return {'status':'ok','data':{'sha':'root-commit'}}
            return {'status':'ok','data':{'default_branch':'main'}}
        source={'repository':'quanttide/rules','path':'contract/public-second-brain.md','commit':'pinned-rule'}
        with patch.object(survey,'get',side_effect=fake):r=survey.inspect('example',['quanttide','quanttide-sample'],source)
        self.assertEqual(r['rules']['status'],'changed')
        self.assertEqual(r['repositories'][1]['status'],'exists')
        self.assertEqual(len(r['documents']),3)
        self.assertTrue(all('ref=root-commit' in x for x in calls if '/quanttide/contents/' in x))
        self.assertGreaterEqual(r['finished_at'],r['started_at'])

    def test_new_only_never_reuses_existing_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=ui.e.Provider(tmp,'github','example')
            with patch.object(provider,'info',return_value={'exists':True}),patch.object(ui.e,'command') as cmd:
                with self.assertRaisesRegex(ui.e.WorkflowError,'不能自动复用'):provider.ensure('quanttide-sample',True,'sample',require_new=True)
                cmd.assert_not_called()
            with patch.object(ui.e,'github_identity',return_value={'owner_type':'User'}),patch.object(provider,'info',return_value={'exists':False}),patch.object(ui.e,'command',side_effect=ui.e.WorkflowError('创建冲突')) as cmd:
                with self.assertRaisesRegex(ui.e.WorkflowError,'创建冲突'):provider.ensure('quanttide-sample',True,'sample',require_new=True)
                self.assertEqual(cmd.call_count,1)
                self.assertIn('POST',cmd.call_args.args[0])

    def test_empty_remote_is_distinguishable_from_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=ui.e.Provider(tmp)
            before=ui.e.snapshot(provider,['quanttide-sample'])
            remote=Path(provider.remote('quanttide-sample'));remote.parent.mkdir(parents=True)
            subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
            after=ui.e.snapshot(provider,['quanttide-sample'])
            self.assertEqual(before['quanttide-sample']['remote'],after['quanttide-sample']['remote'])
            self.assertNotEqual(before,after)

    def test_external_change_between_operations_stops_next_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            import yaml
            base=Path(tmp);config=base/'request.yaml';work=base/'work';run=base/'run'
            cfg={'schema_version':1,'scenario':'new-domain','domain':{k:BASE[k] for k in ('chinese_name','short_name','english_name','overview','boundary','neighbors')}}
            config.write_text(yaml.safe_dump(cfg,allow_unicode=True))
            plan=ui.e.make_plan(config,work,run)
            ui.e.approve(run,'automated',plan['id'],simulated=True)
            original=ui.e.snapshot;injected=[]
            def snapshot(provider,names,strict=False):
                observed=original(provider,names,strict)
                path=provider.repo(plan['operations'][0]['repo'])
                if not injected and (path/'.git').exists():
                    (path/'external-change.txt').write_text('another writer changed this repository')
                    injected.append(True)
                return observed
            with patch.object(ui.e,'snapshot',side_effect=snapshot):
                with self.assertRaisesRegex(ui.e.WorkflowError,'执行过程中仓库已变化'):ui.e.apply(run)
            log=ui.e.read_json(run/'execution-log.json')
            self.assertEqual(log['status'],'paused');self.assertEqual(len(log['completed']),1)

class ReliabilityUITests(UITests):
    # Reuse the HTTP fixture; inherited tests run in test_ui.py only.
    def test_readonly_survey_persists_without_creating_runs(self):
        fake={'repositories':[],'documents':{},'rules':{},'started_at':'t','finished_at':'t'}
        with patch.object(ui.survey,'inspect',return_value=fake):
            key=self.json('/api/survey',dict(BASE,survey_organization='quanttide'))['id']
            import time
            for _ in range(100):
                r=self.json('/api/surveys/'+key)
                if r['status']=='completed':break
                time.sleep(.01)
            self.assertEqual(r['report'],fake)
        self.assertFalse((Path(self.temp.name)/'runs').exists())
        self.assertFalse((Path(self.temp.name)/'workspaces').exists())

    def test_remote_created_after_plan_blocks_before_writes(self):
        key,v=self.plan();work=Path(v['plan']['workspace'])
        remote=work/'remotes/quanttide-sample.git';remote.parent.mkdir(parents=True)
        subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
        self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'simulated-test'})
        r=self.wait(key)
        self.assertEqual(r['status'],'paused');self.assertEqual(r['pre_execution']['status'],'blocked')
        self.assertIn('quanttide-sample',r['pre_execution']['changed'])
        self.assertFalse((work/'repositories').exists())

    def test_rule_update_blocks_github_plan_before_engine(self):
        self.studio.enable_github=True
        with patch.object(ui.e,'github_identity',return_value={'owner_type':'User','id':1,'owner_id':1,'owner':'Example'}),patch.object(ui.survey,'inspect',return_value={'rules':{'status':'changed'}}),patch.object(ui.e,'make_plan') as make:
            key=self.json('/api/plan',dict(BASE,provider='github'))['id'];r=self.wait(key)
            self.assertEqual(r['status'],'paused');make.assert_not_called()

# Do not duplicate inherited tests when unittest discovers this module.
for name in list(UITests.__dict__):
    if name.startswith('test_'):setattr(ReliabilityUITests,name,None)
del UITests
