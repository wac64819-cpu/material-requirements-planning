"""Independent expected-value checks plus M43 valid-domain execution traces."""
import ast
from copy import deepcopy
from datetime import datetime
import hashlib
import inspect
import json
from pathlib import Path
import platform
import sys
import core

RESULTS = []
TRACES = {}


def check(case_id, actual, expected):
    ok = actual == expected
    RESULTS.append({"case": case_id, "expected": expected, "actual": actual, "passed": ok})
    if not ok:
        raise AssertionError(f"{case_id}: {actual!r} != {expected!r}")


def rejects(case_id, operation):
    try:
        operation()
    except ValueError:
        check(case_id, "ValueError", "ValueError")
    else:
        check(case_id, "accepted", "ValueError")


def purchase(case_id, inputs, expected):
    lines = []
    def tracer(frame, event, arg):
        if frame.f_code is core.round_purchase_qty.__code__ and event == "line":
            lines.append(frame.f_lineno)
        return tracer
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        actual = core.round_purchase_qty(*inputs)
    finally:
        sys.settrace(previous)
    TRACES[case_id] = {"inputs": inputs, "line_sequence": lines, "actual": actual}
    check(case_id, actual, expected)


def sample(gross=10):
    return {
        "demand_id": "D1", "task_id": "T1", "material_id": "X",
        "needed_date": "2026-10-15", "gross_qty": gross,
        "origins": [{"origin_id": "O1", "task_id": "T1",
                     "parent_demand_id": None, "bom_path": ["A", "X"],
                     "contribution_qty": gross}],
    }


def main():
    for case_id, inputs, expected in [
        ("P00", (0, 100, 10), 0), ("P01", (620, 100, 100), 700),
        ("P02", (1, 100, 10), 100), ("P03", (100, 100, 10), 100),
        ("P04", (101, 100, 10), 110), ("P05", (23, 25, 10), 30),
        ("P06", (7, 0, 1), 7),
        ("P07", (9007199254740993, 0, 10), 9007199254741000),
    ]:
        purchase(case_id, inputs, expected)
    rejects("P08-negative-gap", lambda: core.round_purchase_qty(-1, 0, 1))
    rejects("P09-zero-multiple", lambda: core.round_purchase_qty(1, 0, 0))
    rejects("P10-decimal-gap", lambda: core.round_purchase_qty(1.5, 0, 1))
    rejects("P11-boolean-gap", lambda: core.round_purchase_qty(True, 0, 1))

    for stock, expected in [(0, (0, 10, 0)), (9, (9, 1, 0)),
                            (10, (10, 0, 0)), (11, (10, 0, 1))]:
        d = sample()
        b = {"request_id": "R1", "material_id": "X", "available_qty": stock}
        saved = deepcopy((d, b))
        r = core.allocate_stock(d, b)
        check(f"A{stock}-quantity",
              (r["netted_demand"]["allocated_qty"], r["netted_demand"]["net_qty"],
               r["new_balance"]["available_qty"]), expected)
        check(f"A{stock}-immutable", (d, b), saved)
    d = sample()
    d["origins"] = [
        {"origin_id": "O2", "task_id": "T1", "parent_demand_id": "P2",
         "bom_path": ["A", "Z", "X"], "contribution_qty": 6},
        {"origin_id": "O1", "task_id": "T1", "parent_demand_id": "P1",
         "bom_path": ["A", "B", "X"], "contribution_qty": 4},
    ]
    b = {"request_id": "R1", "material_id": "X", "available_qty": 5}
    r = core.allocate_stock(d, b)
    check("A-origin-attribution", r["netted_demand"]["source_allocations"], [
        {"origin_id": "O1", "allocated_qty": 4, "residual_qty": 0},
        {"origin_id": "O2", "allocated_qty": 1, "residual_qty": 5},
    ])
    d_reversed = deepcopy(d)
    d_reversed["origins"].reverse()
    other = core.allocate_stock(d_reversed, b)
    check("A-origin-row-order", other["ledger"], r["ledger"])
    # The caller must pass forward the returned working balance between tasks.
    high = sample(50); high["task_id"] = "HIGH"; high["demand_id"] = "H"; high["origins"][0]["task_id"] = "HIGH"
    low = sample(100); low["task_id"] = "LOW"; low["demand_id"] = "L"; low["origins"][0]["task_id"] = "LOW"
    stock = {"request_id": "R1", "material_id": "X", "available_qty": 20}
    rh = core.allocate_stock(high, stock)
    rl = core.allocate_stock(low, rh["new_balance"])
    check("A-shared-stock", (rh["netted_demand"]["allocated_qty"],
                             rl["netted_demand"]["allocated_qty"]), (20, 0))
    rejects("A-mismatched-material", lambda: core.allocate_stock(
        sample(), {"material_id": "Y", "available_qty": 20}))
    invalid = sample(); invalid["gross_qty"] = 11
    rejects("A-inconsistent-origins", lambda: core.allocate_stock(invalid, b))
    duplicate = deepcopy(d); duplicate["origins"][1]["origin_id"] = "O2"
    rejects("A-duplicate-origin", lambda: core.allocate_stock(duplicate, b))

    for label, needed, lead, expected in [
        ("D-normal", "2026-10-15", 5, "2026-10-10"),
        ("D-zero", "2026-10-10", 0, "2026-10-10"),
        ("D-year", "2027-01-03", 5, "2026-12-29"),
        ("D-leap", "2028-03-01", 2, "2028-02-28"),
    ]:
        check(label, core.subtract_calendar_days(needed, lead),
              {"status": "OK", "value": expected, "issues": []})
    check("D-range", core.subtract_calendar_days("0001-01-01", 1)["status"], "ERROR")
    rejects("D-invalid", lambda: core.subtract_calendar_days("2026-02-30", 0))
    rejects("D-format", lambda: core.subtract_calendar_days("20261010", 0))
    rejects("D-negative-lead", lambda: core.subtract_calendar_days("2026-10-10", -1))
    events = [{"event_id": "before", "date": "2026-10-09", "task_id": "T1"},
              {"event_id": "equal", "date": "2026-10-10"},
              {"event_id": "after", "date": "2026-10-11"}]
    original = deepcopy(events)
    risks = core.flag_early_dates(events, "2026-10-10")
    check("R-date-boundaries", [(x["source_location"], x["computed_date"],
                               x["days_before_baseline"]) for x in risks],
          [("before", "2026-10-09", 1)])
    check("R-input-immutable", events, original)
    check("R-empty", core.flag_early_dates([], "2026-10-10"), [])

    # Count source statements for M43, excluding its function header/docstring.
    source_path = Path(core.__file__)
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "round_purchase_qty")
    statement_lines = sorted({
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.stmt) and not isinstance(n, ast.FunctionDef)
        and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                 and isinstance(n.value.value, str))
    })
    actual_lines = sorted(set(TRACES["P00"]["line_sequence"] + TRACES["P01"]["line_sequence"]))
    check("W-M43-statements-P00-P01", actual_lines, statement_lines)
    result = {
        "executed_at": datetime.now().astimezone().isoformat(),
        "python_version": sys.version, "platform": platform.platform(),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "passed": sum(row["passed"] for row in RESULTS), "total": len(RESULTS),
        "checks": RESULTS, "M43_traces": TRACES,
        "M43_statement_lines": statement_lines,
        "scope": "Four implemented leaves; M43 normal paths under validated-input preconditions. Not full E4/E5.",
    }
    target = Path(__file__).parent / "results"
    target.mkdir(exist_ok=True)
    (target / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{result['passed']}/{result['total']} checks passed")
    print("M43 P00 trace:", TRACES["P00"]["line_sequence"])
    print("M43 P01 trace:", TRACES["P01"]["line_sequence"])


if __name__ == "__main__":
    main()
