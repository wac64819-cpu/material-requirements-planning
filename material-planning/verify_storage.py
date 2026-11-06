"""Persistence checks use an isolated temporary database, never user data."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import sqlite3

import storage
import web_server
from sample_data import priority_case


def main():
    checks = []

    def check(name, actual, expected):
        checks.append(dict(name=name,actual=actual,expected=expected,passed=actual == expected))

    def sql(database, query):
        connection = sqlite3.connect(database)
        try:
            with connection:
                return connection.execute(query).fetchall()
        finally:
            connection.close()

    with TemporaryDirectory(prefix="mrp-storage-") as directory:
        database = Path(directory) / "planning.sqlite3"
        storage.initialize(database)
        check("empty workspace", storage.load_workspace(database)["payload"], None)
        check("empty history", storage.list_batches(database), dict(items=[],next_offset=None))
        sources,request=priority_case()
        payload=dict(sources=sources,request=request)
        original=deepcopy(payload)
        first=storage.save_workspace(database,payload,None)
        check("first source saved",first["status"],"SAVED")
        check("save does not mutate input",payload,original)
        check("reopen reads exact source snapshot",storage.load_workspace(database)["payload"],first["payload"])
        revision=first["revision_id"]
        invalid=deepcopy(payload);invalid["sources"]["stocks"][0]["reserved"]=1
        check("invalid source rejected",storage.save_workspace(database,invalid,revision)["status"],"INVALID")
        check("rejection preserves head",storage.load_workspace(database)["revision_id"],revision)
        check("stale save conflicts",storage.save_workspace(database,payload,None)["status"],"CONFLICT")
        check("conflict adds no revision",sql(database,"SELECT count(*) FROM source_revision")[0][0],1)
        # Abort after inserting the revision but before switching the head.
        sql(database,"CREATE TRIGGER fail_head BEFORE UPDATE ON source_head BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
        failed=False
        try:
            storage.save_workspace(database,payload,revision)
        except sqlite3.Error:
            failed=True
        check("write failure raised",failed,True)
        check("failed commit rolls back entire revision",sql(database,"SELECT count(*) FROM source_revision")[0][0],1)
        check("failed commit leaves old head",storage.load_workspace(database)["revision_id"],revision)
        sql(database,"DROP TRIGGER fail_head")
        plan=storage.calculate_and_save(database,payload)
        batch_id=plan["saved_batch"]["batch_id"]
        history=storage.get_batch(database,batch_id)
        check("plan snapshot exact on reopen",history["outcome"]["result"],plan["result"])
        check("calculate does not mutate input",payload,original)
        check("calculate never changes master stock",storage.load_workspace(database)["payload"],first["payload"])
        changed=deepcopy(payload);changed["sources"]["tasks"][0]["required_qty"]=10
        second=storage.save_workspace(database,changed,revision)
        storage.calculate_and_save(database,changed)
        check("old history unchanged after new save and calculation",storage.get_batch(database,batch_id),history)
        check("independent old input retained",history["outcome"]["result"]["net_bundle"]["context"]["sources"]["tasks"][1]["required_qty"],100)
        check("invalid plan not recorded",storage.calculate_and_save(database,invalid)["status"],"INVALID")
        check("only two valid batches",len(storage.list_batches(database)["items"]),2)
        sql(database,"CREATE TRIGGER fail_batch BEFORE INSERT ON plan_batch BEGIN SELECT RAISE(ABORT,'simulated full disk'); END")
        failed=False
        try:
            storage.calculate_and_save(database,payload)
        except sqlite3.Error:
            failed=True
        check("plan commit failure not reported as valid",failed,True)
        check("no partial batch after failure",len(storage.list_batches(database)["items"]),2)
        # Verify HTTP maps storage failure to an explicit 503.
        web_server.DATABASE=database
        body=json.dumps(payload).encode()
        env=dict(HTTP_HOST="127.0.0.1:8765",SERVER_PORT="8765",PATH_INFO="/api/calculate",
                 REQUEST_METHOD="POST",CONTENT_TYPE="application/json",CONTENT_LENGTH=str(len(body)))
        env["wsgi.input"]=BytesIO(body)
        response_status=[]
        response=b"".join(web_server.application(env,lambda status,headers:response_status.append(status)))
        check("API save failure status",response_status[0],"503 Service Unavailable")
        check("API save failure explicit",json.loads(response)["status"],"SAVE_FAILED")
        sql(database,"DROP TRIGGER fail_batch")
        for table in ("source_revision","plan_batch"):
            for verb in ("UPDATE","DELETE"):
                query=f"UPDATE {table} SET created_at='changed'" if verb=="UPDATE" else f"DELETE FROM {table}"
                denied=False
                try:
                    sql(database,query)
                except sqlite3.IntegrityError:
                    denied=True
                check(table+" blocks "+verb,denied,True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(storage.save_workspace,database,payload,second["revision_id"]) for _ in range(2)]
            check("concurrent writers cannot lose update",sorted(f.result()["status"] for f in futures),["CONFLICT","SAVED"])
        check("batch lookup parameterized",storage.get_batch(database,"' OR 1=1 --"),None)
        big=deepcopy(payload);big["sources"]["tasks"][0]["required_qty"]=9007199254740991
        large=storage.calculate_and_save(database,big)
        check("large integer DB roundtrip",storage.get_batch(database,large["saved_batch"]["batch_id"])["outcome"]["result"],large["result"])
        check("browser large integer encoding",web_server.browser_numbers(18014398509481962),"18014398509481962")
        page=storage.list_batches(database,limit=2)
        check("history page size and continuation",[len(page["items"]),page["next_offset"]],[2,2])
        last=storage.list_batches(database,limit=2,offset=2)
        check("history final page",[len(last["items"]),last["next_offset"]],[1,None])
        check("source versions preserved",sql(database,"SELECT count(*) FROM source_revision")[0][0],3)
        empty=deepcopy(payload);empty["request"]["selected_task_ids"]=[]
        current=storage.load_workspace(database)["revision_id"]
        saved_empty=storage.save_workspace(database,empty,current)
        check("source save allows no selected tasks",saved_empty["status"],"SAVED")
        check("empty selection persists",storage.load_workspace(database)["payload"]["request"]["selected_task_ids"],[])
    root=Path(__file__).parent
    result=dict(executed_at=datetime.now().astimezone().isoformat(),passed=sum(x["passed"] for x in checks),total=len(checks),
                checks=checks,source_sha256={f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in ("storage.py","web_server.py")},
                scope="Isolated SQLite/API regression. No production database was modified.")
    (root/"results"/"storage-verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"{result['passed']}/{result['total']} storage checks passed")
    for x in checks:
        if not x["passed"]:print(x)
    return 0 if result["passed"]==result["total"] else 1


if __name__=="__main__":
    raise SystemExit(main())
