"""Independent CSV expectations and isolated persistence/API checks."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import csv
import hashlib
import json

import csv_io
import storage
import web_server
from sample_data import priority_case


def main():
    checks=[]
    def check(name, actual, expected):
        checks.append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))
    sources,request=priority_case();payload=dict(sources=sources,request=request)
    before=deepcopy(payload)
    with ZipFile(BytesIO(csv_io.templates_zip())) as archive:
        check("Four named templates",sorted(archive.namelist()),["bom.csv","materials.csv","stocks.csv","tasks.csv"])
        files={name[:-4]:archive.read(name).decode("utf-8-sig") for name in archive.namelist()}
    ready=csv_io.preview_import(payload,files)
    check("Four table preview valid",ready["status"],"READY")
    check("Preview preserves current input",payload,before)
    check("Preview counts",ready["counts"],dict(materials=4,bom=3,stocks=4,tasks=2))
    check("Preview preserves selection IDs",ready["payload"]["request"]["selected_task_ids"],["LOW","HIGH"])
    for text,code in [("bad\nX\n","CSV_HEADER"),(files["tasks"].replace("task_id,product_id","task_id,task_id"),"CSV_HEADER"),
                      (files["tasks"].replace(",100,",",1.5,"),"CSV_INTEGER"),
                      (files["tasks"].replace(",100,",",1e2,"),"CSV_INTEGER"),
                      (files["tasks"].replace(",100,",",9007199254740993,"),"CSV_INTEGER"),
                      (files["tasks"]+'EXTRA,FIELD\n',"CSV_COLUMNS"),
                      (files["tasks"]+'"unclosed',"CSV_SYNTAX")]:
        result=csv_io.preview_import(payload,dict(tasks=text))
        check(code+" rejected",[result["status"],result["errors"][0]["code"]],["INVALID",code])
    bad=csv_io.preview_import(payload,dict(bom=files["bom"].replace("A,B,2","A,MISSING,2")))
    check("Unknown reference rejected",bad["status"],"INVALID")
    check("CSV row location retained",bad["errors"][0]["source_location"],"CSV bom.csv:2")
    cycle=csv_io.preview_import(payload,dict(bom=files["bom"]+"B,A,1\r\n"))
    check("BOM cycle blocks import",any(e["code"]=="BOM_CYCLE" for e in cycle["errors"]),True)
    bad=csv_io.preview_import(payload,dict(stocks=files["stocks"].replace("2026-10-01","2026-10-02")))
    check("Snapshot mismatch rejected",bad["errors"][0]["code"],"SNAPSHOT_DATE")
    check("Empty file rejected",csv_io.preview_import(payload,dict(tasks=""))["status"],"INVALID")
    check("No files rejected",csv_io.preview_import(payload,{})["status"],"INVALID")
    check("Unknown table rejected",csv_io.preview_import(payload,{"other":"x"})["status"],"INVALID")
    check("Size limit",csv_io.parse_table("tasks","x"*500001)[2][0]["code"],"CSV_SIZE")
    # Quoted newlines, commas and quotes round-trip as one field.
    fields=csv_io.COLUMNS["materials"]
    special='成品甲, "限定"\n第二行'
    rows=[["X",special,"BUY","pcs",0,0,1],["Y","=1+1","BUY","pcs",0,0,1],["Z","'名称","BUY","pcs",0,0,1]]
    encoded=csv_io.encode_csv(fields,rows)
    parsed,_,errors=csv_io.parse_table("materials",encoded.decode("utf-8"))
    check("UTF8 BOM present",encoded[:3].hex(),"efbbbf")
    check("Quoted Chinese roundtrip",[r["name"] for r in parsed],[special,"=1+1","'名称"])
    check("Protected formula cell",b"'=1+1" in encoded,True)
    check("Quoted input no parse errors",errors,[])
    partial=csv_io.preview_import(payload,dict(tasks=files["tasks"].replace(",100,",",10,")))
    check("Single table leaves stock unchanged",partial["payload"]["sources"]["stocks"],sources["stocks"])
    removed=csv_io.preview_import(payload,dict(tasks=files["tasks"].replace("LOW,A,100,2026-10-20,2\r\n","")))
    check("Removed tasks deselected",removed["payload"]["request"]["selected_task_ids"],["HIGH"])
    with TemporaryDirectory(prefix="mrp-csv-") as directory:
        db=Path(directory)/"test.sqlite3";storage.initialize(db)
        saved=storage.calculate_and_save(db,payload);batch_id=saved["saved_batch"]["batch_id"]
        record=storage.get_batch(db,batch_id)
        original_csv=csv_io.export_batch(record,"MAKE")
        decoded=list(csv.DictReader(StringIO(original_csv.decode("utf-8-sig"))))
        check("MAKE independent quantities",[(r["task_id"],r["material_id"],r["make_qty"]) for r in decoded],
              [("HIGH","A","50"),("HIGH","B","80"),("LOW","A","100"),("LOW","B","200")])
        check("Batch ID in every row",all(r["batch_id"]==batch_id for r in decoded),True)
        for kind,count in [("PURCHASE",4),("ALLOCATION",8),("TRACE",8),("RISK",0)]:
            output=csv_io.export_batch(record,kind)
            check(kind+" rows",len(list(csv.DictReader(StringIO(output.decode("utf-8-sig"))))),count)
        changed=deepcopy(payload);changed["sources"]["tasks"][0]["required_qty"]=10
        storage.save_workspace(db,changed,None);storage.calculate_and_save(db,changed)
        check("Historical CSV unchanged after new source/plan",csv_io.export_batch(storage.get_batch(db,batch_id),"MAKE")==original_csv,True)
        # Preview is read-only: neither head nor history changes.
        head=storage.load_workspace(db);history=storage.list_batches(db)
        csv_io.preview_import(payload,files)
        check("Preview does not persist",[storage.load_workspace(db),storage.list_batches(db)],[head,history])
        web_server.DATABASE=db
        def get(route):
            env=dict(HTTP_HOST="127.0.0.1:8765",SERVER_PORT="8765",PATH_INFO=route,REQUEST_METHOD="GET")
            meta=[];body=b"".join(web_server.application(env,lambda status,headers:meta.append((status,dict(headers)))))
            return meta[0],body
        meta,body=get('/api/history/'+batch_id+'/csv/MAKE')
        check("HTTP export body exact",body==original_csv,True)
        check("HTTP download header",meta[1]["Content-Disposition"],'attachment; filename="plan-'+batch_id+'-MAKE.csv"')
        check("Unknown batch returns404",get('/api/history/missing/csv/MAKE')[0][0],"404 Not Found")
        check("Invalid export type returns400",get('/api/history/'+batch_id+'/csv/OTHER')[0][0],"400 Bad Request")
    root=Path(__file__).parent
    report=dict(executed_at=datetime.now().astimezone().isoformat(),passed=sum(c["passed"] for c in checks),total=len(checks),checks=checks,
                source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ("csv_io.py","web_server.py")})
    (root/'results'/'csv-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'results'/'mrp-csv-templates.zip').write_bytes(csv_io.templates_zip())
    print(f"{report['passed']}/{report['total']} CSV checks passed")
    for c in checks:
        if not c['passed']:print(c)
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':
    raise SystemExit(main())
