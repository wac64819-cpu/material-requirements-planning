// Real-browser acceptance checks for the refined workspace; no production mocks.
const fs = require("fs"),
  path = require("path"),
  os = require("os");
const { spawn } = require("child_process");
const { chromium } = require(
  process.env.MRP_PLAYWRIGHT ||
    path.join(
      os.homedir(),
      ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
    ),
);
const python = process.env.MRP_PYTHON || "python";
const out =
  process.env.MRP_TEST_ARTIFACT_DIR ||
  path.join(__dirname, "results/refined-ui-2026-11-18");
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "mrp-refined-"));
const url = "http://127.0.0.1:8773",
  checks = [],
  errors = [];
let browser,
  server,
  completed = false,
  failure = null;
function check(name, actual, expected) {
  checks.push({
    name,
    actual,
    expected,
    passed: JSON.stringify(actual) === JSON.stringify(expected),
  });
  if (!checks.at(-1).passed)
    throw new Error(name + ": " + JSON.stringify(actual));
}
(async () => {
  try {
    server = spawn(
      python,
      [
        path.join(__dirname, "web_server.py"),
        "--port",
        "8773",
        "--database",
        path.join(temp, "test.sqlite3"),
      ],
      { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
    );
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(Error("Server startup timeout")),
        10000,
      );
      server.stdout.on("data", (b) => {
        if (b.toString().includes("Open http")) {
          clearTimeout(timer);
          resolve();
        }
      });
      server.stderr.on("data", () => {});
      server.on("error", reject);
    });
    browser = await chromium.launch({ channel: "msedge", headless: true });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (message) => {if(message.type()==="error") errors.push(message.text());});
    page.on("dialog", (d) => d.accept());
    await page.goto(url);
    await page.waitForFunction(
      () => document.querySelector("#count-materials")?.textContent === "4",
    );
    check(
      "Landing opens overview",
      await page.locator(".view:visible").getAttribute("id"),
      "view-overview",
    );
    check(
      "Uncalculated risk is not reported as zero",
      await page.locator("#dashboard-risk").innerText(),
      "待计算",
    );
    check(
      "Overview reports two current tasks",
      await page.locator("#dashboard-tasks").innerText(),
      "2",
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "01-overview.png"),
      fullPage: true,
      animations: "disabled",
    });
    const go = async (view) => page.locator(`[data-view="${view}"]`).click();
    await go("data");
    check(
      "Default table shows values instead of input fields",
      await page.locator("#editor input").count(),
      0,
    );
    await page.locator("#data-search").fill("D");
    check(
      "Search finds only matching material",
      await page.locator("#editor tbody tr").count(),
      1,
    );
    await page.locator("[data-edit]").click();
    await page.getByLabel("名称", { exact: true }).fill("精密紧固件");
    await page.getByRole("button", { name: "应用修改", exact: true }).click();
    check(
      "Filtered drawer edits original row",
      await page
        .locator("#editor")
        .innerText()
        .then((t) => t.includes("精密紧固件")),
      true,
    );
    await page.locator("#data-search").fill("");
    await page.locator("#data-filter").selectOption("MAKE");
    check(
      "Supply filter selects self-made parts",
      await page.locator("#editor tbody tr").count(),
      2,
    );
    await page.locator("#data-filter").selectOption("");
    await page.locator("#page-size").selectOption("2");
    check(
      "Pagination limits visible rows",
      await page.locator("#editor tbody tr").count(),
      2,
    );
    await page.locator("#next-page").click();
    check(
      "Next page retains original row identity",
      await page.locator("[data-edit]").first().getAttribute("data-edit"),
      "2",
    );
    await page.locator("[data-edit]").first().click();
    await page.getByLabel("名称", { exact: true }).fill("不应保存");
    await page.keyboard.press("Escape");
    check(
      "Escape cancels drawer changes",
      !(await page.locator("#editor").innerText()).includes("不应保存"),
      true,
    );
    await page.locator("#page-size").selectOption("10");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "02-data.png"),
      fullPage: true,
      animations: "disabled",
    });
    await go("bom");
    check(
      "BOM tree includes all four nodes",
      await page.locator("[data-bom-node]").count(),
      4,
    );
    check(
      "BOM tree shows relationship usage",
      await page
        .locator("#bom-tree")
        .innerText()
        .then((t) => t.includes("单件用量 4")),
      true,
    );
    await page.locator('[data-bom-node="D"]').click();
    check(
      "BOM node detail uses current stock",
      await page
        .locator("#bom-detail")
        .innerText()
        .then((t) => t.includes("100")),
      true,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "03-bom.png"),
      fullPage: true,
      animations: "disabled",
    });
    await go("planning");
    await page.locator("#calculate").click();
    await page.locator("#status").filter({ hasText: "计算完成" }).waitFor();
    check(
      "Existing priority ordering preserved",
      (await page.locator("#results").innerText()).includes("HIGH → LOW"),
      true,
    );
    await page.locator("#analysis-tab-flow").click();
    await page
      .locator("#demand-select")
      .selectOption({ label: "HIGH / B / 2026-10-19" });
    check(
      "Demand explanation uses actual netting",
      [
        await page.locator("#flow-gross").innerText(),
        await page.locator("#flow-stock").innerText(),
        await page.locator("#flow-net").innerText(),
      ],
      ["100", "20", "80"],
    );
    await page.locator('[data-explain="gross"]').click();
    check(
      "Explanation opens trace with BOM path",
      (await page.locator("#drawer-content").innerText()).includes("A → B"),
      true,
    );
    await page.keyboard.press("Escape");
    await page.locator("#analysis-tab-timeline").click();
    check(
      "Timeline contains production, purchasing and delivery",
      await page.locator(".timeline-row").count(),
      10,
    );
    const widthRatio = await page.locator('.timeline-bar').first().evaluate(el=>el.getBoundingClientRect().width/el.parentElement.getBoundingClientRect().width);
    check('Five-day purchase occupies 5/11 of eleven-day axis',Math.abs(widthRatio-0.4409)<0.02,true);
    check(
      "Timeline shows actual earliest purchase date",
      (await page.locator("#timeline").innerText()).includes("2026-10-10"),
      true,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "04-planning.png"),
      fullPage: true,
      animations: "disabled",
    });
    await go("overview");
    check(
      "Overview risk derived after successful calculation",
      await page.locator("#dashboard-risk").innerText(),
      "0",
    );
    check(
      "Overview unique short materials",
      await page.locator("#dashboard-shortage").innerText(),
      "2",
    );
    await go("history");
    await page.locator("#history-list [data-history]").first().waitFor();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "05-history.png"),
      fullPage: true,
      animations: "disabled",
    });
    await go("data");
    await page.locator('[data-edit="0"]').click();
    await page.getByLabel("名称", { exact: true }).fill("未保存的新名字");
    await page.getByRole("button", { name: "应用修改", exact: true }).click();
    await go("overview");
    check(
      "Editing invalidates overview result metrics",
      await page.locator("#dashboard-risk").innerText(),
      "待计算",
    );
    await go("history");
    await page.locator("#history-list [data-history]").first().click();
    await page.getByText("历史计划 · 只读", { exact: true }).waitFor();
    check(
      "History timeline remains tied to snapshot",
      await page.locator(".timeline-row").count(),
      10,
    );
    await go("data");
    check(
      "History preserves current editing data",
      (await page.locator("#editor").innerText()).includes("未保存的新名字"),
      true,
    );
    // Inputs below exercise validation and visualization boundaries through the real UI.
    await page.locator('[data-edit="0"]').click();
    await page.getByLabel("编号", { exact: true }).fill("B");
    await page.getByRole("button", { name: "应用修改", exact: true }).click();
    check(
      "Drawer rejects duplicate material IDs",
      (await page.locator("#drawer-errors").innerText()).includes("编号已存在"),
      true,
    );
    await page.keyboard.press("Escape");
    const count = await page.locator("#editor tbody tr").count();
    await page.locator("#add").click();
    await page.getByLabel("编号", { exact: true }).fill("CANCEL");
    await page.keyboard.press("Escape");
    check(
      "Cancelled new record is not inserted",
      await page.locator("#editor tbody tr").count(),
      count,
    );
    await go("bom");
    await page.locator('[data-bom-toggle="root"]').click();
    check(
      "Collapse hides descendant nodes",
      await page.locator("[data-bom-node]").count(),
      1,
    );
    await page.locator("#bom-expand").click();
    check(
      "Expand restores descendant nodes",
      await page.locator("[data-bom-node]").count(),
      4,
    );
    await page.locator("#bom-root").selectOption("B");
    check(
      "Selected BOM root excludes unrelated parts",
      await page.locator("[data-bom-node]").count(),
      2,
    );
    await page.locator("#bom-root").selectOption("A");
    await go("history");
    await page.locator("#history-search").fill("no-such-plan");
    check(
      "History search reports no matching record",
      await page.locator("#history-list [data-history]").count(),
      0,
    );
    await page.locator("#history-search").fill("HIGH");
    check(
      "History search matches task in saved snapshot",
      await page.locator("#history-list [data-history]").count(),
      1,
    );
    await page.locator("#history-search").fill("");
    await go("data");
    await page.locator("#quick-edit").click();
    await page.getByRole("tab", { name: "BOM", exact: true }).click();
    await page.locator("#add").click();
    await page.getByLabel("BOM第4行 父项编号", { exact: true }).fill("B");
    await page.getByLabel("BOM第4行 子项编号", { exact: true }).fill("A");
    await go("bom");
    check(
      "Cycle is visibly reported instead of infinite expansion",
      (await page.locator("#bom-warning").innerText()).includes("循环引用"),
      true,
    );
    async function load(value) {
      await go("data");
      await page.locator("#example").selectOption(value);
      await page.locator("#load").click();
      await page.getByText("示例已载入", { exact: true }).waitFor();
    }
    async function calculate() {
      await go("planning");
      const wait = page.waitForResponse(
        (r) =>
          r.url() === url + "/api/calculate" && r.request().method() === "POST",
      );
      await page.locator("#calculate").click();
      const outcome = await (await wait).json();
      await page.locator("#status").filter({ hasText: "计算完成" }).waitFor();
      return outcome;
    }
    await load("surplus");
    const surplus = await calculate();
    await page.locator("#demand-select").selectOption("0");
    await page.locator('[data-explain="purchase"]').click();
    check(
      "Purchase explanation includes lot multiple",
      (await page.locator("#drawer-content").innerText()).includes("采购倍数"),
      true,
    );
    check(
      "Purchase explanation rounds demand 23 to lot size 30",
      await page.locator("#drawer-content .detail-list dd").nth(5).innerText(),
      "30",
    );
    await page.keyboard.press("Escape");
    await page.locator("#demand-select").selectOption("1");
    check(
      "Later demand displays earlier surplus use",
      (await page.locator(".purchase-explanation").innerText()).includes(
        "前期余量",
      ),
      true,
    );
    check(
      "Real surplus case uses positive earlier surplus",
      surplus.result.purchase_buckets.some((b) => b.surplus_used > 0),
      true,
    );
    await load("priority");
    await page.getByRole("tab", { name: "物料", exact: true }).click();
    await page.getByLabel("物料第1行 提前期 / 天", { exact: true }).fill("30");
    const risky = await calculate();
    await page.locator("#analysis-tab-timeline").click();
    check(
      "Earlier events are highlighted on timeline",
      (await page.locator(".timeline-row.early").count()) > 0,
      true,
    );
    await page.locator("#timeline-filter").selectOption("purchase");
    check(
      "Timeline filter retains only purchase events",
      await page.locator(".timeline-row").count(),
      4,
    );
    await page.locator(".timeline-bar").first().click();
    check(
      "Timeline bar opens exact dates",
      (await page.locator("#drawer-content").innerText()).includes("2026-09"),
      true,
    );
    await page.keyboard.press("Escape");
    await go("overview");
    check(
      "Dashboard risk agrees with saved plan",
      await page.locator("#dashboard-risk").innerText(),
      String(risky.result.summary.risk_count),
    );
    await load("basic");
    await page.getByRole("tab", { name: "生产任务", exact: true }).click();
    await page
      .getByLabel("生产任务第1行 需求数量", { exact: true })
      .fill("9007199254740991");
    await calculate();
    await page
      .locator("#demand-select")
      .selectOption({ label: "T001 / B / 2026-10-18" });
    check(
      "Explanation preserves quantities beyond JS safe integer",
      await page.locator("#flow-gross").innerText(),
      "18014398509481982",
    );
    await go("bom");
    await page.locator('[data-bom-node="B"]').click();
    check(
      "BOM net demand keeps exact large integer",
      (await page.locator("#bom-detail").innerText()).includes(
        "18014398509481962",
      ),
      true,
    );
    await load("priority");
    await page.locator("#quick-edit").click();
    await calculate();
    await go("overview");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "01-overview.png"),
      fullPage: true,
      animations: "disabled",
    });
    await page.setViewportSize({ width: 390, height: 844 });
    for (const view of ["overview", "data", "bom", "planning", "history"]) {
      await go(view);
      check(
        "390px " + view + " has no page overflow",
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
    }
    await go("overview");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "06-mobile.png"),
      fullPage: true,
      animations: "disabled",
    });
    check("Browser has no unhandled errors", errors, []);
    completed = true;
  } catch (error) {
    failure = error.message;
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(out, "verification.json"),
      JSON.stringify(
        {
          executed_at: new Date().toISOString(),
          completed,
          failure,
          passed: checks.filter((c) => c.passed).length,
          total: checks.length,
          checks,
          errors,
        },
        null,
        2,
      ),
    );
    if (browser) await browser.close();
    if (server && server.exitCode === null)
      await new Promise((r) => {
        server.once("exit", r);
        server.kill();
      });
    for (const suffix of ["", "-journal", "-wal", "-shm"]) {
      const file = path.join(temp, "test.sqlite3" + suffix);
      if (fs.existsSync(file)) fs.unlinkSync(file);
    }
    if (fs.readdirSync(temp).length === 0) fs.rmdirSync(temp);
  }
  console.log(
    checks.length + "/" + checks.length + " refined UI checks passed",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
