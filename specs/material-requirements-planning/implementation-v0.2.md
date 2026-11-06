# Calculation Prototype v0.2

Date: 2026-09-26. Status: working in-memory prototype, not a complete application or final E3/E4/E5 submission.

## Scope and module mapping

Python standard-library functions and ordinary records are used. There are no custom classes. Python remains the provisional prototype language.

| E2 responsibility | Implementation | Remaining boundary |
|---|---|---|
| S2 / M22–M25: validation, graph, ordering, snapshot | validate_and_prepare | Repository reader absent; several designed leaves remain consolidated |
| S3 / M30–M35: netting, inventory, MAKE explosion, BUY shortages | net_requirements and existing allocate_stock | Further function extraction can follow finalized detailed design |
| S4 / M40–M44: groups, excess, rounding, buckets | plan_purchases and existing round_purchase_qty | No purchase execution |
| S5: dates, risks, result | required_start, calculate_plan, existing date/risk leaves | No capacity feasibility calculation |
| S1 and S6: maintenance, storage, history, export | JSON input and demonstration output only | Database, atomic storage, history and CSV pending |

The public interface is `calculate_plan(sources, request)`, returning status, result and errors. A blocking error yields INVALID with a null result, even if found during date calculation. This adapter does not implement all 39 E2 interfaces verbatim.

## Algorithm

1. Copy and normalize input; validate schemas and references. Check selected-task reachability, required BOM/stock and acyclicity. Produce a deterministic topological order.
2. Initialize balances once. Order tasks by priority, due date and ordinal ID.
3. Per task, visit materials with every parent before its children. Merge each material/date demand and its origins, then process dates earliest first. Allocate stock and expand only positive MAKE residuals.
4. After all tasks, group BUY shortages by material/date. Consume earlier eligible planned excess, round the gap and record a new excess lot. Zero-purchase buckets remain only for tracing.
5. Assess task due dates and positive MAKE/BUY start dates. Preserve early dates and flag risks. Return snapshots, calculations, trace references and counts.

## Boundaries

All supplied rows receive schema and reference validation. Structural MAKE/BUY rules, cycles and missing stock are checked across the full graph reachable from selected tasks, including stock-covered nodes. An unrelated malformed row can reject the input snapshot; an unrelated disconnected cycle is outside the selected graph.

Dates are strict ISO calendar dates. Quantities reject decimals, booleans and negative values. IDs are trimmed, case sensitive and ordinally ordered. Only rule version `prototype-v0.2` is accepted. Inputs and actual inventory remain unchanged.

JSON outputs are replaceable demonstration artifacts, not immutable historical batches or atomic persistence. Performance for the proposed 200-material/500-edge/100-task workload has not been measured. Retaining full BOM paths can increase memory use on heavily branching graphs.

## Executed evidence

- results/planner-verification.json: 114/114 checks passed, including independent expectations and source hashes.
- results/verification.json: existing four-leaf regression, 38/38 passed. M43 source and normal-path traces remain unchanged.
- Scenarios cover E1 quantities/dates, priority, source residual propagation, shared-child date order, stock boundaries, merged purchasing, excess, rejection, repeatability and conservation.
- results/demo-plans.json and .html: three actual examples.

These checks do not establish full system testing, five-criterion white-box coverage for all selected modules, group-count compliance or completed group review.
