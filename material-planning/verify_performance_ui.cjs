// Large-input browser smoke measurements. All writes use a fresh temporary DB.
const fs=require('fs'), path=require('path'), os=require('os');
const {spawn}=require('child_process');
const {createHash}=require('crypto');
const {performance}=require('perf_hooks');
const {chromium}=require('C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const python='C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mrp-performance-ui-'));
const database=path.join(temp,'test.sqlite3'), url='http://127.0.0.1:8769';
const checks=[], errors=[], measurements=[];
let server,browser,browserVersion=null,completed=false;
function check(name,actual,expected){
  checks.push({name,actual,expected,passed:JSON.stringify(actual)===JSON.stringify(expected)});
  if(!checks.at(-1).passed)throw new Error(name+': '+JSON.stringify(actual));
}
(async()=>{
  try{
    server=spawn(python,[path.join(__dirname,'web_server.py'),'--port','8769','--database',database],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Test server startup timed out')),10000);
      server.stdout.on('data',b=>{if(b.toString().includes('Open http')){clearTimeout(timer);resolve();}});
      server.stderr.on('data',()=>{});
      server.on('error',e=>{clearTimeout(timer);reject(e);});
      server.on('exit',code=>{clearTimeout(timer);reject(new Error('Test server exited '+code));});
    });
    browser=await chromium.launch({channel:'msedge',headless:true});browserVersion=browser.version();
    const page=await browser.newPage({viewport:{width:1440,height:1050}});
    page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));
    async function waitForSummaryInViewport(){
      await page.waitForFunction(()=>{
        const element=document.querySelector('.metric strong');
        if(!element)return false;
        const bounds=element.getBoundingClientRect();
        return bounds.top>=0&&bounds.bottom<=innerHeight;
      });
    }
    for(const name of ['shared-stock','deep-zero-stock']){
      const payload=JSON.parse(fs.readFileSync(path.join(__dirname,'results/performance-'+name+'.json'),'utf8'));
      const previous=await page.request.get(url+'/api/workspace').then(r=>r.json());
      const saved=await page.request.post(url+'/api/workspace',{data:{payload,expected_revision:previous.revision_id}}).then(r=>r.json());
      check(name+': source save',saved.status,'SAVED');
      const startLoad=performance.now();
      await page.goto(url);await page.getByText('已保存',{exact:true}).waitFor();
      check(name+': 200 material rows and 100 selected tasks',
        [await page.locator('#editor tbody tr').count(),await page.locator('[data-select]:checked').count()],[200,100]);
      const loadSeconds=(performance.now()-startLoad)/1000;
      const response=page.waitForResponse(r=>r.url()===url+'/api/calculate'&&r.request().method()==='POST');
      const start=performance.now();
      await page.locator('#calculate').click();
      const record=await(await response).json();
      await page.locator('#status').filter({hasText:'计算完成'}).waitFor();
      await waitForSummaryInViewport();
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const visibleSeconds=(performance.now()-start)/1000;
      check(name+': complete batch generated',record.status,'VALID');
      const bundle=record.result.net_bundle;
      const expectedRows=[bundle.make_lines.length,record.result.purchase_buckets.length,bundle.allocations.length,
        bundle.demands.reduce((sum,row)=>sum+row.demand.origins.length,0)];
      check(name+': all result and trace rows reach the DOM',await page.locator('#results table').evaluateAll(tables=>tables.map(t=>t.tBodies[0].rows.length)),expectedRows);
      check(name+': 100 tasks visible in summary',await page.locator('.metric strong').first().innerText(),'100');
      const firstBatch=record.saved_batch.batch_id;
      const startHistory=performance.now();
      await page.locator(`[data-history="${firstBatch}"]`).click();
      await page.getByText('历史计划 · 只读',{exact:true}).waitFor();
      await waitForSummaryInViewport();
      const historyVisibleSeconds=(performance.now()-startHistory)/1000;
      check(name+': history retains every production row',await page.locator('#results table').first().locator('tbody tr').count(),bundle.make_lines.length);
      await page.setViewportSize({width:390,height:844});
      check(name+': narrow viewport has no page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.setViewportSize({width:1440,height:1050});
      await page.evaluate(()=>window.scrollTo({top:document.querySelector('#results').getBoundingClientRect().top+scrollY-130,behavior:'instant'}));
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      await page.screenshot({path:path.join(__dirname,'results/performance-'+name+'.png')});
      measurements.push({case:name,load_seconds:loadSeconds,click_to_visible_seconds:visibleSeconds,history_click_to_visible_seconds:historyVisibleSeconds,result_rows:expectedRows});
      console.log(name+': click-to-visible '+visibleSeconds.toFixed(3)+'s');
    }
    check('No unhandled browser errors',errors,[]);completed=true;
  }finally{
    const report={executed_at:new Date().toISOString(),completed,browser:'Headless Microsoft Edge '+browserVersion,
      method:'One UI observation per fixture; real loopback HTTP, commit, JSON and DOM. Timing includes automation and is not a latency guarantee.',
      passed:checks.filter(c=>c.passed).length,total:checks.length,checks,errors,measurements,
      source_sha256:Object.fromEntries(['verify_performance_ui.cjs','web/app.js','web/style.css','web/index.html'].map(name=>[name,createHash('sha256').update(fs.readFileSync(path.join(__dirname,name))).digest('hex')])),
      scope:'Fresh isolated database. Formal workspace and history not changed.'};
    fs.writeFileSync(path.join(__dirname,'results/performance-ui-verification.json'),JSON.stringify(report,null,2));
    if(browser)await browser.close();
    if(server&&server.exitCode===null)await new Promise(resolve=>{server.once('exit',resolve);server.kill();});
    for(const suffix of ['','-journal','-wal','-shm'])if(fs.existsSync(database+suffix))fs.unlinkSync(database+suffix);
    if(fs.readdirSync(temp).length===0)fs.rmdirSync(temp);
  }
  console.log(checks.filter(c=>c.passed).length+'/'+checks.length+' large-input browser checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
