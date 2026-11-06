"""Verify the final E4 artifact against saved tests and current source."""
from pathlib import Path
import ast
import hashlib
import json
from datetime import datetime
from docx import Document

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];APP=ROOT/'material-planning'
e=json.loads((APP/'results/whitebox-e4.json').read_text(encoding='utf-8'))
docpath=OUT/'E4-white-box-testing-en.docx';doc=Document(docpath)
text='\n'.join([p.text for p in doc.paragraphs]+[c.text for t in doc.tables for r in t.rows for c in r.cells])
checks=[]
def check(name,condition):checks.append(dict(name=name,passed=bool(condition)))
check('Source hash unchanged',e['source_sha256']==hashlib.sha256((APP/'core.py').read_bytes()).hexdigest())
check('Harness hash matches',e['harness_sha256']==hashlib.sha256((APP/'verify_whitebox.py').read_bytes()).hexdigest())
check('All 62 cases passed',e['total']==e['passed']==62 and all(c['passed'] for c in e['cases']))
check('Twelve evidence checks passed',len(e['checks'])==12 and all(c['passed'] for c in e['checks']))
check('All original and observed full outputs match',all(c['instrumented_matches'] for c in e['cases']))
check('All inputs unchanged',all(c['inputs_unchanged'] for c in e['cases']))
check('Six deliberate defects detected',len(e['mutations'])==6 and all(m['detected'] for m in e['mutations']))
tree=ast.parse((APP/'core.py').read_text(encoding='utf-8'))
fn={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
for mod,names in [('M33',['allocate_stock']),('M43',['round_purchase_qty','_integer'])]:
    nodes=[n for name in names for n in ast.walk(fn[name])]
    statement=sum(isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)) for n in nodes)
    branch=2*sum(isinstance(n,(ast.If,ast.For)) for n in nodes)
    check(mod+' statement denominator independently recounted',statement==e['coverage'][mod]['statement']['total'])
    check(mod+' branch denominator independently recounted',branch==e['coverage'][mod]['branch']['total'])
    for criterion,kinds in [('statement',{'S'}),('branch',{'D','L'}),('condition',{'C'})]:
        c=e['coverage'][mod][criterion]
        check(mod+' '+criterion+' numerator complete',c['covered']==c['total'] and not c['missing'])
        check(mod+' '+criterion+' figure in report',f"{c['covered']}/{c['total']}" in text)
        rows=[r for r in e['cases'] if r['module']==mod]
        def events(row):return {tuple(ev) for ev in row['events'] if ev[0] in kinds and ev[1].split(':')[0] in names}
        all_events=set().union(*(events(r) for r in rows))
        chosen=set().union(*(events(r) for r in rows if r['id'] in c['minimum_cases']))
        check(mod+' '+criterion+' selected subset covers measured universe',chosen==all_events)
    paths=e['coverage'][mod]['observed_paths']
    check(mod+' path representatives valid',all(p['representative'] in [r['id'] for r in e['cases']] for p in paths))
check('Eight M43 finite paths',len(e['coverage']['M43']['observed_paths'])==8)
check('Twenty M33 observed traces',len(e['coverage']['M33']['observed_paths'])==20)
for label,expected in [('C',24),('I',4),('G',4)]:
    rows=[r for r in e['cases'] if r['id'].startswith(label)]
    check(label+' logical vectors complete',len({tuple(r['logical_vector']) for r in rows})==expected)
    check(label+' shadow values match asserted vectors',all(r['logical_vector']==r['independently_evaluated_vector'] for r in rows))
typed=[(r,ast.literal_eval(r['input_literal'])) for r in e['cases'] if r['id'].startswith('C')]
check('Tuple and list distinctions preserved in literal evidence',all((not isinstance(args[0]['origins'][0]['bom_path'],list))==r['logical_vector'][2] for r,args in typed))
check('Report shows tuple path notation',"('X',)" in text and "['X']" in text)
check('Report source and harness hashes present',e['source_sha256'] in text and e['harness_sha256'] in text)
check('Report execution timestamp matches',e['executed_at'] in text)
check('Two embedded diagrams',len(doc.inline_shapes)==2)
check('Title style used',any(p.style.name=='Title' and 'White Box Unit Testing' in p.text for p in doc.paragraphs))
check('M33 exhaustive path limitation stated','no exhaustive percentage' in text and 'Full bounded-path coverage is also not claimed' in text)
check('Group review and identity remain placeholders','[Name and student ID]' in text and '[Actual questions, replies and decisions]' in text)
check('E5 explicitly separate','E5 system testing report' in text)
check('Both regression evidence files pass',all((lambda r:r['passed']==r['total'])(json.loads((APP/'results'/file).read_text(encoding='utf-8'))) for file in ['verification.json','planner-verification.json']))
pages=json.loads((OUT/'qa/page-text.json').read_text(encoding='utf-8'))
check('Rendered PDF has matching execution timestamp',e['executed_at'] in '\n'.join(p['text'] for p in pages))
check('No empty rendered page',all(p['characters']>100 for p in pages))
result=dict(checked_at=datetime.now().astimezone().isoformat(),passed=sum(c['passed'] for c in checks),total=len(checks),
    document_sha256=hashlib.sha256(docpath.read_bytes()).hexdigest(),evidence_sha256=hashlib.sha256((APP/'results/whitebox-e4.json').read_bytes()).hexdigest(),
    pdf_sha256=hashlib.sha256((OUT/'qa/E4-white-box-testing-en.pdf').read_bytes()).hexdigest(),pages=len(pages),checks=checks,
    rendering='Packaged render_docx.py failed because LibreOffice soffice.exe is unavailable; Word read-only export plus pypdfium2 rasterization used. Visual review is documented separately.')
(OUT/'verification-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"E4 report checks: {result['passed']}/{result['total']}; pages: {result['pages']}")
if result['passed']!=result['total']:
    print([c for c in checks if not c['passed']]);raise SystemExit(1)
