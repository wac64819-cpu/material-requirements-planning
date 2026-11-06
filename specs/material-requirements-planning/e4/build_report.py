"""Build E4 from executed evidence; no application source or database writes."""
from pathlib import Path
import hashlib
import json
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
APP=ROOT/'material-planning'
E=json.loads((APP/'results/whitebox-e4.json').read_text(encoding='utf-8'))
assert E['passed']==E['total'] and all(c['passed'] for c in E['checks'])
assert E['source_sha256']==hashlib.sha256((APP/'core.py').read_bytes()).hexdigest()
CASES={c['id']:c for c in E['cases']}
FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
DOC=Document();MD=[]
section=DOC.sections[0]
section.page_width=Inches(8.5);section.page_height=Inches(11)
section.top_margin=section.bottom_margin=Inches(.72)
section.left_margin=section.right_margin=Inches(.8)
for name,size in [('Normal',12),('Title',22),('Heading 1',16),('Heading 2',14),('Caption',10.5)]:
    s=DOC.styles[name];s.font.name='Times New Roman';s.font.size=Pt(size);s.font.color.rgb=RGBColor(0,0,0)
    s.paragraph_format.line_spacing=1.5 if name=='Normal' else 1.12
    s.paragraph_format.space_after=Pt(7)
for s in DOC.styles:
    for el in s.element.xpath('.//w:pBdr'):
        el.getparent().remove(el)
    for el in s.element.xpath('.//w:rFonts'):
        for key in list(el.attrib):
            if 'theme' in key.lower():del el.attrib[key]
header=section.header.paragraphs[0];header.text='MATERIAL REQUIREMENTS PLANNING  |  E4 UNIT TESTING'
header.runs[0].font.size=Pt(9)
footer=section.footer.paragraphs[0];footer.alignment=2
r=footer.add_run('Page ');r.font.size=Pt(9)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)

def p(text):
    DOC.add_paragraph(text);MD.append(text+'\n')
def h(text,new=False,level=1):
    if text.startswith(('3 Inventory allocation design','7 Purchase rounding design')):DOC.add_page_break()
    DOC.add_heading(text,level);MD.append('#'*(level+1)+' '+text+'\n')
def table(caption,headers,rows,widths=None):
    cp=DOC.add_paragraph(caption,'Caption');cp.paragraph_format.keep_with_next=True
    t=DOC.add_table(rows=1, cols=len(headers));t.autofit=False
    if widths:
        for col,w in zip(t.columns,widths):col.width=Inches(w)
    for cell,text in zip(t.rows[0].cells,headers):cell.text=str(text)
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for cell,text in zip(t.add_row().cells,row):cell.text=str(text)
    for i,row in enumerate(t.rows):
        no_split=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(no_split)
        for j,cell in enumerate(row.cells):
            if widths:cell.width=Inches(widths[j])
            cell.vertical_alignment=1
            props=cell._tc.get_or_add_tcPr()
            borders=OxmlElement('w:tcBorders')
            for edge in ('top','bottom','left','right'):
                border=OxmlElement('w:'+edge);border.set(qn('w:val'),'single');border.set(qn('w:sz'),'4');border.set(qn('w:color'),'D9D9D9');borders.append(border)
            props.append(borders)
            if i==0:
                shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'EDEDED');props.append(shade)
            for para in cell.paragraphs:
                para.paragraph_format.line_spacing=1.05
                para.paragraph_format.space_before=Pt(4);para.paragraph_format.space_after=Pt(4)
                para.paragraph_format.keep_with_next=(i<2 or len(t.rows)<=6) and i<len(t.rows)-1
                for run in para.runs:run.font.size=Pt(10.5);run.bold=i==0
    spacer=DOC.add_paragraph();spacer.paragraph_format.space_after=Pt(0);spacer.paragraph_format.line_spacing=Pt(3)
    spacer.add_run().font.size=Pt(2)
    MD.extend([caption,'| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |'])
    MD.extend('| '+' | '.join(map(str,row))+' |' for row in rows);MD.append('')
def code(text):
    for line in text.splitlines():
        para=DOC.add_paragraph();para.paragraph_format.space_after=Pt(0);para.paragraph_format.line_spacing=1.0
        run=para.add_run(line);run.font.name='Consolas';run.font.size=Pt(9)
    MD.extend(['```python',text,'```',''])
def diagram(name,blocks,arrows):
    compact=name=='m43-control-flow'
    if compact:
        blocks={key:(x,int(y*.65),w,int(ht*.65),txt,kind) for key,(x,y,w,ht,txt,kind) in blocks.items()}
        arrows=[([(x,int(y*.65)) for x,y in pts],label,(lpos[0],int(lpos[1]*.65)) if lpos else None) for pts,label,lpos in arrows]
    im=Image.new('RGB',(1350,780 if compact else 1300),'white');d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',25)
    for key,(x,y,w,ht,txt,kind) in blocks.items():
        if kind=='decision':d.polygon([(x+w/2,y),(x+w,y+ht/2),(x+w/2,y+ht),(x,y+ht/2)],outline='black',width=2)
        else:d.rectangle((x,y,x+w,y+ht),outline='black',width=2)
        box=d.multiline_textbbox((0,0),txt,font=font,spacing=5,align='center')
        d.multiline_text((x+(w-box[2])/2,y+(ht-box[3])/2),txt,font=font,fill='black',spacing=5,align='center')
    for pts,label,lpos in arrows:
        d.line(pts,fill='black',width=2)
        a,b=pts[-2:];dx=b[0]-a[0];dy=b[1]-a[1];norm=(dx*dx+dy*dy)**.5;ux=dx/norm;uy=dy/norm
        d.polygon([b,(b[0]-12*ux+5*uy,b[1]-12*uy-5*ux),(b[0]-12*ux-5*uy,b[1]-12*uy+5*ux)],fill='black')
        if label:d.text(lpos,label,font=font,fill='black')
    path=FIG/(name+'.png');im.save(path)
    para=DOC.add_paragraph();para.alignment=1;para.add_run().add_picture(str(path),width=Inches(6.3))
    MD.append(f'![{name}](figures/{name}.png)\n')
def tf(vector):return ''.join('T' if x else 'F' for x in vector)
def result_text(c):
    a=c['actual']
    return ('ValueError: '+a['message']) if 'error' in a else repr(a['return'])

DOC.add_paragraph('White Box Unit Testing of the Material Planning System','Title')
p('Experiment 4 | English technical report | 22 October 2026')
p('This report tests inventory allocation M33 and purchase quantity rounding M43 in the implemented procedural material planning system. The 62 new test cases passed on the recorded source revision. Coverage claims below apply only to the stated units and input domain. M33 contains loops, so its complete path space is not exhausted by a finite suite.')
table('Table 1.1 Experiment identity',['Item','Value'],[
('Group size','2 members, confirmed by the user'),('Group and members','[Group number]  [Member A name and student ID]  [Member B name and student ID]'),
('Design basis','E3 detailed design, M33 and M43; original E4 experiment guide'),('Execution','Automated local tests; no formal database writes'),('Status','Technical testing draft completed; actual group review and contributions pending')],[1.4,5.5])
h('1 Scope and acceptance criteria')
p('The E4 guide requires at least as many selected modules as group members, meaningful complexity, all five white-box techniques for each module, and an English report. Two selected modules meet the numeric requirement. M33 supplies a five-condition predicate, a nested generator predicate, explicit loops, and business invariants. M43 supplies exact arithmetic and three calls to a shared compound input guard.')
p('The source files are procedural Python functions. This experiment adds a test harness and report only. It does not replace the separate E5 system testing report or establish performance, database, browser, or deployment coverage.')

h('2 Measurement method and boundaries',True)
p('Every case is executed first against the original core.py and then against an in-memory instrumented copy of the same parsed syntax tree. The copy records executable statement sites, explicit if outcomes, explicit for entry and exhaustion, and actually evaluated Boolean atoms. Its result or exception and input immutability must match the original execution. The application file is never rewritten.')
table('Table 2.1 Counting rules',['Criterion','Denominator and interpretation'],[
('Statement','Executable AST statement sites, including if and for sites; function headers and docstrings excluded. A multiline assignment is one site.'),
('Branch','True and false outcomes of explicit if decisions plus entry and normal exhaustion of explicit for loops. Implicit library, comprehension and exception-dispatch branches are not included.'),
('Condition','True and false outcomes of each executed atomic predicate, including the two atoms inside the any generator. Skipped atoms count as unobserved.'),
('Condition combination','Feasible logical vectors per compound predicate, plus runtime short-circuit traces. Shadow evaluations use only safe built-in values; they are explicitly distinguished from executed atoms.'),
('Path','M43 includes the integer guard and has eight finite control paths in scope. M33 reports 20 observed traces; no exhaustive percentage is assigned to its unbounded loop paths.')],[1.25,5.65])
p('M33 covers core.py lines 30 to 85, including its generator expression. The _integer and _date callees, standard library internals, comprehensions and lambdas are opaque at this boundary. M43 covers lines 90 to 97 and the _integer body at lines 8 to 9. Its 10 statement sites therefore include the two guard sites. M33 guard failures are supplementary tests, not a claim of callee coverage.')
p('Tests assume record keys exist and use ordinary built-in values. Missing keys, adversarial Python objects, resource exhaustion and all malformed object shapes are outside the denominator. Tuple paths are deliberately invalid direct-unit inputs for testing the list-type guard; they are not asserted to be JSON input values.')
p('For statement, branch and condition coverage, an exact set-cover search finds a smallest subset within the executed candidate suite. These minima do not prove a globally smallest suite across every possible input. Combination minima are stated per predicate; the full suite also retains boundary and business-oracle cases.')

h('3 Inventory allocation design',True)
p('M33 receives a demand and an available balance. It checks input invariants, allocates at most the available stock, distributes that allocation in BOM-path and origin-ID order, and returns new records. Neither caller-owned input may change. This control-flow refinement follows the M33 contract in E3.')
diagram('m33-control-flow',{
'a':(160,15,640,80,'Read fields and validate quantities and date','box'),
'b':(160,135,640,95,'D1 mismatched material OR D2 no origins','decision'),
'c':(160,270,640,80,'L1 next origin','box'),
'd':(160,390,640,120,'Validate contribution\nD3 A OR B OR C OR D OR E','decision'),
'e':(160,590,640,100,'D4 duplicate origin IDs','decision'),
'f':(160,735,640,100,'D5 contribution total differs from gross','decision'),
'g':(160,880,640,80,'Allocate min(stock, gross) and sort origins','box'),
'h':(160,1000,640,80,'L2 distribute stock over sorted origins','box'),
'i':(160,1160,640,80,'Return allocation ledger and new balance','box'),
'x':(1000,450,270,130,'Reject input\nValueError','box')},[
([(480,95),(480,135)],'',None),([(800,180),(1135,180),(1135,450)],'T',(870,145)),
([(480,230),(480,270)],'F',(490,240)),([(480,350),(480,390)],'item',(495,355)),
([(800,450),(1000,500)],'T',(885,440)),([(160,450),(90,450),(90,310),(160,310)],'F',(40,360)),
([(800,310),(900,310),(900,640),(800,640)],'exhausted',(805,550)),
([(480,690),(480,735)],'F',(495,697)),([(800,640),(1135,640),(1135,580)],'T',(870,608)),
([(800,785),(1180,785),(1180,580)],'T',(870,750)),([(480,835),(480,880)],'F',(495,840)),
([(480,960),(480,1000)],'',None),([(160,1040),(100,1040),(100,1120),(480,1120),(480,1080)],'next',(110,1090)),
([(800,1040),(930,1040),(930,1200),(800,1200)],'done',(950,1120))])
DOC.add_paragraph('Figure 3.1 M33 control flow with collapsed helper calls', 'Caption')
p('D1 and D2 are two separate sequential checks in the source; the diagram groups their rejection edges for space. Helper exceptions also leave the function immediately. The measured decision IDs and exact source expressions are retained in whitebox-e4.json.')

h('4 Inventory allocation cases and coverage',True)
p('Default demand D1 belongs to task T1 and material X, is needed on 2026-10-30, and has gross quantity 10. Its origin O1 contributes 10 along [P, X]. Default available stock is 5. Every successful case checks [allocated, net, balance after, ordered origin allocations] against an independent expected value, as well as input immutability.')
table('Table 4.1 M33 business and rejection cases',['Case','Change to default input','Expected result'],[
('A00 to A03','Available stock 0, 5, 10, 11','Allocated/net/after: 0/10/0; 5/5/0; 10/0/0; 10/0/1'),
('A04','O2 contributes 6 on P/Z/X; O1 contributes 4 on P/B/X; reverse input order','O1 gets 4, residual 0; O2 gets 1, residual 5'),
('A05','Three origins O3=5, O1=2, O2=3 supplied out of order','O1 gets 2; O2 gets 3; O3 gets 0 and has residual 5'),
('A06','Balance material Y','Reject mismatched material IDs'),('A07','No origins','Reject missing origins'),('A08','Two origins both named O2','Reject duplicate origins'),
('A09','Gross becomes 11; contribution stays 10','Reject quantity mismatch'),('A10 and A11','Gross 0 or Boolean true','Reject integer or lower-bound violation'),
('A12','Needed date 2026-02-30','Reject invalid calendar date'),('A13','Available stock -1','Reject negative stock'),('A14','Origin contribution 0','Reject nonpositive contribution'),
('A15','Path [P, 0]','Generator accepts prefix then rejects invalid element'),('A16','First origin valid; second has empty ID','Validation loop rejects the second origin')],[1.0,2.8,3.1])
rows=[]
for criterion in ('statement','branch','condition'):
    s=E['coverage']['M33'][criterion]
    rows.append((criterion.title(),f"{s['covered']}/{s['total']}",', '.join(s['minimum_cases'])))
table('Table 4.2 M33 minimum candidate subsets',['Criterion','Measured','Smallest subset in this suite'],rows,[1.05,.8,5.05])
p('All five explicit if decisions take both outcomes. Both for loops enter and exhaust. The 22 condition outcomes include the nested generator atoms. The six-case statement and branch subsets exercise the five distinct local rejection sites and a successful allocation. More cases are retained because coverage alone cannot establish arithmetic correctness or stable source attribution.')

h('5 Inventory compound conditions',True)
code('A = not isinstance(origin_id, str)\nB = not origin_id\nC = not isinstance(bom_path, list)\nD = not bom_path\nE = any(not isinstance(part, str) or not part for part in bom_path)\nD3 = A or B or C or D or E\nU = not isinstance(part, str)\nV = not part')
p('For safe shadow evaluation, origin IDs are O1, an empty string, 1 or 0. Paths are a nonempty valid list, a nonempty invalid list, an empty list, and the corresponding tuples. A and B realize all four truth pairs. C, D and E realize six triples; the two triples with D=true and E=true are impossible because an empty built-in container has no invalid member. Consequently 24 of the 32 outer logical vectors are feasible in this defined domain.')
table('Table 5.1 All feasible outer logical vectors',['Case','A B C D E','Origin ID','Path','Expected and actual'],[
(c['id'],' '.join(tf(c['logical_vector'])),repr(c['inputs'][0]['origins'][0]['origin_id']),c['origin_path_literal'],'Return 5/5/0' if not any(c['logical_vector']) else 'ValueError')
for c in E['cases'] if c['id'].startswith('C')],[.6,1.3,.8,1.2,3.0])
p('All 24 cases matched their expected results and their independently evaluated logical vectors. Each single-origin test supplies one vector, so 24 is the per-predicate minimum when each vector is represented by a separate invocation. This is not a global lower bound if a single invocation is allowed to contain several valid origins.')

h('5 Continued short circuit interpretation',True)
table('Table 5.2 Executed outer predicate traces',['Witness','Observed A B C D E','Reason'],[
('C12','T - - - -','First atom rejects the ID type'),('C06','F T - - -','Empty string ID'),('C03','F F T - -','Tuple path rejected as non-list'),('C02','F F F T -','Empty list'),('C01','F F F F T','Invalid member in nonempty list'),('C00','F F F F F','Valid origin')],[.85,1.85,4.2])
p('A dash means the application did not evaluate that atom. In particular C12 through C23 do not execute the path checks. Their remaining truth values are explanatory shadow values, never additional runtime condition hits. The six traces above are the six feasible short-circuit outcomes of the outer OR expression.')
table('Table 5.3 Inner generator combinations',['Case','Path member','Logical U V','Runtime U V','Result'],[
('I0',repr('X'),'F F','F F','Accept'),('I1',repr(''),'F T','F T','Reject'),('I2','1','T F','T -','Reject'),('I3','0','T T','T -','Reject')],[.6,1.25,1.15,1.15,2.75])
p('Four cases are the per-predicate minimum for the four logical U/V pairs. Runtime evaluation has only three short-circuit traces because V is skipped when U is true. A15 also checks generator continuation after a valid member. Empty paths reject before the generator is entered; this structural dependency is not counted as missing coverage.')
table('Table 5.4 Single condition combinations for other M33 decisions',['Decision','False witness','True witness'],[
('D1 material IDs differ','A00','A06'),('D2 no origins','A00','A07'),('D4 duplicate IDs','A00','A08'),('D5 contribution total differs','A00','A09')],[4.0,1.45,1.45])
p('For condition-combination coverage of all M33 predicates, use C00 to C23, I0 to I3, A06 to A09. I0 and I1 repeat combinations already reached by C00 and C01 and may be omitted. This yields a 30-case sufficient suite. The per-predicate minima and feasible-vector argument above are the optimization claim; no global minimum for this combined suite is asserted.')

h('6 Inventory paths and loop limits',True)
p('Twenty distinct measured traces were observed when statements, decisions, conditions and explicit loop events are retained and helper internals are collapsed. This is a coverage inventory of the executed suite, not an exhaustive list of feasible control paths. The trace sequences are saved in the machine-readable evidence file.')
pathrows=[]
for i,path in enumerate(E['coverage']['M33']['observed_paths'],1):
    c=CASES[path['representative']]
    pathrows.append((f'A-path-{i:02}',c['id'],c['note'] or result_text(c)))
table('Table 6.1 One witness for each observed M33 trace',['Trace','Witness','Distinguishing outcome or input'],pathrows,[.95,.8,5.15])
p('The loop-focused suite uses A07 for zero origins and early rejection, A00 for one origin, A04 for two, A05 for three, and A16 for rejection after the first valid origin. C02 rejects an empty path, C00 accepts a one-member path, A00 visits two valid path members, and A15 visits a valid member followed by an invalid one. Zero origins never reaches the allocation loops because the contract rejects it first.')
p('An arbitrary number of origins or path members generates arbitrarily long traces. Therefore neither 20 observed traces nor the loop cases justify 100 percent path coverage. Full bounded-path coverage is also not claimed: the suite samples loop lengths and rejection positions rather than enumerating every combination. Finite source-level statement, explicit branch, and atomic-condition obligations are met; exhaustive M33 path coverage remains inapplicable without an agreed finite bound and expanded enumeration.')

h('7 Purchase rounding design',True)
p('M43 returns zero for zero shortage. Otherwise it rounds the greater of the shortage and minimum order quantity upward to a multiple of the purchase lot. Exact integer arithmetic is required, including above the JavaScript safe-integer threshold when the function is called directly in Python. The web input limits remain separate.')
code('def round_purchase_qty(remaining_gap, minimum_qty, purchase_multiple):\n    _integer(remaining_gap, "remaining_gap")\n    _integer(minimum_qty, "minimum_qty")\n    _integer(purchase_multiple, "purchase_multiple", 1)\n    if remaining_gap == 0:\n        return 0\n    target = max(remaining_gap, minimum_qty)\n    lot_count = (target + purchase_multiple - 1) // purchase_multiple\n    return lot_count * purchase_multiple\n\ndef _integer(value, name, minimum=0):\n    if type(value) is not int or value < minimum:\n        raise ValueError(...)')
p('The ellipsis abbreviates the error message only; executed source and exact messages are recorded in the evidence file. G1 means type(value) is not int; G2 means value < minimum. The guard decision is G1 OR G2. Built-in max is a call, not an invented source if branch.')
diagram('m43-control-flow',{
'a':(160,40,680,100,'Gap guard G1 OR G2','decision'),
'b':(160,250,680,100,'Minimum guard G1 OR G2','decision'),
'c':(160,460,680,100,'Multiple guard G1 OR G2','decision'),
'd':(160,690,680,130,'Z: remaining gap == 0','decision'),
'e':(80,960,350,110,'Return 0','box'),
'f':(590,920,510,160,'target = max(gap, minimum)\nRound target up to a lot\nReturn lot count * multiple','box'),
'x':(1030,240,280,120,'ValueError','box')},[
([(500,140),(500,250)],'F',(515,185)),([(500,350),(500,460)],'F',(515,395)),([(500,560),(500,690)],'F',(515,620)),
([(840,90),(1180,90),(1180,240)],'T',(960,52)),([(840,300),(1030,300)],'T',(915,263)),
([(840,510),(1180,510),(1180,360)],'T',(965,470)),([(160,755),(255,870),(255,960)],'T',(170,870)),
([(840,755),(845,920)],'F',(860,835))])
DOC.add_paragraph('Figure 7.1 M43 with all three guard calls', 'Caption')

h('8 Purchase cases and all five coverage criteria',True)
table('Table 8.1 M43 expected and actual results',['Case','Gap minimum multiple','Expected and actual'],[
(c['id'],repr(c['inputs']),str(c['actual'].get('return','ValueError: '+c['actual'].get('message','')))) for c in E['cases'] if c['module']=='M43'],[.6,2.35,3.95])
rows=[]
for criterion in ('statement','branch','condition'):
    s=E['coverage']['M43'][criterion]
    rows.append((criterion.title(),f"{s['covered']}/{s['total']}",', '.join(s['minimum_cases'])))
table('Table 8.2 M43 minimum candidate subsets',['Criterion','Measured','Smallest subset in this suite'],rows,[1.25,.85,4.8])
p('Three cases are necessary for all statement sites and explicit decision outcomes: one zero return, one positive return, and one guard exception. Four are necessary for actual atomic-condition coverage because a wrong-type failure skips the lower-bound test, while a below-minimum integer evaluates that test true. The recorded subset achieves these bounds.')
table('Table 8.3 Guard logical combinations',['Witness','Value and minimum','G1 G2','Executed G1 G2'],[
('P00','0 and 0','F F','F F'),('P11','-1 and 0','F T','F T'),('P14','1.5 and 1','T F','T -'),('P16','-1.5 and 0','T T','T -')],[.85,2.1,1.2,2.75])
p('The numeric-domain combination suite is P00, P01, P11, P14 and P16. It covers all four logical guard combinations and both outcomes of Z. Five cases are minimal for these obligations in this suite: two normal outcomes and three distinct rejecting guard vectors. G0 to G3 additionally test the shared guard directly. For nonnumeric values, G2 may not be defined; short-circuit rejection is the applicable obligation, not an invented truth value.')

h('9 Purchase path coverage',True)
table('Table 9.1 All eight finite M43 paths',['Path','Witness','Control sequence'],[
('P-path-1','P00','Three guards accept; Z true; return zero'),('P-path-2','P01','Three guards accept; Z false; calculate and return'),
('P-path-3','P10','First guard G1 true; reject'),('P-path-4','P11','First guard G1 false and G2 true; reject'),
('P-path-5','P12','First guard accepts; second guard G1 true; reject'),('P-path-6','P13','First guard accepts; second guard G1 false and G2 true; reject'),
('P-path-7','P14','First two guards accept; third guard G1 true; reject'),('P-path-8','P15','First two guards accept; third guard G1 false and G2 true; reject')],[.85,.75,5.3])
p('Each guard has two rejecting short-circuit paths and one accepting path. Any rejection terminates the call. After three successful guards, Z has two normal exits. This gives six rejecting paths plus two normal paths, all witnessed above. Eight invocations are necessary and sufficient to cover the eight complete paths. P16 repeats the first wrong-type path while adding a different logical guard vector.')
p('The path claim abstracts the internals of type, integer comparison, max and Python arithmetic, and excludes hostile user-defined objects and resource exhaustion. It is a complete result for the declared source control-flow boundary, not all interpreter paths.')
h('10 Validation strength and regressions')
p('All 62 E4 cases passed, including original-versus-instrumented equivalence and unchanged inputs. Twelve evidence checks passed. Two existing regression suites were rerun on the same application source: 38 of 38 core checks and 114 of 114 planner checks. These counts are separate suites with overlapping scenarios, not 214 unique requirements.')
table('Table 10.1 Targeted mutation checks',['Temporary defect','First detecting case'],[(m['mutation'],m['detected_by'][0]) for m in E['mutations']],[5.2,1.7])
p('All six deliberate defects were detected. Mutations were compiled only in temporary memory; no application file was changed. These checks show that the independent expected outputs can reject representative wrong implementations. They do not constitute an exhaustive mutation score.')

h('11 Evidence and reproducibility',True)
p('Execution time: '+E['executed_at']+'. Python: '+E['python'].splitlines()[0]+'. Platform: '+E['platform']+'.')
table('Table 11.1 Evidence files relative to the project root',['File','Purpose'],[
('material-planning/core.py','Unmodified implementation under test'),('material-planning/verify_whitebox.py','Case definitions, AST observers, exact subset search and mutation checks'),
('material-planning/results/whitebox-e4.json','Inputs, expected and actual results, complete traces, site manifest, coverage and checks'),
('material-planning/results/verification.json','Fresh 38-check core regression result'),('material-planning/results/planner-verification.json','Fresh 114-check planner regression result'),
('specs/material-requirements-planning/e4/verification-report.json','Document and source consistency checks; page QA recorded separately')],[3.2,3.7])
p('Source SHA256: '+E['source_sha256'])
p('Harness SHA256: '+E['harness_sha256'])
p('To reproduce, run verify_whitebox.py, verify_core.py and verify_planner.py using the recorded Python runtime from any working directory. Each script resolves its own application directory. Only result files are written; the production SQLite database is not part of this experiment. Rebuild this report after regenerating evidence so timestamps and hashes stay aligned.')
p('The source report E4 brief from September 2026 is retained as historical work. This report supersedes its one-module technical coverage and its outdated statements about unimplemented system features. The original experiment guide and E3 design document remain unchanged.')
h('12 Findings and remaining limits')
p('The tested units preserve stock bounds and demand quantities, distribute stock deterministically, reject inconsistent origins, and compute exact purchase lots under the tested inputs. Full measured statement, explicit branch and atomic-condition obligations were achieved in the specified source boundary. Logical combination tables explain feasible and infeasible vectors without crediting skipped atoms as execution.')
p('M33 cannot receive an exhaustive unbounded-path completion claim. A stricter bounded-path requirement would require an agreed maximum number of origins and path members and additional enumeration. E5 equivalence classes, boundary-value system scenarios and saved-plan user journeys are the next technical deliverable. Database and browser behavior were not rerun in this E4 round.')

h('13 Group records to complete',True)
p('The following fields are deliberately pending. Automated execution establishes technical evidence; it does not establish who performed academic work or whether an all-member review meeting occurred. Each member should record only actual work and understanding.')
table('Table 13.1 Actual member tasks',['Member','Identity','Actual task and evidence'],[
('A','[Name and student ID]','[Fill after confirmation: work actually performed, artifact or case IDs, dates]'),
('B','[Name and student ID]','[Fill after confirmation: work actually performed, artifact or case IDs, dates]')],[.8,1.8,4.3])
h('13.1 Review meeting record',level=2)
p('Date and location: [To be recorded after the meeting]. Participants: [Both actual members]. Chair and recorder: [To be confirmed].')
p('Agenda: verify the two-module scope; check independent expected values; review the difference between logical vectors and executed short-circuit atoms; confirm the M33 path limitation; check English terminology and consistency with E3; record agreed corrections and owners.')
p('Discussion record: [Actual questions, replies and decisions]. Corrections and evidence: [Actual changes and recheck results]. Review outcome: [Accepted, accepted with corrections, or requires further work]. No review outcome is asserted in this draft.')
h('13.2 Individual contribution statements',level=2)
p('Member A: [Describe actual module analysis, case design, test execution, interpretation and lessons learned. Cite specific case IDs or report sections.]')
p('Member B: [Describe actual module analysis, case design, test execution, interpretation and lessons learned. Cite specific case IDs or report sections.]')
h('13.3 Submission checklist',level=2)
p('Technical report: prepared with recorded scope limitations. English language: used throughout the report. Actual member tasks: pending. Literal all-member review record: pending. Personal contributions: pending. Final course submission: not performed.')
h('14 Source materials',level=1)
p('[1] Course handout. Experiment 4 Using White Box Testing in Unit Testing [Z]. Supplied original DOC, read on 21 October 2026.')
p('[2] Project working document. E3 Detailed Design of the Material Planning System [R]. English technical draft, 15 October 2026.')
p('[3] Project implementation and evidence. core.py and whitebox-e4.json [CP]. Source hash and execution timestamp recorded in Section 11.')

DOC.save(OUT/'E4-white-box-testing-en.docx')
(OUT/'E4-white-box-testing-en.md').write_text('\n'.join(MD),encoding='utf-8')
print('Saved E4-white-box-testing-en.docx')
