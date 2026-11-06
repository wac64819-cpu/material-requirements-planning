from pathlib import Path
p=Path(r"C:\Users\许yq\Desktop\软件工程\specs\material-requirements-planning\e2\build_e2.py")
s=p.read_text(encoding="utf-8")
s=s.replace('"MaintenanceSubmission, repository","Result[MaintenanceOutcome]"','"MaintenanceSubmission, repository","MaintenanceOutcome"')
s=s.replace('"PlanningRequest, repository, RuleSnapshot","Result[PreparedContext]"','"PlanningRequest, repository, RuleSnapshot","PreparationResult"')
s=s.replace('Obtain one consistent snapshot, validate selected data and BOM, order tasks and freeze a read-only context.','Obtain one consistent snapshot, validate selected data and BOM, order tasks and freeze a read-only context. Return READY with prepared input, or call M26 and return INVALID with that outcome.')
s=s.replace('"NettedDemand, Material, child_edges","Result[ExpansionResult]"','"NettedDemand, Material, child_edges","Result[MakeExpansion]"')
s=s.replace('("PreparedContext","context: E1 Context; graph: GraphIndex"','("PreparationResult","tag READY or INVALID; prepared: PreparedContext only for READY; outcome: CalculationOutcome only for INVALID","M00 sends INVALID directly to M60, and calls M26 itself only for a later calculation failure."),\n("MakeExpansion","optional MAKE line and child demands","The narrow M34 return; M30 retains the unmodified netted demand and prior accumulated state in the logical G34 carrier."),\n("PreparedContext","context: E1 Context; graph: GraphIndex"')
p.write_text(s,encoding="utf-8")
