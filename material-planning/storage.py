"""SQLite function adapters: immutable snapshots and atomic commits."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from planner import calculate_plan, validate_and_prepare


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def connect(database):
    connection = sqlite3.connect(str(database), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(database)) as connection, connection:
        connection.executescript('''
        CREATE TABLE IF NOT EXISTS source_revision (
          revision_id TEXT PRIMARY KEY, parent_revision_id TEXT REFERENCES source_revision(revision_id),
          created_at TEXT NOT NULL, document TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_head (
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision_id TEXT NOT NULL REFERENCES source_revision(revision_id));
        CREATE TABLE IF NOT EXISTS plan_batch (
          batch_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, baseline_date TEXT NOT NULL,
          task_ids TEXT NOT NULL, summary TEXT NOT NULL, document TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS revision_no_update BEFORE UPDATE ON source_revision BEGIN
          SELECT RAISE(ABORT,'immutable source revision'); END;
        CREATE TRIGGER IF NOT EXISTS revision_no_delete BEFORE DELETE ON source_revision BEGIN
          SELECT RAISE(ABORT,'immutable source revision'); END;
        CREATE TRIGGER IF NOT EXISTS batch_no_update BEFORE UPDATE ON plan_batch BEGIN
          SELECT RAISE(ABORT,'immutable plan batch'); END;
        CREATE TRIGGER IF NOT EXISTS batch_no_delete BEFORE DELETE ON plan_batch BEGIN
          SELECT RAISE(ABORT,'immutable plan batch'); END;
        ''')


def load_workspace(database):
    with closing(connect(database)) as connection:
        row = connection.execute('''SELECT r.* FROM source_head h JOIN source_revision r
                                    ON r.revision_id=h.revision_id WHERE h.singleton=1''').fetchone()
    if row is None:
        return dict(revision_id=None, payload=None, created_at=None)
    return dict(revision_id=row["revision_id"], created_at=row["created_at"], payload=json.loads(row["document"]))


def save_workspace(database, payload, expected_revision):
    if not isinstance(payload, dict):
        return dict(status="INVALID", errors=[dict(code="SCHEMA", source_location="input", message="输入数据格式无效。")])
    payload = deepcopy(payload)
    empty_selection = isinstance(payload.get("request"), dict) and payload["request"].get("selected_task_ids") == []
    if empty_selection and isinstance(payload.get("sources"), dict) and isinstance(payload["sources"].get("tasks"), list):
        payload["request"]["selected_task_ids"] = [row.get("task_id") if isinstance(row, dict) else None for row in payload["sources"]["tasks"]]
    prepared, errors = validate_and_prepare(payload.get("sources"), payload.get("request"))
    if errors:
        return dict(status="INVALID", errors=errors)
    normalized = dict(sources=prepared["context"]["sources"], request=prepared["context"]["request"])
    # Saving source data validates BOM/stock for all tasks, even unselected ones.
    all_request = deepcopy(normalized["request"])
    all_request["selected_task_ids"] = [row["task_id"] for row in normalized["sources"]["tasks"]]
    _, errors = validate_and_prepare(normalized["sources"], all_request)
    if errors:
        return dict(status="INVALID", errors=errors)
    if empty_selection:
        normalized["request"]["selected_task_ids"] = []
    revision, created = uuid4().hex, timestamp()
    normalized["sources"]["source_revision"] = revision
    with closing(connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        head = connection.execute("SELECT revision_id FROM source_head WHERE singleton=1").fetchone()
        current = head[0] if head else None
        if current != expected_revision:
            return dict(status="CONFLICT", current_revision=current,
                        message="另一页面已保存新数据，请载入已保存数据后再编辑。当前编辑未被覆盖。")
        connection.execute("INSERT INTO source_revision VALUES (?,?,?,?)", (revision,current,created,encode(normalized)))
        connection.execute("INSERT INTO source_head VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET revision_id=excluded.revision_id", (revision,))
    return dict(status="SAVED", revision_id=revision, created_at=created, payload=normalized)


def calculate_and_save(database, payload):
    """A failed commit raises; the HTTP boundary must not report success."""
    payload = deepcopy(payload)
    batch_id, created = uuid4().hex, timestamp()
    if not isinstance(payload, dict):
        return calculate_plan(None, None)
    if isinstance(payload.get("sources"), dict):
        payload["sources"]["source_revision"] = "batch-input-" + batch_id
    outcome = calculate_plan(payload.get("sources"), payload.get("request"))
    if outcome["status"] != "VALID":
        return outcome
    context = outcome["result"]["net_bundle"]["context"]
    saved = dict(batch_id=batch_id, created_at=created)
    document = dict(outcome=outcome, saved_batch=saved)
    with closing(connect(database)) as connection, connection:
        connection.execute("INSERT INTO plan_batch VALUES (?,?,?,?,?,?)", (
            batch_id,created,context["request"]["baseline_date"],encode(context["ordered_task_ids"]),
            encode(outcome["result"]["summary"]),encode(document)))
    return {**outcome, "saved_batch": saved}


def list_batches(database, limit=100, offset=0):
    with closing(connect(database)) as connection:
        rows = connection.execute('''SELECT batch_id,created_at,baseline_date,task_ids,summary FROM plan_batch
                                     ORDER BY created_at DESC,batch_id DESC LIMIT ? OFFSET ?''', (limit+1,offset)).fetchall()
    return dict(items=[dict(batch_id=row["batch_id"],created_at=row["created_at"],baseline_date=row["baseline_date"],
                           task_ids=json.loads(row["task_ids"]),summary=json.loads(row["summary"])) for row in rows[:limit]],
                next_offset=offset+limit if len(rows)>limit else None)


def get_batch(database, batch_id):
    with closing(connect(database)) as connection:
        row = connection.execute("SELECT document FROM plan_batch WHERE batch_id=?", (batch_id,)).fetchone()
    return json.loads(row["document"]) if row else None
