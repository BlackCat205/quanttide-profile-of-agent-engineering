/* Browser checks for account UI. All GitHub responses are simulated; no remote writes. */
const fs=require('fs'),path=require('path'),os=require('os'),{spawn}=require('child_process');
let pw;try{pw=require('playwright')}catch{pw=require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'))}
const root=path.resolve(__dirname,'../../../..'),out=path.resolve(process.argv[2]);
if(fs.existsSync(out))throw Error('Use new evidence path');fs.mkdirSync(out,{recursive:true});
const store=fs.mkdtempSync(path.join(os.tmpdir(),'brain-account-ui-'));
const server=spawn('python',['launch.py','--no-browser','--storage',store],{cwd:root,detached:true,stdio:['ignore','pipe','pipe']});
let browser,errors=[],checks=[],stderr='';server.stderr.on('data',d=>stderr+=d);
function check(condition,message){if(!condition)throw Error(message);checks.push(message)}
(async()=>{
 const url=await new Promise((resolve,reject)=>{let text='';const timeout=setTimeout(()=>reject(Error(stderr||'Startup timed out')),15000);server.stdout.on('data',d=>{text+=d;const m=text.match(/http:\/\/127\.0\.0\.1:\d+\/#[^\s]+/);if(m){clearTimeout(timeout);resolve(m[0])}})});
 browser=await pw.chromium.launch({headless:true,executablePath:process.env.SECOND_BRAIN_BROWSER,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:900}});page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/github/check',route=>route.fulfill({json:{status:'connected',login:'BlackCat205',id:205,message:'模拟授权状态，仅验证页面。',checked_at:new Date().toISOString()}}));
 let missing=true;
 await page.route('**/api/github/login',route=>route.fulfill({json:missing?{status:'missing',message:'模拟未安装 CLI'}:{status:'waiting',device_code:'TEST-0000',message:'模拟验证码，不可用于实际登录。'}}));
 await page.route('**/api/github/cancel',route=>route.fulfill({json:{status:'cancelled',message:'已取消本次登录。'}}));
 await page.goto(url);await page.waitForFunction(()=>rules!==null);
 check(!(await page.locator('#github-option').isDisabled()),'Personal GitHub option is enabled in standard launcher');
 await page.locator('#provider').selectOption('github');await page.locator('#github-login').click();await page.locator('#github-install').waitFor({state:'visible'});
 check((await page.locator('#github-install').textContent()).includes('Download MSI'),'Missing CLI shows Windows installer instructions');
 await page.waitForTimeout(1200);check(await page.locator('#github-install').isVisible(),'Installation guidance survives instead of being overwritten by login polling');
 missing=false;await page.waitForFunction(()=>!busy);await page.locator('#github-login').click();await page.waitForFunction(()=>document.querySelector('#github-code').textContent.includes('TEST-0000'));
 check((await page.locator('#github-authorize').getAttribute('href'))==='https://github.com/login/device','Device code points to official GitHub authorization page');
 check(await page.locator('#github-cancel').isVisible(),'Waiting authorization can be cancelled');
 await page.waitForFunction(()=>!busy);await page.locator('#github-cancel').click();await page.locator('#github-code').waitFor({state:'hidden'});check(!(await page.locator('#github-code').isVisible()),'Cancellation removes one-time code');
 await page.waitForFunction(()=>!busy);await page.locator('#github-check').click();await page.waitForFunction(()=>document.querySelector('input[name=organization]').value==='BlackCat205');check((await page.locator('input[name=organization]').inputValue())==='BlackCat205','Canonical mixed-case account fills target');
 await page.locator('input[name=root_repo]').fill('second-brain-test');
 await page.evaluate(()=>{view={status:'completed'};reset()});
 check((await page.locator('#provider').inputValue())==='github','Next creation keeps GitHub mode');
 check((await page.locator('input[name=root_repo]').inputValue())==='second-brain-test','Next creation keeps selected root');
 check((await page.locator('select[name=root_mode]').inputValue())==='existing','After completion next creation uses existing root');
 check(await page.locator('input[name=test_organization]').isVisible(),'Owned test organization field is available');
 await page.evaluate(()=>{view={status:'completed',organization:'TestOrg',plan:{provider:'github',owner_type:'Organization',account_login:'BlackCat205',root_repo:'second-brain-test',root_mode:'new'}};reset()});
 check((await page.locator('input[name=test_organization]').inputValue())==='TestOrg','Next creation preserves the selected organization');
 check((await page.locator('input[name=organization]').inputValue())==='BlackCat205','Organization selection does not replace logged-in account identity');
 await page.setViewportSize({width:390,height:844});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Account form fits mobile viewport');
 await page.setViewportSize({width:1280,height:900});await page.screenshot({path:path.join(out,'account-form.png'),fullPage:true});
 check(!fs.existsSync(path.join(store,'runs')),'Account UI test makes no creation plans or repositories');
 check(!errors.length,'No JavaScript errors');
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'passed',checked_at:new Date().toISOString(),platform:process.platform,checks,errors,github_api:'simulated',real_github:false,real_windows:false},null,2));console.log(JSON.stringify({status:'passed',checks:checks.length}));
})().catch(e=>{fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'failed',error:String(e),checks,errors,stderr},null,2));console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();try{process.kill(-server.pid,'SIGTERM')}catch{}});
