"""In-memory procedural MRP prototype. No classes, I/O or stock posting.

The public boundary returns VALID/INVALID. E2 repository and persistence
adapters are intentionally not implemented in this calculation prototype.
"""
from collections import defaultdict
from copy import deepcopy
import heapq
import json

from core import (_date, _integer, allocate_stock, round_purchase_qty,
                  subtract_calendar_days, flag_early_dates)

RULE_VERSION = "prototype-v0.2"


def record_id(*parts):
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def issue(code, location, message, task_id=None, material_id=None):
    return dict(code=code, severity="BLOCKING", source_location=location,
                message=message, task_id=task_id, material_id=material_id,
                computed_date=None, days_before_baseline=None)


def validate_and_prepare(sources, request):
    """M22-M25 prototype: normalize a copy, validate, index and order tasks.

    Schema/reference checks cover all supplied rows; MAKE structure, missing
    stock and cycle checks cover the full graph reachable from selected tasks.
    Row locations are zero-based. A stock-covered MAKE still needs valid BOM.
    """
    errors = []
    if not isinstance(sources, dict) or not isinstance(request, dict):
        return None, [issue("SCHEMA", "input", "Sources and request must be records.")]
    sources, request = deepcopy(sources), deepcopy(request)

    def text_field(row, field, loc):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(issue("REQUIRED_TEXT", loc + "." + field, "Nonempty text required."))
            return None
        row[field] = value.strip()
        return row[field]

    def number_field(row, field, loc, minimum=0):
        try:
            _integer(row.get(field), field, minimum)
        except ValueError as exc:
            errors.append(issue("INTEGER", loc + "." + field, str(exc)))

    def date_field(row, field, loc):
        try:
            _date(row.get(field))
        except ValueError as exc:
            errors.append(issue("DATE", loc + "." + field, str(exc)))

    text_field(sources, "source_revision", "sources")
    text_field(request, "request_id", "request")
    date_field(request, "baseline_date", "request")
    if request.get("rule_version") != RULE_VERSION:
        errors.append(issue("RULE_VERSION", "request.rule_version", "Unsupported calculation rules."))
    selected = request.get("selected_task_ids")
    if (not isinstance(selected, list) or not selected
            or any(not isinstance(v, str) or not v.strip() for v in selected)):
        errors.append(issue("SELECTION", "request.selected_task_ids", "Select at least one task ID."))
        selected = []
    else:
        selected = [v.strip() for v in selected]
        if len(set(selected)) != len(selected):
            errors.append(issue("DUPLICATE_SELECTION", "request.selected_task_ids", "Repeated task ID."))
    request["selected_task_ids"] = sorted(set(selected))
    indexes = {}
    for table, key in (("materials", "material_id"), ("tasks", "task_id"),
                       ("stocks", "material_id"), ("bom", None)):
        rows = sources.get(table)
        index = {}
        indexes[table] = index
        if not isinstance(rows, list):
            errors.append(issue("SCHEMA", table, "A list of records is required."))
            continue
        for i, row in enumerate(rows):
            loc = f"{table}[{i}]"
            if not isinstance(row, dict):
                errors.append(issue("SCHEMA", loc, "A record is required."))
                continue
            if key:
                identifier = text_field(row, key, loc)
                if identifier in index:
                    errors.append(issue("DUPLICATE_ID", loc + "." + key, "Duplicate identifier."))
                if identifier is not None:
                    index[identifier] = row
            if table == "materials":
                text_field(row, "name", loc)
                text_field(row, "unit", loc)
                if row.get("supply_type") not in ("MAKE", "BUY"):
                    errors.append(issue("SUPPLY_TYPE", loc, "Supply type must be MAKE or BUY."))
                number_field(row, "lead_time_days", loc)
                if row.get("supply_type") == "BUY":
                    row.setdefault("min_purchase_qty", 0)
                    row.setdefault("purchase_multiple", 1)
                    number_field(row, "min_purchase_qty", loc)
                    number_field(row, "purchase_multiple", loc, 1)
            elif table == "tasks":
                text_field(row, "product_id", loc)
                number_field(row, "required_qty", loc, 1)
                if type(row.get("priority")) is not int or row["priority"] not in (1, 2, 3):
                    errors.append(issue("PRIORITY", loc + ".priority", "Priority must be 1, 2 or 3."))
                date_field(row, "due_date", loc)
            elif table == "stocks":
                number_field(row, "on_hand", loc)
                number_field(row, "reserved", loc)
                date_field(row, "snapshot_date", loc)
                if row.get("snapshot_date") != request.get("baseline_date"):
                    errors.append(issue("SNAPSHOT_DATE", loc, "Stock and planning dates must match."))
                if (type(row.get("on_hand")) is int and type(row.get("reserved")) is int
                        and row["reserved"] > row["on_hand"]):
                    errors.append(issue("RESERVED_EXCEEDS_STOCK", loc, "Reserved quantity exceeds stock."))
            else:
                text_field(row, "parent_id", loc)
                text_field(row, "child_id", loc)
                number_field(row, "qty_per", loc, 1)
    if errors:
        return None, errors
    materials, tasks, stocks = (indexes[k] for k in ("materials", "tasks", "stocks"))
    adjacency = {mid: [] for mid in materials}
    seen = set()
    for i, edge in enumerate(sources["bom"]):
        parent, child = edge["parent_id"], edge["child_id"]
        loc = f"bom[{i}]"
        if parent not in materials or child not in materials:
            errors.append(issue("UNKNOWN_MATERIAL", loc, "BOM references an unknown material."))
            continue
        if (parent, child) in seen:
            errors.append(issue("DUPLICATE_EDGE", loc, "Repeated parent-child relation."))
        seen.add((parent, child))
        adjacency[parent].append(edge)
    for table, key in (("tasks", "product_id"), ("stocks", "material_id")):
        for i, row in enumerate(sources[table]):
            if row[key] not in materials:
                errors.append(issue("UNKNOWN_MATERIAL", f"{table}[{i}].{key}", "Unknown material."))
    for tid in request["selected_task_ids"]:
        if tid not in tasks:
            errors.append(issue("UNKNOWN_TASK", "request.selected_task_ids", "Unknown selected task.", tid))
    if errors:
        return None, errors
    for edges in adjacency.values():
        edges.sort(key=lambda e: e["child_id"])
    reachable = set()
    pending = [tasks[tid]["product_id"] for tid in request["selected_task_ids"]]
    while pending:
        mid = pending.pop()
        if mid not in reachable:
            reachable.add(mid)
            pending.extend(e["child_id"] for e in adjacency[mid])
    for mid in sorted(reachable):
        if mid not in stocks:
            errors.append(issue("MISSING_STOCK", f"stocks:{mid}", "Stock snapshot row missing.", material_id=mid))
        make = materials[mid]["supply_type"] == "MAKE"
        if make and not adjacency[mid]:
            errors.append(issue("MISSING_BOM", f"bom:{mid}", "Reachable MAKE requires BOM.", material_id=mid))
        if not make and adjacency[mid]:
            errors.append(issue("BUY_HAS_CHILDREN", f"bom:{mid}", "BUY must be a leaf.", material_id=mid))
    indegree = {mid: 0 for mid in reachable}
    for mid in reachable:
        for edge in adjacency[mid]:
            indegree[edge["child_id"]] += 1
    ready = [mid for mid in reachable if indegree[mid] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        mid = heapq.heappop(ready)
        order.append(mid)
        for edge in adjacency[mid]:
            child = edge["child_id"]
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(reachable):
        blocked = sorted(mid for mid in reachable if indegree[mid])
        errors.append(issue("BOM_CYCLE", "bom", "Cycle prevents ordering; affected materials: " + ", ".join(blocked)))
    if errors:
        return None, errors
    ordered_tasks = sorted((tasks[tid] for tid in request["selected_task_ids"]),
                           key=lambda t: (t["priority"], t["due_date"], t["task_id"]))
    # Canonical snapshots make result records independent of input row order.
    for table, key in (("materials", "material_id"), ("tasks", "task_id"), ("stocks", "material_id")):
        sources[table].sort(key=lambda row: row[key])
    sources["bom"].sort(key=lambda row: (row["parent_id"], row["child_id"]))
    balances = {mid: dict(material_id=mid, available_qty=stocks[mid]["on_hand"] - stocks[mid]["reserved"])
                for mid in sorted(reachable)}
    context = dict(request=request, sources=sources, rules=dict(version=RULE_VERSION,
                   task_order=["priority", "due_date", "task_id"], quantity="integer",
                   date_basis="calendar_days", stock="on_hand_minus_reserved"),
                   ordered_task_ids=[t["task_id"] for t in ordered_tasks], initial_balances=deepcopy(balances))
    return dict(context=context, materials=materials, tasks=ordered_tasks, balances=balances,
                graph=dict(adjacency=adjacency, reachable=sorted(reachable), topological_order=order)), []


def required_start(needed_date, lead, location, tid, mid):
    result = subtract_calendar_days(needed_date, lead)
    for error in result["issues"]:
        error.update(source_location=location, task_id=tid, material_id=mid)
    return result["value"], result["issues"]


def net_requirements(prepared):
    """M30: all parents feed a material before its dates consume shared stock."""
    balances = deepcopy(prepared["balances"])
    bundle = dict(context=deepcopy(prepared["context"]), demands=[], allocations=[],
                  make_lines=[], buy_shortages=[], final_balances=None)
    for task in prepared["tasks"]:
        tid, root = task["task_id"], task["product_id"]
        pending = defaultdict(lambda: defaultdict(list))
        pending[root][task["due_date"]].append(dict(origin_id=record_id("root", tid), task_id=tid,
            parent_demand_id=None, bom_path=[root], contribution_qty=task["required_qty"]))
        for mid in prepared["graph"]["topological_order"]:
            material = prepared["materials"][mid]
            for needed, origins in sorted(pending[mid].items()):
                origins.sort(key=lambda o: (tuple(o["bom_path"]), o["origin_id"]))
                did = record_id("demand", tid, mid, needed)
                demand = dict(demand_id=did, task_id=tid, material_id=mid, needed_date=needed,
                              gross_qty=sum(o["contribution_qty"] for o in origins), origins=origins)
                allocation = allocate_stock(demand, balances[mid])
                netted = allocation["netted_demand"]
                balances[mid] = allocation["new_balance"]
                bundle["demands"].append(netted)
                bundle["allocations"].append(allocation["ledger"])
                net = netted["net_qty"]
                if not net:
                    continue
                residuals = [a for a in netted["source_allocations"] if a["residual_qty"]]
                origin_ids = [a["origin_id"] for a in residuals]
                if material["supply_type"] == "BUY":
                    bundle["buy_shortages"].append(dict(shortage_id=record_id("shortage", tid, mid, needed),
                        demand_id=did, task_id=tid, material_id=mid, needed_date=needed,
                        shortage_qty=net, origin_ids=origin_ids))
                    continue
                start, errors = required_start(needed, material["lead_time_days"], did, tid, mid)
                if errors:
                    return None, errors
                bundle["make_lines"].append(dict(line_id=record_id("make", tid, mid, needed),
                    demand_id=did, task_id=tid, material_id=mid, gross_qty=demand["gross_qty"],
                    allocated_qty=netted["allocated_qty"], make_qty=net, needed_date=needed,
                    start_date=start, origin_ids=origin_ids))
                source_by_id = {o["origin_id"]: o for o in origins}
                for edge in prepared["graph"]["adjacency"][mid]:
                    child = edge["child_id"]
                    for residual in residuals:
                        path = source_by_id[residual["origin_id"]]["bom_path"] + [child]
                        pending[child][start].append(dict(origin_id=record_id("origin", tid, path),
                            task_id=tid, parent_demand_id=did, bom_path=path,
                            contribution_qty=residual["residual_qty"] * edge["qty_per"]))
    bundle["final_balances"] = balances
    return bundle, []


def plan_purchases(bundle, materials):
    """M40: dated BUY aggregation and FIFO use of planned rounding excess."""
    groups = defaultdict(list)
    for shortage in bundle["buy_shortages"]:
        groups[shortage["material_id"], shortage["needed_date"]].append(shortage)
    buckets, uses = [], []
    pools = defaultdict(list)
    for (mid, needed), shortages in sorted(groups.items()):
        bid = record_id("purchase_bucket", mid, needed)
        gross = sum(row["shortage_qty"] for row in shortages)
        gap = gross
        for lot in sorted(pools[mid], key=lambda row: (row["arrival_date"], row["supply_bucket_id"])):
            if lot["arrival_date"] <= needed and gap and lot["remaining_qty"]:
                used = min(gap, lot["remaining_qty"])
                lot["remaining_qty"] -= used
                gap -= used
                uses.append(dict(supply_bucket_id=lot["supply_bucket_id"], demand_bucket_id=bid,
                    qty=used, source_arrival_date=lot["arrival_date"], use_date=needed))
        material = materials[mid]
        qty = round_purchase_qty(gap, material["min_purchase_qty"], material["purchase_multiple"])
        order_date = None
        if qty:
            order_date, errors = required_start(needed, material["lead_time_days"], bid, None, mid)
            if errors:
                return None, errors
            if qty > gap:
                pools[mid].append(dict(supply_bucket_id=bid, material_id=mid,
                                       arrival_date=needed, remaining_qty=qty - gap))
        reasons = []
        if gross > gap:
            reasons.append("EARLIER_PLANNED_SURPLUS")
        if gap and gap < material["min_purchase_qty"]:
            reasons.append("MINIMUM_QUANTITY")
        if gap and qty > max(gap, material["min_purchase_qty"]):
            reasons.append("PURCHASE_MULTIPLE")
        buckets.append(dict(bucket_id=bid, material_id=mid, needed_date=needed,
            shortage_ids=sorted(row["shortage_id"] for row in shortages), gross_shortage=gross,
            surplus_used=gross-gap, remaining_gap=gap, purchase_qty=qty, order_date=order_date,
            surplus_after=sum(lot["remaining_qty"] for lot in pools[mid]),
            adjustment_reason=" + ".join(reasons) or "EXACT_SHORTAGE"))
    return dict(net_bundle=bundle, purchase_buckets=buckets, surplus_uses=uses,
                final_surplus_lots=[lot for mid in sorted(pools) for lot in pools[mid] if lot["remaining_qty"]]), []


def calculate_plan(sources, request):
    """Prototype application boundary: input snapshots -> complete result/error."""
    request_id = request.get("request_id") if isinstance(request, dict) else None
    invalid = dict(request_id=request_id, status="INVALID", result=None, errors=[])
    prepared, errors = validate_and_prepare(sources, request)
    if errors:
        return {**invalid, "errors": errors}
    bundle, errors = net_requirements(prepared)
    if errors:
        return {**invalid, "errors": errors}
    result, errors = plan_purchases(bundle, prepared["materials"])
    if errors:
        return {**invalid, "errors": errors}
    events = [dict(event_id=record_id("task_due", t["task_id"]), date=t["due_date"],
                   task_id=t["task_id"], material_id=t["product_id"]) for t in prepared["tasks"]]
    events.extend(dict(event_id=row["line_id"], date=row["start_date"],
                       task_id=row["task_id"], material_id=row["material_id"]) for row in bundle["make_lines"])
    events.extend(dict(event_id=row["bucket_id"], date=row["order_date"],
                       material_id=row["material_id"]) for row in result["purchase_buckets"] if row["purchase_qty"])
    result["risks"] = flag_early_dates(events, prepared["context"]["request"]["baseline_date"])
    result["summary"] = dict(task_count=len(prepared["tasks"]), make_line_count=len(bundle["make_lines"]),
        purchase_line_count=sum(row["purchase_qty"] > 0 for row in result["purchase_buckets"]),
        risk_count=len(result["risks"]))
    return dict(request_id=prepared["context"]["request"]["request_id"], status="VALID", result=result, errors=[])
