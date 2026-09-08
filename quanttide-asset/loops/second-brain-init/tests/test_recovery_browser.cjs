/* Recovery UI behavior only; fixture responses, no GitHub or repository writes. */
const fs=require('fs'),path=require('path'),os=require('os'),{spawn}=require('child_process');
const pw=require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'));
const root=path.resolve(__dirname,'../../../..'),out=path.resolve(process.argv[2]);fs.mkdirSync(out,{recursive:true});
const server=spawn('python',['launch.py','--no-browser','--test-mode','--storage',fs.mkdtempSync(path.join(os.tmpdir(),'recovery-ui-'))],{cwd:root,detached:true,stdio:['ignore','pipe','pipe']});
let browser,checks=[],errors=[],stderr='';server.stderr.on('data',d=>stderr+=d);
const check=(value,label)=>{if(!value)throw Error(label);checks.push(label)};
(async()=>{
 const url=await new Promise((resolve,reject)=>{let text='';const t=setTimeout(()=>reject(Error(stderr||'startup timed out')),15000);server.stdout.on('data',d=>{text+=d;const m=text.match(/http:\/\/127\.0\.0\.1:\d+\/#[^\s]+/);if(m){clearTimeout(t);resolve(m[0])}})});
 browser=await pw.chromium.launch({executablePath:process.env.SECOND_BRAIN_BROWSER,headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1360,height:900}});page.on('pageerror',e=>errors.push(e.message));await page.goto(url);await page.waitForFunction(()=>rules!==null);
 const fixture={id:'0123456789abcdef',status:'paused',title:'恢复测试（模拟界面）',organization:'Example',provider:'github',total:27,completed:27,can_resume:false,events:[],repair:{id:'repair-fixture',root:'quanttide',content:'Creative Commons Attribution 4.0 International (CC BY 4.0)',created_at:'2026-09-08T00:00:00Z'},report:{provider:'github',technical_passed:false,scope:'模拟响应，不代表真实 GitHub 验收。',checked_at:'2026-09-08T00:00:00Z',rows:[{title:'远端提交是否一致',standard:'读取远端核验。',actual:'网络读取失败。',status:'unknown',source:'模拟测试',documents:[]}],failures:[{repo:'quanttide',reason:'未提交 LICENSE',status:'failed'},{repo:'quanttide-sample',reason:'连接中断',status:'unknown'}],repositories:[{name:'quanttide-sample',url:'https://github.com/Example/quanttide-sample',status:'unknown',checked_at:'2026-09-08T00:00:00Z'}]}};
 let writes=0;
 await page.route('**/api/runs/0123456789abcdef/repair-apply',r=>{writes++;return r.fulfill({json:{id:fixture.id}})});
 await page.route('**/api/runs/0123456789abcdef',r=>r.fulfill({json:fixture}));
 await page.evaluate(f=>{current=f.id;view=f;render()},fixture);
 check((await page.locator('#technical-status').textContent()).includes('1 项发现问题，1 项暂时无法核验'),'Unavailable observations are separate from actual defects');
 check((await page.locator('#failure-reasons').textContent()).includes('quanttide-sample'),'Failure details identify repository');
 check((await page.locator('#report-rows').textContent()).includes('暂时无法核验'),'Requirement row preserves unknown state');
 check((await page.locator('#repair-content').textContent()).includes('CC BY 4.0'),'Repair displays proposed license content');
 await page.locator('#repair-apply').click();check(writes===0,'No repair request without explicit confirmation');
 await page.locator('#repair-confirmed').check();await page.locator('#repair-apply').click();await page.waitForFunction(()=>!busy);check(writes===1,'Confirmed repair sends exactly one request');
 await page.screenshot({path:path.join(out,'repair-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Paused repair screen fits mobile viewport');
 await page.screenshot({path:path.join(out,'repair-mobile.png'),fullPage:true});check(errors.length===0,'No JavaScript errors');
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'passed',at:new Date().toISOString(),checks,errors,platform:process.platform,github:'simulated',real_windows:false},null,2));console.log(JSON.stringify({status:'passed',checks:checks.length}));
})().catch(e=>{fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'failed',error:String(e),checks,errors},null,2));console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();try{process.kill(-server.pid,'SIGTERM')}catch{}});
