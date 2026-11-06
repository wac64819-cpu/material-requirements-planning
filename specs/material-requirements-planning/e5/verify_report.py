"""Check the report against frozen execution evidence; visual QA is separate."""
import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from docx import Document

OUT=Path(__file__).resolve().parent
APP=OUT.parents[2]/'material-planning'
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
E=read(OUT/'evidence/blackbox-e5.json')
I=read(OUT/'evidence/blackbox-e5-initial.json')
D=Document(OUT/'E5-black-box-testing-en.docx')
text='\n'.join([p.text for p in D.paragraphs]+[c.text for t in D.tables for r in t.rows for c in r.cells])
checks=[]
def check(name,value): checks.append({'name':name,'passed':bool(value)})
check('Final run completed',E['completed'])
check('125 out of 125',E['passed']==E['total']==len(E['cases'])==125)
check('Every case passed',all(c['passed'] for c in E['cases']))
ids=[c['id'] for c in E['cases']]
check('Case IDs unique',len(set(ids))==125)
docids=Counter(r.cells[0].text for t in D.tables for r in t.rows)
check('All executed cases appear once in report',all(docids[i]==1 for i in ids))
for group in ['Planning','Source','History']:
    for method in ['EP','BVA']:
        check(group+' includes '+method,any(c['group']==group and method in c['method'] for c in E['cases']))
for n in range(1,9):
    req=f'FR{n:02}'
    check(req+' mapped to executed cases',req in text and any(req in c['requirement'] for c in E['cases']))
for name,value in E['source_sha256'].items(): check('Current source '+name,sha(APP/name)==value)
check('Runner hash matches',sha(APP/'verify_blackbox.py')==E['harness_sha256'])
tree=ast.parse((APP/'verify_blackbox.py').read_text(encoding='utf-8'))
imports=set()
for node in ast.walk(tree):
    if isinstance(node,ast.Import): imports.update(x.name.split('.')[0] for x in node.names)
    if isinstance(node,ast.ImportFrom): imports.add((node.module or '').split('.')[0])
check('No application imports',not imports.intersection({'core','planner','storage','csv_io','web_server','sample_data'}))
run=APP/E['artifacts']
exchanges=read(run/'exchanges.json')
check('All 371 exchanges preserved',len(exchanges)==E['exchange_count']==371)
check('Raw exchange files exist',all((run/e[key]).is_file() for e in exchanges for key in ['request_file','response_file'] if e.get(key)))
check('Test database isolated',run.is_relative_to(APP/'results/e5-runs') and (run/'test.sqlite3').is_file())
for prefix in ['ROW','BYTE','NUM']:
    check(prefix+' lower exact upper witnesses',all(any(c['id']==prefix+str(i) and c['passed'] for c in E['cases']) for i in range(3)))
check('Initial CSV defect evidence retained',all(any(c['id']==i and not c['passed'] for c in I['cases']) for i in ['BYTE0','BYTE1']))
for name,count in [('workbench-verification.json',30),('persistence-ui-verification.json',14),('csv-ui-verification.json',21),('csv-verification.json',38)]:
    r=read(OUT/'evidence'/name)
    check(name+' passing evidence',r['passed']==r['total']==count)
check('Contracts documented',all(x in text for x in ['Preconditions','Postconditions','S1','S6','2 members']))
check('Residual issue explicit','OBS02' in text and 'not marked fixed' in text)
check('Real group records pending','[Name and student ID]' in text and '[To be completed after the meeting]' in text)
check('Title style present',any(p.style.name=='Title' and 'Black Box' in p.text for p in D.paragraphs))
check('Evidence hashes printed',E['harness_sha256'] in text and E['source_sha256']['csv_io.py'] in text)
pages=read(OUT/'qa/page-text.json')
check('No empty PDF pages',len(pages)>0 and all(p['characters']>100 for p in pages))
pdftext='\n'.join(p['text'] for p in pages)
check('PDF uses final execution timestamp',E['executed_at'] in pdftext)
check('PDF includes all case IDs',all(i in pdftext for i in ids))
check('PDF is newer than DOCX',(OUT/'qa/E5-black-box-testing-en.pdf').stat().st_mtime>=(OUT/'E5-black-box-testing-en.docx').stat().st_mtime)
result={'executed_at':datetime.now().astimezone().isoformat(),'passed':sum(c['passed'] for c in checks),'total':len(checks),'pages':len(pages),'checks':checks,'docx_sha256':sha(OUT/'E5-black-box-testing-en.docx'),'pdf_sha256':sha(OUT/'qa/E5-black-box-testing-en.pdf'),'evidence_sha256':sha(OUT/'evidence/blackbox-e5.json'),'rendering':'Packaged renderer unavailable because LibreOffice is absent; Word read-only PDF export and pypdfium2 rendering used. Visual review recorded separately.'}
(OUT/'verification-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"{result['passed']}/{result['total']} checks; {result['pages']} pages")
for c in checks:
    if not c['passed']: print('FAIL:',c['name'])
raise SystemExit(0 if all(c['passed'] for c in checks) else 1)
