"""Small reproducible fixtures, matching the independent E1 examples."""
from planner import RULE_VERSION


def material(mid, kind="BUY", lead=0, minimum=0, multiple=1):
    row = dict(material_id=mid, name=mid, supply_type=kind, unit="pcs", lead_time_days=lead)
    if kind == "BUY":
        row.update(min_purchase_qty=minimum, purchase_multiple=multiple)
    return row


def task(tid, product, qty, due="2026-10-20", priority=2):
    return dict(task_id=tid, product_id=product, required_qty=qty, due_date=due, priority=priority)


def dataset(materials, edges, tasks, stock=None, baseline="2026-10-01"):
    stock = stock or {}
    sources = dict(source_revision="sample-v1", materials=materials,
        bom=[dict(parent_id=p, child_id=c, qty_per=q) for p, c, q in edges], tasks=tasks,
        stocks=[dict(material_id=m["material_id"], on_hand=stock.get(m["material_id"], 0),
                     reserved=0, snapshot_date=baseline) for m in materials])
    request = dict(request_id="DEMO-001", selected_task_ids=[t["task_id"] for t in tasks],
                   baseline_date=baseline, rule_version=RULE_VERSION)
    return sources, request


def basic_case():
    return dataset([material("A", "MAKE", 2), material("B", "MAKE", 3),
                    material("C", lead=4), material("D", lead=5)],
                   [("A", "B", 2), ("A", "C", 3), ("B", "D", 4)],
                   [task("T001", "A", 100)], {"B": 20, "C": 50, "D": 100})


def priority_case():
    sources, request = basic_case()
    sources["tasks"] = [task("LOW", "A", 100), task("HIGH", "A", 50, "2026-10-21", 1)]
    request["selected_task_ids"] = ["LOW", "HIGH"]
    return sources, request


def surplus_case():
    return dataset([material("X", lead=2, minimum=10, multiple=10)], [],
                   [task("T1", "X", 23, "2026-10-10"), task("T2", "X", 7, "2026-10-11")])
