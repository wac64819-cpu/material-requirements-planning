from pathlib import Path
import html, json, re, subprocess
root=Path(r"C:\Users\许yq\Desktop\软件工程")
spec=root/"specs"/"material-requirements-planning"
out=spec/"e3"
out.mkdir(exist_ok=True); (out/"diagrams").mkdir(exist_ok=True)
def write(n,s): (out/n).write_text(s,encoding="utf-8")
sections=[
("M23 Validate and index the BOM",
"Input: SourceSet and validated selected task IDs. Output: Result[GraphIndex]. Inspect every reachable branch, including stock-covered materials.",
"""reachable, edges = collect_reachable_graph_with_visited_set(selected_roots)
IF an unknown material, duplicate edge or nonpositive usage exists:
    RETURN ERROR(located issues)
IF any BUY has children OR any reachable MAKE has no children:
    RETURN ERROR(type/structure issues)
indegree = count_incoming_edges(reachable, edges)
ready = zero-indegree materials ordered by ordinal material ID
order = empty list
WHILE ready is not empty:
    parent = remove_smallest(ready)
    append parent to order
    FOR each child edge in ordinal child-ID order:
        decrement indegree[child]
        IF indegree[child] = 0: add child to ready
IF length(order) != size(reachable):
    RETURN ERROR(BOM_CYCLE, remaining graph records)
RETURN OK(GraphIndex(adjacency, reachable, order, roots))""",
"Later: specify graph collection, exact error locations and extraction of a concrete cycle. A visited set prevents traversal from looping; it must not discard distinct valid BOM edges."),
("M30 Net multilevel requirements",
"Input: PreparedContext from E2. Output: Result[NetBundle]. All field and graph validation has passed. M30 alone owns the temporary balance map.",
"""context, graph = prepared.context, prepared.graph\nbalances = M31.initialize_balances(context.request.request_id, context.sources.stocks)    // once per batch
outputs = empty accumulated demand, allocation, MAKE and BUY records
FOR task_id IN context.ordered_task_ids:    // priority, due date, ordinal ID
    task = lookup task_id in context.sources.tasks\n    pending = one root demand(task.product_id, task.required_qty, task.due_date)
    FOR material IN graph.parent_before_child_order:
        buckets = M32.collect_material_demands(task_id, material, pending)
        FOR demand IN buckets ordered by needed_date:
            allocation = M33.allocate_stock(demand, balances[material])
            balances[material] = allocation.new_balance
            retain allocation.netted_demand and allocation.ledger
            IF material.supply_type = MAKE:
                expansion = M34.expand_make_demand(
                    allocation.netted_demand, material, graph.children[material])
                IF expansion is ERROR: RETURN that ERROR
                retain expansion.make_line if present
                merge expansion.children into pending, preserving origins
            ELSE:
                retain M35.record_buy_shortage(allocation.netted_demand, material)
                    if the returned shortage is not null
RETURN M36.assemble_net_bundle(context, outputs.netted_demands,\n    outputs.allocations, outputs.make_lines, outputs.buy_shortages, balances)""",
"All parents finish before a shared child is processed. Same-task, same-material, same-date requests merge before stock allocation. Purchasing surplus is calculated later in M40, not inside this stock loop."),
("M33 Allocate shared stock",
"Input: Demand and Balance with matching material IDs. Preconditions: gross equals origin contributions; quantities are valid and nonnegative. Output: AllocationResult. Inputs are not mutated.",
"""allocated = MIN(balance.available_qty, demand.gross_qty)
new_balance = balance.available_qty - allocated
net = demand.gross_qty - allocated
left_to_attribute = allocated
source_allocations = empty list
FOR origin IN demand.origins ordered by ordinal BOM path then origin ID:
    taken = MIN(left_to_attribute, origin.contribution_qty)
    append (origin.id, taken, origin.contribution_qty - taken)
    left_to_attribute = left_to_attribute - taken
ASSERT left_to_attribute = 0
RETURN AllocationResult(
    netted demand(gross, allocated, net, source_allocations),
    ledger(before=balance.available_qty, allocated, after=new_balance),
    copied balance with available_qty=new_balance)""",
"Invariant: gross = allocated + net; before = allocated + after; after >= 0. Flowchart 1 uses an equivalent conditional form of MIN and summarizes the origin-attribution loop as one process."),
("M34 Expand net manufacturing demand",
"Input: NettedDemand for a MAKE material, its Material record and validated child edges. Output: Result[MakeExpansion]. BUY materials follow M35 instead.",
"""IF netted.net_qty = 0:
    RETURN OK(no MAKE line, empty child list)
start = M52.subtract_calendar_days(netted.demand.needed_date, material.lead_time_days)
IF start is ERROR: RETURN that ERROR
make_line = record netted.net_qty with needed_date and start.value
children = empty list
FOR source IN netted.source_allocations:
    IF source.residual_qty = 0: CONTINUE
    FOR edge IN child_edges ordered by ordinal child ID:
        quantity = source.residual_qty * edge.qty_per
        append child contribution(
            task=netted.demand.task_id, material=edge.child_id,
            needed_date=start.value, quantity=quantity,
            parent_demand_id=netted.demand.demand_id,
            BOM_path=lookup(source.origin_id, netted.demand.origins).bom_path extended with edge.child_id)
RETURN OK(MakeExpansion(make_line, children))""",
"Only residual parent manufacture consumes new child materials. Child contribution IDs must be stable; their exact encoding and merging procedure will be specified in the expanded design."),
("M43 Round a purchase quantity",
"Input: nonnegative integer remaining_gap and minimum_qty; positive integer purchase_multiple. Output: nonnegative integer purchase quantity. M42 has already consumed eligible earlier surplus.",
"""IF remaining_gap = 0:
    purchase_qty = 0
ELSE:
    target = MAX(remaining_gap, minimum_qty)
    lot_count = (target + purchase_multiple - 1) DIV purchase_multiple
    purchase_qty = lot_count * purchase_multiple
RETURN purchase_qty""",
"DIV is exact integer division. No floating-point rounding is used. N-S diagram 2 shows the same selection and sequence. Invalid parameter handling belongs to input validation and will be documented explicitly later."),
("M53 Flag early required dates",
"Input: required events from M51 and baseline_date. Output: List[Issue]. M51 excludes nonexistent zero-quantity manufacturing or purchasing starts.",
"""risks = empty list
FOR event IN required_events:
    IF event.date < baseline_date:
        append Issue(
            severity=RISK, source_location=event.event_id,
            computed_date=event.date,
            days_before_baseline=calendar_days_between(event.date, baseline_date),
            task_id=event.task_id, material_id=event.material_id)
RETURN risks""",
"Equality with baseline is allowed. Dates are preserved, not moved forward. Task due dates are checked even when finished stock satisfies the whole task.")
]
md="# E3 Detailed Design Starter\n\nVersion 0.1 short draft, 26 September 2026. Project: Material Requirements and Purchasing Plan System.\n\n## Scope of this short draft\n\nThis deliberately partial E3 draft covers six selected procedures from E2 with concise pseudocode, one flowchart and one Nassi-Shneiderman diagram. It preserves structured/procedural design and the confirmed priority-first inventory rule. It is not a complete submission, executable application, group review or test report.\n\nThe course's count requirement depends on N and its module/subsystem wording still needs confirmation. Six selected procedures do not establish compliance while N and that interpretation remain unknown. The remaining interface detail, exceptional paths, additional detailed-design diagrams and actual group records will be added later.\n\n"
for title,contract,pseudo,note in sections:
 md+="## "+title+"\n\n"+contract+"\n\n~~~text\n"+pseudo+"\n~~~\n\n"+note+"\n\n"
md+="## Diagram 1 Flowchart for M33\n\n![M33 stock allocation flowchart](diagrams/m33-flowchart.svg)\n\nThe origin-attribution block follows the loop written in the M33 pseudocode. This first diagram focuses on allocation quantity and balance conservation; expanded error and loop paths remain future work.\n\n## Diagram 2 Nassi Shneiderman diagram for M43\n\n![M43 purchase rounding NS diagram](diagrams/m43-ns.svg)\n\nThe left branch handles zero gap. The right branch applies the minimum and then rounds to a purchase multiple. Both branches return a purchase quantity.\n\n## Small design walkthroughs\n\n| Procedure | Input | Expected result |\n|---|---|---|\n| M33 | Gross 200; available 20 | Allocated 20; net 180; balance 0 |\n| M33 | Gross 10; available 10 | Allocated 10; net 0; balance 0 |\n| M34 | B net 180; each B needs 4 D | D gross demand 720 |\n| M43 | Gap 620; minimum 100; multiple 100 | Purchase 700 |\n| M43 | Gap 0; minimum 100; multiple 10 | Purchase 0 |\n| M53 | Event 2026-10-09; baseline 2026-10-10 | Risk 1 calendar day before baseline |\n\nThese are independent expected values, not program test results. In the full CASE01, D demand 720 minus stock 100 yields purchase 620 before lot-size adjustment.\n\n## What to add next\n\n1. M32 demand merging, M42 chronological surplus use and M62 atomic-save pseudocode.\n2. Complete preconditions, postconditions, error results, stable ID construction and trace fields.\n3. More flowcharts and N-S or PAD diagrams for the chosen detailed-design objects; verify the required count with actual N.\n4. A consistent mapping from each decision/loop to later E4 and E5 cases.\n5. Actual member tasks, all-member meeting record and individual contributions.\n\nNo application code, database or test execution is included in this short draft.\n"
write("E3-brief-en.md",md)
flow=r'''digraph G {
graph [rankdir=TB,bgcolor="white",pad="0.3",nodesep="0.45",ranksep="0.5",label="M33  Allocate shared stock",labelloc=t,fontname="Arial",fontsize=22];
node [shape=box,fontname="Arial",fontsize=15,color="#334155",margin="0.16,0.1"];
edge [fontname="Arial",fontsize=13,color="#475569"];
start [shape=ellipse,label="Validated demand and balance"];
decision [shape=diamond,label="available >= gross?"];
yes [label="allocated = gross"];
no [label="allocated = available"];
net [label="net = gross - allocated\nnew balance = available - allocated"];
origins [label="Attribute allocated quantity to ordered origins\nRetain each origin residual"];
result [label="Build netted demand and allocation ledger"];
end [shape=ellipse,label="Return AllocationResult"];
start -> decision;
decision -> yes [label="Yes"];
decision -> no [label="No"];
yes -> net; no -> net; net -> origins; origins -> result; result -> end;
}'''
ns='''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="580" viewBox="0 0 960 580">
<rect width="960" height="580" fill="white"/>
<g font-family="Arial,sans-serif" fill="#111827" text-anchor="middle">
<text x="480" y="43" font-size="26">M43 Purchase quantity   Nassi Shneiderman diagram</text>
<rect x="60" y="85" width="840" height="415" fill="white" stroke="#334155" stroke-width="2"/>
<path d="M60 85 L480 215 L900 85 M60 215 H900 M480 215 V425 M60 425 H900 M480 285 H900 M480 355 H900" fill="none" stroke="#334155" stroke-width="2"/>
<text x="480" y="125" font-size="23">remaining_gap = 0 ?</text>
<text x="118" y="191" font-size="20">True</text><text x="843" y="191" font-size="20">False</text>
<text x="270" y="325" font-size="23">purchase_qty = 0</text>
<text x="690" y="246" font-size="19">target = MAX(gap, minimum)</text>
<text x="690" y="309" font-size="18">lot_count = (target + multiple - 1)</text>
<text x="690" y="336" font-size="18">DIV multiple</text>
<text x="690" y="397" font-size="19">purchase_qty = lot_count * multiple</text>
<text x="480" y="471" font-size="23">RETURN purchase_qty</text>
<text x="480" y="544" font-size="18">Preconditions: gap and minimum are nonnegative integers; multiple is positive.</text>
</g></svg>'''
write("diagrams/m43-ns.svg",ns)
write("diagrams/m33-flowchart.dot",flow)
deps=r"C:\Users\许yq\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
node=r"C:\Users\许yq\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
renderer="const fs=require('fs'),path=require('path');const deps="+json.dumps(deps)+";const {instance}=require(path.join(deps,'@viz-js/viz/dist/viz.cjs'));const sharp=require(path.join(deps,'sharp'));(async()=>{const d=path.join(__dirname,'diagrams');const viz=await instance();fs.writeFileSync(path.join(d,'m33-flowchart.svg'),viz.renderString(fs.readFileSync(path.join(d,'m33-flowchart.dot'),'utf8'),{format:'svg',engine:'dot'}));for(const name of ['m33-flowchart','m43-ns'])await sharp(Buffer.from(fs.readFileSync(path.join(d,name+'.svg'),'utf8')),{density:120}).png().toFile(path.join(d,name+'.png'));})().catch(e=>{console.error(e);process.exit(1)});"
write("render.cjs",renderer)
subprocess.run([node,str(out/"render.cjs")],check=True)
# HTML keeps the short English text, pseudocode, tables and both vector diagrams together.
lines=md.splitlines(); i=0; body=[]
while i<len(lines):
 line=lines[i]
 if not line.strip(): i+=1; continue
 if line.startswith("~~~"):
  block=[]; i+=1
  while i<len(lines) and not lines[i].startswith("~~~"): block.append(lines[i]); i+=1
  body.append("<pre><code>"+html.escape("\n".join(block))+"</code></pre>"); i+=1; continue
 if line.startswith("#"):
  level=len(line)-len(line.lstrip("#")); body.append(f"<h{level}>"+html.escape(line[level:].strip())+f"</h{level}>"); i+=1; continue
 if line.startswith("!["):
  p=re.search(r"\(([^)]+)\)",line).group(1); svg=(out/p).read_text(encoding="utf-8"); body.append("<figure>"+svg[svg.index("<svg"):]+"</figure>"); i+=1; continue
 if line.startswith("|"):
  rows=[]
  while i<len(lines) and lines[i].startswith("|"):
   cells=[v.strip() for v in lines[i].strip("|").split("|")]
   if not all(re.fullmatch("[-: ]+",v) for v in cells): rows.append(cells)
   i+=1
  body.append("<table><thead><tr>"+"".join("<th>"+html.escape(v)+"</th>" for v in rows[0])+"</tr></thead><tbody>")
  for row in rows[1:]: body.append("<tr>"+"".join("<td>"+html.escape(v)+"</td>" for v in row)+"</tr>")
  body.append("</tbody></table>"); continue
 body.append("<p>"+html.escape(line)+"</p>"); i+=1
css="body{margin:0;background:#f4f6f8;font:16px/1.65 Arial,sans-serif;color:#17212e}main{max-width:1000px;margin:25px auto;background:white;padding:40px}h1,h2{color:black;line-height:1.3}h1{font-size:30px}h2{font-size:23px;margin-top:35px}pre{background:#f2f5f8;padding:18px;overflow:auto;font:14px/1.55 Consolas,monospace}table{width:100%;border-collapse:collapse}td,th{border:1px solid #d9d9d9;padding:9px;text-align:left}th{background:#e8eef5}figure{margin:20px 0}svg{width:100%;height:auto;max-height:950px}@media(max-width:700px){main{padding:20px;margin:0}}"
write("E3-brief-en.html",'<html lang="en"><head><meta charset="utf-8"><title>E3 Detailed Design Starter</title><style>'+css+'</style></head><body><main>'+"\n".join(body)+"</main></body></html>")
write("README.md","# E3 简版说明\n\n按本轮要求先做简版，后续扩充；不是最终完整提交稿。\n\n- E3-brief-en.html：可直接阅读的英文简版，包含6个模块的核心伪代码。\n- E3-brief-en.md：可编辑正文。\n- diagrams：库存分配流程图、采购取整N-S图，提供SVG与PNG。\n\n六个模块：M23 BOM校验、M30多层需求协调、M33库存分配、M34净生产展开、M43采购取整、M53交期风险。\n\n后续补充：M32需求合并、M42余量抵扣、M62原子保存；完整输入输出与异常；更多详细设计图；按人数核实数量；真实分工与评审记录。当前没有写应用程序或执行E4/E5测试。\n")
# Brief structural verification, not project test execution.
assert md.count("~~~text")==6
assert all(name in md for name in ("M23","M30","M33","M34","M43","M53"))
assert "balances = M31" in sections[1][2] and sections[1][2].index("balances =")<sections[1][2].index("FOR task")
assert len(list((out/"diagrams").glob("*.svg")))==2
write("verification.md","# E3 brief checks\n\nChecked that six E2 procedure identifiers have pseudocode and both detailed-design notation types have generated SVG/PNG figures. Reviewed priority-first ordering, one balance initialization per batch, net-only MAKE expansion and zero-gap purchase behavior against E1/E2. These are design checks, not program tests.\n\nVisual inspection: pending.\n")
plan=root/"物料需求与采购计划系统-任务计划-2026-09-24.md"
s=plan.read_text(encoding="utf-8")
if "## 11 E3简版进度" not in s:
 s+="\n## 11 E3简版进度 2026-09-26\n\n按用户要求先简略推进，完整细节后补。T13形成6个核心过程的伪代码草稿；T14仅覆盖当前核心路径；T15已有1张流程图和1张N-S图示例；T16完整评审与E3材料尚未完成。\n文件：specs/material-requirements-planning/e3/E3-brief-en.html。\n后续补充需求合并、采购余量、原子保存及异常路径，按真实人数核对数量。E3最终验收保持未勾选，尚未开始应用编码或E4/E5执行测试。\n"
plan.write_text(s,encoding="utf-8")
p=spec/"design.md"; s=p.read_text(encoding="utf-8")
s=s.replace("E3的伪代码、流程图/PAD/N-S详细设计，以及E4/E5程序测试均尚未开展。","E3已有简版：6个模块的核心伪代码、库存分配流程图和采购取整N-S图，见 e3/E3-brief-en.html；完整详细设计待补充。E4/E5程序测试尚未开展。")
p.write_text(s,encoding="utf-8")
print(json.dumps({"pseudocode_modules":6,"diagrams":2,"draft":str(out/"E3-brief-en.html")},ensure_ascii=False))
