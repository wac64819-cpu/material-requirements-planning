// New navigation/race checks supplement the original browser suites.
const fs=require('fs'),path=require('path'),os=require('os');
const {spawn}=require('child_process');
const {chromium}=require('C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const python='C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const out=process.env.MRP_TEST_ARTIFACT_DIR || path.join(__dirname,'results');
fs.mkdirSync(out,{recursive:true});
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mrp-navigation-'));
const database=path.join(temp,'test.sqlite3'),url='http://127.0.0.1:8769';
const checks=[],errors=[];let browser,server,completed=false,failure=null;
function check(name,actual,expected){checks.push({name,actual,expected,passed:JSON.stringify(actual)===JSON.stringify(expected)});if(!checks.at(-1).passed)throw new Error(name+': '+JSON.stringify(actual));}
(async()=>{
  try{
    server=spawn(python,[path.join(__dirname,'web_server.py'),'--port','8769','--database',database],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Test startup timed out')),10000);server.stdout.on('data',b=>{if(b.toString().includes('Open http')){clearTimeout(timer);resolve();}});server.stderr.on('data',()=>{});server.on('error',reject);});
    browser=await chromium.launch({channel:'msedge',headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
    await page.goto(url);await page.getByText('示例已载入',{exact:true}).waitFor();
    const go=async view=>page.locator(`[data-view="${view}"]`).click();
    for(const view of ['planning','history','data']){
      await go(view);
      check(view+' is the sole visible section',await page.locator('.view:visible').evaluateAll(nodes=>nodes.map(n=>n.id)),['view-'+view]);
      check(view+' navigation and focus match',await page.evaluate(()=>[document.querySelector('[aria-current="page"]').dataset.view,document.activeElement.id]),[view,'page-title']);
    }
    check('Overview matches source rows',await page.locator('.overview strong').allTextContents(),['4','3','4','2']);
    await page.getByLabel('物料第1行 名称',{exact:true}).fill('跨页编辑保留');
    await go('history');await go('planning');await go('data');
    check('Navigation retains unsaved input',await page.getByLabel('物料第1行 名称',{exact:true}).inputValue(),'跨页编辑保留');
    await go('planning');await page.locator('#calculate').click();await page.locator('#status').filter({hasText:'计算完成'}).waitFor();
    check('Calculation keeps priority ordering',(await page.locator('#results').innerText()).includes('HIGH → LOW'),true);
    await go('history');await page.locator('[data-history]').first().waitFor();
    const id=await page.locator('[data-history]').first().getAttribute('data-history');
    const historyUrl=url+'/api/history/'+id;
    let release,arrived,finished;
    const gate=new Promise(r=>release=r),seen=new Promise(r=>arrived=r),done=new Promise(r=>finished=r);
    await page.route(historyUrl,async route=>{const response=await route.fetch();arrived();await gate;await route.fulfill({response});finished();});
    await page.locator('[data-history]').first().click();await seen;
    await go('data');release();await done;await page.unroute(historyUrl);
    await go('history');
    check('Cancelled history read clears loading message',await page.locator('#history-message').innerText(),'');
    await page.route(historyUrl,route=>route.abort());
    await page.locator('[data-history]').first().click();
    await page.waitForFunction(()=>{const message=document.querySelector('#history-message').textContent;return message && !message.includes('正在读取');});
    check('History read failure remains visible',await page.locator('#history-message').isVisible(),true);
    await page.unroute(historyUrl);await page.locator('[data-history]').first().click();
    await page.getByText('历史计划 · 只读',{exact:true}).waitFor();
    check('History retry clears previous failure',await page.locator('#history-message').textContent(),'');
    // A cancelled request must not overwrite the status of a newer successful read.
    await go('history');
    let releaseFailure,arrivedFailure,finishedFailure;
    const failureGate=new Promise(r=>releaseFailure=r),failureSeen=new Promise(r=>arrivedFailure=r),failureDone=new Promise(r=>finishedFailure=r);
    let historyRequestCount=0;
    await page.route(historyUrl,async route=>{if(++historyRequestCount>1){await route.continue();return;}arrivedFailure();await failureGate;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'旧请求失败，不应覆盖新结果'})});finishedFailure();});
    await page.locator('[data-history]').first().click();await failureSeen;
    await go('data');await go('history');
    await page.locator('[data-history]').first().click();await page.getByText('历史计划 · 只读',{exact:true}).waitFor();
    releaseFailure();await failureDone;await page.unroute(historyUrl);
    await page.waitForTimeout(150); // Allow the deliberately late JSON failure to reach its UI handler.
    check('Late failure cannot overwrite a newer result',await page.locator('#history-message').textContent(),'');
    check('Late failure cannot change the active page',await page.locator('.view:visible').getAttribute('id'),'view-planning');
    await go('data');
    check('History read preserves unsaved input',await page.getByLabel('物料第1行 名称',{exact:true}).inputValue(),'跨页编辑保留');
    await page.setViewportSize({width:390,height:844});
    for(const view of ['data','planning','history']){
      await go(view);
      check('390px '+view+' has no page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      check('390px '+view+' navigation remains reachable',await page.locator(`[data-view="${view}"]`).isVisible(),true);
      await page.screenshot({path:path.join(out,'navigation-mobile-'+view+'.png'),fullPage:true,animations:'disabled'});
    }
    await page.locator('[data-history]').first().click();await page.getByText('历史计划 · 只读',{exact:true}).waitFor();
    check('390px history table action opens the saved plan',await page.locator('.view:visible').getAttribute('id'),'view-planning');
    await go('planning');await page.locator('#calculate').click();await page.locator('#status').filter({hasText:'计算完成'}).waitFor();
    check('390px calculation and export are usable',await page.locator('#export-controls').isVisible(),true);
    await page.screenshot({path:path.join(out,'navigation-mobile-result.png'),fullPage:true,animations:'disabled'});
    check('No unhandled browser errors',errors,[]);completed=true;
  }catch(error){failure=error.message;throw error;}
  finally{
    fs.writeFileSync(path.join(out,'navigation-ui-verification.json'),JSON.stringify({executed_at:new Date().toISOString(),completed,failure,passed:checks.filter(c=>c.passed).length,total:checks.length,checks,errors},null,2));
    if(browser)await browser.close();if(server && server.exitCode===null)await new Promise(resolve=>{server.once('exit',resolve);server.kill();});
    // Only the exact files in this newly-created temporary directory are removed.
    for(const suffix of ['','-journal','-wal','-shm'])if(fs.existsSync(database+suffix))fs.unlinkSync(database+suffix);
    if(fs.readdirSync(temp).length===0)fs.rmdirSync(temp);
  }
  console.log(checks.length+'/'+checks.length+' navigation browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
