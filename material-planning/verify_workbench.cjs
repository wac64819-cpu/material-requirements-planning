const path = require('path');
const fs = require('fs');
const {chromium} = require('C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out = process.env.MRP_TEST_ARTIFACT_DIR || path.join(__dirname,'results');
fs.mkdirSync(out,{recursive:true});
const checks = [];
function check(name, actual, expected) {
  checks.push({name, actual, expected, passed:JSON.stringify(actual)===JSON.stringify(expected)});
  if (!checks.at(-1).passed) throw new Error(name+': '+JSON.stringify(actual));
}
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  try {
    await page.goto(process.env.MRP_TEST_URL || 'http://127.0.0.1:8765');
    await page.getByText('示例已载入',{exact:true}).waitFor();
    if(process.argv.includes('--before')) {
      await page.screenshot({path:path.join(out,'workbench-before.png'),fullPage:true});
      console.log('Baseline captured: editable page loads, before visual refinement.');
      return;
    }
    async function calculate() {
      await page.locator('[data-view="planning"]').click();
      await page.getByRole('button',{name:'生成计划',exact:true}).click();
      await page.locator('#status').filter({hasText:/计算完成|未生成计划/}).waitFor();
    }
    async function tab(name) {await page.locator('[data-view="data"]').click();await page.getByRole('tab',{name,exact:true}).click();}
    async function load(value) {
      await page.locator('[data-view="data"]').click();
      await page.locator('#example').selectOption(value);
      await page.locator('#load').click();
      await page.getByText('示例已载入',{exact:true}).waitFor();
    }
    check('Initial material rows',await page.locator('#editor tbody tr').count(),4);
    await page.screenshot({path:path.join(out,'workbench-desktop.png'),fullPage:true});
    await calculate();
    check('Priority order',await page.locator('#results').innerText().then(t=>t.includes('HIGH → LOW')),true);
    const resultRows=await page.locator('#results table').first().locator('tbody tr').allTextContents();
    check('Higher priority B net production',resultRows[1].includes('80'),true);
    check('Lower priority B net production',resultRows[3].includes('200'),true);
    await page.screenshot({path:path.join(out,'workbench-results.png'),fullPage:true});
    await tab('生产任务');
    await page.getByLabel('生产任务第1行 需求数量',{exact:true}).fill('10');
    check('Edit invalidates old results',await page.locator('#result-badge').innerText(),'待重新计算');
    check('Old result tables removed',await page.locator('#results table').count(),0);
    await calculate();
    check('Edited LOW quantity recalculated',await page.locator('#results table').first().locator('tbody tr').nth(2).locator('td').nth(4).innerText(),'10');
    await tab('生产任务');
    await page.getByLabel('生产任务第1行 需求数量',{exact:true}).fill('1.5');
    await calculate();
    check('Decimal input rejected',await page.locator('#result-badge').innerText(),'校验未通过');
    await page.getByRole('button',{name:'定位',exact:true}).first().click();
    check('Error location focuses field',await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),'生产任务第1行 需求数量');
    await page.screenshot({path:path.join(out,'workbench-error.png'),fullPage:true});
    await page.getByLabel('生产任务第1行 需求数量',{exact:true}).fill('9007199254740993');
    await calculate();
    check('Unsafe integer input rejected',await page.locator('#results').innerText().then(t=>t.includes('安全整数范围')),true);
    await load('basic');
    await tab('生产任务');
    await page.getByLabel('生产任务第1行 需求数量',{exact:true}).fill('9007199254740991');
    await calculate();
    check('Large calculated quantity displayed exactly',await page.locator('#results table').first().locator('tbody tr').nth(1).locator('td').nth(4).innerText(),'18014398509481962');
    await load('priority');
    for(const [name,count] of [['物料',4],['BOM',3],['库存',4],['生产任务',2]]) {
      await tab(name);
      await page.locator('#add').click();
      check(name+' row addition',await page.locator('#editor tbody tr').count(),count+1);
      await page.locator('#editor [data-delete]').last().click();
      check(name+' row deletion',await page.locator('#editor tbody tr').count(),count);
    }
    await page.locator('[data-view="planning"]').click();
    await page.locator('[data-select="0"]').uncheck();
    await page.locator('[data-select="1"]').uncheck();
    await calculate();
    check('Empty task selection rejected',await page.locator('#results').innerText().then(t=>t.includes('至少选择')),true);
    await page.locator('#select-all').click();
    await tab('库存');
    await page.getByLabel('库存第1行 已占用',{exact:true}).fill('1');
    await calculate();
    check('Invalid reserved stock surfaced',await page.locator('#results').innerText().then(t=>t.includes('不能超过')),true);
    await load('surplus');
    await calculate();
    const buying=await page.locator('#results table').first().locator('tbody tr').allTextContents();
    check('Two purchase date buckets',buying.length,2);
    check('Later bucket buys zero',await page.locator('#results table').first().locator('tbody tr').nth(1).locator('td').nth(5).innerText(),'0');
    await tab('物料');
    await page.getByLabel('物料第1行 提前期 / 天',{exact:true}).fill('20');
    await calculate();
    check('Early-date risk visible',await page.locator('.risk').isVisible(),true);
    // The real API result is delayed to verify stale-response rejection.
    await load('basic');
    await page.route('**/api/calculate',async route=>{
      const response=await route.fetch();
      await new Promise(resolve=>setTimeout(resolve,700));
      await route.fulfill({response});
    });
    await page.locator('[data-view="planning"]').click();
    await page.locator('#calculate').click();
    await page.locator('[data-view="data"]').click();
    await page.getByLabel('物料第1行 名称',{exact:true}).fill('修改中的成品');
    await page.locator('[data-view="planning"]').click();
    await page.getByText('输入已改变，本次返回结果已丢弃。',{exact:true}).waitFor();
    check('Stale response rejected',await page.locator('#results table').count(),0);
    await page.unroute('**/api/calculate');
    await page.route('**/api/calculate',route=>route.abort());
    await page.locator('#calculate').click();
    await page.getByText('计算失败',{exact:true}).waitFor();
    check('Network failure allows retry',await page.locator('#calculate').isEnabled(),true);
    await page.unroute('**/api/calculate');
    await calculate();
    check('Retry succeeds',await page.locator('#result-badge').innerText(),'已生成');
    await load('priority');
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'workbench-mobile.png'),fullPage:true});
    check('Mobile no page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.locator('[data-view="planning"]').click();
    check('Mobile calculate reachable',await page.locator('#calculate').isVisible(),true);
    check('No uncaught browser errors',errors,[]);
  } finally {
    if(!process.argv.includes('--before')) fs.writeFileSync(path.join(out,'workbench-verification.json'),JSON.stringify({executed_at:new Date().toISOString(),url:process.env.MRP_TEST_URL || 'http://127.0.0.1:8765',passed:checks.filter(c=>c.passed).length,total:checks.length,checks,errors},null,2));
    await browser.close();
  }
  console.log(checks.filter(c=>c.passed).length+'/'+checks.length+' browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
