const fs=require('fs'),path=require('path'),os=require('os');
const {spawn,spawnSync}=require('child_process');
const {chromium}=require('C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const python='C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const out=process.env.MRP_TEST_ARTIFACT_DIR || path.join(__dirname,'results');
fs.mkdirSync(out,{recursive:true});
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mrp-csv-ui-')),database=path.join(temp,'test.sqlite3'),url='http://127.0.0.1:8768';
const checks=[],errors=[];let server,browser;
function check(name,actual,expected){checks.push({name,actual,expected,passed:JSON.stringify(actual)===JSON.stringify(expected)});if(!checks.at(-1).passed)throw new Error(name+': '+JSON.stringify(actual));}
function csvRows(bytes){
  const parsed=spawnSync(python,['-X','utf8','-c','import csv,io,json,sys; r=csv.DictReader(io.StringIO(sys.stdin.buffer.read().decode("utf-8-sig"),newline="")); rows=list(r); print(json.dumps({"fields":r.fieldnames,"rows":rows}))'],{input:bytes,windowsHide:true});
  if(parsed.status!==0)throw new Error(parsed.stderr.toString());
  return JSON.parse(parsed.stdout.toString());
}
(async()=>{
  try{
    server=spawn(python,[path.join(__dirname,'web_server.py'),'--port','8768','--database',database],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Startup timed out')),10000);server.stdout.on('data',b=>{if(b.toString().includes('Open http')){clearTimeout(timer);resolve();}});server.stderr.on('data',()=>{});server.on('error',reject);});
    browser=await chromium.launch({channel:'msedge',headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1050},acceptDownloads:true});
    page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
    await page.goto(url);await page.getByText('示例已载入',{exact:true}).waitFor();
    await page.locator('.csv-panel summary').click();
    let wait=page.waitForEvent('download');await page.getByText('下载四表示例模板',{exact:true}).click();let file=await wait;
    check('Template ZIP downloads',file.suggestedFilename(),'mrp-csv-templates.zip');
    check('ZIP signature',fs.readFileSync(await file.path()).subarray(0,2).toString(),'PK');
    const csv='task_id,product_id,required_qty,due_date,priority\r\nLOW,A,100,2026-10-20,2\r\nHIGH,A,60,2026-10-21,1\r\n';
    async function upload(text){await page.locator('[data-view="data"]').click();await page.locator('[data-csv="tasks"]').setInputFiles({name:'tasks.csv',mimeType:'text/csv',buffer:Buffer.from(text)});}
    async function preview(){await page.locator('#preview-csv').click();await page.locator('#csv-message').filter({hasText:/校验通过|未应用导入/}).waitFor();}
    await page.getByRole('tab',{name:'生产任务',exact:true}).click();
    await upload(csv);await preview();
    check('Preview does not replace editor',await page.getByLabel('生产任务第1行 需求数量',{exact:true}).inputValue(),'100');
    check('Preview does not save database',(await page.request.get(url+'/api/workspace').then(r=>r.json())).revision_id,null);
    await page.locator('#apply-csv').click();
    check('Apply installs imported row',await page.getByLabel('生产任务第1行 需求数量',{exact:true}).inputValue(),'60');
    check('Apply leaves save explicit',(await page.request.get(url+'/api/workspace').then(r=>r.json())).revision_id,null);
    await page.locator('#save-data').click();await page.locator('#save-status').filter({hasText:'已保存 ·'}).waitFor();
    async function calculate(){await page.locator('[data-view="planning"]').click();const response=page.waitForResponse(r=>r.url()===url+'/api/calculate'&&r.request().method()==='POST');await page.locator('#calculate').click();const result=await(await response).json();await page.locator('#status').filter({hasText:'计算完成'}).waitFor();return result;}
    const first=await calculate();
    async function download(kind){await page.locator('#export-kind').selectOption(kind);const event=page.waitForEvent('download');await page.locator('#export-csv').click();const download=await event;return {name:download.suggestedFilename(),bytes:fs.readFileSync(await download.path())};}
    const made=await download('MAKE');
    check('Download identifies saved batch',made.name,'plan-'+first.saved_batch.batch_id+'-MAKE.csv');
    check('CSV contains independent expected production',made.bytes.toString('utf8').includes(',HIGH,A,60,0,60,2026-10-21,2026-10-19'),true);
    const exports={MAKE:made};
    for(const kind of ['PURCHASE','ALLOCATION','TRACE','RISK']){const output=await download(kind);exports[kind]=output;check(kind+' downloads UTF8 BOM',output.bytes.subarray(0,3).toString('hex'),'efbbbf');}
    const parsed={};
    for(const [kind,count] of Object.entries({MAKE:4,PURCHASE:4,ALLOCATION:8,TRACE:8,RISK:0})){
      fs.writeFileSync(path.join(out,'download-'+kind+'.csv'),exports[kind].bytes);
      parsed[kind]=csvRows(exports[kind].bytes);
      check(kind+' export row count',parsed[kind].rows.length,count);
      check(kind+' export batch and header',parsed[kind].fields[0]==='batch_id' && parsed[kind].rows.every(r=>r.batch_id===first.saved_batch.batch_id),true);
    }
    check('Purchase exported quantities and dates',parsed.PURCHASE.rows.map(r=>[r.material_id,r.needed_date,r.purchase_qty,r.order_date]),[['C','2026-10-18','300','2026-10-14'],['C','2026-10-19','130','2026-10-15'],['D','2026-10-15','800','2026-10-10'],['D','2026-10-16','300','2026-10-11']]);
    const allocation=parsed.ALLOCATION.rows.find(r=>r.task_id==='HIGH' && r.material_id==='B');
    check('Allocation export conserves shared stock',[allocation.before_qty,allocation.allocated_qty,allocation.after_qty],['20','20','0']);
    const trace=parsed.TRACE.rows.find(r=>r.task_id==='HIGH' && r.material_id==='D');
    check('Trace exports BOM path and net demand',[JSON.parse(trace.bom_path),trace.contribution_qty,trace.allocated_qty,trace.residual_qty],[['A','B','D'],'400','100','300']);
    check('Empty risk export retains all columns',parsed.RISK.fields,['batch_id','code','severity','source_location','task_id','material_id','computed_date','days_before_baseline','message']);
    await page.locator('[data-view="data"]').click();
    await page.getByLabel('生产任务第2行 需求数量',{exact:true}).fill('10');
    check('Edit clears stale export control',await page.locator('#export-controls').isHidden(),true);
    await calculate();await page.locator('[data-view="history"]').click();await page.locator('#refresh-history').click();
    await page.locator(`[data-history="${first.saved_batch.batch_id}"]`).click();await page.getByText('历史计划 · 只读',{exact:true}).waitFor();
    const old=await download('MAKE');check('Historical download unaffected by new input',old.bytes.equals(made.bytes),true);
    await upload('task_id,product_id\r\nBAD,A\r\n');await preview();
    check('Bad CSV keeps original edit',await page.getByLabel('生产任务第2行 需求数量',{exact:true}).inputValue(),'10');
    check('Bad CSV cannot apply',await page.locator('#apply-csv').isDisabled(),true);
    check('Bad header error visible',await page.locator('#csv-message').innerText().then(t=>t.includes('表头')),true);
    await upload(csv);await preview();await page.getByLabel('生产任务第2行 需求数量',{exact:true}).fill('11');
    check('Editor change invalidates preview',await page.locator('#apply-csv').isDisabled(),true);
    await page.locator('[data-csv="tasks"]').setInputFiles({name:'bad-encoding.csv',mimeType:'text/csv',buffer:Buffer.from([0xff,0xfe,0x81])});
    await page.locator('#preview-csv').click();await page.locator('#csv-message').filter({hasText:'不是有效的UTF-8'}).waitFor();
    check('Invalid encoding cannot apply',await page.locator('#apply-csv').isDisabled(),true);
    await upload(csv);await preview();
    await page.screenshot({path:path.join(out,'csv-workbench.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'csv-mobile.png'),fullPage:true});
    check('Import toolbar fits narrow screen',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.getByRole('tab',{name:'物料',exact:true}).click();
    await page.getByLabel('物料第1行 提前期 / 天',{exact:true}).fill('30');
    const risky=await calculate(),riskDownload=await download('RISK');
    fs.writeFileSync(path.join(out,'download-RISK-with-rows.csv'),riskDownload.bytes);
    const riskRows=csvRows(riskDownload.bytes).rows;
    check('Nonempty risk export matches saved batch',riskRows.length===risky.result.risks.length && riskRows.length>0 && riskRows.every(r=>r.batch_id===risky.saved_batch.batch_id),true);
    const highRisk=riskRows.find(r=>r.task_id==='HIGH' && r.material_id==='A');
    check('Risk CSV exports independently calculated early date',[highRisk.computed_date,highRisk.days_before_baseline],['2026-09-21','10']);
    check('No unhandled browser errors',errors,[]);
  }finally{
    const report={executed_at:new Date().toISOString(),passed:checks.filter(c=>c.passed).length,total:checks.length,checks,errors,scope:'Isolated test database; no user data changed.'};
    fs.writeFileSync(path.join(out,'csv-ui-verification.json'),JSON.stringify(report,null,2));
    if(browser)await browser.close();if(server && server.exitCode===null)await new Promise(resolve=>{server.once('exit',resolve);server.kill();});
    for(const suffix of ['','-journal','-wal','-shm'])if(fs.existsSync(database+suffix))fs.unlinkSync(database+suffix);
    if(fs.readdirSync(temp).length===0)fs.rmdirSync(temp);
  }
  console.log(checks.filter(c=>c.passed).length+'/'+checks.length+' CSV browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
