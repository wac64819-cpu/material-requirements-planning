"""Verify report structure, current code anchors and independent walkthroughs."""
import ast
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parent
APP=OUT.parents[2]/'material-planning'
sys.path.insert(0,str(APP))
from core import allocate_stock, round_purchase_qty, subtract_calendar_days, flag_early_dates
from planner import calculate_plan
from sample_data import basic_case


def main():
    checks=[]
    def check(name,actual,expected):
        checks.append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))
    manifest=json.loads((OUT/'design-manifest.json').read_text(encoding='utf-8'))
    md=(OUT/'E3-detailed-design-en.md').read_text(encoding='utf-8')
    check('Confirmed group size',manifest['group_size'],2)
    check('Six subsystems satisfy literal 2N requirement',manifest['subsystems']>=2*manifest['group_size'],True)
    check('Fourteen unique selected modules',len({m['id'] for m in manifest['modules']}),14)
    check('Selected modules span all six subsystems',sorted({m['subsystem'] for m in manifest['modules']}),['S1','S2','S3','S4','S5','S6'])
    check('One pseudocode block per selected module',md.count('```text'),14)
    check('Both required design-model types',all(s in md for s in ['Flowchart for M23','Flowchart for M62','Nassi Shneiderman model for M33','Nassi Shneiderman model for M43']),True)
    check('Two business decision tables',all(s in md for s in ['Table 5.1','Table 5.2']),True)
    check('Actual member and meeting records remain pending','Pending actual allocation' in md and 'not evidence that a meeting or review has occurred' in md,True)
    check('Whole-table import differs from E2 patch design','not E2 upsert patches' in md,True)
    check('Logical modules distinguished from real functions','not separate Python functions' in md,True)
    for item in manifest['modules']:
        functions={n.name:n for n in ast.parse((APP/item['file']).read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
        anchors='; '.join(f"{item['file']}:{functions[name].lineno}-{functions[name].end_lineno} {name}" for name in item['functions'])
        check(item['id']+' current function anchors',item['anchor'],anchors)
    for name,expected in manifest['source_sha256'].items():
        check(name+' unchanged source hash',hashlib.sha256((APP/name).read_bytes()).hexdigest(),expected)
    for name in manifest['figures']:
        check(name+' nonempty PNG',(OUT/'diagrams-expanded'/name).read_bytes()[:8].hex(),'89504e470d0a1a0a')
    with ZipFile(OUT/'E3-detailed-design-en.docx') as archive:
        xml=ET.fromstring(archive.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        check('Four embedded diagram instances',len(xml.findall('.//a:blip',ns)),4)
        check('Seven native tables',len(xml.findall('.//w:tbl',ns)),7)
        check('Native Word Title style',len(xml.findall(".//w:pStyle[@w:val='Title']",ns)),1)
        check('No inherited paragraph borders',len(ET.fromstring(archive.read('word/styles.xml')).findall('.//w:pBdr',ns)),0)
        check('No direct paragraph borders',len(xml.findall('.//w:pBdr',ns)),0)
    demand=dict(demand_id='D',task_id='T',material_id='X',needed_date='2026-10-10',gross_qty=12,
        origins=[dict(origin_id='o1',bom_path=['A','X'],contribution_qty=7),dict(origin_id='o2',bom_path=['B','X'],contribution_qty=5)])
    balance=dict(material_id='X',available_qty=8)
    before=deepcopy((demand,balance));result=allocate_stock(demand,balance)
    check('Independent stock attribution',[(a['allocated_qty'],a['residual_qty']) for a in result['netted_demand']['source_allocations']],[(7,0),(1,4)])
    check('Independent stock net and balance',[result['netted_demand']['net_qty'],result['new_balance']['available_qty']],[4,0])
    check('Leaf inputs unchanged',(demand,balance),before)
    for inputs,expected in [((620,100,100),700),((0,100,10),0),((4,12,6),12),((4,10,6),12),((12,4,6),12),((13,4,6),18)]:
        check('Purchase decision '+str(inputs),round_purchase_qty(*inputs),expected)
    check('Leap day arithmetic',subtract_calendar_days('2024-03-01',1)['value'],'2024-02-29')
    check('Calendar date example',subtract_calendar_days('2026-10-10',2)['value'],'2026-10-08')
    check('Date range failure',subtract_calendar_days('0001-01-01',1)['issues'][0]['code'],'DATE_RANGE')
    events=[dict(event_id='early',date='2026-10-09'),dict(event_id='equal',date='2026-10-10')]
    check('Strict baseline comparison',[(r['source_location'],r['days_before_baseline']) for r in flag_early_dates(events,'2026-10-10')],[('early',1)])
    sources,request=basic_case();outcome=calculate_plan(sources,request)
    check('Multilevel example VALID',outcome['status'],'VALID')
    check('Independent B manufacture',[r['make_qty'] for r in outcome['result']['net_bundle']['make_lines'] if r['material_id']=='B'],[180])
    check('Independent D purchase',[r['purchase_qty'] for r in outcome['result']['purchase_buckets'] if r['material_id']=='D'],[620])
    report=dict(executed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),passed=sum(c['passed'] for c in checks),total=len(checks),checks=checks,
        document_sha256=hashlib.sha256((OUT/'E3-detailed-design-en.docx').read_bytes()).hexdigest(),
        scope='Document structure and current small contract walkthroughs; not complete E4/E5 coverage; no database writes.')
    (OUT/'verification-expanded.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for check_row in checks:
        if not check_row['passed']:print('FAILED',check_row['name'],check_row['actual'])
    print(f"{report['passed']}/{report['total']} E3 checks passed")
    return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':raise SystemExit(main())
