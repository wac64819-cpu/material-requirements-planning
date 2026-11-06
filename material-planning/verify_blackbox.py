"""E5 external HTTP tests. Imports no application modules; uses isolated storage."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from zipfile import ZipFile
import csv
import hashlib
import json
import platform
import http.client
import socket
import subprocess
import sys
import time
import uuid

APP=Path(__file__).resolve().parent
RUN=APP/'results'/'e5-runs'/uuid.uuid4().hex
RUN.mkdir(parents=True)
CASES=[];EXCHANGES=[];CURRENT='setup';process=None;COMPLETED=False
MAX=9007199254740991
opener=build_opener(ProxyHandler({}))

def fixture(buy=False):
    materials=[dict(material_id='P',name='Product',supply_type='MAKE',unit='pcs',lead_time_days=2),
               dict(material_id='R',name='Raw',supply_type='BUY',unit='pcs',lead_time_days=3,min_purchase_qty=0,purchase_multiple=5)]
    if buy:materials=materials[1:]
    return dict(sources=dict(source_revision='e5-input',materials=materials,
        bom=[] if buy else [dict(parent_id='P',child_id='R',qty_per=2)],
        stocks=[dict(material_id=m['material_id'],on_hand=0,reserved=0,snapshot_date='2026-11-01') for m in materials],
        tasks=[dict(task_id='T1',product_id='R' if buy else 'P',required_qty=10,due_date='2026-11-20',priority=2)]),
        request=dict(request_id='E5',selected_task_ids=['T1'],baseline_date='2026-11-01',rule_version='prototype-v0.2'))

def http(method,path,payload=None,raw=None,mime='application/json'):
    data=raw if raw is not None else (json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None)
    request=Request(BASE+path,data=data,method=method,headers={'Content-Type':mime})
    try:r=opener.open(request,timeout=30)
    except HTTPError as exc:r=exc
    status=r.status;headers=dict(r.headers);body_error=None
    try:body=r.read()
    except ConnectionAbortedError as exc:
        # Windows may reset after the server rejects an unread oversized body.
        # Preserve the received status and the failed body read as separate facts.
        if status!=413:raise
        body=b'';body_error=repr(exc)
    idx=len(EXCHANGES)+1
    prefix=f'{idx:04}-{CURRENT}'
    (RUN/(prefix+'-response.bin')).write_bytes(body)
    if data is not None:(RUN/(prefix+'-request.bin')).write_bytes(data)
    EXCHANGES.append(dict(case=CURRENT,method=method,path=path,status=status,request_bytes=len(data or b''),
        request_file=prefix+'-request.bin' if data is not None else None,response_file=prefix+'-response.bin',response_headers=headers,body_read_error=body_error))
    try:value=json.loads(body)
    except (ValueError,UnicodeError):value=None
    return status,value,body

def record(cid,group,requirement,method,description,expected,actual):
    passed=expected==actual
    CASES.append(dict(id=cid,group=group,requirement=requirement,method=method,description=description,expected=expected,actual=actual,passed=passed))
    if not passed:print('FAIL',cid,description,repr(actual), 'EXPECTED',repr(expected),flush=True)

def history():
    result=[];offset=0
    while True:
        code,data,_=http('GET','/api/history?offset='+str(offset))
        assert code==200
        result.extend(x['batch_id'] for x in data['items'])
        if data['next_offset'] is None:return result
        offset=data['next_offset']

def purchase(out):return [[r['material_id'],r['needed_date'],int(r['purchase_qty']),r['order_date']] for r in out['result']['purchase_buckets']]
def make(out):return [[r['material_id'],int(r['make_qty']),r['start_date']] for r in out['result']['net_bundle']['make_lines']]

def calculate(cid,description,payload,expected,project=None,req='FR02 FR03',method='EP+BVA'):
    global CURRENT
    CURRENT=cid;before=history()
    code,out,_=http('POST','/api/calculate',payload)
    invalid=expected=='INVALID'
    if invalid:
        actual=dict(http=code,status=out.get('status'),located_errors=bool(out.get('errors')) and all(bool(e.get('source_location')) for e in out['errors']),history_unchanged=history()==before,saved='saved_batch' in out)
        wanted=dict(http=200,status='INVALID',located_errors=True,history_unchanged=True,saved=False)
    else:
        actual=dict(http=code,status=out.get('status'),saved=bool(out.get('saved_batch')),value=project(out) if out.get('status')=='VALID' else out)
        wanted=dict(http=200,status='VALID',saved=True,value=expected)
    record(cid,'Planning',req,method,description,wanted,actual)
    return out

def run():
    global CURRENT,process,BASE
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    BASE='http://127.0.0.1:'+str(port)
    log=open(RUN/'server.log','wb')
    process=subprocess.Popen([sys.executable,str(APP/'web_server.py'),'--port',str(port),'--database',str(RUN/'test.sqlite3')],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(100):
        try:
            code,state,_=http('GET','/api/workspace')
            if code==200:break
        except URLError:time.sleep(.1)
    else:raise RuntimeError('Isolated server did not start')
    record('S00','Source','FR01','EP','Fresh workspace has no saved revision',dict(revision_id=None,payload=None,created_at=None),state)
    base=fixture()
    calculate('P00','Base P10 with two R per P: make10, buy20; calendar lead2+3',base,[[['P',10,'2026-11-18']],[['R','2026-11-18',20,'2026-11-15']],[]],lambda o:[make(o),purchase(o),o['result']['risks']],req='FR04 FR06 FR07')
    for i,v in enumerate([0,1,2,MAX-1,MAX,MAX+1,1.5,True,'10']):
        p=fixture();p['sources']['tasks'][0]['required_qty']=v
        valid=type(v) is int and v>=1
        # Expected multiplication and lot totals calculated independently from the business rule.
        buys={1:5,2:5,MAX-1:18014398509481980,MAX:18014398509481985,MAX+1:18014398509481985}
        calculate(f'Q{i:02}',f'JSON task quantity {v!r}; native positive integer domain; UI safe limit is separate',p,[v,buys[v]] if valid else 'INVALID',lambda o:[int(o['result']['net_bundle']['make_lines'][0]['make_qty']),int(o['result']['purchase_buckets'][0]['purchase_qty'])],req='FR01 FR04 FR06')
    for i,v in enumerate([0,1,2]):
        p=fixture();p['sources']['bom'][0]['qty_per']=v
        calculate(f'B{i:02}',f'BOM usage {v}; positive lower boundary',p,'INVALID' if v==0 else 10*v,lambda o:sum(int(x['purchase_qty']) for x in o['result']['purchase_buckets']),req='FR03 FR04')
    for i,v in enumerate([0,1,2,3,4]):
        p=fixture();p['sources']['tasks'][0]['priority']=v
        calculate(f'PR{i}',f'Priority {v}; closed domain 1 to 3',p,'INVALID' if v in (0,4) else ['T1'],lambda o:o['result']['net_bundle']['context']['ordered_task_ids'],req='FR01 FR02')
    for i,(v,q) in enumerate([(-1,None),(0,20),(19,5),(20,0),(21,0)]):
        p=fixture();p['sources']['stocks'][1]['on_hand']=v
        calculate(f'ST{i}',f'Raw stock {v} around gross requirement20',p,'INVALID' if q is None else q,lambda o:sum(int(x['purchase_qty']) for x in o['result']['purchase_buckets']),req='FR05 FR06')
    for i,(v,q) in enumerate([(-1,None),(0,0),(1,5),(20,20),(21,None)]):
        p=fixture();p['sources']['stocks'][1].update(on_hand=20,reserved=v)
        calculate(f'RS{i}',f'Reserved {v} with on-hand20; allowed interval0..20',p,'INVALID' if q is None else q,lambda o:sum(int(x['purchase_qty']) for x in o['result']['purchase_buckets']),req='FR01 FR05')
    for i,v in enumerate([-1,0,1]):
        p=fixture();p['sources']['materials'][1]['lead_time_days']=v
        calculate(f'LD{i}',f'Purchase lead time {v}; nonnegative lower boundary',p,'INVALID' if v<0 else ['2026-11-18','2026-11-17'][v],lambda o:o['result']['purchase_buckets'][0]['order_date'],req='FR01 FR07')
    for i,v in enumerate([0,1,2]):
        p=fixture();p['sources']['materials'][1]['purchase_multiple']=v
        calculate(f'MU{i}',f'Purchase multiple {v}; positive lower boundary',p,'INVALID' if v==0 else 20,lambda o:int(o['result']['purchase_buckets'][0]['purchase_qty']),req='FR01 FR06')
    for i,(qty,minimum,expected) in enumerate([(9,0,10),(10,0,10),(11,0,20),(1,9,10),(1,10,10),(1,11,20),(1,-1,None)]):
        p=fixture(True);p['sources']['tasks'][0]['required_qty']=qty;p['sources']['materials'][0].update(purchase_multiple=10,min_purchase_qty=minimum)
        calculate(f'LOT{i}',f'BUY root gap{qty}, minimum{minimum}, multiple10',p,'INVALID' if expected is None else expected,lambda o:int(o['result']['purchase_buckets'][0]['purchase_qty']),req='FR06')
    p=fixture(True);p['sources']['stocks'][0]['on_hand']=10;p['sources']['materials'][0]['min_purchase_qty']=100
    calculate('LOT7','Zero shortage with minimum100 creates no purchase',p,[],purchase,req='FR05 FR06')
    for i,(due,expected) in enumerate([('2026-11-05',[['2026-10-31',1]]),('2026-11-06',[]),('2026-11-07',[])]):
        p=fixture();p['sources']['tasks'][0]['due_date']=due
        calculate(f'DT{i}',f'Order date one day before/on/after baseline; due={due}',p,expected,lambda o:[[r['computed_date'],r['days_before_baseline']] for r in o['result']['risks']],req='FR07')
    for i,(due,expected) in enumerate([('2026-02-30',None),('2028-02-29','2028-02-24'),('20261120',None),('0001-01-01',None),('9999-12-31','9999-12-26')]):
        p=fixture();p['sources']['tasks'][0]['due_date']=due
        calculate(f'CAL{i}',f'Calendar partition {due}; leap, format and representable range',p,'INVALID' if expected is None else expected,lambda o:o['result']['purchase_buckets'][0]['order_date'],req='FR01 FR07')
    faults=[]
    p=fixture();p['request']['selected_task_ids']=[];faults.append(('Empty selected task set',p,'FR02'))
    p=fixture();p['request']['selected_task_ids']=['UNKNOWN'];faults.append(('Unknown selected task',p,'FR02'))
    p=fixture();p['sources']['bom'][0]['child_id']='UNKNOWN';faults.append(('Unknown BOM reference',p,'FR03'))
    p=fixture();p['sources']['bom'].append(deepcopy(p['sources']['bom'][0]));faults.append(('Duplicate BOM edge',p,'FR03'))
    p=fixture();p['sources']['bom'][0]['child_id']='P';faults.append(('Self cycle',p,'FR03'))
    p=fixture();p['sources']['materials'][1]['supply_type']='MAKE';p['sources']['bom'].append(dict(parent_id='R',child_id='P',qty_per=1));p['sources']['stocks'][0]['on_hand']=10;faults.append(('Two-node cycle even when finished stock covers task',p,'FR03'))
    p=fixture();p['sources']['bom']=[];faults.append(('MAKE material without children',p,'FR03'))
    p=fixture();p['sources']['materials'][0]['supply_type']='BUY';faults.append(('BUY material with children',p,'FR03'))
    p=fixture();p['sources']['stocks'].pop();faults.append(('Reachable material missing stock',p,'FR03'))
    p=fixture();p['sources']['stocks'][1]['snapshot_date']='2026-11-02';faults.append(('Snapshot date differs from baseline',p,'FR01'))
    p=fixture();p['sources']['materials'].append(deepcopy(p['sources']['materials'][0]));faults.append(('Duplicate material ID',p,'FR01'))
    p=fixture();p['sources']['materials'][0]['material_id']=' ';faults.append(('Blank required identifier',p,'FR01'))
    for i,(label,p,req) in enumerate(faults):calculate(f'INV{i:02}',label,p,'INVALID',req=req,method='EP')
    p=fixture();p['sources']['stocks'][0]['on_hand']=10
    calculate('NET0','Finished stock exactly covers demand; no lower requirements',p,[[],[],1],lambda o:[make(o),purchase(o),len(o['result']['net_bundle']['demands'])],req='FR04 FR05')
    p=fixture();p['sources']['materials'].append(dict(material_id='S',name='Subassembly',supply_type='MAKE',unit='pcs',lead_time_days=1))
    p['sources']['bom']=[dict(parent_id='P',child_id='S',qty_per=2),dict(parent_id='S',child_id='R',qty_per=3)]
    p['sources']['stocks'][0]['on_hand']=2;p['sources']['stocks'][1].update(on_hand=5,reserved=1);p['sources']['stocks'].append(dict(material_id='S',on_hand=4,reserved=0,snapshot_date='2026-11-01'))
    calculate('NET1','Multilevel net explosion: P8, S12, raw gap32 rounded35',p,[[['P',8,'2026-11-18'],['S',12,'2026-11-17']],[['R','2026-11-17',35,'2026-11-14']]],lambda o:[make(o),purchase(o)],req='FR04 FR05 FR06 FR07',method='EP')
    for i,mode in enumerate(['priority','date','identifier']):
        p=fixture();p['sources']['stocks'][1]['on_hand']=5
        p['sources']['tasks']=[dict(task_id='Z',product_id='P',required_qty=2,due_date='2026-11-20',priority=2),dict(task_id='A',product_id='P',required_qty=2,due_date='2026-11-21',priority=1)]
        if mode=='date':p['sources']['tasks'][1]['priority']=2
        if mode=='identifier':p['sources']['tasks'][1].update(priority=2,due_date='2026-11-20')
        p['request']['selected_task_ids']=['Z','A'];order=['Z','A'] if mode=='date' else ['A','Z']
        projection=lambda o:[o['result']['net_bundle']['context']['ordered_task_ids'],[[r['task_id'],r['allocated_qty']] for r in o['result']['net_bundle']['allocations'] if r['material_id']=='R']]
        calculate(f'ORD{i}',f'Shared stock ordering by {mode}',p,[order,[[order[0],4],[order[1],1]]],projection,req='FR02 FR05',method='EP')
        if i==0:
            for rows in p['sources'].values():
                if isinstance(rows,list):rows.reverse()
            p['request']['selected_task_ids'].reverse()
            calculate('ORD3','Reversed input rows preserve business allocation',p,[order,[[order[0],4],[order[1],1]]],projection,req='FR02 FR05 NFR02',method='EP')
            p['request']['selected_task_ids']=['Z']
            calculate('ORD4','Unselected high-priority task consumes no stock',p,[['Z'],[['Z',4]]],projection,req='FR02 FR05',method='EP')
    p=fixture(True);p['sources']['materials'][0]['purchase_multiple']=10
    p['sources']['tasks']=[dict(task_id='EARLY',product_id='R',required_qty=6,due_date='2026-11-10',priority=2),dict(task_id='LATE',product_id='R',required_qty=4,due_date='2026-11-11',priority=1)];p['request']['selected_task_ids']=['LATE','EARLY']
    calculate('SUR0','Earlier purchase surplus covers later demand despite priority order',p,[[['R','2026-11-10',10,'2026-11-07'],['R','2026-11-11',0,None]],[4]],lambda o:[purchase(o),[u['qty'] for u in o['result']['surplus_uses']]],req='FR06',method='EP')
    p['sources']['tasks'][1]['due_date']='2026-11-09'
    calculate('SUR1','Future lot cannot supply earlier demand; chronology reversed',p,[['R','2026-11-09',10,'2026-11-06'],['R','2026-11-10',0,None]],purchase,req='FR06',method='EP')
    p['sources']['tasks'][0]['due_date']='2026-11-09'
    calculate('SUR2','Same-date shortages merge before rounding',p,[['R','2026-11-09',10,'2026-11-06']],purchase,req='FR06',method='EP')

    # Source import partition and byte/row boundaries, through public HTTP only.
    columns=dict(materials=['material_id','name','supply_type','unit','lead_time_days','min_purchase_qty','purchase_multiple'],bom=['parent_id','child_id','qty_per'],stocks=['material_id','on_hand','reserved','snapshot_date'],tasks=['task_id','product_id','required_qty','due_date','priority'])
    def csvtext(kind,rows):
        s=StringIO(newline='');w=csv.writer(s,lineterminator='\r\n');w.writerow(columns[kind]);w.writerows([[r.get(k,'') for k in columns[kind]] for r in rows]);return s.getvalue()
    basefiles={kind:csvtext(kind,fixture()['sources'][kind]) for kind in columns}
    (RUN/'four-table-inputs.json').write_text(json.dumps(basefiles,ensure_ascii=False,indent=2),encoding='utf-8')
    def preview(cid,label,files,expected,projection=lambda out:out.get('status')):
        global CURRENT
        CURRENT=cid;old=http('GET','/api/workspace')[1];oldhist=history()
        status,out,_=http('POST','/api/csv/preview',dict(payload=fixture(),files=files))
        record(cid,'Source','FR01','EP+BVA',label,[200,expected,True,True],[status,projection(out),http('GET','/api/workspace')[1]==old,history()==oldhist])
        return out
    preview('CSV00','Valid four tables; preview does not save or create a plan',basefiles,'READY')
    for cid,label,files in [('CSV01','Empty file selection',{}),('CSV02','Empty tasks file',{'tasks':''}),('CSV03','Unknown table',{'unknown':'x'}),('CSV04','Missing header',{'tasks':'task_id,product_id\nT1,P\n'}),('CSV05','Duplicate header',{'tasks':basefiles['tasks'].replace('product_id','task_id',1)}),('CSV06','Too few columns',{'tasks':basefiles['tasks']+'BAD,P\n'}),('CSV07','Unclosed quote',{'tasks':basefiles['tasks']+'"unfinished'}),('CSV08','Decimal quantity',{'tasks':basefiles['tasks'].replace(',10,',',1.5,')}),('CSV09','Scientific quantity',{'tasks':basefiles['tasks'].replace(',10,',',1e1,')})]:preview(cid,label,files,'INVALID')
    p=fixture();p['sources']['materials'][0]['name']='产品, "甲"\n第二行'
    preview('CSV10','Quoted Chinese comma quote and newline preserved',{'materials':csvtext('materials',p['sources']['materials'])},['READY','产品, "甲"\n第二行'],lambda o:[o['status'],o.get('payload',{}).get('sources',{}).get('materials',[{}])[0].get('name')])
    for i,n in enumerate([MAX-1,MAX,MAX+1]):
        preview(f'NUM{i}',f'CSV quantity {n}; safe-integer maximum boundary',{'tasks':basefiles['tasks'].replace(',10,',f',{n},')},'READY' if n<=MAX else 'INVALID')
    for i,n in enumerate([4999,5000,5001]):
        rows=[dict(task_id=f'T{i:04}',product_id='P',required_qty=1,due_date='2026-11-20',priority=2) for i in range(n)]
        preview(f'ROW{i}',f'CSV row count {n} around5000 maximum',{'tasks':csvtext('tasks',rows)},'READY' if n<=5000 else 'INVALID')
    # Safe filler in an otherwise valid name field, measuring UTF-8 bytes exactly.
    for i,n in enumerate([499999,500000,500001]):
        prefix=basefiles['materials'];filler='x'*(n-len(prefix.encode('utf-8')))
        text=prefix.replace('Product','Product'+filler)
        assert len(text.encode('utf-8'))==n
        preview(f'BYTE{i}',f'CSV bytes {n} around500000 maximum',{'materials':text},'READY' if n<=500000 else 'INVALID')
    CURRENT='CSV11';code,_,data=http('GET','/api/csv/templates.zip')
    with ZipFile(BytesIO(data)) as z:names=sorted(z.namelist())
    record('CSV11','Source','FR01','EP','Template ZIP contains four data tables',[200,['bom.csv','materials.csv','stocks.csv','tasks.csv']],[code,names])

    # State boundaries, historical snapshots and exports.
    CURRENT='H00';code,saved,_=http('POST','/api/workspace',dict(payload=fixture(),expected_revision=None));revision=saved.get('revision_id')
    record('H00','History','FR01 FR08','EP','First save from null revision creates a source version',[200,'SAVED',True],[code,saved.get('status'),bool(revision)])
    CURRENT='H01';invalid=fixture();invalid['sources']['tasks'][0]['required_qty']=0;code,out,_=http('POST','/api/workspace',dict(payload=invalid,expected_revision=revision))
    record('H01','History','FR01 NFR07','EP+BVA','Invalid save preserves last valid revision',[200,'INVALID',revision],[code,out.get('status'),http('GET','/api/workspace')[1]['revision_id']])
    CURRENT='H02';changed=fixture();changed['sources']['tasks'][0]['required_qty']=11;code,new,_=http('POST','/api/workspace',dict(payload=changed,expected_revision=revision))
    record('H02','History','FR01 FR08','EP','Matching revision permits new version',[200,'SAVED',True],[code,new.get('status'),new.get('revision_id')!=revision])
    CURRENT='H03';code,conflict,_=http('POST','/api/workspace',dict(payload=fixture(),expected_revision=revision))
    record('H03','History','FR01 NFR07','EP','Stale revision fails without overwriting newer source',[409,'CONFLICT',11],[code,conflict.get('status'),http('GET','/api/workspace')[1]['payload']['sources']['tasks'][0]['required_qty']])
    first=calculate('H04','Save baseline plan for historical export',fixture(),20,lambda o:int(o['result']['purchase_buckets'][0]['purchase_qty']),req='FR08',method='EP')
    bid=first['saved_batch']['batch_id'];CURRENT='H05';old=http('GET','/api/history/'+bid)[1]
    download={}
    for i,(kind,count) in enumerate([('MAKE',1),('PURCHASE',1),('ALLOCATION',2),('TRACE',2),('RISK',0)]):
        CURRENT=f'EX{i}';code,_,raw=http('GET',f'/api/history/{bid}/csv/{kind}');rows=list(csv.DictReader(StringIO(raw.decode('utf-8-sig'))));download[kind]=raw
        record(CURRENT,'History','FR08','EP+BVA',f'{kind} download rows and batch ID; zero-risk header-only partition',[200,count,True,True],[code,len(rows),raw.startswith(b'\xef\xbb\xbf'),all(r['batch_id']==bid for r in rows)])
    CURRENT='EX5';rows=list(csv.DictReader(StringIO(download['MAKE'].decode('utf-8-sig'))))
    record('EX5','History','FR04 FR08','EP','Export agrees with independent make10 and start date',[[10,'2026-11-18']],[[int(r['make_qty']),r['start_date']] for r in rows])
    calculate('H06','New plan reflects changed demand11',changed,25,lambda o:int(o['result']['purchase_buckets'][0]['purchase_qty']),req='FR06 FR08',method='EP')
    CURRENT='H07';record('H07','History','FR08','EP','Old complete snapshot and CSV unchanged after new plan',[True,True],[http('GET','/api/history/'+bid)[1]==old,http('GET',f'/api/history/{bid}/csv/MAKE')[2]==download['MAKE']])
    CURRENT='H08';workspace=http('GET','/api/workspace')[1]
    record('H08','History','FR05 FR08','EP','Calculating plans does not deduct persisted stock',[(0,0),(0,0)],[(r['on_hand'],r['reserved']) for r in workspace['payload']['sources']['stocks']])
    for i,path in enumerate(['/api/history/missing','/api/history/missing/csv/MAKE','/api/history/'+bid+'/csv/OTHER','/api/history?offset=-1','/api/history?offset=abc']):
        CURRENT=f'HX{i}';status,_,_=http('GET',path);record(CURRENT,'History','FR08','EP+BVA',path,404 if i<2 else 400,status)
    CURRENT='PAGE';ids=history()
    while len(ids)<101:
        status,out,_=http('POST','/api/calculate',fixture());assert status==200 and out['status']=='VALID';ids.append(out['saved_batch']['batch_id'])
    for i,offset in enumerate([0,99,100,101,102]):
        CURRENT=f'PAGE{i}';status,data,_=http('GET','/api/history?offset='+str(offset))
        expected_count=min(100,max(0,len(ids)-offset));expected_next=offset+100 if len(ids)-offset>100 else None
        record(CURRENT,'History','FR08','BVA',f'History offset{offset} with {len(ids)} saved plans',[200,expected_count,expected_next],[status,len(data['items']),data['next_offset']])
    CURRENT='RESTART';before=history();process.terminate();process.wait(timeout=10)
    process=subprocess.Popen([sys.executable,str(APP/'web_server.py'),'--port',str(port),'--database',str(RUN/'test.sqlite3')],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(100):
        try:
            if http('GET','/api/workspace')[0]==200:break
        except URLError:time.sleep(.1)
    record('RESTART','History','FR08 NFR07','EP','Restart retains workspace and all saved history',[True,True],[http('GET','/api/workspace')[1]==workspace,history()==before])
    # Transport boundaries are supplementary to business acceptance.
    for cid,label,raw,mime,expected in [('HTTP0','Empty request body',b'','application/json',413),('HTTP1','Malformed JSON',b'{','application/json',400),('HTTP2','Wrong content type',b'{}','text/plain',415)]:
        CURRENT=cid;code,_,_=http('POST','/api/calculate',raw=raw,mime=mime);record(cid,'Transport','FR01','EP+BVA',label,expected,code)
    for i,n in enumerate([1999999,2000000,2000001]):
        CURRENT=f'HTTP{i+3}';raw=b'{"pad":"'+b'x'*(n-10)+b'"}';assert len(raw)==n
        try:code,out,_=http('POST','/api/calculate',raw=raw)
        except (ConnectionAbortedError,ConnectionResetError,http.client.RemoteDisconnected,URLError) as exc:
            # A diagnostic failure is a result, never a silently omitted case.
            if n<=2000000:raise
            code=0;out=None
            EXCHANGES.append(dict(case=CURRENT,method='POST',path='/api/calculate',status=0,request_bytes=n,transport_error=repr(exc)))
        # Structurally incomplete JSON is INVALID only after passing the size gate.
        record(CURRENT,'Transport','FR01','BVA',f'HTTP UTF-8 body {n} bytes; status only above limit',[200,'INVALID'] if n<=2000000 else [413,None],[code,out.get('status') if isinstance(out,dict) else None])

try:
    run()
    COMPLETED=True
finally:
    if process is not None and process.poll() is None:process.terminate();process.wait(timeout=10)
    report=dict(executed_at=datetime.now().astimezone().isoformat(),python=sys.version,platform=platform.platform(),
        passed=sum(c['passed'] for c in CASES),total=len(CASES),completed=COMPLETED,cases=CASES,exchange_count=len(EXCHANGES),
        artifacts=str(RUN.relative_to(APP)),source_sha256={name:hashlib.sha256((APP/name).read_bytes()).hexdigest() for name in ['core.py','planner.py','storage.py','csv_io.py','web_server.py','web/app.js','web/index.html','web/style.css']},
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='External HTTP only, no application imports, no internal coverage instrumentation, isolated test SQLite; not a complete test of all possible inputs.')
    (RUN/'exchanges.json').write_text(json.dumps(EXCHANGES,ensure_ascii=False,indent=2),encoding='utf-8')
    (APP/'results/blackbox-e5.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"E5 HTTP cases: {report['passed']}/{report['total']}; {len(EXCHANGES)} exchanges",flush=True)
if not CASES or not all(c['passed'] for c in CASES):raise SystemExit(1)
