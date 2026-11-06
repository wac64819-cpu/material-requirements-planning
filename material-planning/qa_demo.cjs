// Local artifact rendering; no network or existing browser profile.
const path = require('path');
const {pathToFileURL} = require('url');
const deps = 'C:/Users/许yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium} = require(path.join(deps, 'playwright'));
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.join(__dirname, 'results/demo-plans.html')).href);
  await page.screenshot({path: path.join(__dirname, 'results/demo-preview.png'), fullPage: true});
  const result = {sections: await page.locator('section').count(), errors,
    desktopOverflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)};
  await page.locator('details').first().locator('summary').click();
  result.inputDetailsOpen = await page.locator('details').first().getAttribute('open') !== null;
  await page.setViewportSize({width: 390, height: 844});
  result.mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  await page.screenshot({path: path.join(__dirname, 'results/demo-mobile-preview.png'), fullPage: true});
  require('fs').writeFileSync(path.join(__dirname, 'results/demo-ui-check.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  await browser.close();
  if (result.sections !== 3 || result.errors.length || result.desktopOverflow || result.mobileOverflow || !result.inputDetailsOpen) process.exitCode = 1;
})().catch(error => {console.error(error); process.exitCode = 1;});
