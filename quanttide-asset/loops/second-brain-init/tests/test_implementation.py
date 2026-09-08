"""Behavior tests use real git repositories; GitHub calls are never made."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'skills/second-brain-init/scripts'))
import engine as e

BASE={'schema_version':1,'scenario':'new-domain','domain':{'chinese_name':'示例工程','short_name':'sample','english_name':'sample-engineering','overview':'验证知识资产管理。','boundary':'包含可公开的示例资料。','neighbors':'正式生产数据归属具体业务领域。'},'register_root':True}

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='second-brain-test-')
        self.base=Path(self.temp.name);self.work=self.base/'work';self.count=0
        self.provider=e.Provider(self.work)
    def tearDown(self):
        self.temp.cleanup()
    def plan(self,cfg=None):
        self.count+=1
        run=self.base/('run-'+str(self.count))
        config=self.base/('input-'+str(self.count)+'.yaml')
        config.write_text(yaml.safe_dump(cfg or BASE,allow_unicode=True),encoding='utf-8')
        plan=e.make_plan(config,self.work,run)
        return run,plan
    def execute(self,cfg=None):
        run,plan=self.plan(cfg)
        e.approve(run,'automated-test',plan['id'],simulated=True)
        report=e.apply(run)
        self.assertEqual(report['status'],'passed',report)
        return run,plan
    def seed(self,name):
        self.provider.ensure(name,True,name)
    def test_new_domain_real_git_and_root_registration(self):
        run,plan=self.execute()
        self.assertEqual(len(list((self.work/'remotes').glob('*.git'))),8) # seven plus root fixture
        domain=self.provider.repo('quanttide-sample')
        self.assertEqual(len(e.modules(domain)),6)
        self.assertIn('domains/quanttide-sample',e.modules(self.provider.repo('quanttide')))
        self.assertEqual(e.read_json(run/'execution-log.json')['status'],'completed')
        self.assertFalse((run/'execution.lock').exists())
        self.assertTrue(e.read_json(run/'approval-record.json')['simulated'])
        self.assertEqual(e.read_json(run/'verification-report.json')['approval_kind'],'simulated')
        self.assertIn('模拟确认', (run/'result.md').read_text(encoding='utf-8'))
    def test_workspace_lock_blocks_other_run(self):
        run,plan=self.plan()
        e.approve(run,'test',plan['id'],True)
        lock=self.work.parent/('.'+self.work.name+'.second-brain-init.lock')
        lock.write_text('other process')
        with self.assertRaises(e.WorkflowError):e.apply(run)
        self.assertFalse(self.work.exists())
        self.assertEqual(lock.read_text(),'other process')
    def test_unapproved_run_never_creates_workspace(self):
        run,plan=self.plan()
        with self.assertRaises(e.WorkflowError):e.apply(run)
        self.assertFalse(self.work.exists())
    def test_changed_plan_invalidates_approval(self):
        run,plan=self.plan()
        e.approve(run,'test',plan['id'],True)
        plan['operations'][0]['repo']='quanttide-other'
        e.save(run/'execution-plan.json',plan)
        with self.assertRaises(e.WorkflowError):e.apply(run)
        self.assertFalse(self.work.exists())
    def test_idempotent_replan_preserves_commit_ids(self):
        self.execute()
        before={p.name:e.git(p,'rev-parse','HEAD').stdout for p in (self.work/'repositories').iterdir()}
        self.execute()
        after={p.name:e.git(p,'rev-parse','HEAD').stdout for p in (self.work/'repositories').iterdir()}
        self.assertEqual(before,after)
    def test_pauses_then_resumes_without_repeating_commits(self):
        run,plan=self.plan()
        e.approve(run,'test',plan['id'],True)
        original=e.Executor.execute
        def once(executor,op):
            if op['id']=='005':raise e.WorkflowError('injected transient failure before action')
            return original(executor,op)
        with patch.object(e.Executor,'execute',once):
            with self.assertRaises(e.WorkflowError):e.apply(run)
        state=e.read_json(run/'execution-log.json')
        self.assertEqual(state['status'],'paused'); self.assertEqual(len(state['completed']),4)
        self.assertEqual(e.apply(run)['status'],'passed')
        events=e.read_json(run/'execution-log.json')['events']
        completed=[x for x in events if x['status']=='passed']
        self.assertEqual(len(completed),len(plan['operations']))
        self.assertEqual(len({x['op'] for x in completed}),len(completed))
        self.assertTrue(any(x['status']=='failed' for x in events))
    def test_new_plan_refuses_dirty_existing_repository(self):
        self.execute()
        (self.provider.repo('quanttide-sample')/'README.md').write_text('# 人工修改\n',encoding='utf-8')
        with self.assertRaises(e.WorkflowError):self.plan()
    def test_drift_after_approval_blocks_execution(self):
        self.seed('quanttide')
        run,plan=self.plan()
        e.approve(run,'test',plan['id'],True)
        (self.provider.repo('quanttide')/'README.md').write_text('# 有新改动\n',encoding='utf-8')
        with self.assertRaises(e.WorkflowError):e.apply(run)
        self.assertFalse(self.provider.repo('quanttide-sample').exists())
    def test_complete_preserves_existing_readme_and_license(self):
        self.seed('quanttide-sample')
        repo=self.provider.repo('quanttide-sample')
        (repo/'README.md').write_text('# 已有领域\n\n保留这段人工内容。\n\n## 概述\n\n人工概述。\n',encoding='utf-8')
        (repo/'LICENSE').write_text('Existing project license\n',encoding='utf-8')
        e.git(repo,'add','--','README.md','LICENSE');e.git(repo,'commit','-m','docs: manual content');e.git(repo,'push')
        cfg=copy.deepcopy(BASE);cfg.update(scenario='complete-existing',target_repo='quanttide-sample')
        self.execute(cfg)
        self.assertIn('保留这段人工内容',e.text_at(repo,'README.md'))
        self.assertEqual(e.text_at(repo,'README.md').count('## 概述'),1)
        self.assertIn('人工概述。',e.text_at(repo,'README.md'))
        self.assertEqual(e.text_at(repo,'LICENSE'),'Existing project license\n')
    def test_append_replaces_only_empty_coordinate(self):
        self.execute()
        cfg=copy.deepcopy(BASE);cfg.update(scenario='append-assets',target_repo='quanttide-sample',assets=['report'])
        self.execute(cfg)
        self.assertIn('data/report',e.modules(self.provider.repo('quanttide-sample')))
    def test_mount_product_and_aggregate(self):
        self.execute();self.seed('qtsample')
        self.execute({'schema_version':1,'scenario':'mount-product','target_repo':'quanttide-sample','mounts':[{'repo':'qtsample','path':'apps/qtsample'}]})
        cfg={'schema_version':1,'scenario':'aggregate-container','asset_type':'journal','mounts':[{'repo':'quanttide-journal-of-sample-engineering','path':'domains/sample'}]}
        self.execute(cfg)
        self.assertIn('domains/sample',e.modules(self.provider.repo('quanttide-journal')))
        self.assertIn('Apache License',e.text_at(self.provider.repo('quanttide-journal'),'LICENSE'))
    def test_rename_assets_updates_domain_and_root_pointers(self):
        self.execute()
        renames={'quanttide-context-of-sample-engineering':'quanttide-context-of-example-engineering'}
        self.execute({'schema_version':1,'scenario':'rename','renames':renames,'reference_repos':['quanttide-sample','quanttide']})
        url=e.modules(self.provider.repo('quanttide-sample'))['data/context']['url']
        self.assertTrue(url.endswith('quanttide-context-of-example-engineering.git'))
        self.assertFalse(Path(self.provider.remote(next(iter(renames)))).exists())
    def test_release_creates_pushed_tag_and_notes(self):
        self.seed('quanttide-example')
        repo=self.provider.repo('quanttide-example')
        (repo/'CHANGELOG.md').write_text('# 变更记录\n\n## [Unreleased]\n\n- 新增功能。\n',encoding='utf-8')
        e.git(repo,'add','--','CHANGELOG.md');e.git(repo,'commit','-m','docs: changelog');e.git(repo,'push')
        self.execute({'schema_version':1,'scenario':'release','target_repo':'quanttide-example','version':'0.2.0','notes':'完成本地测试。'})
        self.assertIn('## [0.2.0]',e.text_at(repo,'CHANGELOG.md'))
    def test_path_injection_and_missing_fields_fail_before_mutation(self):
        cases=[{'schema_version':1,'scenario':'new-domain'},dict(BASE,target_repo='../outside'),dict(BASE,root_repo='quanttide-sample'),{'schema_version':1,'scenario':'mount-product','target_repo':'quanttide-sample','mounts':[{'repo':'qtsample','path':'../../x'}]}]
        for cfg in cases:
            with self.subTest(cfg=cfg):
                with self.assertRaises(e.WorkflowError):self.plan(cfg)
                self.assertFalse(self.work.exists())
    def test_occupied_mount_is_preserved_and_execution_pauses(self):
        self.execute();self.seed('qtsample')
        repo=self.provider.repo('quanttide-sample')
        path=repo/'apps/qtsample';path.mkdir();(path/'manual.txt').write_text('keep')
        e.git(repo,'add','--','apps/qtsample/manual.txt');e.git(repo,'commit','-m','docs: manual app');e.git(repo,'push')
        cfg={'schema_version':1,'scenario':'mount-product','target_repo':'quanttide-sample','mounts':[{'repo':'qtsample','path':'apps/qtsample'}]}
        run,plan=self.plan(cfg);e.approve(run,'test',plan['id'],True)
        with self.assertRaises(e.WorkflowError):e.apply(run)
        self.assertEqual((path/'manual.txt').read_text(),'keep')
    def test_portable_skill_copy_runs_without_source_tree(self):
        destination=self.base/'copied-skill'
        subprocess.run([sys.executable,str(ROOT/'loops/second-brain-init/install.py'),'--destination',str(destination)],check=True,capture_output=True)
        config=self.base/'request.yaml';config.write_text(yaml.safe_dump(BASE,allow_unicode=True),encoding='utf-8')
        command=[sys.executable,str(destination/'scripts/engine.py'),'plan','--config',str(config),'--workspace',str(self.work),'--run-dir',str(self.base/'portable-run')]
        result=subprocess.run(command,cwd=self.base,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.base/'portable-run/execution-plan.json').is_file())
        result=subprocess.run([sys.executable,str(destination/'scripts/validate_outputs.py')],cwd=self.base,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
    def test_asset_contract_bridge_loads_and_dispatches(self):
        result=subprocess.run([sys.executable,str(ROOT/'asset-entry.py'),'check'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['assets']),6)
        config=self.base/'request.yaml';config.write_text(yaml.safe_dump(BASE,allow_unicode=True),encoding='utf-8')
        result=subprocess.run([sys.executable,str(ROOT/'asset-entry.py'),'run','plan','--config',str(config),'--workspace',str(self.work),'--run-dir',str(self.base/'bridge-run')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.base/'bridge-run/execution-plan.json').is_file())

if __name__=='__main__':unittest.main()
