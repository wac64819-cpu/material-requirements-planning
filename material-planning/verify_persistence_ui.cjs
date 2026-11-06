const fs=require('fs'),path=require('path'),os=require('os');
const {spawn,spawnSync}=require('child_process');
const {chromium}=require('C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const python='C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const out=process.env.MRP_TEST_ARTIFACT_DIR || path.join(__dirname,'results');
fs.mkdirSync(out,{recursive:true});
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mrp-ui-'));
const database=path.join(temp,'test.sqlite3'),url='http://127.0.0.1:8767';
let server,serverLog='';const checks=[];
function check(name,actual,expected){checks.push({name,actual,expected,passed:JSON.stringify(actual)===JSON.stringify(expected)});if(!checks.at(-1).passed)throw new Error(name+': '+JSON.stringify(actual));}
async function start(){
  server=spawn(python,[path.join(__dirname,'web_server.py'),'--port','8767','--database',database],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(new Error('Test server startup timed out: '+serverLog)),10000);
    server.stdout.on('data',b=>{serverLog+=b.toString();if(b.toString().includes('Open http')){clearTimeout(timeout);resolve();}});
    server.stderr.on('data',b=>serverLog+=b.toString());
    server.on('error',reject);server.on('exit',code=>{clearTimeout(timeout);if(code)reject(new Error('Test server exited '+code));});
  });
}
async function stop(){if(server && server.exitCode===null)await new Promise(resolve=>{server.once('exit',resolve);server.kill();});}
(async()=>{
  let browser;
  try{
    await start();
    const regression=spawnSync(process.execPath,[path.join(__dirname,'verify_workbench.cjs')],{env:{...process.env,MRP_TEST_URL:url},windowsHide:true,encoding:'utf8',timeout:90000});
    if(regression.status!==0)throw new Error(regression.stdout+regression.stderr);
    console.log(regression.stdout.trim());
    browser=await chromium.launch({channel:'msedge',headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1050}});
    const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));page.on('dialog',d=>d.accept());
    await page.goto(url);await page.getByText('示例已载入',{exact:true}).waitFor();
    await page.getByLabel('物料第1行 名称',{exact:true}).fill('成品甲');
    await page.locator('#save-data').click();await page.locator('#save-status').filter({hasText:'已保存 ·'}).waitFor();
    const workspace=await page.request.get(url+'/api/workspace').then(r=>r.json());
    check('First save creates source version',Boolean(workspace.revision_id),true);
    await page.reload();await page.getByText('已保存',{exact:true}).waitFor();
    check('Reload restores saved edit',await page.getByLabel('物料第1行 名称',{exact:true}).inputValue(),'成品甲');
    async function calculate(){
      await page.locator('[data-view="planning"]').click();
      const response=page.waitForResponse(r=>r.url()===url+'/api/calculate'&&r.request().method()==='POST');
      await page.locator('#calculate').click();const record=await(await response).json();
      await page.locator('#status').filter({hasText:'计算完成'}).waitFor();return record;
    }
    const first=await calculate();
    check('Plan saved badge shown',await page.locator('#history-meta').innerText().then(t=>t.includes(first.saved_batch.batch_id.slice(0,8))),true);
    const other=await browser.newPage();other.on('dialog',d=>d.accept());await other.goto(url);await other.getByText('已保存',{exact:true}).waitFor();
    await page.locator('[data-view="data"]').click();
    await page.getByRole('tab',{name:'生产任务',exact:true}).click();
    await page.getByLabel('生产任务第2行 需求数量',{exact:true}).fill('10');
    await page.locator('#save-data').click();await page.locator('#save-status').filter({hasText:'已保存 ·'}).waitFor();
    await calculate();
    await page.locator('[data-view="history"]').click();
    await page.locator('#refresh-history').click();
    await page.locator(`[data-history="${first.saved_batch.batch_id}"]`).click();
    await page.getByText('历史计划 · 只读',{exact:true}).waitFor();
    check('History shows old LOW quantity',await page.locator('#results table').first().locator('tbody tr').nth(2).locator('td').nth(4).innerText(),'100');
    check('History does not replace current edit',await page.getByLabel('生产任务第2行 需求数量',{exact:true}).inputValue(),'10');
    await page.locator('#historical-input summary').click();
    check('History includes original source snapshot',await page.locator('#historical-input').innerText().then(t=>t.includes('成品甲')),true);
    await page.screenshot({path:path.join(out,'persistence-history.png'),fullPage:true});
    await other.getByLabel('物料第1行 名称',{exact:true}).fill('另一页面的编辑');await other.locator('#save-data').click();
    await other.locator('#save-status').filter({hasText:'另一页面已保存'}).waitFor();
    check('Conflict keeps unsaved local edit',await other.getByLabel('物料第1行 名称',{exact:true}).inputValue(),'另一页面的编辑');
    check('Conflict does not overwrite database',(await page.request.get(url+'/api/workspace').then(r=>r.json())).payload.sources.materials[0].name,'成品甲');
    await page.locator('[data-view="data"]').click();
    await page.getByLabel('生产任务第2行 需求数量',{exact:true}).fill('1.5');await page.locator('#save-data').click();
    await page.locator('#result-badge').filter({hasText:'校验未通过'}).waitFor();
    check('Invalid save keeps previous data',(await page.request.get(url+'/api/workspace').then(r=>r.json())).payload.sources.tasks[1].required_qty,10);
    await page.locator('[data-view="data"]').click();
    await page.locator('#reload-saved').click();await page.getByText('已保存',{exact:true}).waitFor();
    check('Explicit reload restores valid data',await page.getByLabel('生产任务第2行 需求数量',{exact:true}).inputValue(),'10');
    await stop();await start();await page.reload();await page.getByText('已保存',{exact:true}).waitFor();
    check('Server restart restores source',await page.getByLabel('物料第1行 名称',{exact:true}).inputValue(),'成品甲');
    check('Server restart preserves history',(await page.request.get(url+'/api/history/'+first.saved_batch.batch_id).then(r=>r.json())).saved_batch.batch_id,first.saved_batch.batch_id);
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'persistence-mobile.png'),fullPage:true});
    check('Persistence toolbar and history fit mobile',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    check('No unhandled page errors',pageErrors,[]);
    const result={executed_at:new Date().toISOString(),passed:checks.filter(c=>c.passed).length,total:checks.length,checks,scope:'Isolated temporary SQLite, real browser and server restart. User database untouched.'};
    fs.writeFileSync(path.join(out,'persistence-ui-verification.json'),JSON.stringify(result,null,2));
    console.log(result.passed+'/'+result.total+' persistence browser checks passed');
  } finally {
    if(browser)await browser.close();await stop();
    // Only remove known files from the exact freshly-created test directory.
    for(const suffix of ['', '-journal','-wal','-shm'])if(fs.existsSync(database+suffix))fs.unlinkSync(database+suffix);
    if(fs.readdirSync(temp).length===0)fs.rmdirSync(temp);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
