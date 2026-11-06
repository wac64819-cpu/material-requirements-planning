from pathlib import Path
import json, html, re
root=Path(r"C:\Users\许yq\Desktop\软件工程")
spec=root/"specs"/"material-requirements-planning"
out=spec/"e4"; out.mkdir(exist_ok=True)
r=json.loads((root/"material-planning"/"results"/"verification.json").read_text(encoding="utf-8"))
assert r["passed"]==r["total"]
lines=r["M43_statement_lines"]; p0=r["M43_traces"]["P00"]; p1=r["M43_traces"]["P01"]
md=f"""# E4 White Box Testing Starter

Version 0.1. Short initial implementation and test record.

## Implemented scope

Four procedural functions are now executable in material-planning/core.py: M33 allocate_stock, M43 round_purchase_qty, M52 subtract_calendar_days and M53 flag_early_dates. They use the Python standard library and plain records. Python remains the provisional implementation language.

This starter contains a white-box analysis of M43 under its validated-input preconditions. The other implemented functions have regression checks, not complete five-criterion white-box coverage. Full BOM expansion, task orchestration, planned-surplus purchasing, storage and the user interface are not implemented. The demo uses prepared component requirements; it is not a complete CASE01 or CASE04 run.

## Actual execution evidence

Executed at: {r["executed_at"]}

Python: {r["python_version"].splitlines()[0]}

Platform: {r["platform"]}

core.py SHA256: {r["source_sha256"]}

Actual result: {r["passed"]}/{r["total"]} checks passed. Inputs, independent expected values, actual values and individual pass results are retained in material-planning/results/verification.json. The separate demo displays HIGH receiving 20 existing B, LOW receiving 0, a D recommendation of 700 for gap 620 with multiple 100, and a one-day early-date risk.

The check count is not a coverage percentage. It includes quantity checks, unchanged-input checks, invalid-input rejection, date behavior and one trace-based statement check.

## Selected module M43

Purpose: calculate a purchase quantity after eligible planned surplus has already been deducted.

Preconditions: remaining_gap and minimum_qty are nonnegative integers; purchase_multiple is a positive integer. Booleans and decimals are rejected. Input validation helpers are outside the selected M43 white-box boundary.

Postconditions: gap zero gives quantity zero. Otherwise quantity is at least both gap and minimum and is a multiple of purchase_multiple. Integer arithmetic avoids floating-point rounding.

~~~text
validate the three integer preconditions
IF remaining_gap == 0:
    RETURN 0
target = MAX(remaining_gap, minimum_qty)
lot_count = (target + purchase_multiple - 1) DIV purchase_multiple
RETURN lot_count * purchase_multiple
~~~

The only explicit decision in this function body is D1: remaining_gap == 0. The only atomic condition is C1, identical to D1. MAX is a library operation, not an additional explicit branch in this submitted procedure.

## Minimal valid domain coverage set

| Case | Gap | Minimum | Multiple | Expected | Actual | C1 |
|---|---|---|---|---|---|---|
| P00 | 0 | 100 | 10 | 0 | {p0["actual"]} | True |
| P01 | 620 | 100 | 100 | 700 | {p1["actual"]} | False |

P00 executes source lines {", ".join(map(str,p0["line_sequence"]))}.

P01 executes source lines {", ".join(map(str,p1["line_sequence"]))}.

These line sequences were recorded during real calls using a Python execution trace, not inferred from expected results.

## Five coverage criteria for the selected scope

| Criterion | Evidence from P00 and P01 | Scope limitation |
|---|---|---|
| Statement coverage | The union executes all {len(lines)} executable statement lines identified in M43: {", ".join(map(str,lines))}. The verification script checks exact set equality. | Excludes function declaration/docstring and called helper internals. |
| Branch coverage | P00 takes D1 True; P01 takes D1 False. Both branches are observed in the traces. | Explicit M43 decision under valid inputs. |
| Condition coverage | C1 is True in P00 and False in P01. | There is only one atomic condition in this module. |
| Condition combination coverage | The complete combination set for one condition is True and False; both are covered. | No artificial multi-condition claim is made. |
| Path coverage | P00 follows validate, D1 True, return zero; P01 follows validate, D1 False, compute and return. These are both feasible normal paths. | No loops in M43. Exceptions for violated preconditions and library internals are outside these two normal paths. |

Two cases are minimal for these five criteria on this valid-domain body: one case cannot make the same decision both True and False in a single invocation. Additional cases below improve boundary checks but are not needed to add a third normal M43 control path.

## Additional checks actually executed

Purchase cases include a minimum larger than the gap, exact minimum, one above minimum, a minimum not divisible by the multiple, unit multiple, and an integer larger than the exact IEEE-754 integer range. Invalid cases include negative gap, zero multiple, decimal gap and Boolean input.

Inventory checks cover zero stock, one short, exact stock, excess stock, source attribution across two BOM paths, reversed source row order, shared working balance across two calls, material mismatch and inconsistent origins. Date checks cover zero lead time, year crossing, leap-year crossing, range overflow, invalid date, invalid format and negative lead. Risk checks cover before, equal to and after baseline, empty events and unchanged input records.

These regression checks do not prove the entire application correct or fulfill E5 system testing.

## Error behavior at the current stage

A leaf precondition violation raises ValueError. This is a developer contract check at the current stage; the future M22 input layer must turn invalid user records into located issues before calling these leaves. M52 returns a structured DATE_RANGE error when a valid date and lead time imply an unrepresentable computed date. No leaf writes stock or a database.

## Remaining E4 work

1. Confirm group size N and select at least N suitable modules for the final experiment. One fully analyzed starter module does not establish the required count.
2. Add five-criterion analysis for further implemented modules. Loops in allocation and risk functions have unbounded iteration counts; define a justified path scope and identify infeasible paths rather than claiming exhaustive coverage.
3. Complete the remaining planner modules and retain any newly discovered defects and fixes.
4. Record actual member assignments, a real all-member review and individual contributions.
5. Confirm final course formatting, naming and submission requirements.

No full E4 completion, E5 completion or FTP submission is claimed.
"""
(out/"E4-brief-en.md").write_text(md,encoding="utf-8")
body=[]; ls=md.splitlines(); i=0
while i<len(ls):
 t=ls[i]
 if not t.strip(): i+=1; continue
 if t.startswith("#"):
  n=len(t)-len(t.lstrip("#")); body.append(f"<h{n}>"+html.escape(t[n:].strip())+f"</h{n}>");i+=1;continue
 if t.startswith("~~~"):
  i+=1; text=[]
  while i<len(ls) and not ls[i].startswith("~~~"):text.append(ls[i]);i+=1
  body.append("<pre>"+html.escape("\n".join(text))+"</pre>");i+=1;continue
 if t.startswith("|"):
  rows=[]
  while i<len(ls) and ls[i].startswith("|"):
   cells=[v.strip() for v in ls[i].strip("|").split("|")]
   if not all(re.fullmatch("[-: ]+",v) for v in cells):rows.append(cells)
   i+=1
  body.append("<table><tr>"+"".join("<th>"+html.escape(v)+"</th>" for v in rows[0])+"</tr>")
  for row in rows[1:]:body.append("<tr>"+"".join("<td>"+html.escape(v)+"</td>" for v in row)+"</tr>")
  body.append("</table>");continue
 body.append("<p>"+html.escape(t)+"</p>");i+=1
css="body{background:#f4f6f8;font:16px/1.65 Arial,sans-serif;color:#17212e;margin:0}main{max-width:1050px;margin:28px auto;background:white;padding:42px}h1,h2{color:black;line-height:1.3}h2{margin-top:34px;font-size:23px}p{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #d9d9d9;padding:10px;text-align:left;vertical-align:top}th{background:#e8eef5}pre{background:#f2f5f8;padding:18px;overflow:auto;font:14px/1.6 Consolas,monospace}@media(max-width:700px){main{padding:20px;margin:0}}"
(out/"E4-brief-en.html").write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>E4 White Box Testing Starter</title><style>'+css+'</style></head><body><main>'+"\n".join(body)+"</main></body></html>",encoding="utf-8")
(out/"README.md").write_text("# E4 简版与最小核心\n\n先打开 E4-brief-en.html。当前已实现M33、M43、M52、M53四个函数，实际验证38/38通过；完整证据在项目根目录 material-planning/results/verification.json。\n\n五种白盒覆盖仅对M43合法输入域给出分析与真实行轨迹。其余函数当前只有回归检查，未声称完成五种覆盖。调用前置条件被违反时的辅助校验路径也不计入这次M43覆盖范围。\n\n尚未实现完整BOM展开、任务协调、采购余量、数据库和界面；未完成E4人数要求、真实评审或E5。后续需补齐这些内容。\n",encoding="utf-8")
p=root/"物料需求与采购计划系统-任务计划-2026-09-24.md"
s=p.read_text(encoding="utf-8")
s=s.replace("计划状态：E1与E2设计及英文报告草稿已形成；复选框表示最终核实与评审状态，未将草稿产出等同于课程实验最终完成。","计划状态：E1/E2草稿、E3简版已形成；最小核心4个函数已实现并验证，E4仅有局部白盒证据。复选框表示最终验收状态，未将局部成果等同于完整系统或实验完成。")
if "## 12 最小核心与E4起步" not in s:
 s+=f"""\n## 12 最小核心与E4起步 2026-09-26

- 已新增 material-planning/core.py：M33库存分配、M43采购取整、M52日历日期、M53交期风险；暂用Python标准库，过程式实现。
- verify_core.py实际运行{r["passed"]}/{r["total"]}检查通过；保存独立预期、实际结果、执行环境、源码哈希和M43行轨迹。
- run_demo.py提供已展开组件需求的演示；不能将它等同于完整M30、完整CASE01或CASE04。
- E4简版：specs/material-requirements-planning/e4/E4-brief-en.html。仅M43合法输入域具备五种覆盖分析与真实执行证据，辅助输入校验和其他模块的完整覆盖仍待补充。
- T17—T25仅部分起步，数据库、BOM展开、任务协调、采购余量、界面等未完成；T26—T28也未满足完整人数和评审要求，复选框保持未勾选。
"""
p.write_text(s,encoding="utf-8")
p=spec/"design.md"; s=p.read_text(encoding="utf-8")
s=s.replace("E4/E5程序测试尚未开展。","已开始最小核心实现及E4局部验证：M33/M43/M52/M53四个函数、38项检查、M43合法输入域五种覆盖分析。完整E4及E5仍未完成。")
s+="\n\n2026-09-26新增：[E4简版](e4/E4-brief-en.html)；程序与运行说明位于项目根目录 material-planning。Python为本次最小原型采用的暂定方案，尚未锁定完整系统技术方案。\n"
p.write_text(s,encoding="utf-8")
print(f"E4 starter report saved; actual evidence: {r['passed']}/{r['total']}.")
