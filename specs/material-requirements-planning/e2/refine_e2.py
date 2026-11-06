from pathlib import Path
p=Path(r"C:\Users\许yq\Desktop\软件工程\specs\material-requirements-planning\e2\build_e2.py")
s=p.read_text(encoding="utf-8")
s=s.replace("import json, re, html, subprocess, sys","import json, re, html, subprocess, sys, textwrap")
s=s.replace('calls += [("M10","M21","shared")','calls += [("M00","M26","shared"),("M10","M21","shared")')
s=s.replace('return i+"\\n"+n','return i+"\\n"+"\\n".join(textwrap.wrap(n,24))')
s=s.replace('structure("overview","System module structure","M00",[s[2] for s in subsystems])','structure("overview","System module structure","M00",[s[2] for s in subsystems],["M26"])')
s=s.replace('dot_header(title,"LR")','dot_header(title,"TB")').replace('dot_header(d["title"],"LR")','dot_header(d["title"],"TB")')
s=s.replace('("G22","Field checked envelope","ValidationEnvelope")','("G22","Ordered task envelope","ValidationEnvelope")')
s=s.replace('Cross-subsystem calls are M10 to read-only M21 and M34/M44 to pure M52.','Cross-subsystem calls are M10 to read-only M21, M34/M44 to pure M52, and M00 to the M26 failure-outcome formatter.')
s=s.replace('Stop at the first error.','Stop at the first error.')
s=s.replace('then S6; stop at the first error.','then S6; stop at the first error and convert its issues through M26 before publishing rejection.')
s=s.replace('record boxes denote stores','gold store boxes marked D1-D4 denote stores')
# Reduce long horizontal layouts; browser figures remain readable at a normal width.
# Published dictionaries contain only flows actually present in a refined diagram.
marker='# Eliminate accidental opaque carry:'
s=s.replace(marker,'used_flow_ids={fid.split(".")[0] for d in dfds for _,_,fid in d["edges"]}\nflows={i:v for i,v in flows.items() if not i.startswith("G") or i in used_flow_ids}\n'+marker)
s=s.replace('Unused reserved G identifiers are excluded from the generated coverage checks and may be removed without changing a diagram. ','')
s=s.replace('The reusable calendar function M52 implements','Unchanged context carried along a DFD flow is retained by its coordinator; a leaf function consumes only its documented slice and returns the transformed data. This pass-through convention explains the difference between a complete logical flow envelope and a narrow procedure signature. For example C1 returns BalanceMap while M30 carries forward the received Context in G31. F12 remains the E1 Context; the graph index in PreparedContext is derived from that same BOM, not a new external input.\\n\\nThe reusable calendar function M52 implements')
needle='for a,b,mode in calls: ck("call target "+a+" "+b,a in mods and b in mods)'
addition='''def e1_boundary(diagram_index, process_id):
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
'''
s=s.replace(needle,addition+'\n'+needle)
p.write_text(s,encoding="utf-8")
