"""CSV adapters: validate a copied candidate; export only a saved snapshot."""
from copy import deepcopy
import csv
from io import StringIO, BytesIO
import json
import re
from zipfile import ZipFile, ZIP_DEFLATED

from planner import validate_and_prepare
from sample_data import priority_case

MAX_CSV_BYTES = 500_000
# A single field may occupy nearly the whole permitted file. The csv module's
# smaller default would reject valid input as a misleading CSV_SYNTAX error.
csv.field_size_limit(MAX_CSV_BYTES)

COLUMNS = {
    "materials": ["material_id", "name", "supply_type", "unit", "lead_time_days", "min_purchase_qty", "purchase_multiple"],
    "bom": ["parent_id", "child_id", "qty_per"],
    "stocks": ["material_id", "on_hand", "reserved", "snapshot_date"],
    "tasks": ["task_id", "product_id", "required_qty", "due_date", "priority"],
}
NUMERIC = {"lead_time_days", "min_purchase_qty", "purchase_multiple", "qty_per", "on_hand", "reserved", "required_qty", "priority"}


def protected_text(value):
    return isinstance(value, str) and (value.startswith(("'", "\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")))


def encode_csv(columns, rows):
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([("'" + value) if protected_text(value) else value for value in row])
    return output.getvalue().encode("utf-8-sig")


def csv_issue(code, location, message):
    return dict(code=code, severity="BLOCKING", source_location=location, message=message)


def parse_table(kind, text):
    if kind not in COLUMNS or not isinstance(text, str):
        return [], [], [csv_issue("CSV_TYPE", "CSV", "请选择支持的数据表，并使用UTF-8 CSV文件。")]
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        return [], [], [csv_issue("CSV_SIZE", kind+".csv", "单个文件不能超过500KB。")]
    reader = csv.reader(StringIO(text.lstrip("\ufeff"), newline=""), strict=True)
    rows, locations, errors = [], [], []
    try:
        headers = next(reader, [])
        if len(headers) != len(set(headers)) or set(headers) != set(COLUMNS[kind]):
            return [], [], [csv_issue("CSV_HEADER", kind+".csv:1", "表头缺失、重复或含未知列。请使用下载模板的完整表头。")]
        for cells in reader:
            line = reader.line_num
            if not cells:
                continue
            location = f"{kind}.csv:{line}"
            if len(rows) >= 5000:
                return [], [], [csv_issue("CSV_SIZE", location, "每张表最多5000条记录。")]
            if len(cells) != len(headers):
                errors.append(csv_issue("CSV_COLUMNS", location, "列数与表头不一致，请检查逗号和引号。"))
                continue
            row = dict(zip(headers, cells))
            for field, value in row.items():
                if field in NUMERIC:
                    value = value.strip()
                    if not value and field in ("min_purchase_qty", "purchase_multiple"):
                        row[field] = 0 if field == "min_purchase_qty" else 1
                    elif not re.fullmatch(r"[0-9]+", value) or len(value) > 16 or int(value) > 9007199254740991:
                        errors.append(csv_issue("CSV_INTEGER", location+"."+field, "请输入不超过9007199254740991的非负整数，不接受小数或科学计数法。"))
                    else:
                        row[field] = int(value)
                elif value.startswith("'") and protected_text(value[1:]):
                    # Reverse this adapter's Excel formula-protection prefix.
                    row[field] = value[1:]
            rows.append(row)
            locations.append(location)
    except csv.Error:
        errors.append(csv_issue("CSV_SYNTAX", f"{kind}.csv:{reader.line_num}", "CSV引号格式无效。"))
    return rows, locations, errors


def preview_import(payload, files):
    if not isinstance(payload, dict) or not isinstance(files, dict) or not files or any(k not in COLUMNS for k in files):
        return dict(status="INVALID", errors=[csv_issue("CSV_TYPE", "CSV", "请选择至少一个有效的CSV数据表。")])
    candidate = deepcopy(payload)
    if not isinstance(candidate.get("sources"), dict) or not isinstance(candidate.get("request"), dict):
        return dict(status="INVALID", errors=[csv_issue("SCHEMA", "input", "当前工作区格式无效。")])
    errors, locations, counts = [], {}, {}
    for kind, text in files.items():
        rows, lines, problems = parse_table(kind, text)
        errors.extend(problems)
        candidate["sources"][kind] = rows
        locations[kind] = lines
        counts[kind] = len(rows)
    if errors:
        return dict(status="INVALID", errors=errors)
    tasks = candidate["sources"].get("tasks", [])
    task_ids = [t.get("task_id") for t in tasks if isinstance(t, dict)] if isinstance(tasks, list) else []
    wanted = candidate["request"].get("selected_task_ids", [])
    selection = [tid for tid in wanted if isinstance(tid, str) and tid.strip() in [t.strip() for t in task_ids if isinstance(t,str)]] if isinstance(wanted,list) else []
    # Validate every task's reachable graph before applying any imported table.
    candidate["request"]["selected_task_ids"] = task_ids
    prepared, errors = validate_and_prepare(candidate["sources"], candidate["request"])
    if errors:
        for error in errors:
            match = re.match(r"^(materials|bom|stocks|tasks)\[(\d+)\](.*)$", error["source_location"])
            if match and match[1] in locations and int(match[2]) < len(locations[match[1]]):
                error["source_location"] = "CSV " + locations[match[1]][int(match[2])] + match[3]
            else:
                error["source_location"] = "导入后的数据 / " + error["source_location"]
        return dict(status="INVALID", errors=errors)
    normalized = dict(sources=prepared["context"]["sources"], request=prepared["context"]["request"])
    normalized["request"]["selected_task_ids"] = [tid.strip() for tid in selection]
    return dict(status="READY", payload=normalized, counts=counts)


def templates_zip():
    sources, _ = priority_case()
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for kind, fields in COLUMNS.items():
            archive.writestr(kind+".csv", encode_csv(fields, [[r.get(f, "") for f in fields] for r in sources[kind]]))
    return output.getvalue()


def export_batch(record, kind):
    result = record["outcome"]["result"]
    net = result["net_bundle"]
    batch_id = record["saved_batch"]["batch_id"]
    if kind == "MAKE":
        columns = ["line_id","task_id","material_id","gross_qty","allocated_qty","make_qty","needed_date","start_date"]
        rows = [[r[c] for c in columns] for r in net["make_lines"]]
    elif kind == "PURCHASE":
        columns = ["bucket_id","material_id","needed_date","gross_shortage","surplus_used","remaining_gap","purchase_qty","order_date","surplus_after","adjustment_reason","shortage_ids"]
        rows = [[json.dumps(r[c],ensure_ascii=False) if c=="shortage_ids" else r[c] for c in columns] for r in result["purchase_buckets"]]
    elif kind == "ALLOCATION":
        columns = ["allocation_id","demand_id","task_id","material_id","needed_date","before_qty","allocated_qty","after_qty"]
        rows = [[r[c] for c in columns] for r in net["allocations"]]
    elif kind == "TRACE":
        columns = ["demand_id","task_id","material_id","needed_date","origin_id","parent_demand_id","bom_path","contribution_qty","allocated_qty","residual_qty"]
        rows = []
        for item in net["demands"]:
            demand = item["demand"]
            allocation = {r["origin_id"]:r for r in item["source_allocations"]}
            for origin in demand["origins"]:
                row = {**demand, **origin, **allocation[origin["origin_id"]]}
                row["bom_path"] = json.dumps(origin["bom_path"],ensure_ascii=False)
                rows.append([row[c] for c in columns])
    elif kind == "RISK":
        columns = ["code","severity","source_location","task_id","material_id","computed_date","days_before_baseline","message"]
        rows = [[r[c] for c in columns] for r in result["risks"]]
    else:
        raise ValueError("Unsupported CSV type")
    return encode_csv(["batch_id"]+columns, [[batch_id]+row for row in rows])
