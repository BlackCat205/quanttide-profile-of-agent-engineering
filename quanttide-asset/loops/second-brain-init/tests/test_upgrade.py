"""Reliability acceptance: diagnostic failures, durable writes and process isolation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_ui import UITests, BASE, ui

e=ui.e
SCRIPTS=Path(e.__file__).parent

class LockAndStorageTests(unittest.TestCase):
    def test_read_retries_transient_denial_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'record.json';e.save(p,{'completed':['001']})
            original=Path.read_text;attempts=[]
            def read(path,*args,**kw):
                if path==p:
                    attempts.append(1)
                    if len(attempts)<3:raise PermissionError('busy')
                return original(path,*args,**kw)
            with patch.object(Path,'read_text',read),patch.object(e.time,'sleep'):
                self.assertEqual(e.read_json(p),{'completed':['001']})
            self.assertEqual(len(attempts),3)

    def test_corrupt_record_is_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'execution-log.json';p.write_text('{partial')
            with self.assertRaises(e.WorkflowError) as caught:e.read_json(p)
            self.assertEqual(caught.exception.code,'record-corrupt')
            self.assertEqual(p.read_text(),'{partial')

    def test_kernel_lock_blocks_another_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=Path(tmp)/'guard'
            code='import sys;sys.path.insert(0,sys.argv[1]);import engine as e\nwith e.process_lock(sys.argv[2]): print("acquired")'
            with e.process_lock(lock):
                r=subprocess.run([sys.executable,'-c',code,str(SCRIPTS),str(lock)],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0);self.assertNotIn('acquired',r.stdout)
            r=subprocess.run([sys.executable,'-c',code,str(SCRIPTS),str(lock)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

    def test_killed_process_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=Path(tmp)/'guard'
            code='import sys,time;sys.path.insert(0,sys.argv[1]);import engine as e\nwith e.process_lock(sys.argv[2]):\n print("ready",flush=True)\n time.sleep(60)'
            child=subprocess.Popen([sys.executable,'-c',code,str(SCRIPTS),str(lock)],stdout=subprocess.PIPE,text=True)
            try:self.assertEqual(child.stdout.readline().strip(),'ready')
            finally:child.kill();child.wait();child.stdout.close()
            with e.process_lock(lock):pass

    def test_legacy_live_lock_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'run';run.mkdir();work=Path(tmp)/'work'
            lock=run/'execution.lock';lock.write_text(str(os.getpid()))
            with self.assertRaises(e.WorkflowError):
                with e.execution_locks(run,work):pass
            self.assertEqual(lock.read_text(),str(os.getpid()))

    def test_same_root_in_different_workspaces_is_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);a=base/'a';b=base/'b';a.mkdir();b.mkdir()
            plan={'provider':'github','organization':'test-'+base.name,'config':{'root_repo':'root'}}
            e.save(a/'execution-plan.json',plan);e.save(b/'execution-plan.json',plan)
            code='import sys;sys.path.insert(0,sys.argv[1]);import engine as e\nwith e.execution_locks(sys.argv[2],sys.argv[3]): print("acquired")'
            with e.execution_locks(a,base/'work-a'):
                r=subprocess.run([sys.executable,'-c',code,str(SCRIPTS),str(b),str(base/'work-b')],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0)
            self.assertFalse((b/'execution.lock').exists())

    def test_record_failure_blocks_remote_command_before_subprocess(self):
        def blocked(event):raise PermissionError('cannot save execution receipt')
        e.request_observer.before_write=blocked
        try:
            with patch.object(e.subprocess,'run') as run:
                with self.assertRaises(PermissionError):e.command(['git','push','https://github.com/example/repo','HEAD:main'])
                run.assert_not_called()
        finally:e.request_observer.before_write=None

    def test_api_fields_are_not_misclassified_as_readonly(self):
        response=subprocess.CompletedProcess([],1,'','connection reset')
        with patch.object(e.subprocess,'run',return_value=response) as run:
            e.command(['gh','api','repos/example/repo','-f','name=value'],check=False)
        self.assertEqual(run.call_count,1)

    def test_repeated_launcher_reopens_same_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv=[sys.executable,str(ui.HERE/'app.py'),'--storage',tmp,'--test-mode','--no-browser']
            child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertIn('已启动',child.stdout.readline())
                self.assertTrue(child.stdout.readline().startswith('http://127.0.0.1:'))
                again=subprocess.run(argv,capture_output=True,text=True,timeout=10)
                self.assertEqual(again.returncode,0,again.stderr)
                self.assertIn('已打开现有向导',again.stdout)
            finally:
                child.terminate();child.wait(timeout=5);child.stdout.close();child.stderr.close()

    @unittest.skipUnless(os.name=='nt','Windows sharing API requires Windows')
    def test_windows_exclusive_file_handle_is_reported_and_recovers(self):
        import ctypes
        from ctypes import wintypes
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        k.CreateFileW.restype=wintypes.HANDLE;k.CloseHandle.argtypes=[wintypes.HANDLE]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'requests.json';e.save(p,[{'status':'passed'}])
            h=k.CreateFileW(str(p),0x80000000,0,None,3,0,None)
            self.assertNotEqual(h,ctypes.c_void_p(-1).value)
            try:
                with self.assertRaises(PermissionError):e.read_json(p)
            finally:k.CloseHandle(h)
            self.assertEqual(len(e.read_json(p)),1)

class UpgradeUITests(UITests):
    def test_unreadable_diagnostic_does_not_block_creation_or_overwrite_history(self):
        key,v=self.plan();folder=self.studio.folder(key);path=folder/'requests.json'
        e.save(path,[{'operation':'historical','status':'unknown'}]);before=path.read_bytes()
        original=e.read_json
        def read(p):
            if Path(p).name=='requests.json':raise PermissionError('Windows exclusive handle')
            return original(p)
        with patch.object(e,'read_json',read):
            self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'test'})
            result=self.wait(key)
            self.assertEqual(result['status'],'completed',result)
            self.assertTrue(result['diagnostic_warning'])
            self.assertEqual(self.request('/api/runs/'+key+'/diagnostics')[0],200)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(self.studio.view(key)['completed'],27)

    def test_critical_read_failure_disables_actions_and_recovers(self):
        key,v=self.plan();original=e.read_json
        def read(p):
            if Path(p).name=='execution-plan.json':raise PermissionError('denied')
            return original(p)
        with patch.object(e,'read_json',read):
            result=self.studio.view(key)
            self.assertEqual(result['status'],'paused');self.assertFalse(result['can_resume'])
            self.assertEqual(result['recovery']['action'],'storage-check')
        self.assertEqual(self.json('/api/runs/'+key+'/storage-check',{})['status'],'checked')
        self.assertTrue(self.studio.view(key)['has_plan'])

    def test_missing_executed_plan_never_offers_replanning(self):
        key,v=self.plan();folder=self.studio.folder(key)
        e.save(folder/'execution-log.json',{'plan_id':v['plan']['id'],'completed':['001']})
        (folder/'execution-plan.json').unlink()
        result=self.studio.view(key)
        self.assertEqual(result['recovery']['code'],'record-corrupt')
        self.assertNotEqual(result['recovery']['action'],'retry-plan')
        self.assertEqual(self.request('/api/runs/'+key+'/storage-check',{})[0],400)

    def test_artifacts_visible_before_final_report(self):
        key,v=self.plan();folder=self.studio.folder(key);plan=e.read_json(folder/'execution-plan.json')
        states=json.loads(json.dumps(plan['before']));name=plan['names'][0]
        states[name].update(remote_exists=True,local='new',remote='old',status='')
        e.save(folder/'execution-log.json',{'plan_id':plan['id'],'completed':['001'],'checkpoint':states,'phases':[]})
        result=self.studio.view(key)
        row=next(r for r in result['artifacts'] if r['name']==name)
        self.assertIn('待同步',row['status']);self.assertIsNone(result['report'])
        self.assertFalse(result['milestones']['technical_passed'])

    def test_critical_write_failure_can_resume_without_duplicate_commit(self):
        key,v=self.plan();folder=self.studio.folder(key);original=e.save;failed=[]
        def save(path,value):
            if Path(path).name=='execution-log.json' and value.get('write_intent') and not failed:
                failed.append(True);raise PermissionError('disk busy before push')
            return original(path,value)
        with patch.object(e,'save',save):
            self.json('/api/runs/'+key+'/execute',{'plan_id':v['plan']['id'],'confirmed':True,'reviewer':'test'})
            stopped=self.wait(key)
        self.assertEqual(stopped['status'],'paused');self.assertTrue(failed)
        self.json('/api/runs/'+key+'/storage-check',{})
        self.assertEqual(self.studio.view(key)['recovery']['action'],'resume')
        self.json('/api/runs/'+key+'/resume',{'plan_id':v['plan']['id']})
        result=self.wait(key)
        self.assertEqual(result['completed'],27,result);self.assertEqual(result['status'],'completed',result)

    def test_previous_executor_plan_keeps_original_approval_and_scope(self):
        key,v=self.plan();folder=self.studio.folder(key);plan=e.read_json(folder/'execution-plan.json')
        plan.pop('id');plan['engine_sha256']='5b2d36940bae6355215c18101a51b722d59e1f8b752e4127410ad58ba56b75c0'
        plan['version']='0.4.6';plan['id']=e.digest(plan);e.save(folder/'execution-plan.json',plan)
        original=(folder/'execution-plan.json').read_bytes()
        self.json('/api/runs/'+key+'/execute',{'plan_id':plan['id'],'confirmed':True,'reviewer':'test'})
        result=self.wait(key)
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual((folder/'execution-plan.json').read_bytes(),original)
        self.assertEqual(e.read_json(folder/'approval-record.json')['plan_id'],plan['id'])

    def test_history_keeps_all_tasks_and_collapses_recovery_lineage(self):
        key,v=self.plan();folder=self.studio.folder(key);new='e'*16;destination=folder.parent/new;destination.mkdir()
        e.save(destination/'ui.json',{'id':new,'title':'恢复任务','status':'paused','created_at':e.now()})
        e.save(folder/'partial-migration.json',{'destination':new})
        rows=self.json('/api/runs');self.assertNotIn(key,[r['id'] for r in rows]);self.assertIn(new,[r['id'] for r in rows])
        self.assertTrue((folder/'ui.json').exists())

    def test_repeated_outage_requires_fresh_download_check(self):
        key,v=self.plan();folder=self.studio.folder(key);plan=e.read_json(folder/'execution-plan.json')
        e.save(folder/'approval-record.json',{'plan_id':plan['id'],'accepted':True})
        failure=e.error_info(e.WorkflowError('push outage',code='connection',attempts=3))
        log={'completed':[],'failure':failure}
        r=ui.recovery_guidance(folder,{'status':'paused','failure':failure},plan,log,[])
        self.assertEqual(r['action'],'connection-check')
        e.save(folder/'connection-check.json',{'finished_at':e.now(),'checks':[{'label':'下载连接','status':'passed'}]})
        r=ui.recovery_guidance(folder,{'status':'paused','failure':failure},plan,log,[])
        self.assertEqual(r['action'],'resume')

for name in list(UITests.__dict__):
    if name.startswith('test_'):setattr(UpgradeUITests,name,None)
del UITests
