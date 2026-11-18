"use strict";
const $ = (selector) => document.querySelector(selector);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const schema = {
  materials: [
    ["material_id", "编号", "text"],
    ["name", "名称", "text"],
    ["supply_type", "类型", "type"],
    ["unit", "单位", "text"],
    ["lead_time_days", "提前期 / 天", "number"],
    ["min_purchase_qty", "最小采购量", "number"],
    ["purchase_multiple", "采购倍数", "number"],
  ],
  bom: [
    ["parent_id", "父项编号", "text"],
    ["child_id", "子项编号", "text"],
    ["qty_per", "单件用量", "number"],
  ],
  stocks: [
    ["material_id", "物料编号", "text"],
    ["on_hand", "账面库存", "number"],
    ["reserved", "已占用", "number"],
    ["snapshot_date", "快照日期", "date"],
  ],
  tasks: [
    ["task_id", "任务编号", "text"],
    ["product_id", "成品编号", "text"],
    ["required_qty", "需求数量", "number"],
    ["due_date", "交货日期", "date"],
    ["priority", "优先级", "priority"],
  ],
};
const names = {
  materials: "物料",
  bom: "BOM",
  stocks: "库存",
  tasks: "生产任务",
};
const tips = {
  materials: "自制件必须有 BOM，外购件作为叶子。采购参数仅对外购件生效。",
  bom: "单件用量表示生产一件父项需要多少子项。编号须与物料表一致。",
  stocks: "可用库存 = 账面库存 − 已占用。每个参与计算的物料都需要库存记录。",
  tasks:
    "需求数量按交付量计算，可先用成品库存抵扣。在“计划计算”中勾选本次参与的任务。",
};
let data = null,
  active = "materials",
  selected = new Set(),
  version = 0,
  dirty = false,
  busy = false;
let savedRevision = null,
  saving = false,
  historyOffset = null,
  historyRows = [],
  viewToken = 0;
let csvCandidate = null,
  csvToken = 0,
  csvWorking = false,
  exportBatch = null;
let currentView = "overview",
  quickEdit = false,
  editorPage = 0;
let currentValidResult = null,
  displayedResult = null,
  historyLoaded = false,
  historyFailure = "";
let drawerState = null,
  drawerReturnFocus = null,
  bomSelected = "",
  bomRoot = "",
  bomCollapsed = new Set();
const viewCopy = {
  overview: [
    "工作总览",
    "WORKSPACE / OVERVIEW",
    "工作总览",
    "从任务到物料，让每一份计划都有清晰的依据。",
  ],
  data: [
    "基础数据",
    "WORKSPACE / DATA FOUNDATION",
    "基础数据",
    "维护物料、结构与库存，准备本次生产计划的输入。",
  ],
  bom: [
    "BOM 结构",
    "WORKSPACE / BILL OF MATERIALS",
    "物料结构",
    "展开产品组成，查看每一层的用量、库存与需求。",
  ],
  planning: [
    "计划计算",
    "WORKSPACE / REQUIREMENTS PLANNING",
    "计划计算",
    "按优先级分配库存，生成生产与采购建议。",
  ],
  history: [
    "历史记录",
    "WORKSPACE / PLAN ARCHIVE",
    "历史记录",
    "每一份计划，保留独立的数据快照与计算依据。",
  ],
};
function showView(view, focus = true) {
  if (!viewCopy[view]) return;
  currentView = view;
  document.querySelectorAll(".view").forEach((panel) => {
    panel.hidden = panel.id !== "view-" + view;
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    if (button.dataset.view === view)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const [label, eyebrow, title, description] = viewCopy[view];
  $("#breadcrumb-current").textContent = label;
  $("#page-eyebrow").textContent = eyebrow;
  $("#page-title").innerHTML = title;
  $("#page-description").textContent = description;
  if (view === "overview") renderDashboard();
  if (view === "bom") renderBom();
  if (focus) {
    $("#page-title").focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }
}
function updateOverview() {
  if (!data) return;
  Object.keys(schema).forEach((kind) => {
    $("#count-" + kind).textContent = data.sources[kind].length;
  });
  $("#selected-count").textContent =
    selected.size + " / " + data.sources.tasks.length;
  renderDashboard();
}

function clearCsvPreview() {
  if (csvCandidate)
    $("#csv-message").textContent = "数据或文件已改变，请重新校验。";
  csvCandidate = null;
  csvToken++;
  $("#apply-csv").disabled = true;
}
function setExport(id) {
  exportBatch = id;
  $("#export-controls").hidden = !id;
  $("#export-status").textContent = "";
}

function invalidate() {
  currentValidResult = null;
  displayedResult = null;
  updateOverview();
  clearCsvPreview();
  setExport(null);
  version++;
  dirty = true;
  viewToken++;
  $("#history-meta").hidden = true;
  $("#edit-state").textContent = "有编辑 · 尚未保存";
  $("#save-status").textContent = "有未保存的修改";
  $("#result-badge").textContent = "待重新计算";
  $("#results").innerHTML =
    '<div class="empty">数据已改变，请重新生成计划。<small>旧结果已清除，避免混用不同版本的数据。</small></div>';
  $("#status").textContent = "数据已更新，尚未重新计算。";
}

function renderEditor() {
  updateOverview();
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.tab === active)),
    );
  $("#table-help").textContent = tips[active];
  const query = $("#data-search").value.trim().toLocaleLowerCase(),
    filter = $("#data-filter").value;
  const rows = data.sources[active]
    .map((row, i) => ({ row, i }))
    .filter(
      ({ row }) =>
        Object.values(row).some((v) =>
          String(v ?? "")
            .toLocaleLowerCase()
            .includes(query),
        ) &&
        (!filter ||
          String(
            row[
              active === "materials"
                ? "supply_type"
                : active === "tasks"
                  ? "priority"
                  : ""
            ],
          ) === filter),
    );
  const pageSize = Number($("#page-size").value);
  editorPage = Math.max(
    0,
    Math.min(editorPage, Math.ceil(rows.length / pageSize) - 1),
  );
  const pageRows = rows.slice(
    editorPage * pageSize,
    (editorPage + 1) * pageSize,
  );
  const cells = pageRows
    .map(
      ({ row, i }) =>
        "<tr>" +
        schema[active]
          .map(([key, label, type]) => {
            if (!quickEdit) {
              let value = esc(row[key] ?? "—");
              if (type === "type")
                value =
                  '<span class="tag ' +
                  (row[key] === "MAKE" ? "sage" : "") +
                  '">' +
                  (row[key] === "MAKE" ? "自制件" : "外购件") +
                  "</span>";
              if (type === "priority") value = priorityTag(row[key]);
              if (
                active === "materials" &&
                row.supply_type === "MAKE" &&
                ["min_purchase_qty", "purchase_multiple"].includes(key)
              )
                value = '<span class="muted">不适用</span>';
              return (
                '<td class="' +
                (key.endsWith("_id")
                  ? "cell-id"
                  : key === "name"
                    ? "cell-name"
                    : "") +
                '">' +
                value +
                "</td>"
              );
            }
            const attrs = `data-row="${i}" data-key="${key}" aria-label="${names[active]}第${i + 1}行 ${label}"`;
            const disabled =
              active === "materials" &&
              row.supply_type === "MAKE" &&
              ["min_purchase_qty", "purchase_multiple"].includes(key);
            if (type === "type" || type === "priority") {
              const choices =
                type === "type"
                  ? [
                      ["MAKE", "自制"],
                      ["BUY", "外购"],
                    ]
                  : [
                      [1, "1 · 高"],
                      [2, "2 · 中"],
                      [3, "3 · 低"],
                    ];
              return (
                "<td><select " +
                attrs +
                ">" +
                choices
                  .map(
                    ([v, l]) =>
                      `<option value="${v}" ${String(row[key]) === String(v) ? "selected" : ""}>${l}</option>`,
                  )
                  .join("") +
                "</select></td>"
              );
            }
            return `<td><input ${attrs} type="${type}" value="${esc(disabled ? "" : row[key])}" ${type === "number" ? 'step="1" min="0"' : ""} ${disabled ? 'disabled placeholder="不适用"' : ""}></td>`;
          })
          .join("") +
        `<td class="row-actions"><button data-edit="${i}" aria-label="编辑${names[active]}第${i + 1}行">编辑</button><button class="delete" data-delete="${i}" aria-label="删除${names[active]}第${i + 1}行">删除</button></td></tr>`,
    )
    .join("");
  $("#editor").innerHTML =
    `<table><thead><tr>${schema[active].map(([, label]) => "<th>" + label + "</th>").join("")}<th>操作</th></tr></thead><tbody>${cells}</tbody></table>` +
    (rows.length
      ? ""
      : '<p class="empty">没有匹配的记录<small>调整搜索与筛选，或新增一条记录。</small></p>');
  $("#page-info").textContent = rows.length
    ? `第 ${editorPage * pageSize + 1}–${Math.min((editorPage + 1) * pageSize, rows.length)} 条 / 共 ${rows.length} 条`
    : "共 0 条";
  $("#previous-page").disabled = editorPage === 0;
  $("#next-page").disabled = (editorPage + 1) * pageSize >= rows.length;
}

function renderSelection() {
  updateOverview();
  $("#task-selection").innerHTML =
    data.sources.tasks
      .map((t, i) => {
        const unit =
          data.sources.materials.find(
            (m) => m.material_id.trim() === t.product_id.trim(),
          )?.unit || "";
        return `<label class="task-check"><input type="checkbox" data-select="${i}" ${selected.has(i) ? "checked" : ""}><span>${esc(t.task_id || "未填写编号")}<small>${esc(t.product_id || "未填写成品")} · ${esc(t.required_qty ?? "—")} ${esc(unit === "pcs" ? "件" : unit)} · 优先级 ${esc(t.priority)}<br>交期 ${esc(t.due_date || "未填写")}</small></span></label>`;
      })
      .join("") || '<p class="muted">请先在生产任务表新增任务。</p>';
}

async function loadExample(confirmReplace = true) {
  if (
    confirmReplace &&
    dirty &&
    !window.confirm("载入示例将替换当前页面的数据，是否继续？")
  )
    return;
  $("#load").disabled = true;
  try {
    const response = await fetch("/api/example/" + $("#example").value);
    if (!response.ok) throw new Error("示例读取失败，请确认本地服务正在运行。");
    const incoming = await response.json();
    currentValidResult = null;
    displayedResult = null;
    resetEditorFilters();
    data = incoming;
    selected = new Set(data.sources.tasks.map((_, i) => i));
    version++;
    viewToken++;
    dirty = confirmReplace;
    $("#baseline").value = data.request.baseline_date;
    clearCsvPreview();
    setExport(null);
    $("#history-meta").hidden = true;
    $("#save-status").textContent = "示例尚未保存，点击“保存数据”可保留";
    renderEditor();
    renderSelection();
    $("#edit-state").textContent = "示例已载入";
    $("#result-badge").textContent = "尚未计算";
    $("#results").innerHTML =
      '<div class="empty">准备好数据后，点击“生成计划”。<small>可以直接计算示例，也可以先编辑任意表格。</small></div>';
    $("#status").textContent = "已选择 " + selected.size + " 个任务。";
  } catch (error) {
    $("#status").textContent = error.message;
    $("#save-status").textContent = error.message;
  } finally {
    $("#load").disabled = false;
  }
}

function table(headers, rows) {
  if (!rows.length) return '<p class="muted">本次没有相关记录。</p>';
  return (
    '<div class="table-wrap"><table><thead><tr>' +
    headers.map((h) => "<th>" + esc(h) + "</th>").join("") +
    "</tr></thead><tbody>" +
    rows
      .map(
        (row) =>
          "<tr>" +
          row.map((v) => "<td>" + esc(v ?? "—") + "</td>").join("") +
          "</tr>",
      )
      .join("") +
    "</tbody></table></div>"
  );
}

const messages = {
  SCHEMA: "输入记录格式有误。",
  REQUIRED_TEXT: "必填内容不能为空。",
  INTEGER:
    "数量须为符合范围的整数，不能填写小数或负数；用量和采购倍数必须大于零。",
  DATE: "请填写有效的日期。",
  SUPPLY_TYPE: "请选择自制或外购。",
  PRIORITY: "优先级须为1、2或3。",
  SNAPSHOT_DATE: "库存快照日期必须与计划基准日一致。",
  RESERVED_EXCEEDS_STOCK: "已占用数量不能超过账面库存。",
  DUPLICATE_ID: "编号重复，请修改。",
  DUPLICATE_EDGE: "同一父项与子项的BOM关系重复。",
  UNKNOWN_MATERIAL: "引用的物料编号不存在，请核对物料表。",
  UNKNOWN_TASK: "选中的任务不存在。",
  MISSING_STOCK: "参与计算的物料缺少库存记录。",
  MISSING_BOM: "自制物料缺少BOM，即使库存足够也必须补充。",
  BUY_HAS_CHILDREN: "外购物料不能有下层BOM。",
  BOM_CYCLE: "BOM存在循环引用，请检查父项与子项关系。",
  SELECTION: "请至少选择一个生产任务。",
  DUPLICATE_SELECTION: "选中的任务编号重复。",
  DATE_RANGE: "提前期倒推超出可表示的日期范围。",
  RULE_VERSION: "计算规则版本不匹配，请重新载入页面。",
};

function locationLabel(location) {
  const match = /^(materials|bom|stocks|tasks)\[(\d+)\](?:\.(\w+))?/.exec(
    location,
  );
  if (!match)
    return location === "request.selected_task_ids"
      ? "本次任务选择"
      : location === "request.baseline_date"
        ? "计划基准日"
        : location;
  const field = schema[match[1]].find(([key]) => key === match[3]);
  return (
    names[match[1]] +
    "第" +
    (Number(match[2]) + 1) +
    "行" +
    (field ? " · " + field[1] : "")
  );
}

function showOutcome(outcome, reveal = true) {
  if (reveal) showView("planning", false);
  setExport(null);
  $("#history-meta").hidden = true;
  if (outcome.status !== "VALID") {
    displayedResult = null;
    $("#result-badge").textContent = "校验未通过";
    $("#status").textContent = "未生成计划，请先修正下方问题。";
    $("#results").innerHTML =
      '<div class="error-box"><strong>发现 ' +
      outcome.errors.length +
      " 项问题，本次未生成有效计划</strong><ul>" +
      outcome.errors
        .map(
          (e) =>
            "<li><strong>" +
            esc(locationLabel(e.source_location)) +
            "</strong>：" +
            esc(messages[e.code] || e.message) +
            (/^(materials|bom|stocks|tasks)\[/.test(e.source_location)
              ? `<button data-locate="${esc(e.source_location)}">定位</button>`
              : "") +
            (e.code === "BOM_CYCLE"
              ? "<br><small>" + esc(e.message) + "</small>"
              : "") +
            "</li>",
        )
        .join("") +
      "</ul></div>";
    return;
  }
  const r = outcome.result,
    n = r.net_bundle,
    s = r.summary;
  displayedResult = r;
  $("#result-badge").textContent = r.risks.length
    ? "已生成 · 存在交期风险"
    : "已生成";
  $("#status").textContent = "计算完成。未扣减实际库存。";
  const metrics = [
    ["参与任务", s.task_count],
    ["生产计划行", s.make_line_count],
    ["采购建议行", s.purchase_line_count],
    ["交期风险", s.risk_count],
  ];
  let html =
    '<div class="metrics">' +
    metrics
      .map(
        ([l, v]) =>
          '<div class="metric"><strong>' +
          v +
          "</strong><span>" +
          l +
          "</span></div>",
      )
      .join("") +
    '</div><p class="muted">实际处理顺序：' +
    esc(n.context.ordered_task_ids.join(" → ")) +
    "</p>";
  html += analysisMarkup(r);
  html +=
    "<h3>新增生产计划</h3>" +
    table(
      [
        "任务",
        "物料",
        "毛需求",
        "抵扣库存",
        "新增生产",
        "开始日期",
        "需要日期",
      ],
      n.make_lines.map((x) => [
        x.task_id,
        x.material_id,
        x.gross_qty,
        x.allocated_qty,
        x.make_qty,
        x.start_date,
        x.needed_date,
      ]),
    );
  html +=
    '<h3>采购建议与余量</h3><p class="muted">采购量为0表示由早期计划余量满足，不产生采购建议。</p>' +
    table(
      [
        "物料",
        "需要日期",
        "库存后缺口",
        "使用余量",
        "剩余缺口",
        "采购量",
        "下单日期",
        "本期后余量",
      ],
      r.purchase_buckets.map((x) => [
        x.material_id,
        x.needed_date,
        x.gross_shortage,
        x.surplus_used,
        x.remaining_gap,
        x.purchase_qty,
        x.order_date,
        x.surplus_after,
      ]),
    );
  html +=
    "<details><summary>查看库存分配明细</summary>" +
    table(
      ["任务", "物料", "需要日期", "分配前", "本次分配", "分配后"],
      n.allocations.map((x) => [
        x.task_id,
        x.material_id,
        x.needed_date,
        x.before_qty,
        x.allocated_qty,
        x.after_qty,
      ]),
    ) +
    "</details>";
  html +=
    "<details><summary>查看需求来源与 BOM 路径</summary>" +
    table(
      ["任务", "物料", "需要日期", "来源路径", "贡献数量"],
      n.demands.flatMap((x) =>
        x.demand.origins.map((o) => [
          x.demand.task_id,
          x.demand.material_id,
          x.demand.needed_date,
          o.bom_path.join(" → "),
          o.contribution_qty,
        ]),
      ),
    ) +
    "</details>";
  if (r.risks.length)
    html +=
      '<div class="risk"><h3>交期风险：建议日期早于基准日</h3>' +
      table(
        ["任务", "物料", "原计算日期", "早于基准日 / 天"],
        r.risks.map((x) => [
          x.task_id,
          x.material_id,
          x.computed_date,
          x.days_before_baseline,
        ]),
      ) +
      "</div>";
  $("#results").innerHTML = html;
  renderDemandFlow();
  renderTimeline();
}

async function calculate() {
  if (!data || busy || saving) return;
  const unsafe = inputErrors();
  if (unsafe.length) {
    showOutcome({ status: "INVALID", errors: unsafe });
    return;
  }
  const current = version;
  const payload = currentPayload();
  viewToken++;
  $("#history-meta").hidden = true;
  setExport(null);
  busy = true;
  $("#calculate").disabled = true;
  $("#calculate").textContent = "计算中…";
  $("#status").textContent = "正在校验、计算并保存计划，请稍候。";
  $("#result-badge").textContent = "计算中";
  $("#results").innerHTML = '<div class="empty">正在计算…</div>';
  try {
    const response = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const outcome = await response.json();
    if (!response.ok)
      throw new Error(outcome.message || "计算服务暂不可用，请重试。");
    if (outcome.saved_batch) refreshHistory();
    if (version !== current) {
      $("#status").textContent =
        "输入已改变，请重新生成计划；刚才提交的快照如已计算成功，可在历史中查看。";
      $("#result-badge").textContent = "待重新计算";
      $("#results").innerHTML =
        '<div class="empty">输入已改变，本次返回结果已丢弃。</div>';
      return;
    }
    currentValidResult = outcome.status === "VALID" ? outcome.result : null;
    renderDashboard();
    showOutcome(outcome, false);
    if (outcome.saved_batch) {
      setExport(outcome.saved_batch.batch_id);
      $("#history-meta").hidden = false;
      $("#history-meta").textContent =
        "已保存计划 " +
        outcome.saved_batch.batch_id.slice(0, 8) +
        " · " +
        formatTime(outcome.saved_batch.created_at);
    }
    if (currentView === "planning")
      $("#result-section").scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
  } catch (error) {
    const message =
      error instanceof TypeError
        ? "无法连接服务，未确认计划是否保存。请恢复连接后刷新历史列表。"
        : error.message;
    $("#status").textContent = message;
    $("#result-badge").textContent = "计算失败";
    $("#results").innerHTML =
      '<div class="error-box">' + esc(message) + "</div>";
  } finally {
    busy = false;
    $("#calculate").disabled = false;
    $("#calculate").textContent = "生成计划";
  }
}

function inputErrors() {
  const unsafe = [];
  for (const [table, fields] of Object.entries(schema)) {
    data.sources[table].forEach((row, i) =>
      fields.forEach(([key, , type]) => {
        if (
          type === "number" &&
          Number.isInteger(row[key]) &&
          !Number.isSafeInteger(row[key])
        )
          unsafe.push({
            code: "UI_INTEGER_RANGE",
            message:
              "页面输入须在安全整数范围内（不超过 9007199254740991），请减小数量。",
            source_location: `${table}[${i}].${key}`,
          });
      }),
    );
  }
  return unsafe;
}

function currentPayload() {
  const payload = structuredClone(data);
  payload.request.baseline_date = $("#baseline").value;
  payload.request.selected_task_ids = [...selected]
    .sort((a, b) => a - b)
    .map((i) => data.sources.tasks[i].task_id);
  return payload;
}

function formatTime(value) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function installSaved(record) {
  currentValidResult = null;
  displayedResult = null;
  resetEditorFilters();
  clearCsvPreview();
  setExport(null);
  data = record.payload;
  savedRevision = record.revision_id;
  selected = new Set(
    data.sources.tasks
      .map((t, i) =>
        data.request.selected_task_ids.includes(t.task_id) ? i : -1,
      )
      .filter((i) => i >= 0),
  );
  version++;
  viewToken++;
  dirty = false;
  $("#baseline").value = data.request.baseline_date;
  renderEditor();
  renderSelection();
  $("#edit-state").textContent = "已保存";
  $("#save-status").textContent = "已保存 · " + formatTime(record.created_at);
  $("#history-meta").hidden = true;
  $("#result-badge").textContent = "尚未计算";
  $("#results").innerHTML =
    '<div class="empty">已载入保存的数据，可继续编辑或生成计划。</div>';
}

async function loadSaved(initial = false) {
  if (saving || busy) return;
  if (
    !initial &&
    dirty &&
    !confirm("载入已保存数据将替换当前未保存的编辑，是否继续？")
  )
    return;
  const current = version;
  $("#reload-saved").disabled = true;
  try {
    const response = await fetch("/api/workspace");
    const record = await response.json();
    if (!response.ok) throw new Error(record.message || "读取已保存数据失败");
    if (current !== version) {
      $("#save-status").textContent = "读取期间有新编辑，未替换当前内容";
      return;
    }
    savedRevision = record.revision_id;
    if (record.payload) installSaved(record);
    else if (initial) await loadExample(false);
    else $("#save-status").textContent = "尚无已保存数据，当前编辑保留";
  } catch (error) {
    $("#save-status").textContent = error.message;
  } finally {
    $("#reload-saved").disabled = false;
  }
}

async function saveData() {
  if (!data || saving || busy) return;
  viewToken++;
  const unsafe = inputErrors();
  if (unsafe.length) {
    showOutcome({ status: "INVALID", errors: unsafe });
    return;
  }
  const current = version;
  saving = true;
  $("#save-data").disabled = true;
  $("#save-status").textContent = "正在校验并保存…";
  try {
    const response = await fetch("/api/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        payload: currentPayload(),
        expected_revision: savedRevision,
      }),
    });
    const record = await response.json();
    if (!response.ok)
      throw new Error(record.message || "保存失败，未确认成功，请重试");
    if (record.status === "INVALID") {
      showOutcome(record);
      $("#save-status").textContent = "校验未通过，已保存版本保持不变";
      return;
    }
    savedRevision = record.revision_id;
    if (current === version) installSaved(record);
    else
      $("#save-status").textContent = "已保存提交时的数据；当前新修改尚未保存";
  } catch (error) {
    $("#save-status").textContent =
      error instanceof TypeError
        ? "连接中断，未确认保存成功。请重新连接后载入已保存数据核对。"
        : error.message;
  } finally {
    saving = false;
    $("#save-data").disabled = false;
  }
}

async function refreshHistory(more = false) {
  const offset = more ? historyOffset : 0;
  if (offset === null) return;
  $("#refresh-history").disabled = true;
  $("#more-history").disabled = true;
  try {
    const response = await fetch("/api/history?offset=" + offset);
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "历史读取失败");
    historyRows = more ? [...historyRows, ...result.items] : result.items;
    historyOffset = result.next_offset;
    historyLoaded = true;
    historyFailure = "";
    renderHistoryList();
    renderDashboard();
    $("#more-history").hidden = historyOffset === null;
  } catch (error) {
    historyFailure = error.message;
    $("#history-list").textContent = error.message;
    renderDashboard();
  } finally {
    $("#refresh-history").disabled = false;
    $("#more-history").disabled = false;
  }
}

async function viewHistory(id) {
  if (busy) return;
  $("#history-message").textContent = "正在读取计划…";
  const token = ++viewToken;
  try {
    const response = await fetch("/api/history/" + encodeURIComponent(id));
    const record = await response.json();
    if (!response.ok) throw new Error(record.message || "历史读取失败");
    if (token !== viewToken) return;
    showOutcome(record.outcome);
    setExport(id);
    $("#result-badge").textContent = "历史计划 · 只读";
    $("#status").textContent = "正在查看历史计划，基础数据中的编辑未改变。";
    $("#history-message").textContent = "";
    $("#history-meta").hidden = false;
    $("#history-meta").textContent =
      "历史计划 " +
      id.slice(0, 8) +
      " · " +
      formatTime(record.saved_batch.created_at) +
      " · 使用当时保存的输入和结果";
    const context = record.outcome.result.net_bundle.context;
    $("#results").insertAdjacentHTML(
      "beforeend",
      '<details id="historical-input"><summary>查看本次输入快照</summary><p class="muted">基准日 ' +
        esc(context.request.baseline_date) +
        "</p>" +
        Object.entries(schema)
          .map(
            ([kind, fields]) =>
              "<h3>" +
              names[kind] +
              "</h3>" +
              table(
                fields.map((f) => f[1]),
                context.sources[kind].map((row) =>
                  fields.map(([key]) => row[key]),
                ),
              ),
          )
          .join("") +
        "</details>",
    );
    $("#result-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (token === viewToken) $("#history-message").textContent = error.message;
  }
}

document.querySelectorAll("[data-view],[data-go]").forEach((button) =>
  button.addEventListener("click", () => {
    viewToken++;
    $("#history-message").textContent = "";
    showView(button.dataset.view || button.dataset.go);
  }),
);
document.querySelectorAll("[data-tab]").forEach((b) =>
  b.addEventListener("click", () => {
    if (data) {
      active = b.dataset.tab;
      resetEditorFilters();
      renderEditor();
    }
  }),
);
$("#editor").addEventListener("input", (event) => {
  const control = event.target,
    key = control.dataset.key;
  if (!key) return;
  const row = data.sources[active][Number(control.dataset.row)];
  row[key] =
    control.type === "number"
      ? control.value === ""
        ? null
        : Number(control.value)
      : key === "priority"
        ? Number(control.value)
        : control.value;
  if (key === "supply_type" && row[key] === "BUY") {
    row.min_purchase_qty ??= 0;
    row.purchase_multiple ??= 1;
  }
  invalidate();
  if (active === "tasks" || active === "materials") renderSelection();
  if (key === "supply_type") renderEditor();
});
$("#editor").addEventListener("click", (event) => {
  const edit = event.target.closest("[data-edit]");
  if (edit) {
    openEditor(Number(edit.dataset.edit));
    return;
  }
  const button = event.target.closest("[data-delete]");
  if (!button) return;
  const i = Number(button.dataset.delete);
  data.sources[active].splice(i, 1);
  if (active === "tasks")
    selected = new Set(
      [...selected].filter((v) => v !== i).map((v) => (v > i ? v - 1 : v)),
    );
  invalidate();
  renderEditor();
  renderSelection();
});
$("#add").addEventListener("click", () => {
  if (!data) return;
  if (!quickEdit) {
    openEditor(null);
    return;
  }
  resetEditorFilters();
  data.sources[active].push(defaultRecord(active));
  editorPage = Math.floor(
    (data.sources[active].length - 1) / Number($("#page-size").value),
  );
  invalidate();
  renderEditor();
  renderSelection();
  $("#editor tbody tr:last-child input")?.focus();
});
$("#task-selection").addEventListener("change", (event) => {
  const i = Number(event.target.dataset.select);
  if (event.target.checked) selected.add(i);
  else selected.delete(i);
  invalidate();
});
$("#select-all").addEventListener("click", () => {
  if (!data) return;
  selected = new Set(data.sources.tasks.map((_, i) => i));
  invalidate();
  renderSelection();
});
$("#baseline").addEventListener("input", () => {
  if (data) invalidate();
});
$("#load").addEventListener("click", () => loadExample());
$("#calculate").addEventListener("click", calculate);
$("#results").addEventListener("click", (event) => {
  const button = event.target.closest("[data-locate]");
  if (!button) return;
  const m = /^(materials|bom|stocks|tasks)\[(\d+)\](?:\.(\w+))?/.exec(
    button.dataset.locate,
  );
  if (!m) return;
  showView("data", false);
  active = m[1];
  resetEditorFilters();
  quickEdit = true;
  $("#quick-edit").setAttribute("aria-pressed", "true");
  editorPage = Math.floor(Number(m[2]) / Number($("#page-size").value));
  renderEditor();
  const input = $(
    `#editor [data-row="${m[2]}"]${m[3] ? `[data-key="${m[3]}"]` : ""}`,
  );
  if (input) {
    input.classList.add("invalid-field");
    input.focus();
    input.scrollIntoView({ block: "center" });
  }
});
window.addEventListener("beforeunload", (event) => {
  if (dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
$("#save-data").addEventListener("click", saveData);
$("#reload-saved").addEventListener("click", () => loadSaved());
$("#refresh-history").addEventListener("click", () => refreshHistory());
$("#more-history").addEventListener("click", () => refreshHistory(true));
$("#history-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-history]");
  if (button) viewHistory(button.dataset.history);
});
async function previewCsv() {
  if (!data || csvWorking) return;
  clearCsvPreview();
  const current = version,
    token = csvToken;
  csvWorking = true;
  $("#preview-csv").disabled = true;
  $("#csv-message").textContent = "正在读取和校验文件…";
  try {
    const files = {};
    for (const input of document.querySelectorAll("[data-csv]")) {
      const file = input.files[0];
      if (!file) continue;
      if (file.size > 500000)
        throw new Error(file.name + " 超过500KB，请拆分或缩小文件。");
      try {
        files[input.dataset.csv] = new TextDecoder("utf-8", {
          fatal: true,
        }).decode(await file.arrayBuffer());
      } catch {
        throw new Error(
          file.name + " 不是有效的UTF-8文件，请另存为CSV UTF-8后重试。",
        );
      }
    }
    if (!Object.keys(files).length) throw new Error("请至少选择一个CSV文件。");
    const response = await fetch("/api/csv/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload: currentPayload(), files }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "CSV校验服务不可用。");
    if (current !== version || token !== csvToken) {
      $("#csv-message").textContent = "校验期间数据或文件已改变，请重新校验。";
      return;
    }
    if (result.status !== "READY") {
      $("#csv-message").innerHTML =
        "未应用导入，原数据保持不变。<ul>" +
        result.errors
          .map(
            (e) =>
              "<li>" +
              esc(e.source_location) +
              "：" +
              esc(messages[e.code] || e.message) +
              "</li>",
          )
          .join("") +
        "</ul>";
      return;
    }
    csvCandidate = { payload: result.payload, version: current, token };
    $("#apply-csv").disabled = false;
    $("#csv-message").textContent =
      "校验通过，将替换：" +
      Object.entries(result.counts)
        .map(([k, v]) => names[k] + " " + v + " 行")
        .join("、") +
      "。请核对后点击应用。";
  } catch (error) {
    $("#csv-message").textContent =
      error instanceof TypeError
        ? "无法连接校验服务，请保持启动窗口运行后重试。"
        : error.message;
  } finally {
    csvWorking = false;
    $("#preview-csv").disabled = false;
  }
}

function applyCsv() {
  if (busy || saving) {
    $("#csv-message").textContent = "请等待当前保存或计算完成后再应用。";
    return;
  }
  if (
    !csvCandidate ||
    csvCandidate.version !== version ||
    csvCandidate.token !== csvToken
  ) {
    clearCsvPreview();
    $("#csv-message").textContent = "预览已失效，请重新校验。";
    return;
  }
  data = csvCandidate.payload;
  selected = new Set(
    data.sources.tasks
      .map((t, i) =>
        data.request.selected_task_ids.includes(t.task_id) ? i : -1,
      )
      .filter((i) => i >= 0),
  );
  invalidate();
  renderEditor();
  renderSelection();
  $("#baseline").value = data.request.baseline_date;
  $("#csv-message").textContent =
    "已应用到编辑区，请核对任务勾选并点击“保存数据”。";
}

async function downloadCsv() {
  if (!exportBatch) return;
  const id = exportBatch,
    kind = $("#export-kind").value;
  $("#export-csv").disabled = true;
  try {
    const response = await fetch(
      "/api/history/" + encodeURIComponent(id) + "/csv/" + kind,
    );
    if (!response.ok) {
      const problem = await response.json();
      throw new Error(problem.message || "导出失败。");
    }
    const blob = await response.blob(),
      url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = "plan-" + id + "-" + kind + ".csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (exportBatch === id)
      $("#export-status").textContent = "已导出计划 " + id.slice(0, 8);
  } catch (error) {
    $("#export-status").textContent =
      error instanceof TypeError
        ? "连接失败，请重新连接后导出。"
        : error.message;
  } finally {
    $("#export-csv").disabled = false;
  }
}

document.querySelectorAll("[data-csv]").forEach((input) =>
  input.addEventListener("change", () => {
    clearCsvPreview();
    $("#csv-message").textContent = "文件已选择，请校验后应用。";
  }),
);
$("#preview-csv").addEventListener("click", previewCsv);
$("#apply-csv").addEventListener("click", applyCsv);
$("#export-csv").addEventListener("click", downloadCsv);
// Presentation helpers consume the existing source and result records. Planning stays on the server.
function priorityTag(value) {
  return (
    '<span class="tag ' +
    (Number(value) === 1 ? "rust" : Number(value) === 2 ? "" : "neutral") +
    '">' +
    esc({ 1: "高优先级", 2: "中优先级", 3: "低优先级" }[value] || "未设置") +
    "</span>"
  );
}
function resetEditorFilters() {
  editorPage = 0;
  $("#data-search").value = "";
  $("#data-filter").innerHTML =
    active === "materials"
      ? '<option value="">全部类型</option><option value="MAKE">自制件</option><option value="BUY">外购件</option>'
      : active === "tasks"
        ? '<option value="">全部优先级</option><option value="1">高优先级</option><option value="2">中优先级</option><option value="3">低优先级</option>'
        : '<option value="">全部记录</option>';
  $("#data-filter").disabled = !["materials", "tasks"].includes(active);
}
function defaultRecord(kind) {
  return {
    materials: {
      material_id: "",
      name: "",
      supply_type: "BUY",
      unit: "pcs",
      lead_time_days: 0,
      min_purchase_qty: 0,
      purchase_multiple: 1,
    },
    bom: { parent_id: "", child_id: "", qty_per: 1 },
    stocks: {
      material_id: "",
      on_hand: 0,
      reserved: 0,
      snapshot_date: $("#baseline").value,
    },
    tasks: {
      task_id: "",
      product_id: "",
      required_qty: 1,
      due_date: $("#baseline").value,
      priority: 2,
    },
  }[kind];
}
function renderDashboard() {
  if (!data) return;
  $("#dashboard-tasks").textContent = data.sources.tasks.length;
  $("#dashboard-selected").textContent = selected.size;
  const shortages = currentValidResult
    ? new Set(
        currentValidResult.net_bundle.buy_shortages.map((x) => x.material_id),
      ).size
    : null;
  for (const [id, value] of [
    ["dashboard-shortage", shortages],
    ["dashboard-risk", currentValidResult?.summary.risk_count],
  ]) {
    const node = $("#" + id);
    node.textContent = value == null ? "待计算" : value;
    node.classList.toggle("pending", value == null);
  }
  const queue = data.sources.tasks
    .map((t, i) => ({ ...t, index: i }))
    .sort(
      (a, b) =>
        Number(a.priority) - Number(b.priority) ||
        String(a.due_date).localeCompare(String(b.due_date)) ||
        String(a.task_id).localeCompare(String(b.task_id)),
    );
  $("#dashboard-queue").innerHTML = queue.length
    ? queue
        .slice(0, 5)
        .map(
          (t, i) =>
            '<div class="queue-item"><span class="queue-index">' +
            String(i + 1).padStart(2, "0") +
            "</span><div><strong>" +
            esc(t.task_id || "未填写编号") +
            "</strong><p>" +
            esc(t.product_id || "未填写产品") +
            " · " +
            esc(t.required_qty ?? "—") +
            " · " +
            (selected.has(t.index) ? "已选入本次计算" : "未选入本次计算") +
            '</p></div><div class="queue-meta">' +
            priorityTag(t.priority) +
            "<small>" +
            esc(t.due_date || "日期未填写") +
            "</small></div></div>",
        )
        .join("") +
      (queue.length > 5
        ? '<p class="muted">展示前 5 项，共 ' + queue.length + " 项任务。</p>"
        : "")
    : '<div class="empty">还没有生产任务<small>在基础数据中添加任务，即可开始计划。</small></div>';
  $("#dashboard-readiness").innerHTML =
    Object.entries(names)
      .map(
        ([key, label]) =>
          '<div class="readiness-line"><span>' +
          label +
          "</span><strong>" +
          data.sources[key].length +
          " 条</strong></div>",
      )
      .join("") +
    "<small>基准日 " +
    esc($("#baseline").value || "未填写") +
    "<br>数据完整性将在保存或计算时校验。</small>";
  $("#dashboard-recent").innerHTML = historyFailure
    ? '<p class="muted">历史读取失败：' +
      esc(historyFailure) +
      "。请到历史记录页重试。</p>"
    : !historyLoaded
      ? '<p class="muted">正在读取历史计划…</p>'
      : historyRows.length
        ? historyRows
            .slice(0, 3)
            .map(
              (r) =>
                '<div class="recent-plan"><div><strong>' +
                esc(r.batch_id.slice(0, 8)) +
                "</strong><small>" +
                esc(formatTime(r.created_at)) +
                " · " +
                r.summary.task_count +
                ' 个任务</small></div><button data-recent="' +
                esc(r.batch_id) +
                '">查看计划</button></div>',
            )
            .join("")
        : '<div class="empty">尚无已保存计划<small>成功计算后，独立快照会显示在这里。</small></div>';
}
function renderHistoryList() {
  const query = $("#history-search").value.trim().toLocaleLowerCase();
  const rows = historyRows.filter((r) =>
    [r.batch_id, r.baseline_date, formatTime(r.created_at), ...r.task_ids].some(
      (v) => String(v).toLocaleLowerCase().includes(query),
    ),
  );
  $("#history-list").innerHTML = rows.length
    ? '<div class="table-wrap"><table><thead><tr><th>计划编号</th><th>保存时间</th><th>基准日</th><th>任务</th><th>生产 / 采购 / 风险</th><th>操作</th></tr></thead><tbody>' +
      rows
        .map(
          (r) =>
            `<tr><td class="mono">${esc(r.batch_id.slice(0, 8))}</td><td>${esc(formatTime(r.created_at))}</td><td>${esc(r.baseline_date)}</td><td>${esc(r.task_ids.join("、"))}</td><td>${r.summary.make_line_count} / ${r.summary.purchase_line_count} / <span class="tag ${r.summary.risk_count ? "rust" : "sage"}">${r.summary.risk_count}</span></td><td><button data-history="${esc(r.batch_id)}">查看</button></td></tr>`,
        )
        .join("") +
      "</tbody></table></div>"
    : '<div class="empty">' +
      (query ? "已加载记录中没有匹配项" : "还没有历史计划") +
      "<small>" +
      (query
        ? "清除搜索或加载更多历史记录。"
        : "在计划计算中生成第一份计划，系统会自动保存到这里。") +
      "</small></div>";
}
function openDrawer(title, html, kicker = "RECORD DETAILS") {
  drawerReturnFocus = document.activeElement;
  $("#drawer-title").textContent = title;
  $("#drawer-kicker").textContent = kicker;
  $("#drawer-content").innerHTML = html;
  $("#record-drawer").showModal();
  (
    $(
      "#drawer-content input:not(:disabled),#drawer-content select:not(:disabled)",
    ) || $("#drawer-close")
  ).focus();
}
function closeDrawer() {
  if (
    drawerState &&
    $("#drawer-form") &&
    $("#drawer-form").dataset.changed === "true" &&
    !confirm("放弃尚未应用的修改？")
  )
    return;
  $("#record-drawer").close();
  drawerState = null;
  if (drawerReturnFocus?.isConnected) drawerReturnFocus.focus();
  else $("#page-title").focus({ preventScroll: true });
}
function openEditor(index) {
  if (!data) return;
  const row =
    index === null
      ? defaultRecord(active)
      : structuredClone(data.sources[active][index]);
  drawerState = { kind: active, index, version, row };
  const fields = schema[active]
    .map(([key, label, type]) => {
      const attr = 'name="' + key + '" id="drawer-' + key + '"';
      let control;
      if (type === "type" || type === "priority") {
        const choices =
          type === "type"
            ? [
                ["MAKE", "自制件"],
                ["BUY", "外购件"],
              ]
            : [
                [1, "1 · 高优先级"],
                [2, "2 · 中优先级"],
                [3, "3 · 低优先级"],
              ];
        control =
          "<select " +
          attr +
          ">" +
          choices
            .map(
              ([v, l]) =>
                '<option value="' +
                v +
                '" ' +
                (String(v) === String(row[key]) ? "selected" : "") +
                ">" +
                l +
                "</option>",
            )
            .join("") +
          "</select>";
      } else
        control =
          "<input " +
          attr +
          ' type="' +
          type +
          '" value="' +
          esc(row[key] ?? "") +
          '" ' +
          (type === "number"
            ? 'step="1" min="' +
              (["qty_per", "required_qty", "purchase_multiple"].includes(key)
                ? "1"
                : "0") +
              '" max="9007199254740991"'
            : "") +
          " " +
          (["parent_id", "child_id", "material_id", "product_id"].includes(
            key,
          ) && !(active === "materials" && key === "material_id")
            ? 'list="material-options"'
            : "") +
          " required>";
      return '<label for="drawer-' + key + '">' + label + control + "</label>";
    })
    .join("");
  openDrawer(
    (index === null ? "新增" : "编辑") + names[active],
    '<form id="drawer-form"><p class="muted">应用到当前编辑数据后，点击“保存数据”才会写入本机存储。</p><datalist id="material-options">' +
      data.sources.materials
        .map(
          (m) =>
            '<option value="' +
            esc(m.material_id) +
            '">' +
            esc(m.name) +
            "</option>",
        )
        .join("") +
      '</datalist><div class="drawer-fields">' +
      fields +
      '</div><p id="drawer-errors" class="drawer-errors" role="alert"></p><div class="drawer-footer"><button type="button" id="drawer-cancel">取消</button><button class="primary" type="submit">应用修改</button></div></form>',
    "DATA / " + active.toUpperCase(),
  );
  syncDrawerSupply();
}
function syncDrawerSupply() {
  const field = $("#drawer-supply_type");
  if (!field) return;
  for (const key of ["min_purchase_qty", "purchase_multiple"]) {
    const input = $("#drawer-" + key);
    input.disabled = field.value === "MAKE";
    input.required = !input.disabled;
    if (!input.disabled && input.value === "")
      input.value = key === "purchase_multiple" ? "1" : "0";
  }
}
function applyDrawer(event) {
  event.preventDefault();
  if (!drawerState) return;
  if (drawerState.version !== version) {
    $("#drawer-errors").textContent = "数据已发生变化，请关闭后重新打开记录。";
    return;
  }
  const row = { ...drawerState.row };
  for (const [key, , type] of schema[drawerState.kind]) {
    const control = $("#drawer-" + key);
    if (control.disabled) continue;
    row[key] =
      type === "number" || type === "priority"
        ? Number(control.value)
        : control.value.trim();
  }
  const fields = schema[drawerState.kind];
  if (
    fields.some(
      ([key, , type]) =>
        type === "number" &&
        !$("#drawer-" + key).disabled &&
        !Number.isSafeInteger(row[key]),
    )
  ) {
    $("#drawer-errors").textContent = "数量须为安全整数，请检查输入。";
    return;
  }
  const idKey =
    drawerState.kind === "materials"
      ? "material_id"
      : drawerState.kind === "tasks"
        ? "task_id"
        : null;
  if (
    idKey &&
    data.sources[drawerState.kind].some(
      (r, i) =>
        i !== drawerState.index && String(r[idKey]).trim() === row[idKey],
    )
  ) {
    $("#drawer-errors").textContent = "编号已存在，请使用不同编号。";
    return;
  }
  if (drawerState.kind === "stocks" && row.reserved > row.on_hand) {
    $("#drawer-errors").textContent = "已占用数量不能超过账面库存。";
    return;
  }
  const isNew = drawerState.index === null;
  if (isNew) data.sources[drawerState.kind].push(row);
  else data.sources[drawerState.kind][drawerState.index] = row;
  $("#drawer-form").dataset.changed = "false";
  closeDrawer();
  if (isNew) {
    resetEditorFilters();
    editorPage = Math.floor(
      (data.sources[active].length - 1) / Number($("#page-size").value),
    );
  }
  invalidate();
  renderEditor();
  renderSelection();
}
function stockAvailable(mid) {
  const stock = data.sources.stocks.find(
    (s) => String(s.material_id).trim() === mid,
  );
  if (!stock) return null;
  if (
    !Number.isSafeInteger(stock.on_hand) ||
    !Number.isSafeInteger(stock.reserved)
  )
    return null;
  return BigInt(stock.on_hand) - BigInt(stock.reserved);
}
function renderBom() {
  if (!data) return;
  const materials = data.sources.materials,
    ids = new Set(
      materials.map((m) => String(m.material_id).trim()).filter(Boolean),
    );
  const children = new Set(
    data.sources.bom.map((e) => String(e.child_id).trim()),
  );
  if (!ids.has(bomRoot))
    bomRoot =
      materials
        .find(
          (m) =>
            !children.has(String(m.material_id).trim()) &&
            m.supply_type === "MAKE",
        )
        ?.material_id?.trim() ||
      materials[0]?.material_id?.trim() ||
      "";
  $("#bom-root").innerHTML = [...ids]
    .map(
      (id) =>
        '<option value="' +
        esc(id) +
        '" ' +
        (id === bomRoot ? "selected" : "") +
        ">" +
        esc(id) +
        " · " +
        esc(materials.find((m) => m.material_id.trim() === id)?.name || "") +
        "</option>",
    )
    .join("");
  if (!bomRoot) {
    $("#bom-tree").innerHTML =
      '<div class="empty">暂无物料<small>先在基础数据中建立物料档案和 BOM 关系。</small></div>';
    $("#bom-detail").textContent = "选择一个物料节点查看详情。";
    $("#bom-warning").textContent = "";
    return;
  }
  if (!ids.has(bomSelected)) bomSelected = bomRoot;
  const adjacency = new Map();
  for (const edge of data.sources.bom) {
    const parent = String(edge.parent_id).trim();
    if (!adjacency.has(parent)) adjacency.set(parent, []);
    adjacency.get(parent).push(edge);
  }
  let count = 0;
  const warnings = new Set();
  const walk = (mid, qty, trail, path) => {
    if (count >= 250 || trail.length >= 32) {
      warnings.add(
        "结构较大，仅展示前 250 个节点与 32 层；可切换根物料继续查看。",
      );
      return "";
    }
    count++;
    const material = materials.find(
        (m) => String(m.material_id).trim() === mid,
      ),
      edges = adjacency.get(mid) || [],
      cycle = trail.includes(mid);
    if (cycle) warnings.add("检测到循环引用，请修正 BOM 后再计算。");
    if (!material) warnings.add("存在未建档的物料编号，请检查基础数据。");
    const collapsed = bomCollapsed.has(path),
      available = stockAvailable(mid),
      label = cycle
        ? "循环引用"
        : material?.supply_type === "MAKE"
          ? "自制件"
          : "外购件";
    let html =
      '<div class="bom-node-row">' +
      (edges.length && !cycle
        ? '<button class="bom-toggle" data-bom-toggle="' +
          esc(path) +
          '" aria-expanded="' +
          !collapsed +
          '" aria-label="' +
          (collapsed ? "展开" : "折叠") +
          " " +
          esc(mid) +
          '">' +
          (collapsed ? "+" : "−") +
          "</button>"
        : '<span class="bom-leaf-space"></span>') +
      '<button class="bom-node" data-bom-node="' +
      esc(mid) +
      '" aria-pressed="' +
      (mid === bomSelected) +
      '"><strong>' +
      esc(mid) +
      '<span class="tag ' +
      (cycle ? "rust" : material?.supply_type === "MAKE" ? "sage" : "") +
      '">' +
      label +
      "</span></strong><small>" +
      esc(material?.name || "未建档") +
      (qty === null ? " · 根物料" : " · 单件用量 " + esc(qty)) +
      "</small><small>可用库存 " +
      (available === null ? "待核对" : esc(available.toString())) +
      "</small></button></div>";
    if (edges.length && !cycle && !collapsed)
      html +=
        '<div class="bom-branch">' +
        edges
          .map((edge, i) =>
            walk(
              String(edge.child_id).trim(),
              edge.qty_per,
              [...trail, mid],
              path + "/" + i,
            ),
          )
          .join("") +
        "</div>";
    return html;
  };
  $("#bom-tree").innerHTML = walk(bomRoot, null, [], "root");
  $("#bom-warning").textContent = [...warnings].join(" ");
  renderBomDetail();
}
function renderBomDetail() {
  if (!data) return;
  const m = data.sources.materials.find(
    (m) => String(m.material_id).trim() === bomSelected,
  );
  if (!m) {
    $("#bom-detail").textContent = "该物料尚未建档。";
    return;
  }
  const stock = stockAvailable(bomSelected),
    result = currentValidResult;
  const demands =
    result?.net_bundle.demands.filter(
      (d) => d.demand.material_id === bomSelected,
    ) || [];
  const sum = (key) =>
    demands.reduce((total, d) => total + BigInt(d[key]), 0n).toString();
  $("#bom-detail").innerHTML =
    '<h3 class="bom-detail-title">' +
    esc(m.material_id) +
    '</h3><p class="muted">' +
    esc(m.name) +
    '</p><span class="tag ' +
    (m.supply_type === "MAKE" ? "sage" : "") +
    '">' +
    (m.supply_type === "MAKE" ? "自制件" : "外购件") +
    '</span><dl class="detail-list">' +
    [
      ["计量单位", m.unit],
      ["提前期", m.lead_time_days + " 天"],
      ["可用库存", stock === null ? "待核对" : stock.toString()],
      ["本次库存抵扣", result ? sum("allocated_qty") : "待计算"],
      ["本次净需求", result ? sum("net_qty") : "待计算"],
    ]
      .map(([l, v]) => "<div><dt>" + l + "</dt><dd>" + esc(v) + "</dd></div>")
      .join("") +
    '</dl><p class="notice">' +
    (result
      ? "净需求汇总当前计划的所有任务。外购净需求尚未抵扣采购余量或按采购倍数取整。"
      : "库存来自当前编辑数据。生成计划后可查看实际抵扣与净需求。") +
    '</p><p class="muted">树中的单件用量是结构比例，不等于本次需要采购的数量。</p>';
}
function analysisMarkup(r) {
  const demands = r.net_bundle.demands;
  return (
    '<section class="analysis"><div class="analysis-tabs" role="tablist" aria-label="计划解读"><button id="analysis-tab-flow" role="tab" aria-selected="true" aria-controls="analysis-flow" data-analysis="flow">计算过程</button><button id="analysis-tab-timeline" role="tab" aria-selected="false" aria-controls="analysis-timeline" data-analysis="timeline">计划时间轴</button></div><div id="analysis-flow" role="tabpanel" aria-labelledby="analysis-tab-flow"><div class="flow-toolbar"><label for="demand-select">选择需求</label><select id="demand-select">' +
    demands
      .map(
        (d, i) =>
          '<option value="' +
          i +
          '">' +
          esc(
            [d.demand.task_id, d.demand.material_id, d.demand.needed_date].join(
              " / ",
            ),
          ) +
          "</option>",
      )
      .join("") +
    '</select></div><div id="demand-flow"></div></div><div id="analysis-timeline" role="tabpanel" aria-labelledby="analysis-tab-timeline" hidden><div class="flow-toolbar"><label for="timeline-filter">事件类型</label><select id="timeline-filter"><option value="">全部事件</option><option value="make">生产</option><option value="purchase">采购</option><option value="delivery">交付</option></select></div><div class="timeline-legend"><span><i></i>生产</span><span><i class="purchase"></i>采购</span><span><i class="delivery"></i>交付</span><span class="tag rust">早于基准日</span></div><div id="timeline"></div></div></section>'
  );
}
function selectedDemand() {
  return displayedResult?.net_bundle.demands[
    Number($("#demand-select")?.value || 0)
  ];
}
function renderDemandFlow() {
  const d = selectedDemand();
  if (!d || !$("#demand-flow")) return;
  const mid = d.demand.material_id,
    m = displayedResult.net_bundle.context.sources.materials.find(
      (m) => m.material_id === mid,
    );
  const bucket = displayedResult.purchase_buckets.find(
    (b) => b.material_id === mid && b.needed_date === d.demand.needed_date,
  );
  let html =
    '<div class="flow-steps">' +
    [
      ["gross", "毛需求", d.demand.gross_qty],
      ["stock", "抵扣库存", d.allocated_qty],
      ["net", "净需求", d.net_qty],
    ]
      .map(
        ([key, label, value]) =>
          '<button class="flow-step" data-explain="' +
          key +
          '"><span>' +
          label +
          '</span><strong id="flow-' +
          key +
          '">' +
          esc(value) +
          "</strong><small>点击查看依据 ↗</small></button>",
      )
      .join("") +
    '</div><p class="muted">净需求 = 毛需求 − 本次库存抵扣。' +
    (m?.supply_type === "MAKE"
      ? "自制件按净需求安排生产，再展开下层物料。"
      : "外购净需求按物料与需要日期汇总，再处理余量与采购取整。") +
    "</p>";
  if (bucket)
    html +=
      '<div class="purchase-explanation"><p><strong>同日采购汇总 · ' +
      esc(mid) +
      "</strong></p><p>" +
      esc(bucket.gross_shortage) +
      " 缺口 − " +
      esc(bucket.surplus_used) +
      " 前期余量 = " +
      esc(bucket.remaining_gap) +
      ' 剩余缺口</p><p>建议采购 <button class="text-button" data-explain="purchase">' +
      esc(bucket.purchase_qty) +
      " " +
      esc(m?.unit || "") +
      " ↗</button></p><small>此处包含同一物料、同一需要日期的所有任务。</small></div>";
  $("#demand-flow").innerHTML = html;
}
function explainDemand(kind) {
  const d = selectedDemand();
  if (!d) return;
  drawerState = null;
  const title = {
    gross: "毛需求来源",
    stock: "库存分配依据",
    net: "净需求与后续安排",
    purchase: "采购数量依据",
  }[kind];
  let html =
    '<p class="notice">' +
    esc(d.demand.task_id) +
    " / " +
    esc(d.demand.material_id) +
    " / " +
    esc(d.demand.needed_date) +
    "</p>";
  if (kind === "purchase") {
    const b = displayedResult.purchase_buckets.find(
      (b) =>
        b.material_id === d.demand.material_id &&
        b.needed_date === d.demand.needed_date,
    );
    const m = displayedResult.net_bundle.context.sources.materials.find(
      (m) => m.material_id === d.demand.material_id,
    );
    if (!b || !m) return;
    html +=
      '<dl class="detail-list">' +
      [
        ["同日所有任务缺口", b.gross_shortage],
        ["已用前期余量", b.surplus_used],
        ["剩余缺口", b.remaining_gap],
        ["最小采购量", m.min_purchase_qty],
        ["采购倍数", m.purchase_multiple],
        ["建议采购", b.purchase_qty],
        ["下单日期", b.order_date || "无需下单"],
      ]
        .map(([l, v]) => "<div><dt>" + l + "</dt><dd>" + esc(v) + "</dd></div>")
        .join("") +
      '</dl><p class="muted">剩余缺口为零时不采购；否则先满足最小采购量，再向上取整到采购倍数。余量只可用于到货日及之后的需求。</p>';
  } else {
    const allocation = displayedResult.net_bundle.allocations.find(
      (a) => a.demand_id === d.demand.demand_id,
    );
    if (allocation)
      html +=
        '<p class="muted">分配前库存 ' +
        esc(allocation.before_qty) +
        " − 本次抵扣 " +
        esc(allocation.allocated_qty) +
        " = 分配后库存 " +
        esc(allocation.after_qty) +
        "</p>";
    html +=
      "<p>毛需求 " +
      esc(d.demand.gross_qty) +
      " − 抵扣 " +
      esc(d.allocated_qty) +
      " = 净需求 " +
      esc(d.net_qty) +
      "</p><h3>需求贡献路径</h3>" +
      d.demand.origins
        .map((o) => {
          const a = d.source_allocations.find(
            (a) => a.origin_id === o.origin_id,
          );
          return (
            '<article class="trace-card"><strong>' +
            esc(o.bom_path.join(" → ")) +
            "</strong><p>贡献 " +
            esc(o.contribution_qty) +
            " · 抵扣 " +
            esc(a?.allocated_qty ?? "—") +
            " · 剩余 " +
            esc(a?.residual_qty ?? "—") +
            "</p></article>"
          );
        })
        .join("") +
      '<p class="muted">处理顺序：' +
      esc(displayedResult.net_bundle.context.ordered_task_ids.join(" → ")) +
      "。多个任务共享库存时，先满足高优先级任务。</p>";
  }
  openDrawer(title, html, "PLAN / TRACEABILITY");
}
function timelineEvents() {
  if (!displayedResult) return [];
  const r = displayedResult,
    context = r.net_bundle.context;
  const tasks = context.sources.tasks.filter((t) =>
    context.ordered_task_ids.includes(t.task_id),
  );
  return [
    ...r.net_bundle.make_lines.map((x) => ({
      kind: "make",
      label: x.task_id + " / " + x.material_id,
      start: x.start_date,
      end: x.needed_date,
      qty: x.make_qty,
    })),
    ...r.purchase_buckets
      .filter((x) => BigInt(x.purchase_qty) > 0n)
      .map((x) => ({
        kind: "purchase",
        label: x.material_id + " · 采购",
        start: x.order_date,
        end: x.needed_date,
        qty: x.purchase_qty,
      })),
    ...tasks.map((t) => ({
      kind: "delivery",
      label: t.task_id + " · 交付",
      start: t.due_date,
      end: t.due_date,
      qty: t.required_qty,
    })),
  ].sort(
    (a, b) => a.start.localeCompare(b.start) || a.label.localeCompare(b.label),
  );
}
function renderTimeline() {
  if (!$("#timeline") || !displayedResult) return;
  const all = timelineEvents(),
    filter = $("#timeline-filter").value,
    events = all.filter((e) => !filter || e.kind === filter);
  if (!events.length) {
    $("#timeline").innerHTML = '<div class="empty">没有此类型的计划事件</div>';
    return;
  }
  const day = (value) => Date.parse(value + "T00:00:00Z") / 86400000;
  const min = Math.min(...all.map((e) => day(e.start))),
    max = Math.max(...all.map((e) => day(e.end))),
    span = Math.max(1, max - min);
  const baseline = displayedResult.net_bundle.context.request.baseline_date;
  $("#timeline").innerHTML =
    '<p class="muted">基准日 ' +
    esc(baseline) +
    ' · 日期按日历日倒推，不代表产能排程。</p><div class="timeline-range"><span>' +
    new Date(min * 86400000).toISOString().slice(0, 10) +
    "</span><span>" +
    new Date(max * 86400000).toISOString().slice(0, 10) +
    "</span></div>" +
    events
      .map((e) => {
        const early = e.start < baseline,
          index = all.indexOf(e);
        return (
          '<div class="timeline-row ' +
          (early ? "early" : "") +
          '"><div class="timeline-label">' +
          esc(e.label) +
          "<small>" +
          esc(e.qty) +
          " · " +
          esc(e.start.slice(5)) +
          " — " +
          esc(e.end.slice(5)) +
          '</small></div><div class="timeline-track"><button class="timeline-bar ' +
          e.kind +
          (early ? " early" : "") +
          '" data-event="' +
          index +
          '" aria-label="' +
          esc(
            e.label +
              "，" +
              e.start +
              "至" +
              e.end +
              (early ? "，早于基准日" : ""),
          ) +
          '" title="' +
          esc(e.start + " → " + e.end) +
          '"></button></div></div>'
        );
      })
      .join("") +
    '<details class="timeline-date-list"><summary>查看完整日期明细</summary><ul>' +
    events
      .map(
        (e) =>
          "<li>" +
          esc(e.label) +
          " · " +
          esc(e.start) +
          " → " +
          esc(e.end) +
          (e.start < baseline ? " · 早于基准日" : "") +
          "</li>",
      )
      .join("") +
    "</ul></details>";
  // Set numeric CSS properties through the DOM; inline style attributes are
  // deliberately disallowed by the server's existing Content-Security-Policy.
  document.querySelectorAll('#timeline [data-event]').forEach(bar=>{
    const event=all[Number(bar.dataset.event)];
    bar.style.left=(((day(event.start)-min)/span)*97)+'%';
    bar.style.width=Math.max(1,((day(event.end)-day(event.start))/span)*97)+'%';
  });
}
// Lucide-style line icons, embedded locally so the workspace stays offline-capable.
const iconPaths = {
  overview:
    '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  data: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5 M3 12a9 3 0 0 0 18 0"/>',
  bom: '<rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v4 M5 16v-4h14v4"/>',
  planning:
    '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8 M8 11h2 M14 11h2 M8 15h2 M14 15h2"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8 M3 3v5h5 M12 7v5l3 2"/>',
  search: '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
};
document
  .querySelectorAll("[data-icon]")
  .forEach(
    (el) =>
      (el.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        iconPaths[el.dataset.icon] +
        "</svg>"),
  );
$("#data-search").addEventListener("input", () => {
  editorPage = 0;
  if (data) renderEditor();
});
$("#data-filter").addEventListener("change", () => {
  editorPage = 0;
  if (data) renderEditor();
});
$("#page-size").addEventListener("change", () => {
  editorPage = 0;
  if (data) renderEditor();
});
$("#previous-page").addEventListener("click", () => {
  editorPage--;
  renderEditor();
});
$("#next-page").addEventListener("click", () => {
  editorPage++;
  renderEditor();
});
$("#quick-edit").addEventListener("click", () => {
  quickEdit = !quickEdit;
  $("#quick-edit").setAttribute("aria-pressed", String(quickEdit));
  if (data) renderEditor();
});
$("#drawer-close").addEventListener("click", closeDrawer);
$("#record-drawer").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDrawer();
});
$("#drawer-content").addEventListener("click", (event) => {
  if (event.target.closest("#drawer-cancel")) closeDrawer();
});
$("#drawer-content").addEventListener("input", () => {
  if ($("#drawer-form")) $("#drawer-form").dataset.changed = "true";
  syncDrawerSupply();
});
$("#drawer-content").addEventListener("submit", applyDrawer);
$("#history-search").addEventListener("input", renderHistoryList);
$("#dashboard-recent").addEventListener("click", (event) => {
  const b = event.target.closest("[data-recent]");
  if (b) {
    showView("history");
    viewHistory(b.dataset.recent);
  }
});
$("#bom-root").addEventListener("change", () => {
  bomRoot = $("#bom-root").value;
  bomSelected = bomRoot;
  bomCollapsed.clear();
  renderBom();
});
$("#bom-expand").addEventListener("click", () => {
  bomCollapsed.clear();
  renderBom();
});
$("#bom-tree").addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-bom-toggle]"),
    node = event.target.closest("[data-bom-node]");
  if (toggle) {
    const key = toggle.dataset.bomToggle;
    if (bomCollapsed.has(key)) bomCollapsed.delete(key);
    else bomCollapsed.add(key);
    renderBom();
  } else if (node) {
    bomSelected = node.dataset.bomNode;
    document
      .querySelectorAll("[data-bom-node]")
      .forEach((n) =>
        n.setAttribute(
          "aria-pressed",
          String(n.dataset.bomNode === bomSelected),
        ),
      );
    renderBomDetail();
  }
});
$("#results").addEventListener("change", (event) => {
  if (event.target.id === "demand-select") renderDemandFlow();
  if (event.target.id === "timeline-filter") renderTimeline();
});
$("#results").addEventListener("click", (event) => {
  const tab = event.target.closest("[data-analysis]");
  if (tab) {
    for (const view of ["flow", "timeline"]) {
      const active = tab.dataset.analysis === view;
      $("#analysis-" + view).hidden = !active;
      $("#analysis-tab-" + view).setAttribute("aria-selected", String(active));
    }
    return;
  }
  const explain = event.target.closest("[data-explain]");
  if (explain) {
    explainDemand(explain.dataset.explain);
    return;
  }
  const eventButton = event.target.closest("[data-event]");
  if (eventButton) {
    const e = timelineEvents()[Number(eventButton.dataset.event)];
    if (!e) return;
    drawerState = null;
    openDrawer(
      e.label,
      '<dl class="detail-list">' +
        [
          [
            "事件类型",
            { make: "生产", purchase: "采购", delivery: "交付" }[e.kind],
          ],
          ["数量", e.qty],
          ["开始日期", e.start],
          ["需要日期", e.end],
          [
            "计划基准日",
            displayedResult.net_bundle.context.request.baseline_date,
          ],
        ]
          .map(
            ([l, v]) => "<div><dt>" + l + "</dt><dd>" + esc(v) + "</dd></div>",
          )
          .join("") +
        '</dl><p class="muted">这里只展示计划日期，不代表实际生产进度或已完成采购。</p>',
      "PLAN / TIMELINE",
    );
  }
});
showView("overview", false);
loadSaved(true);
refreshHistory();
