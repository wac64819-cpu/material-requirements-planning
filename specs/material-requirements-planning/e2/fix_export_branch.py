from pathlib import Path
p=Path(r"C:\Users\许yq\Desktop\软件工程\specs\material-requirements-planning\e2\build_e2.py")
s=p.read_text(encoding="utf-8")
needle='# Recreate DOT after node refinement.'
s=s.replace(needle,'dfds[5]["edges"]=[(a,b,"G65.csv" if a=="F4b" and b=="F5" else fid) for a,b,fid in dfds[5]["edges"]]\ndfds[5]["edges"].append(("F4a","F5","G65.view"))\n'+needle)
s=s.replace("S6's CSV node represents optional conversion: VIEW/LIST pass the ReportView onward unchanged; CSV invokes M65.","S6 has an explicit optional conversion branch: F4a sends VIEW/LIST data directly to F5 through G65.view; CSV goes through F4b/M65 and G65.csv. Both flows are alternatives of the same PresentationWork record.")
p.write_text(s,encoding="utf-8")
