"""Procedural MRP calculation leaves; no database or global stock state."""
from copy import deepcopy
from datetime import date, timedelta
import json


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _date(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid calendar date") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must use YYYY-MM-DD")
    return parsed


def allocate_stock(demand, balance):
    """M33: return a new AllocationResult without changing either input.

    Caller supplies validated E1 records. ValueError indicates a violated
    leaf precondition; user-facing validation will belong to M22.
    """
    gross = demand["gross_qty"]
    available = balance["available_qty"]
    _integer(gross, "gross_qty", 1)
    _integer(available, "available_qty")
    if demand["material_id"] != balance["material_id"]:
        raise ValueError("material IDs must match")
    _date(demand["needed_date"])
    origins = demand["origins"]
    if not origins:
        raise ValueError("a demand requires origins")
    for origin in origins:
        _integer(origin["contribution_qty"], "contribution_qty", 1)
        if (not isinstance(origin["origin_id"], str) or not origin["origin_id"]
                or not isinstance(origin["bom_path"], list) or not origin["bom_path"]
                or any(not isinstance(part, str) or not part for part in origin["bom_path"])):
            raise ValueError("invalid origin identifier or BOM path")
    if len({origin["origin_id"] for origin in origins}) != len(origins):
        raise ValueError("origin IDs must be unique within a demand")
    if sum(origin["contribution_qty"] for origin in origins) != gross:
        raise ValueError("origin quantities must sum to gross demand")

    allocated = min(available, gross)
    remaining = allocated
    source_allocations = []
    for origin in sorted(origins, key=lambda row: (tuple(row["bom_path"]), row["origin_id"])):
        taken = min(remaining, origin["contribution_qty"])
        source_allocations.append({
            "origin_id": origin["origin_id"],
            "allocated_qty": taken,
            "residual_qty": origin["contribution_qty"] - taken,
        })
        remaining -= taken
    after = available - allocated
    ledger = {
        "allocation_id": json.dumps(
            ["allocation", demand["task_id"], demand["demand_id"]],
            ensure_ascii=False, separators=(",", ":")),
        "demand_id": demand["demand_id"],
        "task_id": demand["task_id"],
        "material_id": demand["material_id"],
        "needed_date": demand["needed_date"],
        "before_qty": available,
        "allocated_qty": allocated,
        "after_qty": after,
        "source_allocations": deepcopy(source_allocations),
    }
    return {
        "netted_demand": {
            "demand": deepcopy(demand),
            "allocated_qty": allocated,
            "net_qty": gross - allocated,
            "source_allocations": source_allocations,
        },
        "ledger": ledger,
        "new_balance": {**deepcopy(balance), "available_qty": after},
    }


def round_purchase_qty(remaining_gap, minimum_qty, purchase_multiple):
    """M43: exact integer lot rounding; zero shortage never buys anything."""
    _integer(remaining_gap, "remaining_gap")
    _integer(minimum_qty, "minimum_qty")
    _integer(purchase_multiple, "purchase_multiple", 1)
    if remaining_gap == 0:
        return 0
    target = max(remaining_gap, minimum_qty)
    lot_count = (target + purchase_multiple - 1) // purchase_multiple
    return lot_count * purchase_multiple


def subtract_calendar_days(needed_date, lead_days):
    """M52: Result[Date]; no weekend/holiday adjustment."""
    _integer(lead_days, "lead_days")
    parsed = _date(needed_date)
    try:
        result = parsed - timedelta(days=lead_days)
    except OverflowError:
        return {
            "status": "ERROR", "value": None,
            "issues": [{
                "code": "DATE_RANGE", "severity": "BLOCKING",
                "message": "Calculated date is outside the supported calendar range.",
                "source_location": "subtract_calendar_days",
                "task_id": None, "material_id": None,
                "computed_date": None, "days_before_baseline": None,
            }],
        }
    return {"status": "OK", "value": result.isoformat(), "issues": []}


def flag_early_dates(required_events, baseline_date):
    """M53: preserve event dates and flag only those strictly before baseline."""
    baseline = _date(baseline_date)
    risks = []
    for event in required_events:
        computed = _date(event["date"])
        if computed < baseline:
            risks.append({
                "code": "EARLY_REQUIRED_DATE",
                "severity": "RISK",
                "message": "Required date precedes the planning baseline.",
                "source_location": event["event_id"],
                "task_id": event.get("task_id"),
                "material_id": event.get("material_id"),
                "computed_date": event["date"],
                "days_before_baseline": (baseline - computed).days,
            })
    return risks
