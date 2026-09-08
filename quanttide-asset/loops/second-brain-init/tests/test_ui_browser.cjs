/* Run with Node + Playwright and an installed Chromium. Uses simulated feedback. */
const fs=require('fs'),path=require('path'),os=require('os'),{spawn}=require('child_process');
let playwright;try{playwright=require('playwright')}catch{playwright=require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'))}
const repo=path.resolve(__dirname,'../../../..');
const out=path.resolve(process.argv[2]||'ui-browser-evidence');
if(fs.existsSync(out))throw new Error('Use a new evidence directory');fs.mkdirSync(out,{recursive:true});
const storage=fs.mkdtempSync(path.join(os.tmpdir(),'second-brain-browser-'));
if(process.env.SECOND_BRAIN_BROWSER)fs.chmodSync(process.env.SECOND_BRAIN_BROWSER,0o755);
const server=spawn(process.env.SECOND_BRAIN_TEST_PYTHON||'python',['launch.py','--no-browser','--test-mode','--storage',storage],{cwd:repo,detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});
const checks=[],errors=[];let browser,serverErrors='';server.stderr.on('data',d=>serverErrors+=d.toString());
async function capture(page,args){if(process.env.SECOND_BRAIN_SCREENSHOTS==='focused'&&!['00-survey.png','03-review.png'].includes(path.basename(args.path)))return;return page.screenshot(args);}
function check(condition,message){if(!condition)throw new Error(message);checks.push(message)}
(async()=>{
 let log='';const url=await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error('Server did not start')),15000);server.stdout.on('data',d=>{log+=d;const m=log.match(/http:\/\/127\.0\.0\.1:\d+\/#[^\s]+/);if(m){clearTimeout(t);resolve(m[0])}});server.on('exit',c=>reject(new Error('Server exited '+c+' '+serverErrors)))});
 browser=await playwright.chromium.launch({headless:true,...(process.env.SECOND_BRAIN_BROWSER?{executablePath:process.env.SECOND_BRAIN_BROWSER}:{}),args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url);await page.waitForFunction(()=>rules!==null);await page.locator('#fill-example').click();
 for(const [value,expected] of [['My Project','小写'],['sample_name','下划线'],['-sample','开头'],['a--b','单个'],['journal','资产类别'],['领域','小写']]){
  await page.locator('input[name=short_name]').fill(value);
  check((await page.locator('#feedback-short_name').textContent()).includes(expected),'Inline guidance explains invalid name: '+value);
 }
 await page.locator('#plan-button').click();check(!fs.existsSync(path.join(storage,'runs')),'Invalid name creates no plan or repositories');
 await capture(page,{path:path.join(out,'00-invalid-name.png'),fullPage:true});
 await page.locator('#fill-example').click();
 check((await page.locator('#feedback-short_name').textContent()).includes('quanttide-sample'),'Valid short name previews repository name');
 check((await page.locator('#feedback-english_name').textContent()).includes('quanttide-journal-of-sample-engineering'),'English name previews asset suffix');
 const surveyFixture={id:'fixture',status:'completed',domain:{chinese_name:'模拟调查',short_name:'sample',english_name:'sample-engineering'},report:{organization:'quanttide',started_at:'2026-01-01T00:00:00Z',finished_at:'2026-01-01T00:00:01Z',scope:'模拟响应：仅测试界面显示',repositories:[{name:'quanttide',status:'exists',action:'已找到总入口，当前仅查看，未修改',checked_at:'2026-01-01T00:00:00Z',commit:'abc123'},{name:'quanttide-sample',status:'unknown',reason:'未发现公开资源，不能证明名称可用。',checked_at:'2026-01-01T00:00:01Z'}],rules:{status:'changed',adopted:{commit:'old-rule'},latest_file:{sha:'new-rule'}},documents:{'domains/README.md':{status:'ok',text:'# 模拟总目录'}},note:'这是假响应，不代表量潮当前状态。'}};
 await page.route('**/api/survey',route=>route.fulfill({json:{id:'fixture'}}));
 await page.route('**/api/surveys/fixture',route=>route.fulfill({json:surveyFixture}));
 await page.locator('#survey-button').click();await page.waitForFunction(()=>document.querySelector('#survey-result').textContent.includes('abc123'));
 check((await page.locator('#survey-result').textContent()).includes('2026-01-01'),'Survey shows observation timestamp (simulated response)');
 check((await page.locator('#survey-result').textContent()).includes('无法确定'),'Survey preserves uncertainty instead of marking name available');
 check((await page.locator('#survey-result').textContent()).includes('在线文件已变化'),'Survey warns when adopted rule differs');
 check(!fs.existsSync(path.join(storage,'runs')),'Read-only UI action does not create a plan');
 await capture(page,{path:path.join(out,'00-survey.png'),fullPage:true});
 await page.unroute('**/api/survey');await page.unroute('**/api/surveys/fixture');await page.evaluate(()=>sessionStorage.removeItem('second-brain-survey'));

await capture(page,{path:path.join(out,'01-create.png'),fullPage:true});
 check(await page.locator('#test-banner').isVisible(),'UI identifies automated feedback as simulated');
 await page.setViewportSize({width:390,height:844});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile form fits viewport');await capture(page,{path:path.join(out,'02-mobile.png'),fullPage:true});await page.setViewportSize({width:1440,height:1000});
 await page.locator('#plan-button').click();await page.locator('#review-screen').waitFor({state:'visible',timeout:60000});
 check(await page.locator('#preflight-checks .preflight-row').count()===4,'Review shows four requirement checks');
 check((await page.locator('#preflight-checks').textContent()).includes('需人工确认'),'Review does not auto-approve meaning or destination');
 check(!(await page.locator('#preflight-checks').textContent()).includes('需修改'),'Valid planned repository names match specification');
 check((await page.locator('#observation-info').textContent()).includes('没有查询线上'),'Local plan clearly distinguishes local observations');
 check((await page.locator('#repository-list').textContent()).includes('拟新建本地仓库'),'Plan lists per-repository proposed action');
 check(await page.locator('.repo-item').count()===8,'Review explains all eight repositories');
 check(fs.readdirSync(path.join(storage,'runs')).length===1,'One run has been planned');
 check(!fs.existsSync(path.join(storage,'workspaces')),'Planning creates no target repositories');
 await capture(page,{path:path.join(out,'03-review.png'),fullPage:true});
 await page.locator('#reviewer').fill('浏览器自动化测试');await page.locator('#confirmed').check();await page.locator('#execute-button').click();
 await page.locator('#result-screen').waitFor({state:'visible',timeout:120000});
 check((await page.locator('#operation-events').textContent()).includes('保存修改并推送仓库'),'Progress names actual repository operations');
 check((await page.locator('#operation-events').textContent()).includes('开始'),'Progress includes actual started events');
 check((await page.locator('#execution-check').textContent()).includes('通过'),'Result exposes real pre-execution recheck record');
 check((await page.locator('#technical-status').textContent()).includes('技术检查通过'),'Real Git execution passes technical checks');
 check(await page.locator('.report-row').count()===7,'Seven plain-language checks show actual evidence');
 check(await page.locator('#show-storage').isVisible(),'Record location remains accessible on result screen');
 await page.locator('#show-storage').click();await page.locator('#document-dialog').waitFor({state:'visible'});
 check((await page.locator('#document-content').textContent()).includes(storage),'Location dialog shows actual storage directory');await page.locator('#close-document').click();
 const diagnosticDownload=page.waitForEvent('download');await page.locator('#export-diagnostics').click();const diagnostic=await diagnosticDownload;
 check(diagnostic.suggestedFilename()==='second-brain-diagnostics.zip','One-click diagnostic ZIP downloads');await diagnostic.saveAs(path.join(out,'diagnostics.zip'));
 check((await page.locator('#current-operation').textContent()).includes('验收：'),'Verification progress is distinct from creation progress');

 check((await page.locator('#acceptance-state').textContent()).includes('待本人验收'),'Technical pass does not auto-approve human acceptance');
 await page.locator('#open-home').click();await page.locator('#document-dialog').waitFor({state:'visible'});
 check((await page.locator('#document-content').textContent()).includes('相邻领域分工'),'Actual domain README opens in readable dialog');await capture(page,{path:path.join(out,'04-home.png'),fullPage:true});await page.locator('#close-document').click();
 await page.locator('#acceptance-reviewer').fill('浏览器自动化测试');await page.selectOption('select[name=meaning]','passed');await page.selectOption('select[name=navigation]','passed');await page.selectOption('select[name=usability]','improve');await page.locator('#acceptance-form textarea').fill('模拟试用意见：希望提供更多日志填写示例。');await page.locator('#acceptance-form button[type=submit]').click();
 await page.waitForFunction(()=>document.querySelector('#acceptance-state').textContent.includes('模拟验收记录'));
 check((await page.locator('#acceptance-state').textContent()).includes('需要改进'),'Mixed human feedback is preserved as needs improvement');
 const downloadPromise=page.waitForEvent('download');await page.locator('#export-report').click();const download=await downloadPromise;await download.saveAs(path.join(out,'acceptance-export.html'));
 const exported=fs.readFileSync(path.join(out,'acceptance-export.html'),'utf8');check(exported.includes('模拟反馈')&&exported.includes('需改进'),'Export preserves scope and simulated improvement feedback');
 await capture(page,{path:path.join(out,'05-acceptance.png'),fullPage:true});
 await page.reload();await page.locator('#result-screen').waitFor({state:'visible'});check((await page.locator('#acceptance-state').textContent()).includes('模拟验收记录'),'Browser refresh restores run and saved feedback');
 await page.setViewportSize({width:390,height:844});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile report fits viewport');
 // Regression: create a second domain from the completed report, then return to the first.
 const firstKey=fs.readdirSync(path.join(storage,'runs'))[0];
 const firstAcceptance=fs.readFileSync(path.join(storage,'runs',firstKey,'human-acceptance.json'),'utf8');
 await page.locator('#bottom-new').click();await page.locator('#form-screen').waitFor({state:'visible'});
 check(await page.locator('input[name=chinese_name]').inputValue()==='','New-domain action clears prior inputs');
 check(await page.evaluate(()=>scrollY<20),'New-domain action returns to top of form');
 await page.reload();await page.locator('#form-screen').waitFor({state:'visible'});
 check(await page.locator('#form-screen').isVisible(),'Refresh after returning does not reopen the previous report');
 await page.locator('#fill-example').click();
 await page.locator('input[name=chinese_name]').fill('协作工程');await page.locator('input[name=short_name]').fill('collab');await page.locator('input[name=english_name]').fill('collaboration-engineering');
 await page.locator('#plan-button').click();await page.locator('#review-screen').waitFor({state:'visible',timeout:60000});
 await page.locator('#edit-plan').click();check(await page.locator('input[name=chinese_name]').inputValue()==='协作工程','Return to edit preserves selected plan input');
 await page.locator('#plan-button').click();await page.locator('#review-screen').waitFor({state:'visible',timeout:60000});
 await page.locator('#reviewer').fill('连续创建自动化测试');await page.locator('#confirmed').check();await page.locator('#execute-button').click();
 await page.locator('#result-screen').waitFor({state:'visible',timeout:120000});
 check((await page.locator('#result-title').textContent()).includes('协作工程'),'Second domain completes in the same browser session');
 const workspaces=fs.readdirSync(path.join(storage,'workspaces'));
 check(workspaces.length===2,'Two completed domains use two independent local workspaces');
 check(workspaces.some(key=>fs.existsSync(path.join(storage,'workspaces',key,'repositories','quanttide-sample'))),'First domain repositories are preserved');
 check(workspaces.some(key=>fs.existsSync(path.join(storage,'workspaces',key,'repositories','quanttide-collab'))),'Second domain repositories actually exist');
 check(fs.readFileSync(path.join(storage,'runs',firstKey,'human-acceptance.json'),'utf8')===firstAcceptance,'First acceptance record is unchanged');
 await page.locator('.history-item').filter({hasText:'示例工程'}).click();await page.waitForFunction(()=>document.querySelector('#result-title').textContent.includes('示例工程'));
 check((await page.locator('#acceptance-state').textContent()).includes('模拟验收记录'),'History can reopen the first domain and feedback');
 await capture(page,{path:path.join(out,'06-repeat-create-mobile.png'),fullPage:true});
 await page.locator('#result-new').click();await page.locator('#form-screen').waitFor({state:'visible'});
 check(await page.locator('input[name=chinese_name]').inputValue()==='','Result-header new action also works');
 await page.setViewportSize({width:1440,height:1000});await capture(page,{path:path.join(out,'07-return-to-form.png'),fullPage:true});
 check(errors.length===0,'No JavaScript runtime errors');
 const key=firstKey;const run=path.join(storage,'runs',key);
 for(const file of ['request.yaml','ui.json','ui-report.json','human-acceptance.json','approval-record.json','execution-log.json','verification-report.json','pre-execution-check.json'])fs.copyFileSync(path.join(run,file),path.join(out,file));
 fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({status:'passed',at:new Date().toISOString(),browser:browser.version(),platform:process.platform,checks,errors,simulated:true,real_windows_test:false,real_github_test:false},null,2));console.log(JSON.stringify({status:'passed',checks:checks.length,browser:browser.version()}));
})().catch(e=>{fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({status:'failed',error:e.stack,checks,errors,serverErrors},null,2));console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();try{if(process.platform==='win32')server.kill('SIGTERM');else process.kill(-server.pid,'SIGTERM')}catch{}});
