"""Real local Git failure/recovery regression; no real GitHub or Windows execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ui'))
import app as ui
import repair
e=ui.e

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name)/'run';self.work=Path(self.tmp.name)/'work'
        provider=e.Provider(self.work)
        self.plan={'schema_version':2,'version':e.VERSION,'scenario':'new-domain','provider':'local','organization':'quanttide','workspace':str(self.work),'config':{'root_repo':'quanttide'},'names':['quanttide'],'before':e.snapshot(provider,['quanttide']),'operations':[{'id':'001','kind':'ensure-repo','repo':'quanttide','allow_create':True,'title':'test'},{'id':'002','kind':'catalog','repo':'quanttide'},{'id':'003','kind':'finish','repo':'quanttide'}],'checks':[],'engine_sha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),'spec_sha256':hashlib.sha256(e.SPEC.read_bytes()).hexdigest()}
        self.plan['id']=e.digest(self.plan);e.save(self.run/'execution-plan.json',self.plan);e.approve(self.run,'test',self.plan['id'],simulated=True)
        self.repo=provider.repo('quanttide')

    def pause(self):
        original=e.Executor.execute
        def execute(executor,op):
            if op['kind']=='catalog':raise e.WorkflowError('injected interruption')
            return original(executor,op)
        with patch.object(e.Executor,'execute',execute):
            with self.assertRaisesRegex(e.WorkflowError,'injected'):e.apply(self.run)

    def legacy(self):
        self.pause()
        executor=e.Executor(self.plan)
        executor.execute(self.plan['operations'][1])
        e.git(self.repo,'add','--','README.md','CHANGELOG.md')
        e.git(self.repo,'commit','-m','legacy finish omitted LICENSE')
        e.git(self.repo,'push','origin','HEAD:main')
        log=e.read_json(self.run/'execution-log.json');log['completed']=['001','002','003'];log.pop('owned_files',None)
        log['checkpoint']=e.snapshot(e.Provider(self.work),['quanttide']);e.save(self.run/'execution-log.json',log)

    def test_resume_retains_files_created_before_interruption(self):
        self.pause()
        self.assertIn('LICENSE',e.read_json(self.run/'execution-log.json')['owned_files']['quanttide'])
        self.assertEqual(e.apply(self.run)['status'],'passed')
        self.assertIn('LICENSE',e.git(self.repo,'ls-tree','--name-only','HEAD').stdout)
        self.assertEqual(e.git(self.repo,'status','--porcelain').stdout,'')

    def test_unrelated_file_blocks_resume_without_submission(self):
        self.pause();(self.repo/'private-note.txt').write_text('never commit')
        with self.assertRaises(e.WorkflowError):e.apply(self.run)
        self.assertNotIn('private-note',e.git(self.repo,'ls-tree','--name-only','HEAD').stdout)

    def test_edited_workflow_file_blocks_resume_even_if_status_unchanged(self):
        self.pause();(self.repo/'LICENSE').write_text('user changed license terms')
        with self.assertRaisesRegex(e.WorkflowError,'文件内容已变化'):e.apply(self.run)
        self.assertNotIn('LICENSE',e.git(self.repo,'ls-tree','--name-only','HEAD').stdout)

    def test_legacy_repair_preserves_original_records_and_adds_only_license(self):
        self.legacy();before=(self.run/'execution-log.json').read_bytes();old=e.git(self.repo,'rev-parse','HEAD').stdout.strip()
        proposal=repair.preview(self.run);result=repair.apply(self.run,proposal['id'])
        self.assertEqual(result['status'],'pushed')
        self.assertEqual(e.git(self.repo,'diff','--name-status',old,'HEAD').stdout.strip(),'A\tLICENSE')
        self.assertEqual((self.run/'execution-log.json').read_bytes(),before)
        self.assertEqual(e.verify(self.plan)['status'],'passed')

    def test_changed_license_or_extra_file_blocks_repair(self):
        self.legacy();proposal=repair.preview(self.run)
        (self.repo/'LICENSE').write_text('different terms')
        with self.assertRaises(e.WorkflowError):repair.apply(self.run,proposal['id'])
        self.assertEqual(e.git(self.repo,'log','-1','--format=%s').stdout.strip(),'legacy finish omitted LICENSE')

    def test_uncertain_push_is_reconciled_without_duplicate_commit(self):
        self.legacy();proposal=repair.preview(self.run);original=e.git
        def git(repo,*args,**kwargs):
            if args and args[0]=='push':
                original(repo,*args,**kwargs)
                raise e.WorkflowError('response lost after push')
            return original(repo,*args,**kwargs)
        with patch.object(e,'git',git):
            with self.assertRaisesRegex(e.WorkflowError,'response lost'):repair.apply(self.run,proposal['id'])
        head=original(self.repo,'rev-parse','HEAD').stdout
        self.assertEqual(repair.apply(self.run,proposal['id'])['status'],'pushed')
        self.assertEqual(original(self.repo,'rev-parse','HEAD').stdout,head)

    def test_remote_failures_are_unknown_with_timestamp(self):
        e.apply(self.run)
        with patch.object(e.Provider,'head',side_effect=e.RemoteReadError('connection unavailable')):r=e.verify(self.plan)
        self.assertEqual(r['details'][0]['status'],'unknown');self.assertTrue(r['details'][0]['checked_at'])

    def test_read_retry_is_bounded_and_write_is_not_retried(self):
        fail=subprocess.CompletedProcess([],128,'','Recv failure: Connection was reset')
        ok=subprocess.CompletedProcess([],0,'abc\tHEAD\n','')
        with patch.object(e.subprocess,'run',side_effect=[fail,ok]) as run,patch.object(e.time,'sleep'):
            self.assertEqual(e.command(['git','ls-remote','https://github.com/example/repo','HEAD']).stdout,ok.stdout);self.assertEqual(run.call_count,2)
        with patch.object(e.subprocess,'run',return_value=fail) as run,patch.object(e.time,'sleep'):
            with self.assertRaises(e.RemoteReadError):e.command(['git','ls-remote','url','HEAD'])
            self.assertEqual(run.call_count,3)
        with patch.object(e.subprocess,'run',return_value=fail) as run:
            with self.assertRaises(e.WorkflowError):e.command(['git','push','origin','HEAD'])
            self.assertEqual(run.call_count,1)

    def test_diagnostics_excludes_prose_credentials_and_paths(self):
        self.pause();studio=ui.Studio(Path(self.tmp.name)/'store',test_mode=True)
        folder=studio.storage/'runs'/'0123456789abcdef';folder.mkdir(parents=True)
        plan=dict(self.plan,config={'secret':'do-not-export-this-prose'})
        e.save(folder/'execution-plan.json',plan)
        e.save(folder/'execution-log.json',{'error':'token=secret123 ghp_secretvalue','checkpoint':{'quanttide':{'rules':{'secret':'do-not-export-rule'},'status':'?? LICENSE\n'}}})
        import zipfile,io
        with zipfile.ZipFile(io.BytesIO(studio.diagnostics('0123456789abcdef'))) as z:text=z.read('diagnosis.json').decode()
        for secret in ('do-not-export','secret123','ghp_secretvalue',self.tmp.name):self.assertNotIn(secret,text)
        self.assertIn('LICENSE',text)

from test_ui import UITests
class RecoveryHTTPTests(UITests):
    def test_full_legacy_repair_through_authenticated_endpoints(self):
        key,v=self.execute();folder=self.studio.folder(key);plan=e.read_json(folder/'execution-plan.json')
        provider=e.Provider(plan['workspace']);repo=provider.repo('quanttide')
        content=(repo/'LICENSE').read_bytes()
        e.git(repo,'rm','--','LICENSE');e.git(repo,'commit','-m','simulate legacy omission');e.git(repo,'push','origin','HEAD:main');(repo/'LICENSE').write_bytes(content)
        log=e.read_json(folder/'execution-log.json');log['checkpoint']=e.snapshot(provider,plan['names']);log['status']='paused';log.pop('owned_files',None);e.save(folder/'execution-log.json',log)
        # A genuine old plan uses a different engine hash. Resign this synthetic fixture only.
        plan.pop('id');plan['engine_sha256']='old-engine-fixture';plan['id']=e.digest(plan);e.save(folder/'execution-plan.json',plan)
        log['plan_id']=plan['id'];e.save(folder/'execution-log.json',log)
        approval=e.read_json(folder/'approval-record.json');approval['plan_id']=plan['id'];e.save(folder/'approval-record.json',approval)
        self.studio.set_meta(folder,status='paused')
        original=(folder/'execution-log.json').read_bytes()
        self.json('/api/runs/'+key+'/repair-preview',{});preview=self.wait(key)
        self.assertEqual(preview['status'],'paused');self.assertEqual(preview['repair']['files'],['LICENSE'])
        self.assertFalse(preview['can_resume'])
        self.json('/api/runs/'+key+'/repair-apply',{'repair_id':preview['repair']['id'],'confirmed':True});result=self.wait(key)
        self.assertEqual(result['status'],'completed',result.get('error'));self.assertTrue(result['report']['technical_passed'])
        self.assertEqual((folder/'execution-log.json').read_bytes(),original)
        self.assertEqual(result['repair_record']['status'],'pushed')
        self.assertEqual(self.request('/api/runs/'+key+'/diagnostics',headers={'X-Session-Token':''})[0],400)
        self.assertEqual(self.request('/api/runs/'+key+'/diagnostics')[0],200)

for name in list(UITests.__dict__):
    if name.startswith('test_'):setattr(RecoveryHTTPTests,name,None)
del UITests
