"""Executed scenario evidence; not a claim of full E4/E5 coverage."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import hashlib
import json
import platform
import random
import sys

from planner import calculate_plan
from sample_data import basic_case, priority_case, surplus_case, dataset, material, task


def main():
    checks = []

    def check(name, actual, expected):
        checks.append(dict(name=name, expected=expected, actual=actual, passed=actual == expected))

    def valid(name, sources, request):
        saved = deepcopy((sources, request))
        outcome = calculate_plan(sources, request)
        check(name + ": valid", outcome["status"], "VALID")
        check(name + ": input immutable", (sources, request) == saved, True)
        return outcome["result"]

    def purchases(result):
        return [(b["material_id"], b["needed_date"], b["purchase_qty"], b["order_date"])
                for b in result["purchase_buckets"]]

    def reject(name, sources, request, code):
        saved = deepcopy((sources, request))
        outcome = calculate_plan(sources, request)
        check(name, [outcome["status"], outcome["result"], code in [e["code"] for e in outcome["errors"]],
                    bool(outcome["errors"]) and all(e["source_location"] for e in outcome["errors"]),
                    (sources, request) == saved], ["INVALID", None, True, True, True])

    sources, request = basic_case()
    base = valid("CASE01", sources, request)
    check("CASE01 MAKE quantities", [(r["material_id"], r["make_qty"]) for r in base["net_bundle"]["make_lines"]],
          [("A", 100), ("B", 180)])
    check("CASE02 BUY quantities/dates", purchases(base),
          [("C", "2026-10-18", 250, "2026-10-14"), ("D", "2026-10-15", 620, "2026-10-10")])
    check("CASE02 MAKE dates", [(r["material_id"], r["needed_date"], r["start_date"])
                                for r in base["net_bundle"]["make_lines"]],
          [("A", "2026-10-20", "2026-10-18"), ("B", "2026-10-18", "2026-10-15")])
    sources["materials"][3].update(min_purchase_qty=100, purchase_multiple=100)
    rounded = valid("CASE03", sources, request)
    check("CASE03 D rounding", purchases(rounded)[1], ("D", "2026-10-15", 700, "2026-10-10"))
    check("CASE03 final excess", [r["remaining_qty"] for r in rounded["final_surplus_lots"]], [80])

    sources, request = priority_case()
    priority = valid("CASE04", sources, request)
    check("CASE04 priority before due date", priority["net_bundle"]["context"]["ordered_task_ids"], ["HIGH", "LOW"])
    check("CASE04 stock attribution", [(r["task_id"], r["material_id"], r["allocated_qty"])
          for r in priority["net_bundle"]["allocations"] if r["allocated_qty"]],
          [("HIGH", "B", 20), ("HIGH", "C", 50), ("HIGH", "D", 100)])
    check("CASE04 B manufacture", [(r["task_id"], r["make_qty"]) for r in priority["net_bundle"]["make_lines"]
          if r["material_id"] == "B"], [("HIGH", 80), ("LOW", 200)])
    check("CASE04 dated purchasing", purchases(priority),
          [("C", "2026-10-18", 300, "2026-10-14"), ("C", "2026-10-19", 100, "2026-10-15"),
           ("D", "2026-10-15", 800, "2026-10-10"), ("D", "2026-10-16", 220, "2026-10-11")])
    rng = random.Random(260926)
    for i in range(8):
        shuffled, selection = deepcopy(sources), deepcopy(request)
        for table in ("materials", "bom", "stocks", "tasks"):
            rng.shuffle(shuffled[table])
        rng.shuffle(selection["selected_task_ids"])
        check(f"CASE10 row permutation {i+1}", calculate_plan(shuffled, selection)["result"] == priority, True)
    check("CASE10 new run resets balances", calculate_plan(sources, request)["result"] == priority, True)
    request["selected_task_ids"] = ["LOW"]
    only_low = valid("unselected task", sources, request)
    check("unselected HIGH consumes no stock", [r["task_id"] for r in only_low["net_bundle"]["allocations"]
          if r["allocated_qty"]], ["LOW", "LOW", "LOW"])

    sources, request = surplus_case()
    surplus = valid("CASE05", sources, request)
    check("CASE05 dated excess", purchases(surplus),
          [("X", "2026-10-10", 30, "2026-10-08"), ("X", "2026-10-11", 0, None)])
    check("CASE05 trace and final excess", [[u["qty"], u["source_arrival_date"], u["use_date"]]
          for u in surplus["surplus_uses"]], [[7, "2026-10-10", "2026-10-11"]])
    check("CASE05 no excess remains", surplus["final_surplus_lots"], [])
    sources["tasks"][0]["required_qty"] = 12
    sources["tasks"][1].update(required_qty=11, due_date="2026-10-10")
    merged = valid("same day merge", sources, request)
    check("same day rounds once", purchases(merged), [("X", "2026-10-10", 30, "2026-10-08")])
    sources, request = surplus_case()
    sources["tasks"][1]["due_date"] = "2026-10-09"
    chronological = valid("no backward excess", sources, request)
    check("early bucket buys before later supply", purchases(chronological),
          [("X", "2026-10-09", 10, "2026-10-07"), ("X", "2026-10-10", 20, "2026-10-08")])
    check("excess flow direction", [[u["qty"], u["source_arrival_date"], u["use_date"]]
          for u in chronological["surplus_uses"]], [[3, "2026-10-09", "2026-10-10"]])

    for stock, expected in ((0, 10), (9, 1), (10, 0), (11, 0)):
        sources, request = dataset([material("X")], [], [task("T", "X", 10)], {"X": stock})
        result = calculate_plan(sources, request)["result"]
        check(f"CASE06 stock {stock}", sum(r["purchase_qty"] for r in result["purchase_buckets"]), expected)
    sources["stocks"][0].update(on_hand=12, reserved=3)
    check("CASE06 reserved unavailable", calculate_plan(sources, request)["result"]["purchase_buckets"][0]["purchase_qty"], 1)
    sources, request = basic_case()
    sources["stocks"][0]["on_hand"] = 10
    finished = valid("CASE07 finished stock", sources, request)
    check("finished stock only net explodes", [(r["material_id"], r["make_qty"])
          for r in finished["net_bundle"]["make_lines"]], [("A", 90), ("B", 160)])
    check("finished stock reduces purchases", [r["purchase_qty"] for r in finished["purchase_buckets"]], [220, 540])
    sources["stocks"][0]["on_hand"] = 100
    covered = valid("fully covered root", sources, request)
    check("zero net no lower demands", [len(covered["net_bundle"]["demands"]), covered["net_bundle"]["make_lines"],
          covered["purchase_buckets"]], [1, [], []])

    sources, request = dataset([material("A", "MAKE"), material("B", "MAKE"), material("E", "MAKE"), material("D")],
        [("A", "B", 1), ("A", "E", 1), ("B", "D", 2), ("E", "D", 3)], [task("T", "A", 10)])
    shared = valid("CASE07 shared paths", sources, request)
    demand_d = next(r["demand"] for r in shared["net_bundle"]["demands"] if r["demand"]["material_id"] == "D")
    check("shared paths merge with trace", [demand_d["gross_qty"], [o["contribution_qty"] for o in demand_d["origins"]]], [50, [20, 30]])
    sources, request = dataset([material("A", "MAKE"), material("B", "MAKE"), material("E", "MAKE"),
        material("F", "MAKE"), material("X")],
        [("A", "B", 1), ("A", "E", 1), ("B", "F", 2), ("E", "F", 3), ("F", "X", 2)],
        [task("T", "A", 10)], {"F": 25})
    residual = valid("shared MAKE source residual", sources, request)
    x = next(n["demand"] for n in residual["net_bundle"]["demands"] if n["demand"]["material_id"] == "X")
    check("only residual origin explodes", [x["gross_qty"], [o["bom_path"] for o in x["origins"]]],
          [50, [["A", "E", "F", "X"]]])
    # A direct path needs X later; the longer path needs X earlier. DFS can get this wrong.
    sources, request = dataset([material("A", "MAKE"), material("Z", "MAKE", 5), material("X")],
        [("A", "X", 1), ("A", "Z", 1), ("Z", "X", 1)], [task("T", "A", 10)], {"X": 10})
    earlier = valid("CASE11 shared child earlier date", sources, request)
    check("all parents before child allocation", [(r["needed_date"], r["allocated_qty"])
          for r in earlier["net_bundle"]["allocations"] if r["material_id"] == "X"],
          [("2026-10-15", 10), ("2026-10-20", 0)])
    check("later demand keeps shortage", purchases(earlier), [("X", "2026-10-20", 10, "2026-10-20")])
    sources, request = dataset([material("X")], [],
        [task("Z", "X", 1), task("B", "X", 1, "2026-10-19"), task("A", "X", 1)], {"X": 1})
    ties = valid("CASE11 ties", sources, request)
    check("tie dates then ordinal IDs", ties["net_bundle"]["context"]["ordered_task_ids"], ["B", "A", "Z"])

    sources, request = dataset([material("X", lead=2)], [], [task("T", "X", 1, "2026-10-02")])
    risk = valid("CASE08 risk", sources, request)
    check("risk retains actual early date", [[r["computed_date"], r["days_before_baseline"]] for r in risk["risks"]], [["2026-09-30", 1]])
    sources["tasks"][0]["due_date"] = "2026-10-03"
    check("baseline equality allowed", calculate_plan(sources, request)["result"]["risks"], [])
    sources["stocks"][0]["on_hand"] = 1
    sources["tasks"][0]["due_date"] = "2026-09-30"
    check("covered overdue task still risk", [r["days_before_baseline"] for r in calculate_plan(sources, request)["result"]["risks"]], [1])

    mutations = [
        ("self cycle", "BOM_CYCLE", lambda s, r: s["bom"].append(dict(parent_id="A", child_id="A", qty_per=1))),
        ("long cycle", "BOM_CYCLE", lambda s, r: s["bom"].append(dict(parent_id="B", child_id="A", qty_per=1))),
        ("unknown material", "UNKNOWN_MATERIAL", lambda s, r: s["bom"][0].update(child_id="MISSING")),
        ("duplicate edge", "DUPLICATE_EDGE", lambda s, r: s["bom"].append(deepcopy(s["bom"][0]))),
        ("zero usage", "INTEGER", lambda s, r: s["bom"][0].update(qty_per=0)),
        ("negative usage", "INTEGER", lambda s, r: s["bom"][0].update(qty_per=-1)),
        ("decimal quantity", "INTEGER", lambda s, r: s["tasks"][0].update(required_qty=1.5)),
        ("bool quantity", "INTEGER", lambda s, r: s["tasks"][0].update(required_qty=True)),
        ("MAKE without BOM", "MISSING_BOM", lambda s, r: s["bom"].pop()),
        ("BUY children", "BUY_HAS_CHILDREN", lambda s, r: s["bom"].append(dict(parent_id="C", child_id="D", qty_per=1))),
        ("zero multiple", "INTEGER", lambda s, r: s["materials"][2].update(purchase_multiple=0)),
        ("negative lead", "INTEGER", lambda s, r: s["materials"][0].update(lead_time_days=-1)),
        ("invalid priority", "PRIORITY", lambda s, r: s["tasks"][0].update(priority=4)),
        ("duplicate task", "DUPLICATE_ID", lambda s, r: s["tasks"].append(deepcopy(s["tasks"][0]))),
        ("missing stock", "MISSING_STOCK", lambda s, r: s["stocks"].pop()),
        ("over reserved", "RESERVED_EXCEEDS_STOCK", lambda s, r: s["stocks"][0].update(reserved=1)),
        ("snapshot mismatch", "SNAPSHOT_DATE", lambda s, r: s["stocks"][0].update(snapshot_date="2026-10-02")),
        ("invalid date", "DATE", lambda s, r: s["tasks"][0].update(due_date="2026-02-30")),
        ("noncanonical date", "DATE", lambda s, r: s["tasks"][0].update(due_date="20261020")),
        ("unknown task", "UNKNOWN_TASK", lambda s, r: r.update(selected_task_ids=["MISSING"])),
        ("no tasks", "SELECTION", lambda s, r: r.update(selected_task_ids=[])),
        ("duplicate selection", "DUPLICATE_SELECTION", lambda s, r: r.update(selected_task_ids=["T001", " T001 "])),
        ("bad rules", "RULE_VERSION", lambda s, r: r.update(rule_version="unknown")),
        ("missing field", "REQUIRED_TEXT", lambda s, r: s["materials"][0].pop("name")),
        ("bad row shape", "SCHEMA", lambda s, r: s["materials"].append(None)),
    ]
    for name, code, change in mutations:
        sources, request = basic_case()
        change(sources, request)
        reject("CASE09 " + name, sources, request, code)
    sources, request = basic_case()
    sources["stocks"][0]["on_hand"] = 100
    sources["bom"] = []
    reject("stock does not bypass BOM validation", sources, request, "MISSING_BOM")
    for kind in ("MAKE", "BUY"):
        sources, request = basic_case()
        sources["tasks"][0]["due_date"] = "0001-01-01"
        if kind == "BUY":
            sources, request = dataset([material("X", lead=1)], [], [task("T", "X", 1, "0001-01-01")])
        reject(kind + " date overflow", sources, request, "DATE_RANGE")
    reject("bad input container", [], {}, "SCHEMA")
    sources, request = basic_case()
    for row in sources["materials"]:
        row["material_id"] = " " + row["material_id"] + " "
    check("trim IDs before reference resolution", calculate_plan(sources, request)["result"] == base, True)

    # Cross-record conservation and trace closure over three distinct scenarios.
    for name, result in (("priority", priority), ("surplus", surplus), ("shared", shared)):
        bundle = result["net_bundle"]
        demands = {n["demand"]["demand_id"]: n for n in bundle["demands"]}
        shortages = {s["shortage_id"] for s in bundle["buy_shortages"]}
        bucket_ids = {b["bucket_id"] for b in result["purchase_buckets"]}
        conservation = all(n["demand"]["gross_qty"] == n["allocated_qty"] + n["net_qty"]
            and sum(a["allocated_qty"] for a in n["source_allocations"]) == n["allocated_qty"]
            and sum(a["residual_qty"] for a in n["source_allocations"]) == n["net_qty"] for n in demands.values())
        check(name + " demand conservation", conservation, True)
        check(name + " stock conservation", all(b["available_qty"] == bundle["final_balances"][mid]["available_qty"]
            + sum(a["allocated_qty"] for a in bundle["allocations"] if a["material_id"] == mid)
            for mid, b in bundle["context"]["initial_balances"].items()), True)
        check(name + " parent trace closure", all(o["parent_demand_id"] is None or o["parent_demand_id"] in demands
            for n in demands.values() for o in n["demand"]["origins"]), True)
        check(name + " purchase trace closure", all(sid in shortages for b in result["purchase_buckets"] for sid in b["shortage_ids"])
            and all(u["supply_bucket_id"] in bucket_ids and u["demand_bucket_id"] in bucket_ids for u in result["surplus_uses"]), True)
        mids = {b["material_id"] for b in result["purchase_buckets"]}
        check(name + " purchase conservation by material", all(
            sum(b["purchase_qty"] - b["gross_shortage"] for b in result["purchase_buckets"] if b["material_id"] == mid)
            == sum(lot["remaining_qty"] for lot in result["final_surplus_lots"] if lot["material_id"] == mid) for mid in mids), True)

    directory = Path(__file__).parent
    report = dict(executed_at=datetime.now().astimezone().isoformat(), python_version=sys.version,
        platform=platform.platform(), passed=sum(c["passed"] for c in checks), total=len(checks),
        source_sha256={name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                       for name in ("core.py", "planner.py", "sample_data.py", "verify_planner.py")}, checks=checks,
        scope="Calculation integration/regression only; not full E4/E5, persistence, UI or performance acceptance.")
    (directory / "results").mkdir(exist_ok=True)
    (directory / "results" / "planner-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['passed']}/{report['total']} checks passed")
    for row in checks:
        if not row["passed"]:
            print(json.dumps(row, ensure_ascii=False))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
