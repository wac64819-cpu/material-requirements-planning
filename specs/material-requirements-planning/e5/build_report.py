"""Produce the E5 report from complete external test evidence."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];APP=ROOT/'material-planning'
E=json.loads((APP/'results/blackbox-e5.json').read_text(encoding='utf-8'))
assert E['completed'] and E['total']==125
for name,value in E['source_sha256'].items():assert hashlib.sha256((APP/name).read_bytes()).hexdigest()==value
SNAP=OUT/'evidence';SNAP.mkdir(exist_ok=True)
for name in ['blackbox-e5.json','blackbox-e5-initial.json','csv-verification.json','csv-ui-verification.json','persistence-ui-verification.json','workbench-verification.json']:
    shutil.copy2(APP/'results'/name,SNAP/name)
UI=[(label,json.loads((SNAP/name).read_text(encoding='utf-8'))) for label,name in [('Workbench','workbench-verification.json'),('Persistence','persistence-ui-verification.json'),('CSV browser','csv-ui-verification.json')]]
REG=json.loads((SNAP/'csv-verification.json').read_text(encoding='utf-8'))
DOC=Document();MD=[]
s=DOC.sections[0];s.page_width=Inches(8.5);s.page_height=Inches(11);s.top_margin=s.bottom_margin=Inches(.72);s.left_margin=s.right_margin=Inches(.8)
for name,size in [('Normal',12),('Title',22),('Heading 1',16),('Heading 2',14),('Caption',10.5)]:
    style=DOC.styles[name];style.font.name='Times New Roman';style.font.size=Pt(size);style.font.color.rgb=RGBColor(0,0,0)
    style.paragraph_format.line_spacing=1.5 if name=='Normal' else 1.1;style.paragraph_format.space_after=Pt(7)
for st in DOC.styles:
    for e in st.element.xpath('.//w:pBdr'):e.getparent().remove(e)
    for e in st.element.xpath('.//w:rFonts'):
        for k in list(e.attrib):
            if 'theme' in k.lower():del e.attrib[k]
header=s.header.paragraphs[0];header.text='MATERIAL REQUIREMENTS PLANNING  |  E5 SYSTEM TESTING';header.runs[0].font.size=Pt(9)
footer=s.footer.paragraphs[0];footer.alignment=2;footer.add_run('Page ').font.size=Pt(9)
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)

def p(text):DOC.add_paragraph(text);MD.append(text+'\n')
def h(text,level=1):DOC.add_heading(text,level);MD.append('#'*(level+1)+' '+text+'\n')
def table(caption,headers,rows,widths):
    para=DOC.add_paragraph(caption,'Caption');para.paragraph_format.keep_with_next=True
    t=DOC.add_table(rows=1,cols=len(headers));t.autofit=False
    for col,w in zip(t.columns,widths):col.width=Inches(w)
    for c,v in zip(t.rows[0].cells,headers):c.text=str(v)
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for c,v in zip(t.add_row().cells,row):c.text=str(v)
    for i,row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for j,c in enumerate(row.cells):
            c.width=Inches(widths[j]);c.vertical_alignment=1;pr=c._tc.get_or_add_tcPr();b=OxmlElement('w:tcBorders')
            for edge in ['top','bottom','left','right']:
                e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');b.append(e)
            pr.append(b)
            if i==0:
                e=OxmlElement('w:shd');e.set(qn('w:fill'),'EDEDED');pr.append(e)
            for para in c.paragraphs:
                para.paragraph_format.line_spacing=1.05;para.paragraph_format.space_before=Pt(4);para.paragraph_format.space_after=Pt(4)
                para.paragraph_format.keep_with_next=(i<2 or len(t.rows)<=5) and i<len(t.rows)-1
                for run in para.runs:run.font.size=Pt(10.5);run.bold=i==0
    para=DOC.add_paragraph();para.paragraph_format.line_spacing=Pt(4);para.paragraph_format.space_after=Pt(0);para.add_run().font.size=Pt(2)
    MD.extend([caption,'| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |'])
    MD.extend('| '+' | '.join(str(v).replace('\n',' / ') for v in r)+' |' for r in rows);MD.append('')

def compact(value):
    if isinstance(value,dict):
        if value.get('status')=='INVALID' and 'located_errors' in value:return 'INVALID; located errors; no saved plan or history change'
        if value.get('status')=='VALID' and 'value' in value:return 'VALID + saved; '+compact(value['value'])
        if 'revision_id' in value and value['revision_id'] is None:return 'No saved workspace'
    if isinstance(value,list) and len(value)==4 and value[0]==200 and value[2:] == [True,True]:
        return compact(value[1])+'; workspace and history unchanged'
    return json.dumps(value,ensure_ascii=False,separators=(', ',': '))

DOC.add_paragraph('Black Box System Testing of the Material Planning System','Title')
p('Experiment 5 | English technical report | 22 October 2026')
p(f"This report evaluates the implemented material planning system against its user requirements through external HTTP requests and real browser operations. The final HTTP run completed {E['total']} cases, with {E['passed']} passing. Browser suites supplied 65 additional passing checks. A CSV field-length defect found by boundary testing was corrected and retested. An intermittent Windows connection reset on an oversized request remains a documented transport observation.")
table('Table 1.1 Report identity',['Item','Value'],[
('Project','Design and Implementation of a Production Requirements and Procurement Planning System Based on Multilevel Bills of Materials'),
('Method','Structured procedural implementation; equivalence partitioning and boundary value analysis'),
('Group','2 members; [Group number], [Member A name and student ID], [Member B name and student ID]'),
('Test scope','Source maintenance S1; integrated planning S2 to S5; history and export S6'),
('Status','Technical execution and reporting complete within stated scope; actual group review and contributions pending')],[1.15,5.75])
h('1 Objectives and requirements')
p('The E5 guide requires at least as many important modules or subsystems as group members, explicit preconditions and postconditions, test cases combining equivalence partitioning and boundary value analysis, and an English report. The three selected functional groups cover the six existing subsystems and exceed the two-member minimum. Grouping S2 to S5 into one external calculation scenario does not redefine the E2 architecture.')
p('Expected results come from the written BR01 to BR09 rules, FR01 to FR08 acceptance conditions, CSV limits and persistence behavior. Internal coverage, private functions and database tables are not used to decide pass or fail. Source files were inspected only to identify public interfaces and diagnose observed defects; the black-box runner imports no application modules.')

h('2 Selected subsystems and contracts')
table('Table 2.1 Preconditions and postconditions',['Group','Preconditions','Postconditions'],[
('S1 Source maintenance','Current source/request records; named UTF-8 CSV tables or JSON source save; expected previous revision for saving.','Preview either returns READY with a complete candidate or INVALID with located errors. Preview never saves. Valid save creates a version; invalid or stale save preserves current data.'),
('S2 to S5 Integrated planning','Selected task IDs; complete material, BOM and stock records; valid quantities, dates and rule version; matching stock/baseline date.','VALID returns net production, dated purchasing, stock/source trace and risk; a complete batch is saved. INVALID returns blocking errors without a saved batch. Persisted inventory is not deducted.'),
('S6 History and export','Existing saved batch ID, supported export kind or a nonnegative history offset. Source records may have changed since the batch was created.','History returns the original snapshot and result. CSV uses that batch and carries its ID. Missing batches and invalid requests reject. Restart retains saved state.')],[1.2,2.65,3.05])
p('Invalid inputs intentionally violate these preconditions one at a time where practical. Their expected postcondition is an informative rejection with no partial persistence. Cross-record consistency cases cover relationships that individual field partitions cannot express.')
h('2.1 Acceptance limits',2)
p('Task demand and BOM usage are positive integers; stock and lead time are nonnegative integers; priority is 1, 2 or 3. Reserved stock must not exceed on-hand stock. CSV numeric inputs and the browser editor are restricted to the JavaScript safe-integer maximum 9007199254740991. The native JSON calculation interface uses Python integers and does not impose that same upper bound. These are separate entry-point contracts.')
p('Each CSV file is limited to 500000 UTF-8 bytes and 5000 records. The combined HTTP JSON request is limited to 2000000 bytes. Boundary tests keep other constraints valid: the row-limit fixture stays below the byte limit, while the file-size fixture has only two material rows and uses one long name field.')

h('3 Test environment and independent fixtures')
p('Execution: '+E['executed_at']+'. Python '+E['python'].splitlines()[0]+'. Platform '+E['platform']+'. The runner starts the real loopback HTTP server on an unused local port, creates a new test database under results/e5-runs, and stops only that server. It does not open or write the production planning.sqlite3 database.')
p('All 371 recorded HTTP exchanges have request/response artifacts, except a transport exception would instead have an explicit error record. Request bodies preserve exact JSON or CSV bytes. Test IDs bind the readable case register to those artifacts. The final report is based on a completed run, not a partial result emitted during cleanup.')
table('Table 3.1 Base fixture',['Record','Fields'],[
('Material P','MAKE product; unit pcs; lead time 2 days'),('Material R','BUY raw material; unit pcs; lead time 3 days; minimum 0; purchase multiple 5'),
('BOM','P requires 2 units of R'),('Stocks','P and R each have on_hand 0 and reserved 0; snapshot date 2026-11-01'),
('Task T1','Product P; quantity 10; due 2026-11-20; priority 2; selected'),('Request','Baseline 2026-11-01; rule version prototype-v0.2; request ID E5')],[1.2,5.7])
p('Independent base oracle: P has no stock, so manufacture 10. Start P on 18 November. Raw demand is 10 times 2, or 20. No raw stock exists; 20 already meets the multiple of 5, so purchase 20 for arrival on 18 November and order on 15 November. No date precedes the baseline.')
p('The BUY-root variant removes P and all BOM edges, keeps R and its stock, and points T1 directly to R. The multilevel fixture adds S: P requires 2 S and S requires 3 R. With P stock 2, S stock 4 and R on_hand 5/reserved 1, demand10 gives P8, S12, raw gross36, raw gap32 and purchase35. S lead time1 makes the raw arrival17 November and order14 November.')

h('4 Equivalence partitions and boundary selections')
table('Table 4.1 Partition model',['Partition','Valid classes','Invalid classes','Witness families'],[
('EP01 Quantities','Positive native JSON integers; nonnegative stock; CSV/browser safe integers','Zero demand or usage; negative stock; decimal, Boolean or text quantity; CSV number above safe maximum','Q, B, ST, RS, NUM'),
('EP02 Task order','Priority1 to3; known selected tasks; priority/date/ID tie-breaking','Priority0 or4; empty/unknown selection','PR, ORD, INV00 to01'),
('EP03 BOM graph','Known acyclic references; MAKE parents and BUY leaves','Unknown/duplicate edge; self/multiple-node cycle; missing BOM/stock; BUY with children','INV02 to08, NET'),
('EP04 Purchasing','Positive gaps; exact/rounded lots; zero gap; same/later-date surplus','Nonpositive multiple; negative minimum; future surplus used backward is forbidden','MU, LOT, SUR'),
('EP05 Dates','Canonical calendar dates; leap day; dates before/on/after baseline','Impossible/noncanonical date; backward arithmetic below supported date range','LD, DT, CAL, INV09'),
('EP06 CSV input','Four exact headers; valid quoted UTF-8 text; supported table set','Empty selection/file; unknown table; bad headers/columns/quotes/numbers; row/byte excess','CSV, ROW, BYTE, NUM'),
('EP07 Persistence','New/current revision; existing batch; supported export; nonnegative offset','Stale revision; invalid save; absent batch; invalid kind or offset','H, EX, HX, PAGE, RESTART')],[1.1,1.8,2.7,1.3])
table('Table 4.2 Boundary value matrix',['Boundary','Values executed','Reason'],[
('Demand lower bound','0, 1, 2','Just below, at and above positive lower bound'),('CSV safe-integer maximum','9007199254740990, 9007199254740991, 9007199254740992','Below, at and above entry-point maximum'),
('Priority','0, 1, 2, 3, 4','Outside both ends and all valid discrete classes'),('Stock versus demand20','0, 19, 20, 21; negative stock separately','Shortage, exact coverage and surplus'),('Reserved with on-hand20','-1, 0, 1, 20, 21','Lower and cross-field upper limits'),
('Lot multiple10','Gap9, 10, 11; minimum9, 10, 11 with gap1','Below, exact and above a lot threshold'),('Order versus baseline','One day before, same day, one day after','Risk is strict less-than, not less-than-or-equal'),
('CSV records','4999, 5000, 5001','Record count maximum'),('CSV UTF-8 bytes','499999, 500000, 500001','Exact file byte maximum'),('HTTP body bytes','1999999, 2000000, 2000001; empty separately','Combined request maximum'),
('History offsets','0, 99, 100, 101, 102 with 101 batches','100-row page boundary and empty tail')],[1.55,2.75,2.6])
p('EP denotes equivalence partitioning; BVA denotes boundary value analysis. Combined labels describe a case that is both a representative of a partition and a boundary witness. They do not imply every boundary of every input field has been tested. Invalid cases use an otherwise valid base to avoid masking one defect with another.')

h('5 Requirement to test traceability')
mapping=[('FR01','Source maintenance and import','S00, Q, PR, RS, LD, MU, CAL, INV09 to11, CSV, ROW, BYTE, NUM, H00 to03'),
('FR02','Task selection and deterministic order','PR, INV00 to01, ORD0 to4'),('FR03','BOM and snapshot validity','B, INV02 to08'),
('FR04','Multilevel net requirements','P00, Q, B, NET0 to1, EX5'),('FR05','Shared stock and no actual deduction','ST, RS, NET, ORD, H08'),
('FR06','Purchasing and dated planned surplus','P00, Q, ST, MU, LOT, NET1, SUR, H06'),('FR07','Calendar dates and timing risks','P00, LD, DT, CAL, NET1'),('FR08','History, trace and export','H00 to08, HX, EX, PAGE, RESTART and browser suites')]
table('Table 5.1 Functional coverage mapping',['Req ID','Acceptance focus','Test IDs'],mapping,[.85,2.15,3.9])
p('NFR02 reproducibility is checked by ORD3, which reverses input rows. NFR07 data integrity is checked by rejection-side history invariants, H01, H03, H08 and RESTART. Performance was measured in an earlier phase and is not claimed as a new E5 measurement. This map is requirements coverage, not source-code coverage.')

h('6 Executed HTTP case register')
p('Each row reports a specific executed case. Base fixture fields remain unchanged unless the scenario states otherwise. The evidence files contain exact inputs and complete outputs. VALID cases additionally require HTTP200 and a saved batch. INVALID planning cases additionally require HTTP200, at least one located error, unchanged history, and no saved_batch field. CSV cases additionally require HTTP200 and unchanged saved workspace and history. These repeated checks are abbreviated in the tables.')
p('Output notation uses JSON arrays. Purchase rows are [material, arrival date, quantity, order date]; make rows are [material, quantity, start date]. Empty arrays mean no rows. Boolean true means the named invariant was observed. Dynamic revision IDs are shown in full in the evidence; readable tables use the word revision where appropriate.')
for number,group in enumerate(['Planning','Source','History','Transport'],1):
    rows=[c for c in E['cases'] if c['group']==group]
    h(f'6.{number} {group} cases',2)
    formatted=[]
    for c in rows:
        expected=compact(c['expected']);actual=compact(c['actual'])
        # Dynamic identifiers remain exact in the evidence and are equality-tested.
        if c['id']=='H01':expected=actual='200; INVALID; original revision unchanged' if c['passed'] else actual
        formatted.append((c['id'],c['description'],expected,actual+(' | PASS' if c['passed'] else ' | FAIL')))
    table(f'Table 6.{number} {group} expected and observed results',['ID','Scenario and input','Expected','Observed'],formatted,[.9,2.2,1.9,1.9])

h('7 Browser workflows and regression evidence')
p('The API cases exercise the complete running server. Three existing browser suites were also rerun with headless Microsoft Edge and isolated temporary databases. They use actual controls, file upload/download, page reload and server restart. These checks are supplementary scenarios, not a claim of exhaustive browser compatibility.')
table('Table 7.1 Browser suite results',['Suite','Passed','Recorded time','Principal workflow'],[
(label,f"{r['passed']}/{r['total']}",r['executed_at'],{'Workbench':'Edit source, choose tasks, calculate, reject bad input, preserve large displayed integers and check narrow-screen layout','Persistence':'Save, reload, view immutable history, handle stale writer and restart the service','CSV browser':'Download templates, upload, preview, apply, save, calculate and download all five result types'}[label]) for label,r in UI],[1.0,.65,1.9,3.35])
p('All 30 workbench, 14 persistence and 21 CSV browser checks passed. The CSV browser suite was rerun after the field-size fix. The 38 existing CSV parsing/API regression checks also passed after that fix. Counts from these suites overlap in business scenarios and must not be summed into a claim about unique requirements.')
for label,r in UI:
    table('Table 7.'+{'Workbench':'2','Persistence':'3','CSV browser':'4'}[label]+' '+label+' check register',['No','Observed scenario','Result'],[(str(i),c['name'],'PASS' if c['passed'] else 'FAIL') for i,c in enumerate(r['checks'],1)],[.55,5.65,.7])
p('Browser evidence includes results/workbench-results.png, results/persistence-history.png, results/csv-workbench.png and the corresponding mobile screenshots. These images were captured from test databases; they are evidence of those scenarios, not user production records.')

h('8 Findings corrections and residual observations')
table('Table 8.1 Findings and disposition',['ID','Finding','Disposition'],[
('DEF01','A valid 499999-byte or 500000-byte CSV with one long name field returned CSV_SYNTAX. The underlying csv reader default field limit was 131072 characters.','Fixed csv_io.py to align the field parser limit with the existing 500000-byte file ceiling. BYTE0 and BYTE1 now pass; BYTE2 still rejects. Existing CSV and browser regressions pass.'),
('OBS01','The initial Q05 oracle applied the browser/CSV safe-integer ceiling to the native JSON calculation API. That API accepted the larger integer and returned exact calculated values.','Corrected the oracle using the entry-point contract. Q05 tests exact native JSON arithmetic; NUM0 to2 separately verify the CSV safe boundary. Browser regression checks its own limit.'),
('OBS02','An oversized 2000001-byte request intermittently caused Windows connection abortion while the server was returning413. It interrupted two earlier runner attempts.','Final full run observed413 and passed the status-only boundary criterion. A reliable complete error-body delivery is not established. The harness records body-read errors or a failed transport result rather than silently omitting the case. This compatibility observation is not marked fixed.')],[.7,3.05,3.15])
p('The first attempt recorded 118 passing cases out of 121 recorded before interruption; three mismatches included the two CSV failures and the Q05 oracle issue. The preserved blackbox-e5-initial.json and that run directory retain this evidence. The final result contains completed=true and all125 cases. A partial cleanup report must never be mistaken for a completed test run.')
p('The correction changes only CSV parser configuration and its shared byte-limit constant. No calculation rule, stock ordering or user database was changed. E3 and earlier reports are dated design snapshots; final report integration should refresh source line references and hashes affected by the CSV edit.')

h('9 Result interpretation and limitations')
p('The selected cases support the stated quantity, stock, BOM, date, import, persistence and export requirements. Expected values are concrete outputs derived before execution from the business rules. Where full snapshots are compared, a mismatch is visible even if headline quantities are unchanged. Invalid input tests also verify that rejection does not create a history batch.')
p('Passing these cases does not prove correctness for every graph or all inputs. This phase does not exhaust concurrent HTTP clients, disk-full failures, every CSV encoding, every graph depth, alternative browsers or operating systems. Version-conflict behavior is tested with stale revisions and two browser pages, not a high-load concurrency benchmark. The all-member academic review and personal contribution statements remain pending.')
p('Transport OBS02 is supplementary to the selected business cases but remains visible in the report. The final status-only pass does not erase an earlier intermittent failure or establish that every client receives the explanatory error body. A production deployment would require a separate server and compatibility acceptance scope; this project remains a local coursework workbench.')

h('10 Reproducibility and evidence index')
table('Table 10.1 Evidence locations relative to the project root',['Location','Content'],[
('material-planning/verify_blackbox.py','External HTTP runner and independent fixtures; no application imports'),
('material-planning/results/blackbox-e5.json','Final completed case register, actual/expected results, source and harness hashes'),
('material-planning/'+E['artifacts'].replace('\\','/'),'Exact request and response bytes, exchanges.json, test database and server log'),
('specs/material-requirements-planning/e5/evidence','Frozen copies of the initial/final HTTP results and browser/CSV regression results'),
('specs/material-requirements-planning/e5/verification-report.json','Document/evidence/source consistency checks and final artifact hash'),
('specs/material-requirements-planning/e5/qa','Internal Word-exported PDF and page images used for visual review')],[3.5,3.4])
p('Run verify_blackbox.py with the recorded bundled Python runtime; it selects an unused local port and creates a fresh test directory. Run verify_persistence_ui.cjs and verify_csv_ui.cjs with the recorded Node runtime and bundled Playwright/Edge environment; the persistence script also runs the workbench suite. Then run verify_csv.py, rebuild this report, and repeat document verification and page inspection. The scripts stop only the servers they created.')
p('The test run is reproducible in behavior, but batch IDs, revision IDs, port, timestamps and run directory names are intentionally fresh. Equality or invariance checks compare values within the same run. The saved artifacts allow exact reconstruction of a previously executed request.')
p('CSV source SHA256: '+E['source_sha256']['csv_io.py'])
p('HTTP runner SHA256: '+E['harness_sha256'])

h('11 Group records to complete')
p('The group has two members. The following records must describe work actually performed; automated technical execution is not evidence of who authored, reviewed or approved the assignment.')
table('Table 11.1 Actual task allocation',['Member','Identity','Actual task and evidence'],[
('A','[Name and student ID]','[Actual requirements analysis, partition design, case execution or report work; cite IDs and dates]'),('B','[Name and student ID]','[Actual boundary design, independent checking, browser testing or report work; cite IDs and dates]')],[.8,1.7,4.4])
h('11.1 Literal review meeting record',2)
p('Meeting date and place: [To be completed after the meeting]. Participants: [Both actual members]. Chair and recorder: [Actual names].')
p('Review agenda: confirm selected subsystem contracts; check independent fixture calculations; verify partition and boundary choices; inspect DEF01 evidence and OBS02 limitation; confirm expected/actual tables and English wording. Discussion: [Actual questions, responses, decisions, corrections and responsible member]. Review outcome: [Actual outcome after corrections are checked].')
h('11.2 Individual contributions',2)
p('Member A: [Describe actual personal work, test IDs, evidence produced, corrections made and understanding of equivalence partitioning and boundary analysis].')
p('Member B: [Describe actual personal work, independent checking, test IDs, evidence produced and lessons from testing].')
h('11.3 Submission status',2)
p('The English technical report and execution artifacts are prepared. Actual names, task allocation, meeting record and individual contributions are pending. No FTP submission or group approval is claimed. These administrative records must be completed before final coursework submission.')
h('12 Source materials')
p('[1] Course handout. Experiment 5 Using Black Box Testing in System Testing [Z]. Supplied original DOC, read on 22 October 2026.')
p('[2] Project working documents. requirements.md, examples.md, E2 module structure, persistence-v0.4.md and csv-v0.5.md [R]. Local requirement and interface records.')
p('[3] Project execution evidence. blackbox-e5.json, browser verification records and CSV regression record [CP]. Execution times and source hashes recorded in this report and its evidence directory.')
for para in DOC.paragraphs[-3:-1]:
    para.paragraph_format.keep_with_next=True
for t in DOC.tables:
    for row in t.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.text=run.text.replace('物料 row','Material row').replace('库存 row','Stock row').replace('生产任务 row','Production task row')
DOC.save(OUT/'E5-black-box-testing-en.docx')
(OUT/'E5-black-box-testing-en.md').write_text('\n'.join(MD),encoding='utf-8')
print('Saved E5-black-box-testing-en.docx')
