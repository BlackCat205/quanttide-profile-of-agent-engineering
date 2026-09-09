"""Transport fault injection; no external service writes."""
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_recovery

e=test_recovery.e
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.events=[];e.request_observer.callback=self.events.append;e.request_observer.http1=False;e.request_observer.target=None
    def tearDown(self):
        e.request_observer.callback=None;e.request_observer.http1=False;e.request_observer.target=None
    def test_options_are_not_mistaken_for_operation(self):
        self.assertEqual(e.command_kind(['git','-c','x=y','-C','/tmp','ls-remote','url']),'ls-remote')
    def test_read_fallback_is_process_scoped_and_audited(self):
        results=[subprocess.CompletedProcess([],128,'','HTTP/2 connection reset'),subprocess.CompletedProcess([],0,'abc HEAD','')]
        with patch.object(e.subprocess,'run',side_effect=results) as run,patch.object(e.time,'sleep'):
            e.command(['git','-c','x=y','ls-remote','https://github.com/Example/test.git','HEAD'])
            self.assertEqual(run.call_count,2)
            env=run.call_args.kwargs['env'];self.assertIn('HTTP/1.1',env.values())
        self.assertEqual(self.events[-1]['target'],'Example/test')
        self.assertEqual(self.events[-1]['attempt'],2)
        self.assertEqual(self.events[-1]['status'],'passed')
    def test_push_is_never_automatically_repeated(self):
        with patch.object(e.subprocess,'run',return_value=subprocess.CompletedProcess([],128,'','connection reset')) as run:
            with self.assertRaises(e.WorkflowError):e.command(['git','push','https://github.com/Example/test.git','main'])
            self.assertEqual(run.call_count,1)
    def test_github_reads_retry_but_writes_do_not(self):
        failed=subprocess.CompletedProcess([],128,'','connection reset')
        passed=subprocess.CompletedProcess([],0,'{}','')
        with patch.object(e.subprocess,'run',side_effect=[failed,passed]) as run,patch.object(e.time,'sleep'):
            e.command(['gh','api','repos/Example/test'])
            self.assertEqual(run.call_count,2)
        with patch.object(e.subprocess,'run',return_value=failed) as run:
            with self.assertRaises(e.WorkflowError):
                e.command(['gh','api','--method','POST','user/repos'])
            self.assertEqual(run.call_count,1)
    def test_raw_errors_and_credentials_are_not_recorded(self):
        with patch.object(e.subprocess,'run',return_value=subprocess.CompletedProcess([],128,'','authentication ghp_secret')):
            with self.assertRaises(e.WorkflowError):e.command(['git','ls-remote','https://github.com/Example/test.git'])
        self.assertNotIn('ghp_secret',str(self.events))
    def test_local_snapshot_does_not_contact_remote(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            provider=e.Provider(Path(tmp))
            before=e.snapshot(provider,['test'])
            with patch.object(provider,'info',side_effect=AssertionError('network')),patch.object(provider,'head',side_effect=AssertionError('network')):
                self.assertEqual(e.snapshot(provider,['test'],baseline=before),before)
    def test_github_head_uses_authenticated_api_not_git_transport(self):
        info={'exists':True,'branch':'feature/test'}
        response=subprocess.CompletedProcess([],0,json.dumps({'sha':'abc123'}),'')
        with tempfile.TemporaryDirectory() as tmp,patch.object(e,'command',return_value=response) as command:
            provider=e.Provider(tmp,'github','Example')
            self.assertEqual(provider.head('test',info),'abc123')
            args=command.call_args.args[0]
            self.assertEqual(args[:2],['gh','api'])
            self.assertIn('commits/feature%2Ftest',args[2])
            self.assertNotIn('ls-remote',args)
if __name__=='__main__':unittest.main()
