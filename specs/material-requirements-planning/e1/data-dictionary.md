# E1 Data Dictionary

Version 0.2, 26 September 2026. Logical records for structured analysis; these are not classes or physical database tables.

## Conventions

ID is a nonempty trimmed, case-sensitive string. ID sorting is ordinal and independent of locale. Text is Unicode text. Int is an exact integer; reject decimal quantities rather than rounding. Date is a valid YYYY-MM-DD calendar date. Timestamp is ISO 8601 with a timezone. List[T] is a finite sequence of T. Fields are required unless explicitly nullable. Empty lists are allowed unless otherwise stated. All quantities use the material's fixed unit. No stock row may be assumed to exist with a zero quantity.

## Data flows

| ID | Name | Composition | Source and destination | Validation and meaning |
|---|---|---|---|---|
| F01 | Maintenance submission | MaintenanceSubmission | Data clerk -> P1 | A submitted dataset and its input location; never silently round invalid quantities. |
| F02 | Maintenance outcome | MaintenanceOutcome | P1 -> Data clerk | Accepted record counts or located errors. Proposed import policy: validate the entire submission before committing it. |
| F03 | Planning request | PlanningRequest | Planner -> P2 / P2.1 | Selected task IDs, baseline date and rule version; reject an empty selection. |
| F04 | Query and export request | QueryRequest | Planner -> P3 | A saved batch, optional filters, and VIEW or CSV output mode. |
| F05 | Plan response | PlanResponse | P3 -> Planner | Saved results, history views, export data, or located errors. Never label a failed save as successful. |
| F06 | Accepted source records | SourceSet | P1 -> D1 | Validated source updates. Only maintenance changes source data. |
| F07 | Existing source records | SourceSet | D1 -> P1 | Current records for uniqueness, reference and update checks. |
| F08 | Planning source records | SourceSet | D1 -> P2 / P2.1 | One consistent read of selected tasks and their reachable materials, BOM and stock. |
| F09 | Calculation outcome | CalculationOutcome | P2 / P2.1 / P2.3 -> P3 | Tagged union: INVALID with errors, or VALID with a complete calculated batch. F09.invalid and F09.valid denote its alternatives. |
| F10 | Immutable batch record | BatchRecord | P3 -> D2 | Successful results plus complete input and rule snapshots, written atomically. No actual inventory update. |
| F11 | Historical batch records | List[BatchRecord] | D2 -> P3 | Saved snapshots and matching results used for history, trace and CSV. |
| F12 | Validated planning context | Context | P2.1 -> P2.2 / P2.2.1 | Valid selected data, deterministic task order, initial availability and rule snapshot. |
| F13 | Net requirements bundle | NetBundle | P2.2 / P2.2.3 -> P2.3 | Complete context, net manufacturing requirements, dated BUY shortages, demand provenance and allocation ledger. |
| F14 | Allocation candidates | CandidateEnvelope | P2.2.1 -> P2.2.2 | Context plus ordered, merged task-material-date demand buckets with every contributing source. |
| F15 | Working stock updates | List[Balance] | P2.2.2 -> D3 | Replacement batch balances after allocation; nonnegative and isolated from actual stock. |
| F16 | Working stock balances | List[Balance] | D3 -> P2.2.2 | Current batch balances before allocation, indexed by material. |
| F17 | Initial working balances | List[Balance] | P2.2.1 -> D3 | Available stock initialized once per batch from on_hand minus reserved. |
| F18 | Netted demand records | NettedEnvelope | P2.2.2 -> P2.2.3 | Context, demands with allocation and residual quantities, and their allocation records. |
| F19 | Child demand records | List[Demand] | P2.2.3 -> P2.2.1 | New child requests from positive MAKE residuals; child date equals parent planned start. |

F09.invalid contains the INVALID alternative and F09.valid the VALID alternative of F09. These are partitions of the same parent flow, not additional external interfaces. F12 context is carried inside F14, F18 and F13; their consumers therefore receive the BOM, policies and baseline they need.

## Data stores

| ID | Name | Composition | Access | Lifetime and integrity |
|---|---|---|---|---|
| D1 | Source data | SourceSet | P1 writes; P1 and P2.1 read | Material, BOM, task and inventory data. No planning process writes to this store. |
| D2 | Saved plan batches | List[BatchRecord] | P3 writes and reads | All-or-nothing saved input snapshots and output history. |
| D3 | Working stock | List[Balance] | P2.2.1 initializes; P2.2.2 reads and updates | Transient, private to one calculation; introduced inside P2.2, not a new parent boundary. |

## Record definitions

### Material

| Field | Type | Meaning and constraint |
|---|---|---|
| material_id | ID | Unique material identifier. |
| name | Text | Nonempty display name. |
| supply_type | MAKE or BUY | BUY must be a BOM leaf; reachable MAKE requires a valid BOM. |
| unit | Text | One fixed unit per material; no conversion. |
| lead_time_days | Int >= 0 | Calendar days; zero allowed. |
| min_purchase_qty | Int >= 0 or null | BUY default 0; null for MAKE. |
| purchase_multiple | Int > 0 or null | BUY default 1; null for MAKE. |

### BomEdge

| Field | Type | Meaning and constraint |
|---|---|---|
| parent_id, child_id | ID | References to Material; pair is unique; cannot be equal. |
| qty_per | Int > 0 | Child units needed per newly manufactured parent unit. |

The reachable graph must be acyclic. Reusing a child on multiple paths is valid.

### Stock

| Field | Type | Meaning and constraint |
|---|---|---|
| material_id | ID | Unique within snapshot; references Material. |
| snapshot_date | Date | Must equal the planning baseline. |
| on_hand, reserved | Int >= 0 | reserved <= on_hand; missing reachable stock blocks calculation. |

### Task

| Field | Type | Meaning and constraint |
|---|---|---|
| task_id | ID | Unique task identifier. |
| product_id | ID | References Material. |
| required_qty | Int > 0 | Delivery demand; existing finished stock may satisfy it. |
| due_date | Date | Required delivery date. |
| priority | 1, 2 or 3 | 1 is highest. |
| selected | Boolean | Selection in the planning request determines batch participation. |

### RuleSnapshot

| Field | Type | Meaning and constraint |
|---|---|---|
| version | ID | Immutable identifier for the exact rule set. |
| quantity_mode | INTEGER | Provisional integer quantities, awaiting user confirmation. |
| task_order | Text | priority ASC, due_date ASC, task_id ordinal ASC. |
| calendar_mode | CALENDAR_DAYS | No holiday or weekend adjustment. |
| scope_policy | Text | Single warehouse; no transit supply, safety stock, loss, substitutes or capacity constraints. |
| purchase_policy | Text | Date aggregation, earlier surplus first, then minimum and multiple. |
| attribution_policy | Text | Preserve source quantities and links; deterministic allocation detail as stated in Section 5. |

### SourceSet

| Field | Type | Meaning and constraint |
|---|---|---|
| source_revision | ID | Identifies one consistent dataset revision. |
| materials | List[Material] | Referenced master data. |
| bom | List[BomEdge] | Reachable edges for calculation; submitted/current edges for maintenance. |
| stocks | List[Stock] | Relevant stock snapshot rows. |
| tasks | List[Task] | Relevant tasks. |

### MaintenanceSubmission

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Correlates request and response. |
| dataset_kind | MATERIAL / BOM / STOCK / TASK | Submitted dataset. |
| records | List[raw records] | Untrusted field text before conversion to the corresponding record schema. |
| source_name | Text | Form name or import filename. |
| row_locations | List[Text] | Source row/field identifiers retained for error feedback. |

Import/update operations are logical requirements here. Physical file columns and update interfaces are deferred to E2.

### Issue

| Field | Type | Meaning and constraint |
|---|---|---|
| code | ID | Stable error or warning category. |
| severity | BLOCKING or RISK | Input errors block a batch; date risks remain visible in valid results. |
| message | Text | Readable cause. |
| source_location | Text | Dataset, row, field, task or BOM edge. |
| task_id, material_id | ID or null | Relevant identifiers when known. |
| computed_date | Date or null | Required for a date risk; retain the original date. |
| days_before_baseline | Int >= 0 or null | Required for a date risk; strictly positive when flagged. |

### MaintenanceOutcome

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Matches submission. |
| status | ACCEPTED or REJECTED | Proposed all-or-nothing submission policy. |
| accepted_count, rejected_count | Int >= 0 | Rejected submission has accepted_count 0. |
| issues | List[Issue] | Located validation issues. |

### PlanningRequest

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Correlates computation and response. |
| selected_task_ids | Nonempty List[ID] | Unique, existing IDs; no unselected task consumes stock. |
| baseline_date | Date | Reference for inventory snapshot and date risks. |
| rule_version | ID | Resolves to the retained RuleSnapshot. |

### QueryRequest

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Correlates response. |
| batch_id | ID or null | Required for batch detail and export; null for listing history. |
| mode | LIST / VIEW / CSV | Requested representation. |
| task_id, material_id | ID or null | Optional filters; never recompute history from current master data. |

### Context

| Field | Type | Meaning and constraint |
|---|---|---|
| request | PlanningRequest | Original request. |
| sources | SourceSet | Validated immutable calculation snapshot. |
| rules | RuleSnapshot | Exact rules used. |
| ordered_task_ids | List[ID] | Sorted priority first, then due date, then ordinal task ID. |
| initial_balances | List[Balance] | on_hand minus reserved for each reachable material. |

### Balance

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Identifies transient calculation scope. |
| material_id | ID | Balance key within that scope. |
| available_qty | Int >= 0 | Current remaining stock, or starting amount in F17. |

### Origin

| Field | Type | Meaning and constraint |
|---|---|---|
| origin_id | ID | Stable identifier within one calculation. |
| task_id | ID | Root task. |
| parent_demand_id | ID or null | Null for root demand; links a child back to its parent. |
| bom_path | List[ID] | Ordered material path from root to this material. |
| contribution_qty | Int > 0 | This path's contribution to the merged demand. |

### Demand

| Field | Type | Meaning and constraint |
|---|---|---|
| demand_id | ID | Unique task-material-date bucket identifier. |
| task_id, material_id | ID | Associated task and material. |
| needed_date | Date | Root due date or immediate parent's start date. |
| gross_qty | Int > 0 | Sum of contributing origin quantities. |
| origins | Nonempty List[Origin] | Retain every path after merging. |

Merge only within the same task, material and date at this stage. Multiple dates remain separate.

### CandidateEnvelope

| Field | Type | Meaning and constraint |
|---|---|---|
| context | Context | Carried through the calculation; does not bypass validation. |
| candidates | List[Demand] | Deterministic demand order; collect all parent contributions before finalizing a material. |

### Allocation

| Field | Type | Meaning and constraint |
|---|---|---|
| allocation_id, demand_id | ID | Allocation record and linked demand. |
| task_id, material_id | ID | Allocation ownership. |
| needed_date | Date | Demand date. |
| before_qty, allocated_qty, after_qty | Int >= 0 | allocated=min(before,gross); after=before-allocated. |
| source_allocations | List[OriginAllocation] | Attribution within merged demand. |

### OriginAllocation

| Field | Type | Meaning and constraint |
|---|---|---|
| origin_id | ID | Contributing path. |
| allocated_qty, residual_qty | Int >= 0 | Their sum equals the origin contribution. |

Proposed trace tie-break: within one task-material-date bucket, sort origins by ordinal BOM path then origin ID before allocating stock. This changes attribution, not the bucket total.

### NettedDemand

| Field | Type | Meaning and constraint |
|---|---|---|
| demand | Demand | Original merged demand. |
| allocated_qty, net_qty | Int >= 0 | gross_qty = allocated_qty + net_qty. |
| source_allocations | List[OriginAllocation] | Preserves attributable residuals for child expansion. |

### NettedEnvelope

| Field | Type | Meaning and constraint |
|---|---|---|
| context | Context | Retained validated data and rules. |
| records | List[NettedDemand] | Demand outcomes. |
| allocations | List[Allocation] | Matching stock ledger records. |

### MakeLine

| Field | Type | Meaning and constraint |
|---|---|---|
| line_id, demand_id | ID | Output and demand linkage. |
| task_id, material_id | ID | Root task and manufactured material. |
| gross_qty, allocated_qty | Int >= 0 | Demand and stock usage. |
| make_qty | Int > 0 | Net manufacture only; zero creates no production line. |
| needed_date, start_date | Date | start_date = needed_date - lead_time_days. |
| origin_ids | List[ID] | Source trace. |

### BuyShortage

| Field | Type | Meaning and constraint |
|---|---|---|
| shortage_id, demand_id | ID | Shortage and demand linkage. |
| task_id, material_id | ID | Source task and BUY material. |
| needed_date | Date | Required availability date. |
| shortage_qty | Int > 0 | Residual after existing stock allocation. |
| origin_ids | List[ID] | Source trace; zero residual creates no shortage row. |

### NetBundle

| Field | Type | Meaning and constraint |
|---|---|---|
| context | Context | Includes baseline, all material policies and original task due dates. |
| demands | List[NettedDemand] | All processed buckets, including zero-net outcomes. |
| allocations | List[Allocation] | Complete allocation ledger. |
| make_lines | List[MakeLine] | Only positive net manufacturing requirements. |
| buy_shortages | List[BuyShortage] | Dated positive BUY residuals. |
| final_balances | List[Balance] | Remaining actual-stock working balances, never written to D1. |

### PurchaseBucket

| Field | Type | Meaning and constraint |
|---|---|---|
| bucket_id, material_id | ID | Unique material-date aggregate. |
| needed_date | Date | Required arrival date. |
| shortage_ids | List[ID] | All source shortages merged for that day. |
| gross_shortage, surplus_used, remaining_gap | Int >= 0 | remaining_gap = gross_shortage - surplus_used. |
| purchase_qty | Int >= 0 | 0 if gap=0; otherwise ceil(max(gap,min)/multiple)*multiple. |
| order_date | Date or null | needed_date - lead time only if purchase_qty > 0. |
| surplus_after | Int >= 0 | Balance after consuming prior surplus and adding current rounding excess. |
| adjustment_reason | Text | No gap, exact requirement, minimum quantity, multiple rounding, or combination. |

Keep a zero-purchase bucket for traceability; display only positive quantities as purchase recommendations.

### SurplusUse

| Field | Type | Meaning and constraint |
|---|---|---|
| supply_bucket_id, demand_bucket_id | ID | Source purchase bucket and consuming dated bucket. |
| qty | Int > 0 | Theoretical rounding surplus transferred. |
| source_arrival_date, use_date | Date | source_arrival_date <= use_date. |

Never treat planned surplus as actual stock or carry it into another batch. Earliest arrival first; same-date ties use ordinal bucket ID.

### CalculatedBatch

| Field | Type | Meaning and constraint |
|---|---|---|
| net_bundle | NetBundle | Full inputs, net demand and allocation trace. |
| purchase_buckets | List[PurchaseBucket] | Date-ordered procurement calculation. |
| surplus_uses | List[SurplusUse] | Trace of planned excess consumption. |
| risks | List[Issue] | RISK entries; task due or necessary start/order date before baseline. |
| summary | Summary | Counts, not sums of unrelated material units. |

### Summary

| Field | Type | Meaning and constraint |
|---|---|---|
| task_count, make_line_count, purchase_line_count, risk_count | Int >= 0 | Purchase line count includes positive purchase quantities only. |

### CalculationOutcome

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Correlates F03. |
| status | VALID or INVALID | Discriminator. |
| result | CalculatedBatch or null | Required only for VALID. |
| errors | List[Issue] | Nonempty BLOCKING list for INVALID; result must be null. |

### BatchRecord

| Field | Type | Meaning and constraint |
|---|---|---|
| batch_id | ID | Unique immutable historical identifier. |
| created_at | Timestamp | ISO 8601 time with timezone. |
| result | CalculatedBatch | Entire calculated result, snapshots and rule version retained together. |
| save_status | SAVED | Exposed only after complete successful persistence. |

New calculation creates a new batch. Failed persistence creates no successful historical record.

### PlanResponse

| Field | Type | Meaning and constraint |
|---|---|---|
| request_id | ID | Calculation or query correlation. |
| status | SAVED / VIEW / EXPORTED / REJECTED / SAVE_FAILED / NOT_FOUND | Discriminator; no success response on a failed save. |
| records | List[BatchRecord] | Saved result or requested history; empty on failure. |
| issues | List[Issue] | Located errors or risks. |
| csv | Text or null | UTF-8 CSV representation of selected saved records for EXPORTED. |
| export_columns | List[Text] | Named identifiers, quantities, dates and links for exported detail tables. |

CSV must match the selected immutable batch. Separate tables may be exported for production, purchasing, allocation and provenance.

## Cross record invariants

- Each demand gross quantity equals the sum of its origins and equals allocated plus net quantity.
- Every allocation leaves a nonnegative balance. Per material, initial balance minus all allocations equals final balance.
- Only positive MAKE net quantities generate child requests; child contribution equals attributable parent net times BOM usage.
- Purchase buckets merge across tasks only after priority allocation of existing stock has finished.
- Surplus transfer dates never run backwards; each source bucket's rounding excess cannot be consumed more than once.
- Batch snapshots, rules, details, trace links and summary are saved together or no successful batch is exposed.
- Every reference in a saved result resolves within its retained snapshot and trace. Quantities from different material units are never combined as a meaningful purchase total.
