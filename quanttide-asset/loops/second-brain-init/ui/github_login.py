"""Official gh browser login; only the one-time device code reaches the UI."""
import os
import re
import shutil
import subprocess
import threading
import time
import engine as e

class Login:
    def __init__(self):
        self.lock=threading.RLock()
        self.state={'status':'idle'}
        self.process=None

    def status(self):
        with self.lock:return dict(self.state)

    def inspect(self):
        if not shutil.which('gh'):
            return {'status':'missing','message':'请先安装 GitHub CLI，安装后关闭并重新打开启动向导。','install_url':'https://cli.github.com/'}
        try:
            import json
            user=json.loads(e.command(['gh','api','user']).stdout)
            return {'status':'connected','login':e.github_owner(user['login']),'id':user['id'],'checked_at':e.now(),
                    'message':'账号连接正常。创建权限、仓库状态及实际推送结果会在后续步骤核对。'}
        except (e.WorkflowError,ValueError,KeyError):
            return {'status':'disconnected','message':'尚未登录或无法连接 GitHub，请登录或检查网络后刷新。','checked_at':e.now()}

    def start(self):
        with self.lock:
            e.require(self.state['status']!='waiting','登录正在进行，请完成授权或取消。')
            if not shutil.which('gh'):
                self.state=self.inspect()
                return dict(self.state)
            env=dict(os.environ,GH_HOST='github.com',GH_PROMPT_DISABLED='1',GH_BROWSER='')
            # An environment token overrides stored interactive credentials. Do not silently use another identity.
            e.require(not any(env.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN')),'检测到环境变量授权；请使用“检查登录状态”确认账号，或在不设置令牌的终端启动本工具。')
            self.process=subprocess.Popen(['gh','auth','login','--hostname','github.com','--git-protocol','https','--web'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
            proc=self.process
            self.state={'status':'waiting','started_at':e.now(),'message':'等待 GitHub 官方授权；下方出现一次性验证码后，点击授权页面并输入验证码。'}
            try:proc.stdin.write(b'\n');proc.stdin.flush();proc.stdin.close()
            except (BrokenPipeError,OSError):pass
        def collect():
            deadline=threading.Timer(300,lambda:self.cancel(proc,'授权等待超时，请重新连接。'));deadline.daemon=True;deadline.start()
            recent=b''
            try:
                while True:
                    part=proc.stdout.read(1)
                    if not part:break
                    recent=(recent+part)[-2048:]
                    match=re.search(rb'(?:code:|code\s+)\s*([A-Z0-9]{4}-[A-Z0-9]{4})',recent)
                    if match:
                        with self.lock:
                            if self.process is proc and self.state['status']=='waiting':self.state['device_code']=match[1].decode('ascii')
                code=proc.wait()
                result=self.inspect() if code==0 else {'status':'failed','message':'GitHub 授权未完成，请检查网络后重试。'}
                with self.lock:
                    if self.process is proc and self.state['status']=='waiting':self.state=result
            finally:
                deadline.cancel();proc.stdout.close()
        threading.Thread(target=collect,daemon=True).start()
        return self.status()

    def cancel(self,process=None,message='已取消本次登录。'):
        with self.lock:
            if process is not None and self.process is not process:return self.status()
            if self.process and self.process.poll() is None:self.process.terminate()
            self.state={'status':'cancelled','message':message}
            return dict(self.state)
