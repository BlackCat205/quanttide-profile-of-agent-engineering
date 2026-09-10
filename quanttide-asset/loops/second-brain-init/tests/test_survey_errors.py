"""Network observations must not be reported as confirmed rule drift."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ui'))
import survey

class RulesErrors(unittest.TestCase):
    def test_unknown_explains_failed_side(self):
        message=survey.rules_error({'status':'unknown','adopted_file':{'status':'ok','sha':'a'},'latest_file':{'status':'unknown','http_status':403,'reason':'访问受限'}})
        self.assertIn('尚不能判断',message)
        self.assertIn('在线版本：访问受限（HTTP 403）',message)
        self.assertNotIn('已确认',message)

    def test_changed_and_same(self):
        self.assertIn('已确认',survey.rules_error({'status':'changed'}))
        self.assertEqual('',survey.rules_error({'status':'same'}))

    def test_diagnostic_excludes_content(self):
        result=survey.rules_diagnostic({'status':'unknown','latest_file':{'status':'ok','sha':'a','text':'private content'}})
        self.assertNotIn('text',result['latest_file'])
        self.assertEqual('a',result['latest_file']['sha'])

    def test_transient_retry(self):
        with patch.object(survey,'_get_once',side_effect=[{'status':'unknown'},{'status':'ok','data':{}}]) as request, patch.object(survey.time,'sleep'):
            self.assertEqual('ok',survey.get('repos/example/test')['status'])
            self.assertEqual(2,request.call_count)

    def test_no_retry_auth_or_missing(self):
        for status in (401,403,404,429):
            with patch.object(survey,'_get_once',return_value={'status':'unknown','http_status':status}) as request:
                self.assertEqual(status,survey.get('test')['http_status'])
                self.assertEqual(1,request.call_count)

    def test_retry_is_bounded(self):
        with patch.object(survey,'_get_once',return_value={'status':'unknown'}) as request, patch.object(survey.time,'sleep'):
            self.assertEqual('unknown',survey.get('test')['status'])
            self.assertEqual(3,request.call_count)

    def test_inspection_documents_are_read_at_observed_root_commit(self):
        repository={'status':'ok','data':{'default_branch':'main'}}
        commit={'status':'ok','data':{'sha':'locked-commit'}}
        with patch.object(survey,'get',side_effect=[repository,commit]), patch.object(survey,'text_file',return_value={'status':'ok','sha':'rule','text':''}) as text_file:
            result=survey.inspect('example',['root'],{'repository':'rules/source','path':'rule.md','commit':'adopted'},root='root',inspection_paths=('AGENTS.md',))
        self.assertIn('AGENTS.md',result['documents'])
        root_reads=text_file.call_args_list[:4]
        self.assertEqual(['README.md','domains/README.md','.gitmodules','AGENTS.md'],[call.args[2] for call in root_reads])
        self.assertTrue(all(call.args[3]=='locked-commit' for call in root_reads))

    def test_authenticated_reader_is_used_for_every_planning_read(self):
        calls=[]
        def reader(path):
            calls.append(path)
            if path=='repos/example/root':return {'status':'ok','data':{'default_branch':'main'}}
            if '/commits/' in path:return {'status':'ok','data':{'sha':'locked'}}
            if '/contents/' in path:return {'status':'ok','data':{'encoding':'base64','sha':'file','content':''}}
            raise AssertionError(path)
        result=survey.inspect('example',['root'],{'repository':'rules/source','path':'rule.md','commit':'adopted'},root='root',inspection_paths=('AGENTS.md',),get_fn=reader)
        self.assertEqual(result['access'],'已登录的只读调查')
        self.assertTrue(all(path.startswith('repos/') for path in calls))
        self.assertIn('repos/example/root/contents/AGENTS.md?ref=locked',calls)

if __name__=='__main__':unittest.main()
