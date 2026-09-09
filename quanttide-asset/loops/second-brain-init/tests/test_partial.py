"""Real local Git fault injection for phase receipts; never writes to GitHub."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_recovery
e=test_recovery.e
import partial_recovery

class PartialTests(unittest.TestCase):
    setUp=test_recovery.RecoveryTests.setUp

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
        before=self.plan['before'];log={'plan_id':self.plan['id'],'completed':[],'checkpoint':before,'events':[]}
        e.save(self.run/'execution-log.json',log)
        original=(self.run/'execution-plan.json').read_bytes()
        proposal={'source_plan':self.plan['id'],'repo':'quanttide','operation':'001','organization':'Example','repository_id':123,'commit':'abc','content':'# quanttide','before':before,'checked_at':e.now(),'engine_sha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest()}
        proposal['id']=e.digest(proposal);e.save(self.run/'partial-proposal.json',proposal)
        with patch.object(partial_recovery,'inspect',return_value=(self.plan,log,proposal)):
            dest=self.run.parent/'recovered'
            result=partial_recovery.migrate(self.run,dest,proposal['id'],'reviewer')
            self.assertNotEqual(result['id'],self.plan['id'])
            self.assertEqual(e.read_json(dest/'approval-record.json')['plan_id'],result['id'])
            self.assertEqual((self.run/'execution-plan.json').read_bytes(),original)
            with self.assertRaisesRegex(e.WorkflowError,'已生成'):partial_recovery.migrate(self.run,self.run.parent/'duplicate',proposal['id'],'reviewer')

    def test_legacy_inspection_rejects_extra_remote_commit(self):
        from unittest.mock import Mock
        seed=e.Provider(self.work);seed.ensure('seed',True,'quanttide')
        remote=seed.remote('seed');head=seed.head('seed')
        plan=copy.deepcopy(self.plan);plan.update(provider='github',engine_sha256=partial_recovery.LEGACY_ENGINE,github_identity={'owner_id':1})
        log={'plan_id':plan['id'],'completed':[],'checkpoint':plan['before'],'current':{'op':'001'}}
        e.save(self.run/'execution-log.json',log)
        e.save(self.run/'approval-record.json',{'plan_id':plan['id'],'accepted':True,'simulated':False})
        current={'quanttide':dict(plan['before']['quanttide'],remote=head,remote_exists=True,repository_id=2,owner_id=1)}
        provider=Mock();provider.repo.return_value=self.repo;provider.remote.return_value=remote;provider.info.return_value={'can_push':True,'owner_id':1,'id':2}
        with patch.object(e,'load_plan',return_value=plan),patch.object(e,'check_identity'),patch.object(e,'Provider',return_value=provider),patch.object(e,'snapshot',return_value=current):
            self.assertEqual(partial_recovery.inspect(self.run)[2]['commit'],head)
            repo=seed.repo('seed');(repo/'extra.txt').write_text('external change');e.git(repo,'add','extra.txt');e.git(repo,'commit','-m','external');e.git(repo,'push','origin','HEAD:main')
            current['quanttide']['remote']=e.git(repo,'rev-parse','HEAD').stdout.strip()
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
