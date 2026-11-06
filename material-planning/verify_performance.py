"""NFR06 measurements plus independent aggregate checks on fixed large inputs.

Core timings exclude fixture construction, checks, hashing and file I/O.
Adapter timings include calculation, SQLite commit and WSGI serialization,
but exclude network transport and browser rendering. Uses a temporary database.
"""
from collections import Counter, defaultdict, deque
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import argparse
import gc
import json
import os
from pathlib import Path
import platform
import sqlite3
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import csv_io
import storage
import web_server
from performance_data import CASES, build_case
from planner import calculate_plan


ROOT = Path(__file__).resolve().parent


def digest(value):
    return sha256(storage.encode(value).encode("utf-8")).hexdigest()


def graph_facts(payload):
    """Independent graph census: count reachable edges, depth and root paths."""
    sources = payload["sources"]
    children = defaultdict(list)
    incoming = {m["material_id"]: 0 for m in sources["materials"]}
    for edge in sources["bom"]:
        children[edge["parent_id"]].append(edge["child_id"])
        incoming[edge["child_id"]] += 1
    pending = deque(sorted(mid for mid, n in incoming.items() if n == 0))
    order, depth = [], dict.fromkeys(incoming, 0)
    while pending:
        mid = pending.popleft()
        order.append(mid)
        for child in children[mid]:
            depth[child] = max(depth[child], depth[mid] + 1)
            incoming[child] -= 1
            if incoming[child] == 0:
                pending.append(child)
    roots = {t["product_id"] for t in sources["tasks"]}
    reachable = set(roots)
    for mid in order:
        if mid in reachable:
            reachable.update(children[mid])
    paths = Counter(t["product_id"] for t in sources["tasks"])
    for mid in order:
        for child in children[mid]:
            paths[child] += paths[mid]
    return dict(materials=len(incoming), bom_edges=len(sources["bom"]), tasks=len(sources["tasks"]),
                selected_tasks=len(payload["request"]["selected_task_ids"]),
                all_materials_reachable=len(reachable) == len(incoming),
                acyclic=len(order) == len(incoming), depth_edges=max(depth.values()),
                potential_origin_rows_without_stock=sum(paths.values())), order


def zero_stock_totals(payload, order):
    """Quantity oracle using aggregate graph propagation, without planner leaves,
    dates, path expansion or stock-allocation implementation.
    """
    totals = Counter()
    by_parent = defaultdict(list)
    for edge in payload["sources"]["bom"]:
        by_parent[edge["parent_id"]].append(edge)
    for task in payload["sources"]["tasks"]:
        totals[task["product_id"]] += task["required_qty"]
    for parent in order:
        for edge in by_parent[parent]:
            totals[edge["child_id"]] += totals[parent] * edge["qty_per"]
    return dict(totals)


def check_result(payload, outcome, order, add):
    result = outcome["result"]
    bundle = result["net_bundle"]
    balances = {r["material_id"]: r["on_hand"] - r["reserved"] for r in payload["sources"]["stocks"]}
    ledger_valid = True
    for row in bundle["allocations"]:
        mid = row["material_id"]
        ledger_valid &= (row["before_qty"] == balances[mid]
                         and 0 <= row["allocated_qty"] <= row["before_qty"]
                         and row["after_qty"] == row["before_qty"] - row["allocated_qty"])
        balances[mid] = row["after_qty"]
    add("Every stock ledger balances and never double allocates", bool(ledger_valid), True)
    add("Final balances reconcile with every stock ledger",
        {mid: row["available_qty"] for mid, row in bundle["final_balances"].items()}, balances)
    add("Every demand equals allocated plus net and all origin contributions", all(
        row["demand"]["gross_qty"] == row["allocated_qty"] + row["net_qty"]
        == sum(o["contribution_qty"] for o in row["demand"]["origins"])
        for row in bundle["demands"]), True)
    add("All 100 tasks use priority before due date", bundle["context"]["ordered_task_ids"],
        [t["task_id"] for t in sorted(payload["sources"]["tasks"], key=lambda t: (t["priority"], t["due_date"], t["task_id"]))])
    shortage, purchased, surplus = Counter(), Counter(), Counter()
    for row in bundle["buy_shortages"]:
        shortage[row["material_id"]] += row["shortage_qty"]
    for row in result["purchase_buckets"]:
        purchased[row["material_id"]] += row["purchase_qty"]
    for row in result["final_surplus_lots"]:
        surplus[row["material_id"]] += row["remaining_qty"]
    add("Purchases reconcile with shortages and final surplus", dict(purchased), dict(shortage + surplus))
    add("Surplus never moves backwards in time", all(r["source_arrival_date"] <= r["use_date"] for r in result["surplus_uses"]), True)
    if all(r["on_hand"] == 0 for r in payload["sources"]["stocks"]):
        actual = Counter()
        for row in bundle["demands"]:
            actual[row["demand"]["material_id"]] += row["demand"]["gross_qty"]
        add("Zero stock totals match independent aggregate graph oracle", dict(actual), zero_stock_totals(payload, order))


def stats(samples):
    return dict(samples_seconds=samples, min_seconds=min(samples), median_seconds=median(samples), max_seconds=max(samples))


def benchmark(name, repeats):
    payload = build_case(name)
    before = digest(payload)
    checks = []
    def add(label, actual, expected):
        # Hashes keep large independent expectations reviewable without huge reports.
        row = dict(name=label, passed=actual == expected)
        if len(str(actual)) + len(str(expected)) > 1200:
            row.update(actual_sha256=digest(actual), expected_sha256=digest(expected))
        else:
            row.update(actual=actual, expected=expected)
        checks.append(row)
    facts, order = graph_facts(payload)
    add("Required scale", [facts[k] for k in ("materials", "bom_edges", "tasks", "selected_tasks")], [200, 500, 100, 100])
    add("Every material is reached; BOM is acyclic", [facts["all_materials_reachable"], facts["acyclic"]], [True, True])
    add("Longest path at selected fixture depth", facts["depth_edges"], 3 if name == "shared-stock" else 10)
    outcome = calculate_plan(payload["sources"], payload["request"])  # One unmeasured warm-up.
    add("Warm-up returns valid plan", outcome["status"], "VALID")
    if outcome["status"] != "VALID":
        raise RuntimeError(outcome["errors"])
    reference_hash = digest(outcome)
    check_result(payload, outcome, order, add)
    bundle = outcome["result"]["net_bundle"]
    counts = dict(demands=len(bundle["demands"]), origin_rows=sum(len(r["demand"]["origins"]) for r in bundle["demands"]),
                  allocations=len(bundle["allocations"]), **outcome["result"]["summary"])
    del outcome, bundle
    samples = []
    for i in range(repeats):
        gc.collect()  # Outside timed section; GC stays enabled during calculation.
        start = perf_counter()
        outcome = calculate_plan(payload["sources"], payload["request"])
        samples.append(perf_counter() - start)
        add(f"Timed result {i + 1} equals the warm-up", digest(outcome), reference_hash)
        del outcome
    add("Every measured core run completes within 10 seconds", max(samples) < 10.0, True)
    add("Calculation preserves input", digest(payload), before)
    shuffled = deepcopy(payload)
    for rows in shuffled["sources"].values():
        if isinstance(rows, list):
            rows.reverse()
    outcome = calculate_plan(shuffled["sources"], shuffled["request"])
    add("Reversed table rows produce identical complete output", digest(outcome), reference_hash)
    del outcome, shuffled
    adapter_samples, download_metrics = [], {}
    with TemporaryDirectory(prefix="mrp-performance-") as directory:
        database = Path(directory) / "performance.sqlite3"
        storage.initialize(database)
        previous_db = web_server.DATABASE
        web_server.DATABASE = database
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            for i in range(3):
                headers = []
                env = dict(HTTP_HOST="127.0.0.1:8769", SERVER_PORT="8769", PATH_INFO="/api/calculate",
                           REQUEST_METHOD="POST", CONTENT_TYPE="application/json", CONTENT_LENGTH=str(len(body)))
                env["wsgi.input"] = BytesIO(body)
                gc.collect()
                start = perf_counter()
                raw = b"".join(web_server.application(env, lambda status, values: headers.append((status, values))))
                adapter_samples.append(perf_counter() - start)
                record = json.loads(raw)
                add(f"Adapter call {i + 1} commits a complete batch", [headers[0][0], record.get("status"), bool(record.get("saved_batch"))], ["200 OK", "VALID", True])
                response_bytes = len(raw)
            start = perf_counter()
            saved = storage.get_batch(database, record["saved_batch"]["batch_id"])
            history_seconds = perf_counter() - start
            add("History exactly matches the saved result", saved["outcome"], {k: v for k, v in record.items() if k != "saved_batch"})
            add("Exactly three isolated history batches; workspace untouched",
                [len(storage.list_batches(database)["items"]), storage.load_workspace(database)["payload"]], [3, None])
            for kind in ("MAKE", "PURCHASE", "ALLOCATION", "TRACE", "RISK"):
                start = perf_counter()
                exported = csv_io.export_batch(saved, kind)
                download_metrics[kind] = dict(seconds=perf_counter() - start, bytes=len(exported))
            database_bytes = database.stat().st_size
        finally:
            web_server.DATABASE = previous_db
    folder = ROOT / "results"
    folder.mkdir(exist_ok=True)
    input_path = folder / ("performance-" + name + ".json")
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with ZipFile(folder / ("performance-" + name + "-csv.zip"), "w", ZIP_DEFLATED) as archive:
        for table, columns in csv_io.COLUMNS.items():
            rows = [[row.get(key, "") for key in columns] for row in payload["sources"][table]]
            archive.writestr(table + ".csv", csv_io.encode_csv(columns, rows))
    return dict(case=name, input_sha256=before, input_file=input_path.name, facts=facts,
                output_counts=counts, core=stats(samples), adapter=stats(adapter_samples),
                response_bytes=response_bytes, database_bytes_for_3_batches=database_bytes,
                history_read_seconds=history_seconds, csv_exports=download_metrics,
                passed=sum(c["passed"] for c in checks), total=len(checks), checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not 3 <= args.repeats <= 20:
        parser.error("--repeats must be 3 to 20")
    cpu = platform.processor()
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    report = dict(executed_at=datetime.now().astimezone().isoformat(),
                  environment=dict(python=platform.python_version(), os=platform.platform(), cpu=cpu,
                                   logical_cpus=os.cpu_count(), sqlite=sqlite3.sqlite_version),
                  method=dict(warmups_per_case=1, measured_core_runs=args.repeats, adapter_runs=3,
                              core_target_seconds=10, gc_enabled=gc.isenabled(),
                              depth_definition="Longest root-to-leaf path, counted in BOM edges",
                              core_scope="calculate_plan including validation and complete trace results; excludes I/O and checking",
                              adapter_scope="WSGI call including JSON parsing, calculate, SQLite commit and response JSON; excludes network/browser",
                              limitations="Two fixed DAG topologies on this machine; not a worst-case guarantee, load test or browser timing"),
                  source_sha256={name: sha256((ROOT / name).read_bytes()).hexdigest() for name in
                                 ("performance_data.py", "verify_performance.py", "core.py", "planner.py", "storage.py", "web_server.py", "csv_io.py")}, cases=[])
    for name in CASES:
        result = benchmark(name, args.repeats)
        report["cases"].append(result)
        print(f"{name}: core median={result['core']['median_seconds']:.3f}s, max={result['core']['max_seconds']:.3f}s; {result['passed']}/{result['total']} checks", flush=True)
    report.update(passed=sum(c["passed"] for c in report["cases"]), total=sum(c["total"] for c in report["cases"]))
    output = ROOT / "results" / "performance-verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Total: {report['passed']}/{report['total']} checks passed; {output.name}", flush=True)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
