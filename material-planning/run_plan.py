"""Run three examples, or a JSON file containing sources and request."""
from html import escape
from pathlib import Path
import json
import sys

from planner import calculate_plan
from sample_data import basic_case, priority_case, surplus_case


def table(headers, rows):
    head = "".join("<th>" + escape(str(v)) + "</th>" for v in headers)
    body = "".join("<tr>" + "".join("<td>" + escape("—" if v is None else str(v)) + "</td>" for v in row) + "</tr>" for row in rows)
    return '<div class="scroll"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>"


def render(plans):
    parts = []
    for label, outcome in plans.items():
        parts.append("<section><h2>" + escape(label) + "</h2>")
        if outcome["status"] == "INVALID":
            parts.append("<p>本批次未生成有效计划。</p>" + table(["错误", "位置", "说明"],
                [(e["code"], e["source_location"], e["message"]) for e in outcome["errors"]]))
            parts.append("</section>")
            continue
        result = outcome["result"]
        net = result["net_bundle"]
        context = net["context"]
        parts.append("<p>任务处理顺序：<strong>" + escape(" → ".join(context["ordered_task_ids"])) + "</strong>。库存基准日："
                     + escape(context["request"]["baseline_date"]) + "。数量单位：见物料资料，本演示均为件。</p>")
        parts.append("<details><summary>查看输入：任务、BOM 与库存</summary>")
        parts.append(table(["任务", "物料", "需求量", "交期", "优先级（1最高）"],
            [(t["task_id"], t["product_id"], t["required_qty"], t["due_date"], t["priority"]) for t in context["sources"]["tasks"]]))
        parts.append(table(["父项", "子项", "单件用量"], [(e["parent_id"], e["child_id"], e["qty_per"]) for e in context["sources"]["bom"]]))
        parts.append(table(["物料", "账面库存", "已占用"], [(s["material_id"], s["on_hand"], s["reserved"]) for s in context["sources"]["stocks"]]))
        parts.append("</details><h3>新增生产计划</h3>")
        parts.append(table(["任务", "物料", "毛需求", "抵扣库存", "新增生产", "开始日期", "需要日期"],
            [(r["task_id"], r["material_id"], r["gross_qty"], r["allocated_qty"], r["make_qty"], r["start_date"], r["needed_date"])
             for r in net["make_lines"]]))
        parts.append("<h3>采购计算明细</h3><p>采购量为 0 的行仅保留抵扣来源，不产生采购建议。</p>")
        parts.append(table(["物料", "需要日期", "库存后缺口", "使用早期余量", "剩余缺口", "采购量", "下单日期", "本期后余量"],
            [(r["material_id"], r["needed_date"], r["gross_shortage"], r["surplus_used"], r["remaining_gap"], r["purchase_qty"], r["order_date"], r["surplus_after"])
             for r in result["purchase_buckets"]]))
        parts.append("<details><summary>查看库存分配明细</summary>" + table(["任务", "物料", "需要日期", "分配前", "本次分配", "分配后"],
            [(r["task_id"], r["material_id"], r["needed_date"], r["before_qty"], r["allocated_qty"], r["after_qty"])
             for r in net["allocations"]]) + "</details>")
        if result["risks"]:
            parts.append("<h3>交期风险</h3>" + table(["任务", "物料", "原计算日期", "早于基准日天数"],
                [(r["task_id"], r["material_id"], r["computed_date"], r["days_before_baseline"]) for r in result["risks"]]))
        else:
            parts.append("<p>本示例无早于基准日的日期风险。</p>")
        parts.append("</section>")
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>物料需求与采购计划 · 计算原型演示</title><style>
body{font:16px/1.65 "Microsoft YaHei",sans-serif;background:#f3f6fa;color:#1d3045;margin:0}main{max-width:1150px;margin:auto;padding:32px 24px}
h1{font-size:28px;margin:8px 0}h2{font-size:22px}h3{font-size:18px;margin-bottom:10px}section{background:white;padding:24px;margin:24px 0;border:1px solid #d7e0eb;border-radius:12px}
p{color:#43556a}.tag{color:#17635b;font-size:14px;font-weight:bold}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0 20px}
th,td{padding:10px 12px;border-bottom:1px solid #dce4ed;text-align:left;white-space:nowrap}th{background:#eaf0f7}summary{cursor:pointer;color:#165d97;margin:14px 0}
footer{font-size:14px;color:#627287}@media(max-width:600px){main{padding:16px}section{padding:16px}h1{font-size:23px}}
</style><main><div class="tag">过程式计算原型 · v0.2</div><h1>物料需求与采购计划</h1>
<p>先按任务优先级分配库存，再按日期汇总采购。以下数据由本地程序实际计算生成；展开项可以查看输入和库存明细。</p>
''' + "".join(parts) + '''<footer>当前为计算演示：单仓库、整数数量、日历日提前期。计划不扣减实际库存，未验证产能和供应商能力。数据库、历史查询、CSV 和业务操作界面尚待实现。</footer></main></html>'''


def main():
    directory = Path(__file__).parent
    results = directory / "results"
    results.mkdir(exist_ok=True)
    if len(sys.argv) > 2:
        print("Usage: python run_plan.py [input.json]")
        return 2
    if len(sys.argv) == 2:
        try:
            payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
            plans = {"自定义输入": calculate_plan(payload.get("sources"), payload.get("request"))}
        except (OSError, ValueError, AttributeError) as exc:
            print("Cannot read input:", str(exc))
            return 2
        stem = "custom-plan"
    else:
        plans = {label: calculate_plan(*factory()) for label, factory in
                 (("1. 多层 BOM 与提前期", basic_case), ("2. 高优先级任务先分配库存", priority_case),
                  ("3. 采购凑整余量供后续日期使用", surplus_case))}
        sources, request = priority_case()
        (directory / "sample-input.json").write_text(json.dumps(dict(sources=sources, request=request), ensure_ascii=False, indent=2), encoding="utf-8")
        stem = "demo-plans"
    (results / (stem + ".json")).write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")
    (results / (stem + ".html")).write_text(render(plans), encoding="utf-8")
    print("Result:", results / (stem + ".html"))
    return 0 if all(p["status"] == "VALID" for p in plans.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
