# E2 Data Storage Design

This section records the original proposed relational layout. Table descriptions define logical responsibilities and keys. The v0.4 implementation below uses local SQLite with canonical source/result documents; this is a project implementation choice, not a confirmed course technology constraint.

## Source data and revisions

Master-data edits use copy-on-write revisions to make consistent snapshots straightforward for a small course project. A source transaction creates a new revision, copies unchanged rows, applies validated upserts, checks the expected old head, and switches the head only at commit. A conflict returns SOURCE_CONFLICT for explicit reload; no silent lost update. Old revisions are retained while referenced by history. This trades additional storage for simpler traceability; optimize only after measurement.

| Table | Key | Fields and constraints | Owner |
|---|---|---|---|
| source_revision | revision_id | created_at; optional parent_revision_id. Immutable after creation. | M14 |
| source_head | singleton_id = 1 | current_revision_id references source_revision; compare-and-swap within commit. | M14 |
| material | (revision_id, material_id) | name, supply_type, unit, lead_time_days, min_purchase_qty, purchase_multiple; E1 domains. | M14 |
| bom_edge | (revision_id, parent_id, child_id) | qty_per > 0; both references use the same revision; graph cycles checked by procedures. | M14 |
| inventory_snapshot | (revision_id, snapshot_date, material_id) | on_hand >= reserved >= 0; material reference in the same revision. | M14 |
| production_task | (revision_id, task_id) | product_id, required_qty > 0, due_date, priority in 1/2/3. Run selection is not a stock reservation. | M14 |
| plan_batch | batch_id | created_at, source_revision_id, rule_version, baseline_date, status=SAVED, result_document. | M62 |

## Canonical saved result

result_document is a canonical UTF-8 serialized CalculatedBatch document containing its complete source and rule snapshots, every netted demand, origin, allocation, manufacturing line, BUY shortage, purchase bucket, surplus link, risk and summary. E1 BatchRecord metadata wraps it. Preserve exact integers and date text; do not convert quantities to floating point during serialization. Collection ordering is deterministic.

One saved batch is one atomic record; do not split successful metadata from partially saved details. A write transaction either commits the whole document or rolls back. Future normalized result indexes must remain derived views of this canonical record. The current design reads and filters that saved document, which is sufficient as a proposed design for the stated coursework dataset; performance has not been measured.

A batch stores its own calculation snapshot even if the referenced master-data revision is later unavailable. Therefore historical export and source explanation do not depend on current master data.

## Data lifetime

D1 corresponds to source revisions and the current head. D2 corresponds to immutable plan batches. D3 BalanceMap and D4 surplus lots exist only inside one calculation and are discarded afterward. Saving a batch never writes inventory_snapshot or creates a real purchase order.

M21 reads the source head and matching rows in the same read transaction. The later planning calculation uses the frozen copy, so a subsequent maintenance edit does not change that run. M63 reads D2, not the current source head.

## Representation and error policy

IDs remain case-sensitive; perform ordinal ordering in the application rather than relying on database locale collation. Dates must be validated as calendar dates in addition to database field constraints. Use parameterized persistence operations and explicit transactions. The repository parameter denotes a set of function adapters or an opaque connection passed to procedures; no repository class or inheritance is required.

The internal arbitrary-precision integer model must survive the selected storage representation. If an implementation uses a bounded SQL integer, it must validate and report overflow, or store exact decimal text with exact parsing. Do not truncate a correct computed quantity. DATE_RANGE likewise aborts calculation without moving dates or saving partial results.

## Implemented adapter v0.4 (2026-09-30)

storage.py implements three physical tables: source_revision, source_head and plan_batch. The four source entity collections are stored together in the revision's canonical JSON document rather than normalized physical tables. Validation remains procedural. BEGIN IMMEDIATE serializes writers; the expected source head is compared inside the transaction before the new revision and head are committed together. UPDATE/DELETE triggers protect immutable revision and batch rows.

The workbench explicitly saves a validated source version, including the baseline and task selection. Successful calculations separately commit complete immutable plan documents with independent input snapshot identifiers. Reading historical plans never invokes the calculator or consults the latest source head. Storage errors produce SAVE_FAILED at the HTTP boundary, not a successful response with an unsaved result.

This implements the small-project snapshot/persistence responsibility, not every proposed normalized table or all 39 original function interfaces. CSV, restore-to-editor and performance acceptance remain pending. See ../persistence-v0.4.md for executed evidence and UI behavior.
