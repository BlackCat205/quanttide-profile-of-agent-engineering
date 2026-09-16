"""End-to-end UI recovery using local bare Git and simulated GitHub responses."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_github as github
from test_github import LocalGithubTransport,ui,e,BASE

class LostCreateTransport(LocalGithubTransport):
    lost=False
    target='quanttide-laboratory-of-recoverytrial-engineering'
    def command(self,args,cwd=None,check=True):
        args=list(map(str,args))
        if args[:2]==['gh','api'] and len(args)>2:
            parts=args[2].split('/')
            if len(parts)==6 and parts[3]=='git':
                remote=self.path/(parts[2]+'.git');kind,sha=parts[4:]
                def git(*a):return self.real(['git','--git-dir',remote,*a]).stdout
                if kind=='commits':
                    raw=git('cat-file','-p',sha).split('\n\n',1)[0].splitlines()
                    data={'sha':sha,'tree':{'sha':next(x[5:] for x in raw if x.startswith('tree '))},'parents':[{'sha':x[7:]} for x in raw if x.startswith('parent ')]}
                elif kind=='trees':
                    data={'tree':[]}
                    for row in git('ls-tree',sha).splitlines():
                        meta,path=row.split('\t');mode,typ,obj=meta.split();data['tree'].append({'path':path,'mode':mode,'type':typ,'sha':obj})
                elif kind=='blobs':data={'sha':sha,'encoding':'base64','content':base64.b64encode(git('cat-file','-p',sha).encode()).decode()}
                else:raise AssertionError(args)
                return subprocess.CompletedProcess(args,0,json.dumps(data),'')
        result=super().command(args,cwd,check)
        if args[:4]==['gh','api','--method','POST'] and 'name='+self.target in args and not self.lost:
            self.lost=True
            # Model GitHub auto_init completing before its response is lost.
            with tempfile.TemporaryDirectory() as temp:
                repo=Path(temp)/'seed';self.real(['git','clone',self.path/(self.target+'.git'),repo])
                for key,value in [('user.name','fixture'),('user.email','fixture@example.invalid')]:self.real(['git','config',key,value],repo)
                (repo/'README.md').write_text('# '+self.target+'\n')
                self.real(['git','add','README.md'],repo);self.real(['git','commit','-m','Initial commit'],repo)
                self.real(['git','push','origin','HEAD:main'],repo)
            raise e.WorkflowError('连接中断或超时：创建响应丢失')
        return result

class CreateResponseLossTests(unittest.TestCase):
    wait=github.GithubWorkflowTests.wait
    def test_reviewed_recovery_finishes_29_steps_without_recreating_repos(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);remotes=base/'bare';remotes.mkdir();transport=LostCreateTransport(remotes)
            studio=ui.Studio(base/'studio',enable_github=True);real_which=e.shutil.which
            with patch.object(e,'command',side_effect=transport.command),patch.object(e.shutil,'which',side_effect=lambda name:'/fake/gh' if name=='gh' else real_which(name)),patch.object(ui.survey,'inspect',side_effect=transport.survey),patch.object(ui.survey,'text_file',return_value={'status':'ok','sha':'fixture-rules'}):
                payload=dict(BASE,short_name='recoverytrial',english_name='recoverytrial-engineering',provider='github',organization='BlackCat205',root_repo='recovery-root',root_mode='new')
                key=studio.create(payload)['id'];view=self.wait(studio,key)
                studio.execute(key,{'plan_id':view['plan']['id'],'confirmed':True,'reviewer':'SIMULATED','github_confirmation':'BlackCat205'})
                view=self.wait(studio,key);self.assertEqual(view['status'],'paused');self.assertEqual(view['completed'],4)
                studio.execute(key,{'plan_id':view['plan']['id']},resume=True)
                view=self.wait(studio,key);self.assertEqual(view['recovery']['action'],'partial')
                original=(studio.folder(key)/'execution-log.json').read_bytes()
                studio.partial_task(key,{})
                view=self.wait(studio,key);proposal=view['partial_proposal']
                studio.partial_task(key,{'confirmed':True,'reviewer':'SIMULATED','proposal_id':proposal['id']},execute=True)
                view=self.wait(studio,key);newkey=view['partial_migration']['destination']
                self.assertEqual((studio.folder(key)/'execution-log.json').read_bytes(),original)
                newview=studio.view(newkey)
                studio.execute(newkey,{'plan_id':newview['plan']['id']},resume=True)
                result=self.wait(studio,newkey)
                self.assertEqual(result['status'],'completed',result.get('error'))
                self.assertEqual(result['completed'],29);self.assertTrue(result['report']['technical_passed'])
                self.assertEqual(len(transport.mutations),8)
                self.assertEqual(len(set(transport.mutations)),8)
                log=e.read_json(studio.folder(newkey)/'execution-log.json')
                self.assertIn('qtcloud-recoverytrial',log['created_receipts'])
                self.assertEqual(sum(x.get('op')=='001' and x.get('status')=='passed' for x in log['events']),1)

if __name__=='__main__':unittest.main()
