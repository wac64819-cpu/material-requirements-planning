# E2 Procedure Interfaces

Version 0.1, 26 September 2026. Signatures are language-neutral and describe plain records, sequences and functions. They do not mandate classes, Python or a UI framework.

## Error and state conventions

All calculation data is passed explicitly. Pure functions do not read the database or mutate caller-owned input. Coordinators install returned values into private state. Result[T] carries either a value or located issues. INVALID input, DATE_RANGE, SOURCE_CONFLICT, STORAGE_READ_FAILED, STORAGE_WRITE_FAILED and NOT_FOUND cannot produce a saved successful batch. Unexpected technical failures abort the coordinator and are converted through the existing outer response interface; DFDs show business data paths rather than every infrastructure exception.

RuleSnapshot is the documented supported configuration supplied by the application entry point. Request rule_version must match it; downstream functions receive it through Context rather than reading a mutable global.

## S1 Source maintenance

### M10 maintain_sources

| Contract | Definition |
|---|---|
| Inputs | MaintenanceSubmission, repository |
| Returns | MaintenanceOutcome |
| State and I/O | Coordinator |
| Behavior | Read current revision; parse, merge and validate one submission; commit only a fully accepted candidate. |

### M11 parse_submission

| Contract | Definition |
|---|---|
| Inputs | MaintenanceSubmission |
| Returns | Result[TypedImport] |
| State and I/O | Pure |
| Behavior | Parse required fields without rounding, preserve row locations, reject duplicate input keys and unknown columns where policy requires. |

### M12 merge_source_patch

| Contract | Definition |
|---|---|
| Inputs | SourceSet, TypedImport |
| Returns | SourceSet |
| State and I/O | Pure |
| Behavior | Apply explicit upserts to a copy. Stock upserts identify both snapshot date and material. No implicit deletion or mutation of the original. |

### M13 validate_source_edit

| Contract | Definition |
|---|---|
| Inputs | SourceSet candidate, TypedImport |
| Returns | List[Issue] |
| State and I/O | Pure |
| Behavior | Check uniqueness, referenced IDs, integer/date domains and stock bounds. Detect incompatible BUY edges and cycles in changed BOM; full selected MAKE completeness is checked in S2. |

### M14 commit_source_revision

| Contract | Definition |
|---|---|
| Inputs | repository, expected_revision, SourceSet candidate |
| Returns | Result[revision_id] |
| State and I/O | Writes D1 atomically |
| Behavior | In one transaction create an immutable revision, compare the current revision, move the head, and commit; conflicts and failures roll back. |

### M15 make_maintenance_response

| Contract | Definition |
|---|---|
| Inputs | request_id, accepted_count, List[Issue], commit_result |
| Returns | MaintenanceOutcome |
| State and I/O | Pure |
| Behavior | REJECTED has zero accepted records. On commit failure do not report accepted data. |

## S2 Snapshot and BOM validation

### M20 prepare_context

| Contract | Definition |
|---|---|
| Inputs | PlanningRequest, repository, RuleSnapshot |
| Returns | PreparationResult |
| State and I/O | Coordinator |
| Behavior | Obtain one consistent snapshot, validate selected data and BOM, order tasks and freeze a read-only context. Return READY with prepared input, or call M26 and return INVALID with that outcome. |

### M21 read_source_snapshot

| Contract | Definition |
|---|---|
| Inputs | repository, baseline_date or null |
| Returns | Result[SourceSet] |
| State and I/O | Reads D1 |
| Behavior | Read source head and all required revision rows in one read transaction. Null date is used for maintenance reads; planning selects the baseline stock snapshot. |

### M22 validate_selected_data

| Contract | Definition |
|---|---|
| Inputs | PlanningRequest, SourceSet, RuleSnapshot |
| Returns | List[Issue] |
| State and I/O | Pure |
| Behavior | Reject no selection, duplicate or unknown task IDs, unsupported rules, invalid fields and missing reachable stock. Snapshot date must equal baseline. |

### M23 validate_and_index_bom

| Contract | Definition |
|---|---|
| Inputs | SourceSet, selected_task_ids |
| Returns | Result[GraphIndex] |
| State and I/O | Pure |
| Behavior | Validate all selected reachable edges including stock-covered branches; return adjacency and deterministic parent-before-child order or located graph errors. |

### M24 order_tasks

| Contract | Definition |
|---|---|
| Inputs | List[Task], selected_task_ids |
| Returns | List[Task] |
| State and I/O | Pure |
| Behavior | Sort by priority ascending, due date ascending, then ordinal task ID. Preserve no import-row tie-break. |

### M25 freeze_context

| Contract | Definition |
|---|---|
| Inputs | request, sources, rules, ordered_tasks, GraphIndex |
| Returns | PreparedContext |
| State and I/O | Pure |
| Behavior | Copy validated inputs and initial availability into E1 Context; attach only a derived graph index outside the retained E1 Context. |

### M26 make_invalid_outcome

| Contract | Definition |
|---|---|
| Inputs | request_id, nonempty List[Issue] |
| Returns | CalculationOutcome |
| State and I/O | Pure |
| Behavior | Return INVALID with null result and blocking issues. Do not manufacture an empty successful batch. |

## S3 Demand and shared inventory

### M30 net_requirements

| Contract | Definition |
|---|---|
| Inputs | PreparedContext |
| Returns | Result[NetBundle] |
| State and I/O | Coordinator; private memory only |
| Behavior | Own the batch balance map. Complete each task before the next; visit materials in parent-before-child order, then dates ascending. |

### M31 initialize_balances

| Contract | Definition |
|---|---|
| Inputs | request_id, List[Stock] |
| Returns | BalanceMap |
| State and I/O | Pure |
| Behavior | Create available quantities as on_hand minus reserved exactly once per run. |

### M32 collect_material_demands

| Contract | Definition |
|---|---|
| Inputs | task_id, material_id, DemandMap |
| Returns | List[Demand] |
| State and I/O | Pure |
| Behavior | For this task/material collect all contributions, group by date, preserve origins and return dates ascending. The caller must first finish all parents. |

### M33 allocate_stock

| Contract | Definition |
|---|---|
| Inputs | Demand, Balance |
| Returns | AllocationResult |
| State and I/O | Pure |
| Behavior | Allocate min(balance,gross). Split origin attribution by ordinal BOM path then origin ID. Return residual, ledger and new balance; do not mutate caller inputs. |

### M34 expand_make_demand

| Contract | Definition |
|---|---|
| Inputs | NettedDemand, Material, child_edges |
| Returns | Result[MakeExpansion] |
| State and I/O | Pure |
| Behavior | For positive MAKE net quantity derive start date, one MAKE row and children from attributed net origins. Zero net yields no MAKE row or children. Calls M52. |

### M35 record_buy_shortage

| Contract | Definition |
|---|---|
| Inputs | NettedDemand, Material |
| Returns | BuyShortage or null |
| State and I/O | Pure |
| Behavior | Return a positive BUY residual with date/source links; otherwise return null. |

### M36 assemble_net_bundle

| Contract | Definition |
|---|---|
| Inputs | Context, netted_demands, allocations, make_lines, shortages, final_balances |
| Returns | Result[NetBundle] |
| State and I/O | Pure |
| Behavior | Check gross=allocated+net, origin totals, stock conservation and reference integrity before returning the completed bundle. |

## S4 Purchasing and planned surplus

### M40 plan_purchases

| Contract | Definition |
|---|---|
| Inputs | NetBundle |
| Returns | Result[PurchasingEnvelope] |
| State and I/O | Coordinator; private memory only |
| Behavior | Use only BUY residuals after existing-stock allocation completes; iterate material IDs and needed dates with one separate surplus pool per material. |

### M41 group_buy_shortages

| Contract | Definition |
|---|---|
| Inputs | List[BuyShortage] |
| Returns | List[ShortageGroup] |
| State and I/O | Pure |
| Behavior | Group by material and needed date across tasks; preserve shortage IDs. Sort material ID ordinal, then date. |

### M42 consume_surplus

| Contract | Definition |
|---|---|
| Inputs | ShortageGroup, List[SurplusLot] |
| Returns | SurplusAllocation |
| State and I/O | Pure |
| Behavior | Consume only lots available by the needed date, earliest arrival then supply bucket ID. Return remaining gap, updated lots and source-use links. |

### M43 round_purchase_qty

| Contract | Definition |
|---|---|
| Inputs | remaining_gap, minimum_qty, purchase_multiple |
| Returns | Int >= 0 |
| State and I/O | Pure |
| Behavior | Zero gap returns zero even with a positive minimum. Otherwise use exact integer ceiling of max(gap,minimum) to the multiple. |

### M44 finalize_purchase_bucket

| Contract | Definition |
|---|---|
| Inputs | ShortageGroup, SurplusAllocation, purchase_qty, Material |
| Returns | Result[PurchaseStep] |
| State and I/O | Pure |
| Behavior | Build the dated bucket and update the returned pool with new rounding excess; no order date for zero purchase. Calls M52 only for positive purchases. |

### M45 assemble_purchase_envelope

| Contract | Definition |
|---|---|
| Inputs | NetBundle, purchase_buckets, surplus_uses, surplus_lots |
| Returns | Result[PurchasingEnvelope] |
| State and I/O | Pure |
| Behavior | Check quantity/date conservation and produce the complete purchasing result, retaining zero-purchase buckets for trace. |

## S5 Calendar and timing risk

### M50 complete_plan

| Contract | Definition |
|---|---|
| Inputs | PurchasingEnvelope |
| Returns | Result[CalculationOutcome] |
| State and I/O | Coordinator |
| Behavior | Collect required events, assess dates against baseline, assemble totals and return VALID with the calculated result. |

### M51 collect_required_dates

| Contract | Definition |
|---|---|
| Inputs | PurchasingEnvelope |
| Returns | List[DatedEvent] |
| State and I/O | Pure |
| Behavior | Include every selected task due date and positive manufacturing/purchase start; retain event/task/material links. Ignore nonexistent zero-quantity orders. |

### M52 subtract_calendar_days

| Contract | Definition |
|---|---|
| Inputs | Date needed_date, Int >= 0 lead_days |
| Returns | Result[Date] |
| State and I/O | Pure |
| Behavior | Subtract calendar days including weekends and leap days. Zero is valid; return DATE_RANGE if the result cannot be represented. |

### M53 flag_early_dates

| Contract | Definition |
|---|---|
| Inputs | List[DatedEvent], baseline_date |
| Returns | List[Issue] |
| State and I/O | Pure |
| Behavior | Only dates strictly before baseline are RISK; retain original date and positive difference in calendar days. |

### M54 assemble_calculated_batch

| Contract | Definition |
|---|---|
| Inputs | PurchasingEnvelope, List[Issue] risks |
| Returns | CalculatedBatch |
| State and I/O | Pure |
| Behavior | Attach net bundle, procurement, surplus uses, risks and count summary. Do not add quantities across unrelated units. |

## S6 History trace and export

### M60 publish_results

| Contract | Definition |
|---|---|
| Inputs | PublishCommand, repository, clock, id_factory |
| Returns | PlanResponse |
| State and I/O | Coordinator |
| Behavior | For VALID outcome save first, then expose saved data; INVALID becomes rejection. For queries load saved history, build views and optionally CSV. |

### M61 classify_outcome

| Contract | Definition |
|---|---|
| Inputs | CalculationOutcome |
| Returns | Result[CalculatedBatch] |
| State and I/O | Pure |
| Behavior | Pass a valid complete result or return its blocking issues; enforce the tagged union. |

### M62 save_batch_atomic

| Contract | Definition |
|---|---|
| Inputs | CalculatedBatch, repository, batch_id, created_at |
| Returns | Result[BatchRecord] |
| State and I/O | Writes D2 atomically |
| Behavior | Insert one canonical result document including all snapshots in a transaction. Return SAVED only after commit. |

### M63 read_history

| Contract | Definition |
|---|---|
| Inputs | QueryRequest, repository |
| Returns | Result[List[BatchRecord]] |
| State and I/O | Reads D2 |
| Behavior | Read exact saved documents; return NOT_FOUND for missing detail/export batches; listing may return an empty list. |

### M64 build_trace_view

| Contract | Definition |
|---|---|
| Inputs | List[BatchRecord], filters |
| Returns | Result[ReportView] |
| State and I/O | Pure |
| Behavior | Filter display rows while retaining their linked source, demand, allocation and supply records. Never consult current source data. |

### M65 encode_csv

| Contract | Definition |
|---|---|
| Inputs | ReportView, table_kind |
| Returns | CsvDocument |
| State and I/O | Pure |
| Behavior | UTF-8 CSV with a header, proper quoting and ISO dates. Export MAKE, PURCHASE, ALLOCATION, TRACE or RISK; preserve batch identifiers. |

### M66 make_plan_response

| Contract | Definition |
|---|---|
| Inputs | request_id, outcome_status, saved_records, view, csv, issues |
| Returns | PlanResponse |
| State and I/O | Pure |
| Behavior | Map failures and successes consistently. A failed save returns SAVE_FAILED with no successful saved records. |

## Entry coordinator

| Function | Inputs | Returns | Behavior |
|---|---|---|---|
| handle_action | Action, payload, repository, supported_rules, clock, id_factory | ApplicationResponse | Dispatch maintenance, calculation, history or export. During calculation call S2 then S3 then S4 then S5 then S6; stop at the first error and convert its issues through M26 before publishing rejection. |

## Additional record and envelope definitions

| Type | Fields | Constraint |
|---|---|---|
| Result[T] | tag OK or ERROR; value T only for OK; nonempty issues only for ERROR | No exceptions used as ordinary valid return data; I/O/date failures are handled by the coordinator. |
| Action / PublishCommand | MAINTAIN, CALCULATE, LIST, VIEW or CSV plus matching payload; publish accepts OUTCOME or QUERY | No arbitrary function names accepted. |
| TypedImport | dataset_kind, typed_rows, row_locations, request_id | All rows remain attributable to their original input. |
| EditWork | candidate SourceSet, TypedImport, request_id, issues | A2a merges; A2b validates. Includes original field locations. |
| CommitResult | request_id, revision_id or null, accepted_count, issues | Failed commit has no accepted records. |
| PreparationResult | tag READY or INVALID; prepared: PreparedContext only for READY; outcome: CalculationOutcome only for INVALID | M00 sends INVALID directly to M60, and calls M26 itself only for a later calculation failure. |
| MakeExpansion | optional MAKE line and child demands | The narrow M34 return; M30 retains the unmodified netted demand and prior accumulated state in the logical G34 carrier. |
| PreparedContext | context: E1 Context; graph: GraphIndex | Graph is derived and immutable; it is not a class. |
| GraphIndex | adjacency by material; reachable IDs; deterministic topological order; roots by task | Each parent precedes each child; disconnected selected roots included. |
| ValidationEnvelope | request, sources, supported rules, graph if available, ordered tasks if available, issues | Carries progressively validated data through B1a to B4. |
| BalanceMap / DemandMap | material ID -> Balance; task/material/date -> origins | Private to one M30 call; only M30 installs updated balances. |
| AllocationResult | netted demand, Allocation ledger row, new Balance | Ledger and origin totals reconcile. |
| ExpansionResult | current NettedEnvelope, optional MAKE line, child demands, accumulated NettingState | Retains the original netted BUY record so C5 can classify it. This is the G34 carrier, not only newly generated children. |
| NettingState | Context, GraphIndex, current task/material position, pending demand map, balances, accumulated netted demands/allocations/MAKE lines/BUY shortages | G31 and G35 are logical carriers; production interfaces pass only the relevant slices. Completion is emitted only after all tasks/materials finish. |
| ShortageGroup | material_id, needed_date, gross_shortage, shortage_ids | Across-task aggregation follows completed priority-based stock allocation. |
| SurplusLot | supply_bucket_id, material_id, arrival_date, remaining_qty | Nonnegative temporary planned excess, not on-hand stock. |
| SurplusAllocation | group, used_qty, remaining_gap, updated_lots, SurplusUse records | No future supply can cover an earlier demand. |
| PurchaseStep | PurchaseBucket, updated_lots, SurplusUse records | A zero-gap bucket remains in trace but creates no purchase recommendation. |
| PurchaseWork | NetBundle, ordered shortage groups, current group, surplus allocation, quantity if computed, accumulated purchase records | G41-G43/G47 retain policies, context and already accumulated output. |
| PurchasingEnvelope | NetBundle, purchase_buckets, surplus_uses, final_surplus_lots | G20 retains all input snapshots and original task due dates. |
| DatedEvent | event_id, TASK_DUE or MAKE_START or BUY_ORDER, date, task_id/material_id when relevant, source_line_id | Only actual required events are included; one aggregated purchase need not be duplicated per task. |
| RiskWork | PurchasingEnvelope, required events, assessed risks if available | G51/G52 keep enough data to assemble the final batch. |
| ReportView | batch IDs, filtered display tables, required trace closure, immutable snapshots | Filters affect display rows, not historical calculation. |
| CsvDocument | table_kind, filename, UTF-8 content, ordered column names | CSV uses saved values and includes stable identifiers. |
| PresentationWork | saved records, query/filter context, ReportView, optional CsvDocument, response status, issues | G66 bypasses CSV encoding for VIEW/LIST; G65 carries the selected representation. |

## Query refinement

CSV requests add an explicit table_kind selector to E1 QueryRequest: MAKE, PURCHASE, ALLOCATION, TRACE or RISK. VIEW and LIST require no selector and bypass M65. PlanResponse.csv holds one requested CSV table; its export_columns describe that table. This is a presentation refinement, not a new business calculation. A later multi-file export can call the same procedure repeatedly.
