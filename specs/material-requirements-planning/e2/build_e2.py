from pathlib import Path
import json, re, html, subprocess, sys, textwrap
ROOT=Path(r"C:\Users\许yq\Desktop\软件工程\specs\material-requirements-planning")
OUT=ROOT/"e2"
OUT.mkdir(exist_ok=True); (OUT/"diagrams").mkdir(exist_ok=True)
def write(n,s): (OUT/n).write_text(s,encoding="utf-8")
def table(h,rs):
 return "| "+" | ".join(h)+" |\n|"+"|".join("---" for _ in h)+"|\n"+"\n".join("| "+" | ".join(str(v).replace("|"," / ") for v in r)+" |" for r in rs)+"\n"
mods={}
def m(i,s,n,inp,out,contract,effect="Pure"):
 mods[i]=dict(id=i,subsystem=s,name=n,inputs=inp,outputs=out,contract=contract,effect=effect)
m("M00","APP","handle_action","Action, payload, repository, supported_rules, clock, id_factory","ApplicationResponse","Dispatch maintenance, calculation, history or export. During calculation call S2 then S3 then S4 then S5 then S6; stop at the first error and convert its issues through M26 before publishing rejection.","Coordinator; no direct SQL")
m("M10","S1","maintain_sources","MaintenanceSubmission, repository","MaintenanceOutcome","Read current revision; parse, merge and validate one submission; commit only a fully accepted candidate.","Coordinator")
m("M11","S1","parse_submission","MaintenanceSubmission","Result[TypedImport]","Parse required fields without rounding, preserve row locations, reject duplicate input keys and unknown columns where policy requires.")
m("M12","S1","merge_source_patch","SourceSet, TypedImport","SourceSet","Apply explicit upserts to a copy. Stock upserts identify both snapshot date and material. No implicit deletion or mutation of the original.")
m("M13","S1","validate_source_edit","SourceSet candidate, TypedImport","List[Issue]","Check uniqueness, referenced IDs, integer/date domains and stock bounds. Detect incompatible BUY edges and cycles in changed BOM; full selected MAKE completeness is checked in S2.")
m("M14","S1","commit_source_revision","repository, expected_revision, SourceSet candidate","Result[revision_id]","In one transaction create an immutable revision, compare the current revision, move the head, and commit; conflicts and failures roll back.","Writes D1 atomically")
m("M15","S1","make_maintenance_response","request_id, accepted_count, List[Issue], commit_result","MaintenanceOutcome","REJECTED has zero accepted records. On commit failure do not report accepted data.")
m("M20","S2","prepare_context","PlanningRequest, repository, RuleSnapshot","PreparationResult","Obtain one consistent snapshot, validate selected data and BOM, order tasks and freeze a read-only context. Return READY with prepared input, or call M26 and return INVALID with that outcome.","Coordinator")
m("M21","S2","read_source_snapshot","repository, baseline_date or null","Result[SourceSet]","Read source head and all required revision rows in one read transaction. Null date is used for maintenance reads; planning selects the baseline stock snapshot.","Reads D1")
m("M22","S2","validate_selected_data","PlanningRequest, SourceSet, RuleSnapshot","List[Issue]","Reject no selection, duplicate or unknown task IDs, unsupported rules, invalid fields and missing reachable stock. Snapshot date must equal baseline.")
m("M23","S2","validate_and_index_bom","SourceSet, selected_task_ids","Result[GraphIndex]","Validate all selected reachable edges including stock-covered branches; return adjacency and deterministic parent-before-child order or located graph errors.")
m("M24","S2","order_tasks","List[Task], selected_task_ids","List[Task]","Sort by priority ascending, due date ascending, then ordinal task ID. Preserve no import-row tie-break.")
m("M25","S2","freeze_context","request, sources, rules, ordered_tasks, GraphIndex","PreparedContext","Copy validated inputs and initial availability into E1 Context; attach only a derived graph index outside the retained E1 Context.")
m("M26","S2","make_invalid_outcome","request_id, nonempty List[Issue]","CalculationOutcome","Return INVALID with null result and blocking issues. Do not manufacture an empty successful batch.")
m("M30","S3","net_requirements","PreparedContext","Result[NetBundle]","Own the batch balance map. Complete each task before the next; visit materials in parent-before-child order, then dates ascending.","Coordinator; private memory only")
m("M31","S3","initialize_balances","request_id, List[Stock]","BalanceMap","Create available quantities as on_hand minus reserved exactly once per run.")
m("M32","S3","collect_material_demands","task_id, material_id, DemandMap","List[Demand]","For this task/material collect all contributions, group by date, preserve origins and return dates ascending. The caller must first finish all parents.")
m("M33","S3","allocate_stock","Demand, Balance","AllocationResult","Allocate min(balance,gross). Split origin attribution by ordinal BOM path then origin ID. Return residual, ledger and new balance; do not mutate caller inputs.")
m("M34","S3","expand_make_demand","NettedDemand, Material, child_edges","Result[MakeExpansion]","For positive MAKE net quantity derive start date, one MAKE row and children from attributed net origins. Zero net yields no MAKE row or children. Calls M52.")
m("M35","S3","record_buy_shortage","NettedDemand, Material","BuyShortage or null","Return a positive BUY residual with date/source links; otherwise return null.")
m("M36","S3","assemble_net_bundle","Context, netted_demands, allocations, make_lines, shortages, final_balances","Result[NetBundle]","Check gross=allocated+net, origin totals, stock conservation and reference integrity before returning the completed bundle.")
m("M40","S4","plan_purchases","NetBundle","Result[PurchasingEnvelope]","Use only BUY residuals after existing-stock allocation completes; iterate material IDs and needed dates with one separate surplus pool per material.","Coordinator; private memory only")
m("M41","S4","group_buy_shortages","List[BuyShortage]","List[ShortageGroup]","Group by material and needed date across tasks; preserve shortage IDs. Sort material ID ordinal, then date.")
m("M42","S4","consume_surplus","ShortageGroup, List[SurplusLot]","SurplusAllocation","Consume only lots available by the needed date, earliest arrival then supply bucket ID. Return remaining gap, updated lots and source-use links.")
m("M43","S4","round_purchase_qty","remaining_gap, minimum_qty, purchase_multiple","Int >= 0","Zero gap returns zero even with a positive minimum. Otherwise use exact integer ceiling of max(gap,minimum) to the multiple.")
m("M44","S4","finalize_purchase_bucket","ShortageGroup, SurplusAllocation, purchase_qty, Material","Result[PurchaseStep]","Build the dated bucket and update the returned pool with new rounding excess; no order date for zero purchase. Calls M52 only for positive purchases.")
m("M45","S4","assemble_purchase_envelope","NetBundle, purchase_buckets, surplus_uses, surplus_lots","Result[PurchasingEnvelope]","Check quantity/date conservation and produce the complete purchasing result, retaining zero-purchase buckets for trace.")
m("M50","S5","complete_plan","PurchasingEnvelope","Result[CalculationOutcome]","Collect required events, assess dates against baseline, assemble totals and return VALID with the calculated result.","Coordinator")
m("M51","S5","collect_required_dates","PurchasingEnvelope","List[DatedEvent]","Include every selected task due date and positive manufacturing/purchase start; retain event/task/material links. Ignore nonexistent zero-quantity orders.")
m("M52","S5","subtract_calendar_days","Date needed_date, Int >= 0 lead_days","Result[Date]","Subtract calendar days including weekends and leap days. Zero is valid; return DATE_RANGE if the result cannot be represented.")
m("M53","S5","flag_early_dates","List[DatedEvent], baseline_date","List[Issue]","Only dates strictly before baseline are RISK; retain original date and positive difference in calendar days.")
m("M54","S5","assemble_calculated_batch","PurchasingEnvelope, List[Issue] risks","CalculatedBatch","Attach net bundle, procurement, surplus uses, risks and count summary. Do not add quantities across unrelated units.")
m("M60","S6","publish_results","PublishCommand, repository, clock, id_factory","PlanResponse","For VALID outcome save first, then expose saved data; INVALID becomes rejection. For queries load saved history, build views and optionally CSV.","Coordinator")
m("M61","S6","classify_outcome","CalculationOutcome","Result[CalculatedBatch]","Pass a valid complete result or return its blocking issues; enforce the tagged union.")
m("M62","S6","save_batch_atomic","CalculatedBatch, repository, batch_id, created_at","Result[BatchRecord]","Insert one canonical result document including all snapshots in a transaction. Return SAVED only after commit.","Writes D2 atomically")
m("M63","S6","read_history","QueryRequest, repository","Result[List[BatchRecord]]","Read exact saved documents; return NOT_FOUND for missing detail/export batches; listing may return an empty list.","Reads D2")
m("M64","S6","build_trace_view","List[BatchRecord], filters","Result[ReportView]","Filter display rows while retaining their linked source, demand, allocation and supply records. Never consult current source data.")
m("M65","S6","encode_csv","ReportView, table_kind","CsvDocument","UTF-8 CSV with a header, proper quoting and ISO dates. Export MAKE, PURCHASE, ALLOCATION, TRACE or RISK; preserve batch identifiers.")
m("M66","S6","make_plan_response","request_id, outcome_status, saved_records, view, csv, issues","PlanResponse","Map failures and successes consistently. A failed save returns SAVE_FAILED with no successful saved records.")
subsystems=[
("S1","Source maintenance","M10","FR01","P1",["M11","M12","M13","M14","M15"]),
("S2","Snapshot and BOM validation","M20","FR02, FR03","P2.1",["M21","M22","M23","M24","M25","M26"]),
("S3","Demand and shared inventory","M30","FR04, FR05","P2.2",["M31","M32","M33","M34","M35","M36"]),
("S4","Purchasing and planned surplus","M40","FR06","Purchasing part of P2.3",["M41","M42","M43","M44","M45"]),
("S5","Calendar and timing risk","M50","FR07","Risk part of P2.3; shared calendar helper",["M51","M52","M53","M54"]),
("S6","History trace and export","M60","FR08","P3",["M61","M62","M63","M64","M65","M66"])
]
# Call graph. Functions are records and procedures, never classes.
calls=[("M00",s[2],"selection" if s[0] in ("S1","S6") else "calculation") for s in subsystems]
for s in subsystems:
 for c in s[5]:
  if c=="M52": continue
  calls.append((s[2],c,"repeat" if c in ("M32","M33","M34","M35","M42","M43","M44") else "conditional" if c in ("M14","M26","M62","M63","M65") else "call"))
calls += [("M00","M26","shared"),("M10","M21","shared"),("M34","M52","shared"),("M44","M52","shared")]
# Every entry denotes actual arguments/results. Coupling labels use module IDs to avoid an ambiguous abbreviated type.
def q(s): return json.dumps(s)
def dot_header(title,rank="TB"):
 return 'digraph G {\ngraph [rankdir='+rank+', bgcolor="white", pad="0.35", nodesep="0.45", ranksep="0.85", splines=polyline, label='+q(title)+', labelloc=t, fontsize=24, fontname="Arial"];\nnode [shape=box, fontname="Arial", fontsize=16, margin="0.16,0.12", color="#334155", penwidth=1.4];\nedge [fontname="Arial", fontsize=12, color="#475569", arrowsize=0.75];\n'
def module_label(i):
 n=mods[i]["name"].replace("_"," ")
 return i+"\n"+"\n".join(textwrap.wrap(n,24))
figs={}
def structure(sid,title,root,children,external=()):
 dot=dot_header(title)
 for i in [root]+children+list(external):
  dot+=q(i)+' [label='+q(module_label(i))+', style="filled", fillcolor="'+("#edf5ff" if i==root else "#f1f5f9" if i in external else "#ffffff")+'"];\n'
 for a,b,mode in calls:
  if a==root and b in children:
   dot+=q(a)+" -> "+q(b)+' [label='+q("I/"+b+"   O/"+b+("\n"+mode.upper() if mode in ("repeat","conditional","selection") else ""))+'];\n'
 for i in external:
  caller= "M34" if i=="M52" and "M34" in children else "M44" if i=="M52" else root
  dot+=q(caller)+" -> "+q(i)+' [style=dashed,label='+q("shared   I/"+i+" O/"+i)+'];\n'
 # S5 owns M52 but complete_plan does not invoke it. It is a separately callable exported helper.
 if sid=="S5":
  dot+='"M52" [label='+q(module_label("M52")+"\nExported calendar helper")+',style="filled",fillcolor="#f1f5f9"];\n'
  dot+='"M50" -> "M52" [style=dotted,arrowhead=none,label="ownership only; called by M34 and M44"];\n'
 dot+="}"
 figs["structure-"+sid.lower()]=dict(title=title,dot=dot,kind="structure",modules=[root]+children+list(external))
structure("overview","System module structure","M00",[s[2] for s in subsystems],["M26"])
for s in subsystems:
 children=[i for i in s[5] if i!="M52"]
 structure(s[0],s[0]+"   "+s[1],s[2],children,["M21"] if s[0]=="S1" else ["M52"] if s[0] in ("S3","S4") else [])
# Refined DFD registry. Boundary aliases are normalized to their E1 names for balance checking.
base=json.loads((ROOT/"e1"/"dfd-model.json").read_text(encoding="utf-8"))
flows={k:dict(name=v[0],type=v[1]) for k,v in base["flows"].items()}
def f(i,name,typ): flows[i]=dict(name=name,type=typ)
for r in [
("G01","Typed submission","TypedImport"),("G02","Validated source candidate","SourceSet"),("G03","Located maintenance errors","List[Issue]"),("G04","Maintenance commit result","CommitResult"),
("G21","Selected snapshot envelope","ValidationEnvelope"),("G22","Ordered task envelope","ValidationEnvelope"),("G23","Validated graph envelope","ValidationEnvelope"),("G24","Planning validation errors","List[Issue]"),
("G31","Initialized netting state","NettingState"),("G32","Ordered demand bucket","CandidateEnvelope"),("G33","Residual bucket and ledger","NettedEnvelope"),("G34","Manufacturing expansion","ExpansionResult"),("G35","Completed netting state","NettingState"),
("G41","Date grouped shortage envelope","PurchaseWork"),("G42","Surplus adjusted shortage","PurchaseWork"),("G43","Rounded purchasing quantity","PurchaseWork"),("G44","Empty planned surplus pool","List[SurplusLot]"),("G45","Available planned surplus lots","List[SurplusLot]"),("G46","Updated planned surplus lots","List[SurplusLot]"),("G47","Accumulated procurement records","PurchaseWork"),("G20","Purchasing envelope","PurchasingEnvelope"),
("G51","Required dates and retained calculation","RiskWork"),("G52","Assessed dates and retained calculation","RiskWork"),
("G61","Accepted calculated result","CalculatedBatch"),("G62","Rejected outcome issues","List[Issue]"),("G63","Loaded batch records","List[BatchRecord]"),("G64","Committed batch record","BatchRecord"),("G65","View and CSV data","PresentationWork")
]: f(*r)
dfds=[]
def dfd(sid,title,internal,nodes,edges,expected):
 # nodes: id,label,kind,module; edges: source,target,flow
 d=dict(id=sid,title=title,internal=internal,nodes=nodes,edges=edges,expected=expected)
 dot=dot_header(title,"TB")
 for i,label,k,module in nodes:
  opts='shape=box, style="rounded,filled", fillcolor="#edf5ff"' if k=="process" else 'shape=record, style="filled", fillcolor="#fff8e8"' if k=="store" else 'shape=box, style="filled", fillcolor="#f1f5f9"'
  dot+=q(i)+" [label="+q(label)+", "+opts+"];\n"
 for a,b,flow in edges: dot+=q(a)+" -> "+q(b)+" [label="+q(flow)+"];\n"
 dot+="}"
 d["dot"]=dot; dfds.append(d); figs["dfd-"+sid.lower()]=dict(title=title,dot=dot,kind="dfd")
P=lambda i,l,m:(i,i+"\n"+l,"process",m)
X=lambda i,l:(i,l,"external",None)
D=lambda i,l:(i,i+"\n"+l,"store",None)
dfd("S1","S1   Refined source maintenance",["A1","A2","A3","A4"],[
X("EC","Material data clerk"),D("D1","Source data"),P("A1","Parse submission","M11"),P("A2","Merge and validate edit","M12+M13"),P("A3","Commit revision","M14"),P("A4","Build maintenance response","M15")
],[("EC","A1","F01"),("D1","A2","F07"),("A1","A2","G01"),("A1","A4","G03"),("A2","A3","G02"),("A2","A4","G03"),("A3","D1","F06"),("A3","A4","G04"),("A4","EC","F02")],
[("in","EC","F01"),("in","D1","F07"),("out","EC","F02"),("out","D1","F06")])
dfd("S2","S2   Refined snapshot and BOM validation",["B1","B2","B3","B4","B5"],[
X("EP","Production planner"),D("D1","Source data"),X("P2.2","P2.2 Net and expand"),X("P3","P3 Publish results"),
P("B1","Read and check request","M21+M22"),P("B2","Validate graph","M23"),P("B3","Order tasks","M24"),P("B4","Freeze context","M25"),P("B5","Build invalid outcome","M26")
],[("EP","B1","F03"),("D1","B1","F08"),("B1","B2","G21"),("B1","B5","G24"),("B2","B3","G23"),("B2","B5","G24"),("B3","B4","G22"),("B4","P2.2","F12"),("B5","P3","F09.invalid")],
[("in","EP","F03"),("in","D1","F08"),("out","P2.2","F12"),("out","P3","F09")])
dfd("S3","S3   Refined multilevel demand and stock",["C1","C2","C3","C4","C5","C6","D3"],[
X("P2.1","P2.1 Validate"),X("P2.3","P2.3 Procurement and risk"),D("D3","Working stock"),
P("C1","Initialize batch balances","M31"),P("C2","Collect material dates","M32"),P("C3","Allocate stock","M33"),P("C4","Expand net MAKE","M34"),P("C5","Record BUY residuals","M35"),P("C6","Assemble net bundle","M36")
],[("P2.1","C1","F12"),("C1","D3","F17"),("C1","C2","G31"),("C2","C3","F14"),("D3","C3","F16"),("C3","D3","F15"),("C3","C4","F18"),("C4","C2","F19"),("C4","C5","G34"),("C5","C6","G35"),("C6","P2.3","F13")],
[("in","P2.1","F12"),("out","P2.3","F13")])
dfd("S4","S4   Refined purchasing and surplus",["D01","D02","D03","D04","D05","D4"],[
X("P2.2","P2.2 Net requirements"),X("S5","S5 Calendar and risk"),D("D4","Planned surplus pool"),
P("D01","Group dated shortages","M41"),P("D02","Consume eligible surplus","M42"),P("D03","Round purchase quantity","M43"),P("D04","Date bucket and update pool","M44"),P("D05","Assemble purchasing envelope","M45")
],[("P2.2","D01","F13"),("D01","D4","G44"),("D01","D02","G41"),("D4","D02","G45"),("D02","D03","G42"),("D03","D04","G43"),("D04","D4","G46"),("D04","D05","G47"),("D05","S5","G20")],
[("in","P2.2","F13"),("out","S5","G20")])
dfd("S5","S5   Refined timing risk and completed result",["E01","E02","E03"],[
X("S4","S4 Purchasing"),X("P3","P3 Publish results"),P("E01","Collect required dates","M51"),P("E02","Flag early dates","M53"),P("E03","Assemble complete result","M54")
],[("S4","E01","G20"),("E01","E02","G51"),("E02","E03","G52"),("E03","P3","F09.valid")],
[("in","S4","G20"),("out","P3","F09")])
dfd("S6","S6   Refined history trace and export",["F1","F2","F3","F4","F5"],[
X("P2","P2 Calculation outcome"),X("EP","Production planner"),D("D2","Saved plan batches"),
P("F1","Classify outcome","M61"),P("F2","Save complete batch","M62"),P("F3","Read selected history","M63"),P("F4","Build view and CSV","M64+M65"),P("F5","Build plan response","M66")
],[("P2","F1","F09"),("EP","F3","F04"),("F1","F2","G61"),("F1","F5","G62"),("F2","D2","F10"),("D2","F3","F11"),("F2","F4","G64"),("F3","F4","G63"),("F4","F5","G65"),("F5","EP","F05")],
[("in","P2","F09"),("in","EP","F04"),("in","D2","F11"),("out","D2","F10"),("out","EP","F05")])
dfd("bridge","P2.3   Purchasing and risk decomposition",["S4","S5"],[
X("P2.2","P2.2 Net requirements"),X("P3","P3 Publish results"),P("S4","Plan purchases","M40"),P("S5","Assess risk and complete","M50")
],[("P2.2","S4","F13"),("S4","S5","G20"),("S5","P3","F09.valid")],
[("in","P2.2","F13"),("out","P3","F09")])
# Split the three paired primitive nodes so every final DFD process maps to one named function.
def split_node(d,i,first,second,link):
 pos=next(j for j,n in enumerate(d["nodes"]) if n[0]==i); old=d["nodes"][pos]
 d["nodes"][pos:pos+1]=[P(i+"a",first[1],first[0]),P(i+"b",second[1],second[0])]
 d["internal"].remove(i); d["internal"] += [i+"a",i+"b"]
 es=[]
 for a,b,fid in d["edges"]:
  if b==i: b=i+"a"
  if a==i: a=i+"b"
  es.append((a,b,fid))
 es.append((i+"a",i+"b",link)); d["edges"]=es
# Error forwarding remains carried by the result envelope; split leaf readers/parsers return typed Result values.
f("G05","Merged source candidate","EditWork")
f("G25","Consistent request snapshot","ValidationEnvelope")
f("G66","Prepared report view","PresentationWork")
split_node(dfds[0],"A2",("M12","Merge source patch"),("M13","Validate source edit"),"G05")
split_node(dfds[1],"B1",("M21","Read consistent source"),("M22","Validate selected fields"),"G25")
split_node(dfds[5],"F4",("M64","Build saved trace view"),("M65","Encode requested CSV"),"G66")
dfds[5]["edges"]=[(a,b,"G65.csv" if a=="F4b" and b=="F5" else fid) for a,b,fid in dfds[5]["edges"]]
dfds[5]["edges"].append(("F4a","F5","G65.view"))
# Recreate DOT after node refinement.
for d in dfds:
 dot=dot_header(d["title"],"TB")
 for i,label,k,module in d["nodes"]:
  opts='shape=box, style="rounded,filled", fillcolor="#edf5ff"' if k=="process" else 'shape=record, style="filled", fillcolor="#fff8e8"' if k=="store" else 'shape=box, style="filled", fillcolor="#f1f5f9"'
  dot+=q(i)+" [label="+q(label)+", "+opts+"];\n"
 for a,b,fid in d["edges"]: dot+=q(a)+" -> "+q(b)+" [label="+q(fid)+"];\n"
 dot+="}"; d["dot"]=dot; figs["dfd-"+d["id"].lower()]["dot"]=dot
used_flow_ids={fid.split(".")[0] for d in dfds for _,_,fid in d["edges"]}
flows={i:v for i,v in flows.items() if not i.startswith("G") or i in used_flow_ids}
# Eliminate accidental opaque carry: dictionary work envelopes explicitly retain the inputs each process needs.
types=[
("Result[T]","tag OK or ERROR; value T only for OK; nonempty issues only for ERROR","No exceptions used as ordinary valid return data; I/O/date failures are handled by the coordinator."),
("Action / PublishCommand","MAINTAIN, CALCULATE, LIST, VIEW or CSV plus matching payload; publish accepts OUTCOME or QUERY","No arbitrary function names accepted."),
("TypedImport","dataset_kind, typed_rows, row_locations, request_id","All rows remain attributable to their original input."),
("EditWork","candidate SourceSet, TypedImport, request_id, issues","A2a merges; A2b validates. Includes original field locations."),
("CommitResult","request_id, revision_id or null, accepted_count, issues","Failed commit has no accepted records."),
("PreparationResult","tag READY or INVALID; prepared: PreparedContext only for READY; outcome: CalculationOutcome only for INVALID","M00 sends INVALID directly to M60, and calls M26 itself only for a later calculation failure."),
("MakeExpansion","optional MAKE line and child demands","The narrow M34 return; M30 retains the unmodified netted demand and prior accumulated state in the logical G34 carrier."),
("PreparedContext","context: E1 Context; graph: GraphIndex","Graph is derived and immutable; it is not a class."),
("GraphIndex","adjacency by material; reachable IDs; deterministic topological order; roots by task","Each parent precedes each child; disconnected selected roots included."),
("ValidationEnvelope","request, sources, supported rules, graph if available, ordered tasks if available, issues","Carries progressively validated data through B1a to B4."),
("BalanceMap / DemandMap","material ID -> Balance; task/material/date -> origins","Private to one M30 call; only M30 installs updated balances."),
("AllocationResult","netted demand, Allocation ledger row, new Balance","Ledger and origin totals reconcile."),
("ExpansionResult","current NettedEnvelope, optional MAKE line, child demands, accumulated NettingState","Retains the original netted BUY record so C5 can classify it. This is the G34 carrier, not only newly generated children."),
("NettingState","Context, GraphIndex, current task/material position, pending demand map, balances, accumulated netted demands/allocations/MAKE lines/BUY shortages","G31 and G35 are logical carriers; production interfaces pass only the relevant slices. Completion is emitted only after all tasks/materials finish."),
("ShortageGroup","material_id, needed_date, gross_shortage, shortage_ids","Across-task aggregation follows completed priority-based stock allocation."),
("SurplusLot","supply_bucket_id, material_id, arrival_date, remaining_qty","Nonnegative temporary planned excess, not on-hand stock."),
("SurplusAllocation","group, used_qty, remaining_gap, updated_lots, SurplusUse records","No future supply can cover an earlier demand."),
("PurchaseStep","PurchaseBucket, updated_lots, SurplusUse records","A zero-gap bucket remains in trace but creates no purchase recommendation."),
("PurchaseWork","NetBundle, ordered shortage groups, current group, surplus allocation, quantity if computed, accumulated purchase records","G41-G43/G47 retain policies, context and already accumulated output."),
("PurchasingEnvelope","NetBundle, purchase_buckets, surplus_uses, final_surplus_lots","G20 retains all input snapshots and original task due dates."),
("DatedEvent","event_id, TASK_DUE or MAKE_START or BUY_ORDER, date, task_id/material_id when relevant, source_line_id","Only actual required events are included; one aggregated purchase need not be duplicated per task."),
("RiskWork","PurchasingEnvelope, required events, assessed risks if available","G51/G52 keep enough data to assemble the final batch."),
("ReportView","batch IDs, filtered display tables, required trace closure, immutable snapshots","Filters affect display rows, not historical calculation."),
("CsvDocument","table_kind, filename, UTF-8 content, ordered column names","CSV uses saved values and includes stable identifiers."),
("PresentationWork","saved records, query/filter context, ReportView, optional CsvDocument, response status, issues","G66 bypasses CSV encoding for VIEW/LIST; G65 carries the selected representation.")
]
interfaces="# E2 Procedure Interfaces\n\nVersion 0.1, 26 September 2026. Signatures are language-neutral and describe plain records, sequences and functions. They do not mandate classes, Python or a UI framework.\n\n"
interfaces+="## Error and state conventions\n\nAll calculation data is passed explicitly. Pure functions do not read the database or mutate caller-owned input. Coordinators install returned values into private state. Result[T] carries either a value or located issues. INVALID input, DATE_RANGE, SOURCE_CONFLICT, STORAGE_READ_FAILED, STORAGE_WRITE_FAILED and NOT_FOUND cannot produce a saved successful batch. Unexpected technical failures abort the coordinator and are converted through the existing outer response interface; DFDs show business data paths rather than every infrastructure exception.\n\nRuleSnapshot is the documented supported configuration supplied by the application entry point. Request rule_version must match it; downstream functions receive it through Context rather than reading a mutable global.\n\n"
for s in subsystems:
 interfaces+="## "+s[0]+" "+s[1]+"\n\n"
 for i in [s[2]]+s[5]:
  a=mods[i]; interfaces+="### "+i+" "+a["name"]+"\n\n"+table(["Contract","Definition"],[("Inputs",a["inputs"]),("Returns",a["outputs"]),("State and I/O",a["effect"]),("Behavior",a["contract"])])+"\n"
interfaces+="## Entry coordinator\n\n"+table(["Function","Inputs","Returns","Behavior"],[(mods["M00"]["name"],mods["M00"]["inputs"],mods["M00"]["outputs"],mods["M00"]["contract"])])
interfaces+="\n## Additional record and envelope definitions\n\n"+table(["Type","Fields","Constraint"],types)
interfaces+="\n## Query refinement\n\nCSV requests add an explicit table_kind selector to E1 QueryRequest: MAKE, PURCHASE, ALLOCATION, TRACE or RISK. VIEW and LIST require no selector and bypass M65. PlanResponse.csv holds one requested CSV table; its export_columns describe that table. This is a presentation refinement, not a new business calculation. A later multi-file export can call the same procedure repeatedly.\n"
write("interfaces.md",interfaces)
structure_doc="# E2 Module Structure Design\n\nThe system has six business subsystems and one application coordinator. Seven structure charts are supplied: one overview and six subsystem charts. Each rectangular module denotes a callable procedure. Solid downward arrows mean calls; dashed arrows call a shared procedure owned elsewhere. REPEAT marks calls repeated over tasks/materials/dates; CONDITIONAL marks error or selected-mode branches. These are hierarchical module charts, not data-flow diagrams.\n\nI/Mxx and O/Mxx beside a call identify its data couples: the Inputs and Returns fields of module Mxx in interfaces.md. The returned Result tag, query mode and supply type are control information described in the coupling tables below. The interface table provides the full data names so abbreviated edge labels are unambiguous. The dotted ownership link to M52 is explicitly not a call.\n\n![Overall module structure](diagrams/structure-overview.svg)\n\n"
structure_doc+=table(["Subsystem","Responsibility","Entry procedure","Requirements","E1 process"],[(s[0],s[1],mods[s[2]]["name"],s[3],s[4]) for s in subsystems])
for s in subsystems:
 structure_doc+="\n## "+s[0]+" "+s[1]+"\n\n![Subsystem module structure](diagrams/structure-"+s[0].lower()+".svg)\n\n"
 rs=[]
 for a,b,mode in calls:
  if a==s[2] or a in s[5]:
   rs.append((a+" -> "+b,mode,mods[b]["inputs"],mods[b]["outputs"]))
 structure_doc+=table(["Call","Control condition","Input data couple","Return data couple"],rs)
structure_doc+="\n## Transformation from E1\n\nThe overall calculation is a transformation sequence: validate and freeze inputs, net multilevel demand against shared stock, calculate dated purchasing, assess risks, then retain and present the result. M00 controls this sequence; modules do not call each other's top-level controllers. Task-priority stock allocation and date-ordered procurement therefore have distinct owners.\n\nM30 owns D3 working stock; M40 owns D4 planned surplus. Neither writes D1. M14 exclusively commits master-data revisions; M62 exclusively commits D2 batches. M21 and M63 read their respective stores. Calendar subtraction M52 is shared by M34 and M44 so lead-time behavior is consistent. M50 calls risk procedures, not M52 redundantly.\n\n## Cohesion and coupling review\n\nS1 is cohesive around accepted data changes; S2 around valid immutable calculation input; S3 around net demand and stock; S4 around procurement quantities and excess; S5 around dates and complete risk results; S6 around retained output. Narrow leaf interfaces such as M33 and M43 take only the data needed. Aggregate Context/NetBundle carriers belong at coordinator boundaries, rather than mutable global state. Storage and presentation dependencies do not enter the pure arithmetic functions.\n\nCross-subsystem calls are M10 to read-only M21, M34/M44 to pure M52, and M00 to the M26 failure-outcome formatter. There is no controller call cycle. Sharing a date helper does not create an object hierarchy or make the entire risk subsystem a dependency of quantity calculation.\n"
write("module-structure.md",structure_doc)
refined="# E2 Refined Data Flow Diagrams\n\nAll six selected subsystems have a refined DFD. The additional bridge explains the decomposition of E1 P2.3 into S4 and S5. Rounded processes transform data; gray rectangles denote external entities or parent-level boundaries; gold store boxes marked D1-D4 denote stores. Arrows carry records, not calls. Each final primitive process maps to one procedure. E1 F01-F19 retain their established definitions.\n\n"
for d in dfds:
 refined+="## "+d["title"]+"\n\n![Refined DFD](diagrams/dfd-"+d["id"].lower()+".svg)\n\n"
 refined+=table(["Primitive process","Mapped procedure"],[(n[0]+" "+n[1].split("\n",1)[-1],n[3]+" "+mods[n[3]]["name"]) for n in d["nodes"] if n[2]=="process"])+"\n"
 refined+=table(["Flow","Meaning","Record type"],[(i,flows[i.split(".")[0]]["name"],flows[i.split(".")[0]]["type"]) for i in dict.fromkeys(e[2] for e in d["edges"])])+"\n"
refined+="## Iteration and retained data\n\nIn S3, C1 initializes stock once. M30 processes a complete task before the next task and waits for all parents before finalizing a shared material. C2 groups same-date requests; C3 nets them; C4 creates children from positive MAKE residuals only. C5 retains BUY residuals and forwards accumulated state; C6 emits F13 only after the entire run. Zero-net records remain in trace. G34 explicitly retains the original netted record so BUY requirements are not lost on the MAKE path.\n\nIn S4, D01 initializes an empty D4 pool once per run. Each material/date consumes prior eligible surplus, rounds the remaining gap, and updates D4. D05 emits G20 only after every dated group is processed. D4 is not physical stock. It is internal to the refinement of P2.3 and never adds an external parent input.\n\nS6 has an explicit optional conversion branch: F4a sends VIEW/LIST data directly to F5 through G65.view; CSV goes through F4b/M65 and G65.csv. Both flows are alternatives of the same PresentationWork record. The call chart records this selection. Commit and read failures are propagated to F05 by M60/M66; successful G64 exists only after a full commit.\n\nUnchanged context carried along a DFD flow is retained by its coordinator; a leaf function consumes only its documented slice and returns the transformed data. This pass-through convention explains the difference between a complete logical flow envelope and a narrow procedure signature. For example C1 returns BalanceMap while M30 carries forward the received Context in G31. F12 remains the E1 Context; the graph index in PreparedContext is derived from that same BOM, not a new external input.\n\nThe reusable calendar function M52 implements the date transformation inside C4/D04. It is shown in module charts and does not require an additional business data-flow boundary.\n\n## Added internal flow dictionary\n\n"+table(["ID","Data","Type"],[(i,v["name"],v["type"]) for i,v in flows.items() if i.startswith("G")])
refined+="\nEnvelope fields are defined in interfaces.md. F09.valid and F09.invalid are alternatives of F09. Parent/child balance compares their union, never treats them as unrelated flows.\n"
write("refined-dfd.md",refined)

data=r"""# E2 Data Storage Design

This is a proposed relational storage layout. Python and SQLite remain an implementation option, not a confirmed course constraint. Table descriptions define responsibilities and keys; no database has been created by this design.

## Source data and revisions

Master-data edits use copy-on-write revisions to make consistent snapshots straightforward for a small course project. A source transaction creates a new revision, copies unchanged rows, applies validated upserts, checks the expected old head, and switches the head only at commit. A conflict returns SOURCE_CONFLICT for explicit reload; no silent lost update. Old revisions are retained while referenced by history. This trades additional storage for simpler traceability; optimize only after measurement.

"""
data+=table(["Table","Key","Fields and constraints","Owner"],[
("source_revision","revision_id","created_at; optional parent_revision_id. Immutable after creation.","M14"),
("source_head","singleton_id = 1","current_revision_id references source_revision; compare-and-swap within commit.","M14"),
("material","(revision_id, material_id)","name, supply_type, unit, lead_time_days, min_purchase_qty, purchase_multiple; E1 domains.","M14"),
("bom_edge","(revision_id, parent_id, child_id)","qty_per > 0; both references use the same revision; graph cycles checked by procedures.","M14"),
("inventory_snapshot","(revision_id, snapshot_date, material_id)","on_hand >= reserved >= 0; material reference in the same revision.","M14"),
("production_task","(revision_id, task_id)","product_id, required_qty > 0, due_date, priority in 1/2/3. Run selection is not a stock reservation.","M14"),
("plan_batch","batch_id","created_at, source_revision_id, rule_version, baseline_date, status=SAVED, result_document.","M62")
])
data+="""\n## Canonical saved result

result_document is a canonical UTF-8 serialized CalculatedBatch document containing its complete source and rule snapshots, every netted demand, origin, allocation, manufacturing line, BUY shortage, purchase bucket, surplus link, risk and summary. E1 BatchRecord metadata wraps it. Preserve exact integers and date text; do not convert quantities to floating point during serialization. Collection ordering is deterministic.

One saved batch is one atomic record; do not split successful metadata from partially saved details. A write transaction either commits the whole document or rolls back. Future normalized result indexes must remain derived views of this canonical record. The current design reads and filters that saved document, which is sufficient as a proposed design for the stated coursework dataset; performance has not been measured.

A batch stores its own calculation snapshot even if the referenced master-data revision is later unavailable. Therefore historical export and source explanation do not depend on current master data.

## Data lifetime

D1 corresponds to source revisions and the current head. D2 corresponds to immutable plan batches. D3 BalanceMap and D4 surplus lots exist only inside one calculation and are discarded afterward. Saving a batch never writes inventory_snapshot or creates a real purchase order.

M21 reads the source head and matching rows in the same read transaction. The later planning calculation uses the frozen copy, so a subsequent maintenance edit does not change that run. M63 reads D2, not the current source head.

## Representation and error policy

IDs remain case-sensitive; perform ordinal ordering in the application rather than relying on database locale collation. Dates must be validated as calendar dates in addition to database field constraints. Use parameterized persistence operations and explicit transactions. The repository parameter denotes a set of function adapters or an opaque connection passed to procedures; no repository class or inheritance is required.

The internal arbitrary-precision integer model must survive the selected storage representation. If an implementation uses a bounded SQL integer, it must validate and report overflow, or store exact decimal text with exact parsing. Do not truncate a correct computed quantity. DATE_RANGE likewise aborts calculation without moving dates or saving partial results.
"""
write("data-storage-design.md",data)

# Render using the bundled Graphviz WASM and sharp, without network services.
write("model.json",json.dumps(dict(modules=mods,subsystems=subsystems,calls=calls,flows=flows,dfds=dfds,figures=figs),ensure_ascii=False,indent=2))
renderer=r"""const fs=require('fs');const path=require('path');
const deps=String.raw'C:\Users\许yq\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules';
const {instance}=require(path.join(deps,'@viz-js/viz/dist/viz.cjs'));
const sharp=require(path.join(deps,'sharp'));
(async()=>{const root=__dirname;const model=JSON.parse(fs.readFileSync(path.join(root,'model.json'),'utf8'));const viz=await instance();
for(const [id,fig] of Object.entries(model.figures)){const svg=viz.renderString(fig.dot,{format:'svg',engine:'dot'});fs.writeFileSync(path.join(root,'diagrams',id+'.svg'),svg);fs.writeFileSync(path.join(root,'diagrams',id+'.dot'),fig.dot);await sharp(Buffer.from(svg),{density:150}).png().toFile(path.join(root,'diagrams',id+'.png'));}
console.log('Rendered '+Object.keys(model.figures).length+' diagrams.');})().catch(e=>{console.error(e);process.exit(1)});
"""
# Avoid JavaScript tagged template escaping in the outer authoring transport.
renderer=renderer.replace("String.raw'C:", "'C:").replace("node_modules';","node_modules';")
renderer=renderer.replace("const deps='C:\\Users\\许yq\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules';","const deps="+json.dumps(r"C:\Users\许yq\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules")+";")
write("render.cjs",renderer)
subprocess.run([r"C:\Users\许yq\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",str(OUT/"render.cjs")],check=True)

checks=[]
def ck(name,condition):
 if not condition: raise AssertionError(name)
 checks.append(name)
for d in dfds:
 ids={n[0] for n in d["nodes"]}; internal=set(d["internal"]); actual=set()
 for a,b,fid in d["edges"]:
  baseid=fid.split(".")[0]
  ck(d["id"]+" endpoints "+fid,a in ids and b in ids)
  ck(d["id"]+" dictionary "+fid,baseid in flows)
  if (a in internal)!=(b in internal): actual.add(("in" if b in internal else "out",a if b in internal else b,baseid))
 ck(d["id"]+" boundary balance",actual==set(d["expected"]))
 for n in d["nodes"]:
  if n[2]=="process": ck(d["id"]+" primitive "+n[0],n[3] in mods and "+" not in n[3])
def e1_boundary(diagram_index, process_id):
 result=set()
 for e in base["diagrams"][diagram_index]["edges"]:
  a,b,fid=e["src"],e["dst"],e["flow"].split(".")[0]
  if a=="EP2": a="EP"
  if b=="EP2": b="EP"
  if b==process_id: result.add(("in",a,fid))
  if a==process_id: result.add(("out",b,fid))
 return result
for sid,index,parent in [("S1",1,"P1"),("S2",2,"P2.1"),("S3",2,"P2.2"),("S6",1,"P3"),("bridge",2,"P2.3")]:
 d=next(d for d in dfds if d["id"]==sid)
 ck(sid+" matches actual saved E1 parent boundary",set(d["expected"])==e1_boundary(index,parent))
for sid in ("S4","S5"):
 result=set()
 for a,b,fid in dfds[-1]["edges"]:
  if b==sid: result.add(("in",a,fid.split(".")[0]))
  if a==sid: result.add(("out",b,fid.split(".")[0]))
 ck(sid+" matches P2.3 bridge boundary",result==set(next(d for d in dfds if d["id"]==sid)["expected"]))

for a,b,mode in calls: ck("call target "+a+" "+b,a in mods and b in mods)
def visit(i,stack):
 ck("acyclic calls "+i,i not in stack)
 for a,b,_ in calls:
  if a==i: visit(b,stack+[i])
visit("M00",[])
ck("six subsystem charts",all("structure-"+s[0].lower() in figs for s in subsystems))
ck("six refined subsystem DFDs",all(any(d["id"]==s[0] for d in dfds) for s in subsystems))
used={f.split(".")[0] for d in dfds for _,_,f in d["edges"]}
# Remove unused reserved internal identifiers from published dictionary and model registry.
unused=[i for i in flows if i.startswith("G") and i not in used]
for i in unused: del flows[i]
ck("all E1 flows retained or deliberately superseded",set("F%02d"%i for i in range(1,20))<=used | {"F18","F19"})
ck("no netting or purchasing writes D1",not any(b=="D1" for d in dfds if d["id"] in ("S3","S4","S5") for a,b,f in d["edges"]))
write("verification.json",json.dumps(dict(check_count=len(checks),checks=checks,diagram_count=len(figs),module_count=len(mods)),indent=2))
verification="# E2 Design Verification\n\n26 September 2026. "+str(len(checks))+" structural assertions passed. These are document/model checks, not application tests.\n\nVerified: six subsystem DFDs and six subsystem structure charts plus overview/bridge; all primitive DFD processes map to one named procedure; flow references resolve; each refined diagram matches its declared E1 or bridge boundary; calls resolve and have no cycle; calculation subsystems do not write actual source inventory.\n\nVisual inspection of all generated charts: pending.\n\nOutstanding: actual group size and assignment, reviewed assumptions, real meeting and contribution records, final teacher naming/date clarification. No application implementation or E4/E5 execution is claimed.\n"
write("verification.md",verification)
report="# Module Design of the Material Requirements and Purchasing Plan System\n\n## E2 Developing Module Structure Diagrams\n\nVersion 0.1, 26 September 2026. Group number, member names and student IDs: [TO COMPLETE]. This draft continues E1 version 0.2 using structured analysis and procedural decomposition.\n\nThe design divides the project into six business subsystems. It supplies a refined DFD and a corresponding module structure chart for every subsystem, plus an overall call chart and a P2.3 decomposition bridge. Each final DFD process has a named procedure and an explicit data contract. The system has not yet been implemented.\n\n## 1 Scope and course requirements\n\nThe supplied E2 document asks for refined DFDs, module structure diagrams, member tasks, actual all-member review records and individual contributions, all in English. Subsystem and subsystem-chart counts must each be at least group size N. Six subsystems and six corresponding charts satisfy those two counts only if N is at most 6. N is still unknown; no unconditional compliance claim is made. If N is larger, split genuine responsibilities and regenerate both DFDs and module charts, rather than counting the overview as another subsystem.\n\nThe E2 sheet states 15 October 2026 and repeats an experiment-1 filename. Confirm the teacher's naming and schedule before final submission. This draft is not an FTP submission and does not contain invented group meetings.\n\n## 2 Preserved requirements and decisions\n\nTask priority remains first: priority, due date, then ordinal task ID. All tasks share one batch stock balance. Only net MAKE demand creates child requirements. Procurement runs after stock allocation and groups shortages by material/date, consumes earlier planned surplus and applies minimum/multiple rules. Dates use calendar days; history and calculation do not modify actual inventory.\n\nInteger quantities, interpreting task quantity as delivery demand, ordinal origin attribution and all-or-nothing source imports remain the E1 draft assumptions. The language, database product and UI are still provisional. Plain records and function adapters are sufficient; no classes, inheritance or object-oriented modeling are introduced.\n\n## 3 Subsystems and module structure\n\n"+structure_doc.split("\n\n",1)[1]+"\n## 4 Refined logical models\n\n"+refined.split("\n\n",1)[1]
report+="\n## 5 Procedure contracts\n\n"+interfaces.split("\n\n",1)[1]
report+="\n## 6 Data ownership and storage\n\n"+data.split("\n\n",1)[1]
report+="\n## 7 End to end design walkthrough\n\nFor CASE01, M20 freezes A demand 100 and the validated graph. M30 initializes A/B/C/D balances 0/20/50/100. A nets to 100 and creates B 200 and C 300. B nets to 180 and creates D 720. C nets to BUY 250; D nets to BUY 620. M40 groups those dated BUY residuals; with minimum 0 and multiple 1 the purchases remain 250 and 620. Calls to M52 give A start October 18, B start October 15, C order October 14 and D order October 10. M50 finds no date risk against October 1. Only then does M60/M62 save the complete calculated batch.\n\nFor CASE04, M24 places the later-due priority-1 HIGH task before the earlier-due priority-2 LOW task. M30 retains the same balance map between tasks, so HIGH takes B 20, C 50 and D 100. M40 may list LOW purchase dates earlier without undoing that stock ownership. For CASE05, M42/M44 carry a planned excess of 7 from an October 10 purchase of 30 to the October 11 gap of 7, so M43 returns zero for the latter date. D3 remains separate from this D4 surplus.\n\nFor a shared component with two parent paths, M23 supplies a parent-before-child order. M30 finishes both parents before M32 processes the child; M32 retains both origins. A naive depth-first immediate allocation would not guarantee the required earliest-date behavior, so it is not the selected control design.\n\nThese are design walkthroughs against independent expected values, not software test results.\n\n## 8 Traceability to later detailed design and testing\n\n"
report+=table(["Requirement","Main procedures","Existing acceptance cases"],[
("FR01","M10-M15","CASE09"),
("FR02","M20, M22, M24, M25","CASE04, CASE11"),
("FR03","M22, M23","CASE09"),
("FR04","M30, M32, M34, M35, M36","CASE01, CASE07"),
("FR05","M31, M33","CASE04, CASE06, CASE11"),
("FR06","M40-M45","CASE03, CASE05"),
("FR07","M34, M44, M50-M54","CASE02, CASE08"),
("FR08","M60-M66","CASE10")
])
report+="\nE3 will specify algorithms and pseudocode, using the required detailed-design diagram types. Suitable functions include M23, M32, M33, M34, M42, M43, M52 and M62. The required number depends on actual N. E4 must later exercise the required five coverage criteria for selected modules; E5 must apply equivalence classes and boundary values. No design check is counted as those runtime tests.\n\n## 9 Member task allocation\n\n"
report+=table(["Actual member and ID","Assigned subsystem","Refined DFD and module chart","Interface/data work","Review evidence"],[("[TO COMPLETE]","S"+str(i),"[TO ASSIGN]","[TO ASSIGN]","[TO COMPLETE]") for i in range(1,7)])
report+="\nRows represent six responsibility areas, not six asserted group members. One member may own multiple areas; every actual member needs attributable work.\n\n## 10 Actual review meeting record\n\nMeeting date/time [TO COMPLETE]; location/channel [TO COMPLETE]; attendees [TO COMPLETE]; reviewed version [TO COMPLETE]. No meeting has been claimed by this draft.\n\n"
report+=table(["Review question","Actual finding","Owner and correction evidence"],[
("Are subsystem and chart counts at least N?","[TO COMPLETE]","[TO COMPLETE]"),
("Does every primitive DFD process map to a callable function?","[TO COMPLETE]","[TO COMPLETE]"),
("Do data couples, flows and interface types agree?","[TO COMPLETE]","[TO COMPLETE]"),
("Can stock or planned surplus be consumed twice?","[TO COMPLETE]","[TO COMPLETE]"),
("Are task-priority order and purchase-date order kept separate?","[TO COMPLETE]","[TO COMPLETE]"),
("Are error handling, snapshot history and atomic save unambiguous?","[TO COMPLETE]","[TO COMPLETE]")
])
report+="\n## 11 Individual contribution record\n\nFor each actual member, record name and student ID [TO COMPLETE], assigned subsystem [TO COMPLETE], diagrams/procedures analyzed [TO COMPLETE], design decisions and sources studied [TO COMPLETE], review corrections [TO COMPLETE], and concrete evidence [TO COMPLETE]. Do not replace actual work with generic contribution claims.\n\n## 12 Verification and remaining work\n\n"+str(len(checks))+" structural checks passed for this document model. Application behavior, performance, E4 coverage and E5 system tests have not been executed. Before submission complete the actual member information, assumptions review, all-member meeting and teacher clarification. The current deliverable is a reviewable E2 design draft.\n"
write("E2-report-en.md",report)
# Simple local Markdown-to-HTML rendering with embedded vector figures.
def inline(s): return html.escape(s)
def tohtml(s):
 lines=s.splitlines(); out=[]; para=[]; i=0
 def flush():
  if para: out.append("<p>"+inline(" ".join(para))+"</p>"); para.clear()
 while i<len(lines):
  t=lines[i]
  if not t.strip(): flush(); i+=1; continue
  if t.startswith("#"):
   flush(); n=len(t)-len(t.lstrip("#")); text=t[n:].strip(); out.append(f"<h{n}>"+inline(text)+f"</h{n}>"); i+=1; continue
  if t.startswith("!["):
   flush(); path=re.search(r"\(([^)]+)\)",t).group(1); svg=(OUT/path).read_text(encoding="utf-8"); svg=svg[svg.index("<svg"):]
   out.append('<figure>'+svg+"</figure>"); i+=1; continue
  if t.startswith("|"):
   flush(); rows=[]
   while i<len(lines) and lines[i].startswith("|"):
    row=[v.strip() for v in lines[i].strip("|").split("|")]
    if not all(re.fullmatch("[-: ]+",v) for v in row): rows.append(row)
    i+=1
   out.append('<div class="table-wrap"><table><thead><tr>'+"".join("<th>"+inline(v)+"</th>" for v in rows[0])+"</tr></thead><tbody>")
   for row in rows[1:]: out.append("<tr>"+"".join("<td>"+inline(v)+"</td>" for v in row)+"</tr>")
   out.append("</tbody></table></div>"); continue
  para.append(t); i+=1
 flush(); return "\n".join(out)
css="body{font:16px/1.7 Arial,sans-serif;background:#f4f6f8;color:#17212e;margin:0}main{max-width:1240px;margin:28px auto;padding:48px;background:white}h1,h2,h3{color:black;line-height:1.3}h1{font-size:30px}h2{font-size:24px;margin-top:40px}h3{font-size:19px;margin-top:26px}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.5;margin:16px 0 28px}td,th{border:1px solid #d9d9d9;padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e8eef5}tr:nth-child(even){background:#fafbfd}figure{margin:24px 0;overflow:auto;border:1px solid #e2e7ed;padding:10px}svg{width:100%;height:auto;min-width:1050px}nav{background:#edf4fb;padding:14px}nav a{margin-right:18px;color:#214b7d}.table-wrap{overflow:auto}@media(max-width:700px){main{padding:20px;margin:0}}@media print{body{background:white;font-size:10pt}main{margin:0;padding:0}nav{display:none}table{font-size:8pt}figure, tr{break-inside:avoid}h2,h3{break-after:avoid}svg{min-width:0;width:100%;max-height:170mm}figure,.table-wrap{overflow:visible}@page{size:A4 landscape;margin:15mm}}"
content=tohtml(report)
counter=[0]
def heading(match):
 counter[0]+=1; return '<h2 id="sec'+str(counter[0])+'">'+match.group(1)+'</h2>'
content=re.sub(r"<h2>(.*?)</h2>",heading,content)
nav="<nav>"+''.join('<a href="#'+i+'">'+html.escape(t)+"</a>" for i,t in re.findall(r'<h2 id="([^"]+)">([^<]+)</h2>',content) if re.match(r"[1-9][0-9]? ",t))+"</nav>"
write("E2-report-en.html",'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>E2 Module Design</title><style>'+css+'</style></head><body><main>'+nav+content+'</main></body></html>')
write("README.md","# E2 材料说明\n\n2026-09-26。先打开 E2-report-en.html 阅读整份英文报告；E2-report-en.md 为可编辑正文。\n\n本轮包含6个业务子系统、6张细化DFD及1张分解衔接图、6张子系统模块结构图及1张总体图，合计14张图。"+str(len(mods))+"个过程式函数的接口、数据传递、错误与状态责任已定义。另有逻辑表设计、E1对应关系和后续验收案例映射。\n\n单独材料：module-structure.md、refined-dfd.md、interfaces.md、data-storage-design.md。diagrams内提供SVG和PNG，可插入后续Word报告。\n\n本轮不包含应用编码或E3详细算法图。组员人数N仍未知，子系统和对应图数量只有在N<=6时才满足人数要求；不得直接宣称最终达标。真实分工、会议和贡献记录留待填写。整数数量等既有假设仍待评审。\n")
write("model.json",json.dumps(dict(modules=mods,subsystems=subsystems,calls=calls,flows=flows,dfds=dfds,figures=figs),ensure_ascii=False,indent=2))
print(json.dumps(dict(modules=len(mods),diagrams=len(figs),checks=len(checks),out=str(OUT)),ensure_ascii=False))
