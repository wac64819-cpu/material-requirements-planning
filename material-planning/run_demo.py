"""Small runnable examples, not the complete multilevel planner."""
import json
from core import allocate_stock, round_purchase_qty, subtract_calendar_days, flag_early_dates


def demand(task_id, quantity, due, priority):
    return {
        "demand_id": task_id + ":B:" + due,
        "task_id": task_id, "material_id": "B", "needed_date": due,
        "gross_qty": quantity, "priority": priority,
        "origins": [{"origin_id": task_id + ":origin", "task_id": task_id,
                     "parent_demand_id": None, "bom_path": ["A", "B"],
                     "contribution_qty": quantity}],
    }


def main():
    # These are already-expanded B requests. BOM expansion is not implemented.
    requests = [demand("LOW", 200, "2026-10-18", 2),
                demand("HIGH", 100, "2026-10-19", 1)]
    balance = {"request_id": "DEMO", "material_id": "B", "available_qty": 20}
    original_stock = balance.copy()
    rows = []
    # Task deadlines differ by the same one day as these component dates.
    for item in sorted(requests, key=lambda row: (row["priority"], row["needed_date"], row["task_id"])):
        result = allocate_stock(item, balance)
        balance = result["new_balance"]
        rows.append({
            "task": item["task_id"],
            "allocated": result["netted_demand"]["allocated_qty"],
            "net_B": result["netted_demand"]["net_qty"],
        })
    output = {
        "scope": "Four calculation leaves; component demands are prepared inputs",
        "priority_allocation": rows,
        "original_stock": original_stock,
        "working_stock_remaining": balance["available_qty"],
        "purchase_D_for_gap_620_min_100_multiple_100": round_purchase_qty(620, 100, 100),
        "zero_gap_purchase": round_purchase_qty(0, 100, 10),
        "D_order_date": subtract_calendar_days("2026-10-15", 5),
        "risks": flag_early_dates([
            {"event_id": "late-start", "date": "2026-10-09", "material_id": "D"}
        ], "2026-10-10"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
