"""Real local Git fault injection for phase receipts; never writes to GitHub."""
import copy
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import patch
import test_recovery
e=test_recovery.e
ui=test_recovery.ui
import partial_recovery

class PartialTests(unittest.TestCase):
    setUp=test_recovery.RecoveryTests.setUp

    def test_completed_phase_survives_remote_verification_failure(self):
        approved=(self.run/'execution-plan.json').read_bytes()
        original=e.snapshot
        def fail(provider,names,*args,**kwargs):
            if kwargs.get('baseline') is None and provider.info('quanttide')['exists']:
                raise e.RemoteReadError('injected verification outage')
            return original(provider,names,*args,**kwargs)
        with patch.object(e,'snapshot',side_effect=fail):
            with self.assertRaisesRegex(e.WorkflowError,'verification outage'):e.apply(self.run)
        log=e.read_json(self.run/'execution-log.json')
        self.assertEqual(log['pending_phase']['stage'],'remote-created')
        self.assertEqual(log['pending_phase']['status'],'executed-unverified')
        self.assertEqual(log['completed'],[])
        self.assertEqual(log['intent']['kind'],'ensure-repo')
        self.assertEqual((self.run/'execution-plan.json').read_bytes(),approved)

    def test_creation_response_reconciles_only_exact_repository_identity(self):
        from unittest.mock import Mock
        plan={'organization':'Example','names':['test']}
        pending={'op':'001','repo':'test','stage':'remote-created'}
        receipt={'repository_id':12,'owner_id':34,'full_name':'Example/test'}
        state={'checkpoint':{'test':{}},'pending_phase':pending,
               'creation_responses':{'test':{'receipt':receipt}}}
        observed={'remote_exists':True,'remote':'abc','local':None,
                  'repository_id':12,'owner_id':34}
        with patch.object(e,'snapshot',return_value={'test':observed}):
            self.assertTrue(e.reconcile_creation_response(Mock(),plan,state))
        self.assertEqual(state['created_receipts']['test'],observed)
        self.assertNotIn('pending_phase',state)
        changed={'checkpoint':{'test':{}},'pending_phase':pending,
                 'creation_responses':{'test':{'receipt':receipt}}}
        with patch.object(e,'snapshot',return_value={'test':dict(observed,repository_id=99)}):
            with self.assertRaisesRegex(e.WorkflowError,'身份无法'):e.reconcile_creation_response(Mock(),plan,changed)

    def test_clone_disconnect_preserves_receipt_and_resumes(self):
        original=e.command
        def fail(args,*a,**kw):
            if list(args)[:2]==['git','clone']:
                Path(args[-1]).mkdir(parents=True);(Path(args[-1])/'partial-file').write_text('keep')
                raise e.WorkflowError('injected clone disconnect')
            return original(args,*a,**kw)
        with patch.object(e,'command',fail):
            with self.assertRaisesRegex(e.WorkflowError,'disconnect'):e.apply(self.run)
        log=e.read_json(self.run/'execution-log.json')
        self.assertTrue(log['checkpoint']['quanttide']['remote_exists'])
        self.assertIn('quanttide',log['created_receipts'])
        self.assertFalse(self.repo.exists())
        self.assertEqual(e.apply(self.run)['status'],'passed')
        self.assertTrue(list((self.repo.parent.parent/'downloads').glob('*-clone-*/repository/partial-file')))

    def test_push_response_lost_resumes_without_duplicate_commit(self):
        original=e.git;seen=[]
        def fail(repo,*args,**kw):
            result=original(repo,*args,**kw)
            if args and args[0]=='push' and len(args)>1 and args[1]=='origin' and not seen:
                seen.append(original(repo,'rev-parse','HEAD').stdout.strip())
                raise e.WorkflowError('injected lost push response')
            return result
        with patch.object(e,'git',fail):
            with self.assertRaisesRegex(e.WorkflowError,'lost push'):e.apply(self.run)
        self.assertEqual(e.apply(self.run)['status'],'passed')
        self.assertEqual(seen[0],e.git(self.repo,'rev-parse','HEAD').stdout.strip())

    def test_staged_receipt_is_verified_and_resumed_after_process_loss(self):
        original=e.snapshot;failed=[]
        def interrupt(provider,names,*args,**kwargs):
            if kwargs.get('baseline') is not None and not failed:
                repo=provider.repo(names[0])
                if (repo/'.git').exists() and e.git(repo,'diff','--cached','--quiet',check=False).returncode:
                    failed.append(True)
                    raise OSError('injected process loss after staging')
            return original(provider,names,*args,**kwargs)
        with patch.object(e,'snapshot',side_effect=interrupt):
            with self.assertRaisesRegex(e.WorkflowError,'process loss'):e.apply(self.run)
        interrupted=e.read_json(self.run/'execution-log.json')
        self.assertEqual(interrupted['pending_phase']['stage'],'staged')
        self.assertEqual(interrupted['status'],'paused')
        studio=ui.Studio(Path(self.tmp.name)/'studio',test_mode=True)
        key='0123456789abcdef';folder=studio.storage/'runs'/key
        folder.parent.mkdir(parents=True);shutil.copytree(self.run,folder)
        e.save(folder/'ui.json',{'id':key,'status':'paused','provider':'local'})
        with patch.object(studio,'build_report'):
            studio.execute(key,{'plan_id':self.plan['id']},resume=True)
            until=time.monotonic()+20
            while key in studio.active and time.monotonic()<until:time.sleep(.01)
        self.assertNotIn(key,studio.active)
        self.assertEqual(e.read_json(folder/'ui.json')['status'],'completed')
        recovered=e.read_json(folder/'execution-log.json')
        self.assertTrue(any(p.get('recovered_from')=='durable-local-receipt' for p in recovered['phases']))

    def test_041_plan_hash_is_explicitly_compatible(self):
        old_hash=next(iter(e.COMPATIBLE_ENGINE_SHA256S))
        self.assertTrue(e.engine_compatible({'engine_sha256':old_hash}))
        self.assertFalse(e.engine_compatible({'engine_sha256':'unknown'}))
        plan=e.read_json(self.run/'execution-plan.json');plan.pop('id')
        plan['version']='0.4.1';plan['engine_sha256']=old_hash;plan['id']=e.digest(plan)
        e.save(self.run/'execution-plan.json',plan)
        self.assertEqual(e.load_plan(self.run)['id'],plan['id'])

    def test_remote_change_is_not_accepted_as_lost_response(self):
        before={'repo':{'local':'new','remote':'old','status':'','repository_id':1}}
        state={'checkpoint':before,'phases':[{'repo':'repo','kind':'committed'}]}
        self.assertTrue(e.recovery_snapshot_matches({'repo':dict(before['repo'],remote='new')},state))
        self.assertFalse(e.recovery_snapshot_matches({'repo':dict(before['repo'],remote='other')},state))
        self.assertFalse(e.recovery_snapshot_matches({'repo':dict(before['repo'],remote='new',repository_id=2)},state))

    def test_legacy_rejects_unknown_engine_before_network(self):
        with patch.object(e,'check_identity') as identity:
            with self.assertRaisesRegex(e.WorkflowError,'已知旧版'):partial_recovery.inspect(self.run)
            identity.assert_not_called()

    def test_migration_preserves_source_and_binds_new_approval(self):
        import hashlib
        from unittest.mock import Mock
        plan=copy.deepcopy(self.plan);plan.pop('id');plan.update(provider='github',organization='Example',
            github_identity={'owner_id':1},engine_sha256=partial_recovery.LEGACY_ENGINE)
        plan['id']=e.digest(plan);self.plan=plan;e.save(self.run/'execution-plan.json',plan)
        before=plan['before'];log={'plan_id':plan['id'],'completed':[],'checkpoint':before,'events':[]}
        e.save(self.run/'execution-log.json',log)
        e.save(self.run/'approval-record.json',{'plan_id':plan['id'],'accepted':True,'simulated':False})
        proposal={'source_plan':plan['id'],'repo':'quanttide','operation':'001','organization':'Example','repository_id':123,'commit':'abc','content':'# quanttide','before':before,'checked_at':e.now(),'engine_sha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest()}
        proposal['id']=e.digest(proposal);e.save(self.run/'partial-proposal.json',proposal)
        provider=Mock();provider.info.return_value={'id':123,'owner_id':1,'can_push':True,'archived':False}
        provider.head.return_value='abc';provider.repo.return_value=self.repo.parent/'absent'
        original=(self.run/'execution-plan.json').read_bytes()
        with patch.object(e,'check_identity'),patch.object(e,'Provider',return_value=provider):
            dest=self.run.parent/'recovered'
            result=partial_recovery.migrate(self.run,dest,proposal['id'],'reviewer')
            self.assertNotEqual(result['id'],self.plan['id'])
            self.assertEqual(e.read_json(dest/'approval-record.json')['plan_id'],result['id'])
            self.assertEqual((self.run/'execution-plan.json').read_bytes(),original)
            with self.assertRaisesRegex(e.WorkflowError,'已生成'):partial_recovery.migrate(self.run,self.run.parent/'duplicate',proposal['id'],'reviewer')

    def test_legacy_inspection_rejects_extra_remote_commit(self):
        from unittest.mock import Mock
        import base64,json,subprocess
        plan=copy.deepcopy(self.plan);plan.update(provider='github',engine_sha256=partial_recovery.LEGACY_ENGINE,github_identity={'owner_id':1})
        log={'plan_id':plan['id'],'completed':[],'checkpoint':plan['before'],'current':{'op':'001'}}
        e.save(self.run/'execution-log.json',log)
        e.save(self.run/'approval-record.json',{'plan_id':plan['id'],'accepted':True,'simulated':False})
        current={'quanttide':dict(plan['before']['quanttide'],remote='commit',remote_exists=True,repository_id=2,owner_id=1)}
        provider=Mock();provider.repo.return_value=self.repo;provider.info.return_value={'can_push':True,'owner_id':1,'id':2};provider.head.return_value='commit'
        responses=[{'sha':'commit','parents':[],'tree':{'sha':'tree'}},{'tree':[{'path':'README.md','mode':'100644','type':'blob','sha':'blob'}]},{'sha':'blob','encoding':'base64','content':base64.b64encode(b'# quanttide').decode()}]
        def response(args):
            self.assertEqual(args[:2],['gh','api'])
            return subprocess.CompletedProcess(args,0,json.dumps(responses.pop(0)),'')
        with patch.object(e,'load_plan',return_value=plan),patch.object(e,'check_identity'),patch.object(e,'Provider',return_value=provider),patch.object(e,'snapshot',return_value=current),patch.object(e,'command',side_effect=response):
            self.assertEqual(partial_recovery.inspect(self.run)[2]['commit'],'commit')
            responses.append({'sha':'commit','parents':[{'sha':'previous'}]})
            with self.assertRaisesRegex(e.WorkflowError,'后续提交'):partial_recovery.inspect(self.run)

    def test_files_changed_after_commit_block_resume(self):
        original=e.git
        def fail(repo,*args,**kw):
            if args and args[0]=='push' and len(args)>1 and args[1]=='origin':raise e.WorkflowError('injected before push')
            return original(repo,*args,**kw)
        with patch.object(e,'git',fail):
            with self.assertRaises(e.WorkflowError):e.apply(self.run)
        (self.repo/'README.md').write_text('user edit')
        with self.assertRaises(e.WorkflowError):e.apply(self.run)

if __name__=='__main__':unittest.main()
