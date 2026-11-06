Experiment 5 | English technical report | 22 October 2026

This report evaluates the implemented material planning system against its user requirements through external HTTP requests and real browser operations. The final HTTP run completed 125 cases, with 125 passing. Browser suites supplied 65 additional passing checks. A CSV field-length defect found by boundary testing was corrected and retested. An intermittent Windows connection reset on an oversized request remains a documented transport observation.

Table 1.1 Report identity
| Item | Value |
| --- | --- |
| Project | Design and Implementation of a Production Requirements and Procurement Planning System Based on Multilevel Bills of Materials |
| Method | Structured procedural implementation; equivalence partitioning and boundary value analysis |
| Group | 2 members; [Group number], [Member A name and student ID], [Member B name and student ID] |
| Test scope | Source maintenance S1; integrated planning S2 to S5; history and export S6 |
| Status | Technical execution and reporting complete within stated scope; actual group review and contributions pending |

## 1 Objectives and requirements

The E5 guide requires at least as many important modules or subsystems as group members, explicit preconditions and postconditions, test cases combining equivalence partitioning and boundary value analysis, and an English report. The three selected functional groups cover the six existing subsystems and exceed the two-member minimum. Grouping S2 to S5 into one external calculation scenario does not redefine the E2 architecture.

Expected results come from the written BR01 to BR09 rules, FR01 to FR08 acceptance conditions, CSV limits and persistence behavior. Internal coverage, private functions and database tables are not used to decide pass or fail. Source files were inspected only to identify public interfaces and diagnose observed defects; the black-box runner imports no application modules.

## 2 Selected subsystems and contracts

Table 2.1 Preconditions and postconditions
| Group | Preconditions | Postconditions |
| --- | --- | --- |
| S1 Source maintenance | Current source/request records; named UTF-8 CSV tables or JSON source save; expected previous revision for saving. | Preview either returns READY with a complete candidate or INVALID with located errors. Preview never saves. Valid save creates a version; invalid or stale save preserves current data. |
| S2 to S5 Integrated planning | Selected task IDs; complete material, BOM and stock records; valid quantities, dates and rule version; matching stock/baseline date. | VALID returns net production, dated purchasing, stock/source trace and risk; a complete batch is saved. INVALID returns blocking errors without a saved batch. Persisted inventory is not deducted. |
| S6 History and export | Existing saved batch ID, supported export kind or a nonnegative history offset. Source records may have changed since the batch was created. | History returns the original snapshot and result. CSV uses that batch and carries its ID. Missing batches and invalid requests reject. Restart retains saved state. |

Invalid inputs intentionally violate these preconditions one at a time where practical. Their expected postcondition is an informative rejection with no partial persistence. Cross-record consistency cases cover relationships that individual field partitions cannot express.

### 2.1 Acceptance limits

Task demand and BOM usage are positive integers; stock and lead time are nonnegative integers; priority is 1, 2 or 3. Reserved stock must not exceed on-hand stock. CSV numeric inputs and the browser editor are restricted to the JavaScript safe-integer maximum 9007199254740991. The native JSON calculation interface uses Python integers and does not impose that same upper bound. These are separate entry-point contracts.

Each CSV file is limited to 500000 UTF-8 bytes and 5000 records. The combined HTTP JSON request is limited to 2000000 bytes. Boundary tests keep other constraints valid: the row-limit fixture stays below the byte limit, while the file-size fixture has only two material rows and uses one long name field.

## 3 Test environment and independent fixtures

Execution: 2026-10-22T12:29:30.179266+08:00. Python 3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]. Platform Windows-11-10.0.26200-SP0. The runner starts the real loopback HTTP server on an unused local port, creates a new test database under results/e5-runs, and stops only that server. It does not open or write the production planning.sqlite3 database.

All 371 recorded HTTP exchanges have request/response artifacts, except a transport exception would instead have an explicit error record. Request bodies preserve exact JSON or CSV bytes. Test IDs bind the readable case register to those artifacts. The final report is based on a completed run, not a partial result emitted during cleanup.

Table 3.1 Base fixture
| Record | Fields |
| --- | --- |
| Material P | MAKE product; unit pcs; lead time 2 days |
| Material R | BUY raw material; unit pcs; lead time 3 days; minimum 0; purchase multiple 5 |
| BOM | P requires 2 units of R |
| Stocks | P and R each have on_hand 0 and reserved 0; snapshot date 2026-11-01 |
| Task T1 | Product P; quantity 10; due 2026-11-20; priority 2; selected |
| Request | Baseline 2026-11-01; rule version prototype-v0.2; request ID E5 |

Independent base oracle: P has no stock, so manufacture 10. Start P on 18 November. Raw demand is 10 times 2, or 20. No raw stock exists; 20 already meets the multiple of 5, so purchase 20 for arrival on 18 November and order on 15 November. No date precedes the baseline.

The BUY-root variant removes P and all BOM edges, keeps R and its stock, and points T1 directly to R. The multilevel fixture adds S: P requires 2 S and S requires 3 R. With P stock 2, S stock 4 and R on_hand 5/reserved 1, demand10 gives P8, S12, raw gross36, raw gap32 and purchase35. S lead time1 makes the raw arrival17 November and order14 November.

## 4 Equivalence partitions and boundary selections

Table 4.1 Partition model
| Partition | Valid classes | Invalid classes | Witness families |
| --- | --- | --- | --- |
| EP01 Quantities | Positive native JSON integers; nonnegative stock; CSV/browser safe integers | Zero demand or usage; negative stock; decimal, Boolean or text quantity; CSV number above safe maximum | Q, B, ST, RS, NUM |
| EP02 Task order | Priority1 to3; known selected tasks; priority/date/ID tie-breaking | Priority0 or4; empty/unknown selection | PR, ORD, INV00 to01 |
| EP03 BOM graph | Known acyclic references; MAKE parents and BUY leaves | Unknown/duplicate edge; self/multiple-node cycle; missing BOM/stock; BUY with children | INV02 to08, NET |
| EP04 Purchasing | Positive gaps; exact/rounded lots; zero gap; same/later-date surplus | Nonpositive multiple; negative minimum; future surplus used backward is forbidden | MU, LOT, SUR |
| EP05 Dates | Canonical calendar dates; leap day; dates before/on/after baseline | Impossible/noncanonical date; backward arithmetic below supported date range | LD, DT, CAL, INV09 |
| EP06 CSV input | Four exact headers; valid quoted UTF-8 text; supported table set | Empty selection/file; unknown table; bad headers/columns/quotes/numbers; row/byte excess | CSV, ROW, BYTE, NUM |
| EP07 Persistence | New/current revision; existing batch; supported export; nonnegative offset | Stale revision; invalid save; absent batch; invalid kind or offset | H, EX, HX, PAGE, RESTART |

Table 4.2 Boundary value matrix
| Boundary | Values executed | Reason |
| --- | --- | --- |
| Demand lower bound | 0, 1, 2 | Just below, at and above positive lower bound |
| CSV safe-integer maximum | 9007199254740990, 9007199254740991, 9007199254740992 | Below, at and above entry-point maximum |
| Priority | 0, 1, 2, 3, 4 | Outside both ends and all valid discrete classes |
| Stock versus demand20 | 0, 19, 20, 21; negative stock separately | Shortage, exact coverage and surplus |
| Reserved with on-hand20 | -1, 0, 1, 20, 21 | Lower and cross-field upper limits |
| Lot multiple10 | Gap9, 10, 11; minimum9, 10, 11 with gap1 | Below, exact and above a lot threshold |
| Order versus baseline | One day before, same day, one day after | Risk is strict less-than, not less-than-or-equal |
| CSV records | 4999, 5000, 5001 | Record count maximum |
| CSV UTF-8 bytes | 499999, 500000, 500001 | Exact file byte maximum |
| HTTP body bytes | 1999999, 2000000, 2000001; empty separately | Combined request maximum |
| History offsets | 0, 99, 100, 101, 102 with 101 batches | 100-row page boundary and empty tail |

EP denotes equivalence partitioning; BVA denotes boundary value analysis. Combined labels describe a case that is both a representative of a partition and a boundary witness. They do not imply every boundary of every input field has been tested. Invalid cases use an otherwise valid base to avoid masking one defect with another.

## 5 Requirement to test traceability

Table 5.1 Functional coverage mapping
| Req ID | Acceptance focus | Test IDs |
| --- | --- | --- |
| FR01 | Source maintenance and import | S00, Q, PR, RS, LD, MU, CAL, INV09 to11, CSV, ROW, BYTE, NUM, H00 to03 |
| FR02 | Task selection and deterministic order | PR, INV00 to01, ORD0 to4 |
| FR03 | BOM and snapshot validity | B, INV02 to08 |
| FR04 | Multilevel net requirements | P00, Q, B, NET0 to1, EX5 |
| FR05 | Shared stock and no actual deduction | ST, RS, NET, ORD, H08 |
| FR06 | Purchasing and dated planned surplus | P00, Q, ST, MU, LOT, NET1, SUR, H06 |
| FR07 | Calendar dates and timing risks | P00, LD, DT, CAL, NET1 |
| FR08 | History, trace and export | H00 to08, HX, EX, PAGE, RESTART and browser suites |

NFR02 reproducibility is checked by ORD3, which reverses input rows. NFR07 data integrity is checked by rejection-side history invariants, H01, H03, H08 and RESTART. Performance was measured in an earlier phase and is not claimed as a new E5 measurement. This map is requirements coverage, not source-code coverage.

## 6 Executed HTTP case register

Each row reports a specific executed case. Base fixture fields remain unchanged unless the scenario states otherwise. The evidence files contain exact inputs and complete outputs. VALID cases additionally require HTTP200 and a saved batch. INVALID planning cases additionally require HTTP200, at least one located error, unchanged history, and no saved_batch field. CSV cases additionally require HTTP200 and unchanged saved workspace and history. These repeated checks are abbreviated in the tables.

Output notation uses JSON arrays. Purchase rows are [material, arrival date, quantity, order date]; make rows are [material, quantity, start date]. Empty arrays mean no rows. Boolean true means the named invariant was observed. Dynamic revision IDs are shown in full in the evidence; readable tables use the word revision where appropriate.

### 6.1 Planning cases

Table 6.1 Planning expected and observed results
| ID | Scenario and input | Expected | Observed |
| --- | --- | --- | --- |
| P00 | Base P10 with two R per P: make10, buy20; calendar lead2+3 | VALID + saved; [[["P", 10, "2026-11-18"]], [["R", "2026-11-18", 20, "2026-11-15"]], []] | VALID + saved; [[["P", 10, "2026-11-18"]], [["R", "2026-11-18", 20, "2026-11-15"]], []] | PASS |
| Q00 | JSON task quantity 0; native positive integer domain; UI safe limit is separate | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| Q01 | JSON task quantity 1; native positive integer domain; UI safe limit is separate | VALID + saved; [1, 5] | VALID + saved; [1, 5] | PASS |
| Q02 | JSON task quantity 2; native positive integer domain; UI safe limit is separate | VALID + saved; [2, 5] | VALID + saved; [2, 5] | PASS |
| Q03 | JSON task quantity 9007199254740990; native positive integer domain; UI safe limit is separate | VALID + saved; [9007199254740990, 18014398509481980] | VALID + saved; [9007199254740990, 18014398509481980] | PASS |
| Q04 | JSON task quantity 9007199254740991; native positive integer domain; UI safe limit is separate | VALID + saved; [9007199254740991, 18014398509481985] | VALID + saved; [9007199254740991, 18014398509481985] | PASS |
| Q05 | JSON task quantity 9007199254740992; native positive integer domain; UI safe limit is separate | VALID + saved; [9007199254740992, 18014398509481985] | VALID + saved; [9007199254740992, 18014398509481985] | PASS |
| Q06 | JSON task quantity 1.5; native positive integer domain; UI safe limit is separate | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| Q07 | JSON task quantity True; native positive integer domain; UI safe limit is separate | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| Q08 | JSON task quantity '10'; native positive integer domain; UI safe limit is separate | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| B00 | BOM usage 0; positive lower boundary | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| B01 | BOM usage 1; positive lower boundary | VALID + saved; 10 | VALID + saved; 10 | PASS |
| B02 | BOM usage 2; positive lower boundary | VALID + saved; 20 | VALID + saved; 20 | PASS |
| PR0 | Priority 0; closed domain 1 to 3 | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| PR1 | Priority 1; closed domain 1 to 3 | VALID + saved; ["T1"] | VALID + saved; ["T1"] | PASS |
| PR2 | Priority 2; closed domain 1 to 3 | VALID + saved; ["T1"] | VALID + saved; ["T1"] | PASS |
| PR3 | Priority 3; closed domain 1 to 3 | VALID + saved; ["T1"] | VALID + saved; ["T1"] | PASS |
| PR4 | Priority 4; closed domain 1 to 3 | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| ST0 | Raw stock -1 around gross requirement20 | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| ST1 | Raw stock 0 around gross requirement20 | VALID + saved; 20 | VALID + saved; 20 | PASS |
| ST2 | Raw stock 19 around gross requirement20 | VALID + saved; 5 | VALID + saved; 5 | PASS |
| ST3 | Raw stock 20 around gross requirement20 | VALID + saved; 0 | VALID + saved; 0 | PASS |
| ST4 | Raw stock 21 around gross requirement20 | VALID + saved; 0 | VALID + saved; 0 | PASS |
| RS0 | Reserved -1 with on-hand20; allowed interval0..20 | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| RS1 | Reserved 0 with on-hand20; allowed interval0..20 | VALID + saved; 0 | VALID + saved; 0 | PASS |
| RS2 | Reserved 1 with on-hand20; allowed interval0..20 | VALID + saved; 5 | VALID + saved; 5 | PASS |
| RS3 | Reserved 20 with on-hand20; allowed interval0..20 | VALID + saved; 20 | VALID + saved; 20 | PASS |
| RS4 | Reserved 21 with on-hand20; allowed interval0..20 | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| LD0 | Purchase lead time -1; nonnegative lower boundary | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| LD1 | Purchase lead time 0; nonnegative lower boundary | VALID + saved; "2026-11-18" | VALID + saved; "2026-11-18" | PASS |
| LD2 | Purchase lead time 1; nonnegative lower boundary | VALID + saved; "2026-11-17" | VALID + saved; "2026-11-17" | PASS |
| MU0 | Purchase multiple 0; positive lower boundary | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| MU1 | Purchase multiple 1; positive lower boundary | VALID + saved; 20 | VALID + saved; 20 | PASS |
| MU2 | Purchase multiple 2; positive lower boundary | VALID + saved; 20 | VALID + saved; 20 | PASS |
| LOT0 | BUY root gap9, minimum0, multiple10 | VALID + saved; 10 | VALID + saved; 10 | PASS |
| LOT1 | BUY root gap10, minimum0, multiple10 | VALID + saved; 10 | VALID + saved; 10 | PASS |
| LOT2 | BUY root gap11, minimum0, multiple10 | VALID + saved; 20 | VALID + saved; 20 | PASS |
| LOT3 | BUY root gap1, minimum9, multiple10 | VALID + saved; 10 | VALID + saved; 10 | PASS |
| LOT4 | BUY root gap1, minimum10, multiple10 | VALID + saved; 10 | VALID + saved; 10 | PASS |
| LOT5 | BUY root gap1, minimum11, multiple10 | VALID + saved; 20 | VALID + saved; 20 | PASS |
| LOT6 | BUY root gap1, minimum-1, multiple10 | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| LOT7 | Zero shortage with minimum100 creates no purchase | VALID + saved; [] | VALID + saved; [] | PASS |
| DT0 | Order date one day before/on/after baseline; due=2026-11-05 | VALID + saved; [["2026-10-31", 1]] | VALID + saved; [["2026-10-31", 1]] | PASS |
| DT1 | Order date one day before/on/after baseline; due=2026-11-06 | VALID + saved; [] | VALID + saved; [] | PASS |
| DT2 | Order date one day before/on/after baseline; due=2026-11-07 | VALID + saved; [] | VALID + saved; [] | PASS |
| CAL0 | Calendar partition 2026-02-30; leap, format and representable range | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| CAL1 | Calendar partition 2028-02-29; leap, format and representable range | VALID + saved; "2028-02-24" | VALID + saved; "2028-02-24" | PASS |
| CAL2 | Calendar partition 20261120; leap, format and representable range | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| CAL3 | Calendar partition 0001-01-01; leap, format and representable range | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| CAL4 | Calendar partition 9999-12-31; leap, format and representable range | VALID + saved; "9999-12-26" | VALID + saved; "9999-12-26" | PASS |
| INV00 | Empty selected task set | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV01 | Unknown selected task | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV02 | Unknown BOM reference | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV03 | Duplicate BOM edge | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV04 | Self cycle | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV05 | Two-node cycle even when finished stock covers task | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV06 | MAKE material without children | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV07 | BUY material with children | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV08 | Reachable material missing stock | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV09 | Snapshot date differs from baseline | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV10 | Duplicate material ID | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| INV11 | Blank required identifier | INVALID; located errors; no saved plan or history change | INVALID; located errors; no saved plan or history change | PASS |
| NET0 | Finished stock exactly covers demand; no lower requirements | VALID + saved; [[], [], 1] | VALID + saved; [[], [], 1] | PASS |
| NET1 | Multilevel net explosion: P8, S12, raw gap32 rounded35 | VALID + saved; [[["P", 8, "2026-11-18"], ["S", 12, "2026-11-17"]], [["R", "2026-11-17", 35, "2026-11-14"]]] | VALID + saved; [[["P", 8, "2026-11-18"], ["S", 12, "2026-11-17"]], [["R", "2026-11-17", 35, "2026-11-14"]]] | PASS |
| ORD0 | Shared stock ordering by priority | VALID + saved; [["A", "Z"], [["A", 4], ["Z", 1]]] | VALID + saved; [["A", "Z"], [["A", 4], ["Z", 1]]] | PASS |
| ORD3 | Reversed input rows preserve business allocation | VALID + saved; [["A", "Z"], [["A", 4], ["Z", 1]]] | VALID + saved; [["A", "Z"], [["A", 4], ["Z", 1]]] | PASS |
| ORD4 | Unselected high-priority task consumes no stock | VALID + saved; [["Z"], [["Z", 4]]] | VALID + saved; [["Z"], [["Z", 4]]] | PASS |
| ORD1 | Shared stock ordering by date | VALID + saved; [["Z", "A"], [["Z", 4], ["A", 1]]] | VALID + saved; [["Z", "A"], [["Z", 4], ["A", 1]]] | PASS |
| ORD2 | Shared stock ordering by identifier | VALID + saved; [["A", "Z"], [["A", 4], ["Z", 1]]] | VALID + saved; [["A", "Z"], [["A", 4], ["Z", 1]]] | PASS |
| SUR0 | Earlier purchase surplus covers later demand despite priority order | VALID + saved; [[["R", "2026-11-10", 10, "2026-11-07"], ["R", "2026-11-11", 0, null]], [4]] | VALID + saved; [[["R", "2026-11-10", 10, "2026-11-07"], ["R", "2026-11-11", 0, null]], [4]] | PASS |
| SUR1 | Future lot cannot supply earlier demand; chronology reversed | VALID + saved; [["R", "2026-11-09", 10, "2026-11-06"], ["R", "2026-11-10", 0, null]] | VALID + saved; [["R", "2026-11-09", 10, "2026-11-06"], ["R", "2026-11-10", 0, null]] | PASS |
| SUR2 | Same-date shortages merge before rounding | VALID + saved; [["R", "2026-11-09", 10, "2026-11-06"]] | VALID + saved; [["R", "2026-11-09", 10, "2026-11-06"]] | PASS |
| H04 | Save baseline plan for historical export | VALID + saved; 20 | VALID + saved; 20 | PASS |
| H06 | New plan reflects changed demand11 | VALID + saved; 25 | VALID + saved; 25 | PASS |

### 6.2 Source cases

Table 6.2 Source expected and observed results
| ID | Scenario and input | Expected | Observed |
| --- | --- | --- | --- |
| S00 | Fresh workspace has no saved revision | No saved workspace | No saved workspace | PASS |
| CSV00 | Valid four tables; preview does not save or create a plan | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| CSV01 | Empty file selection | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV02 | Empty tasks file | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV03 | Unknown table | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV04 | Missing header | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV05 | Duplicate header | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV06 | Too few columns | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV07 | Unclosed quote | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV08 | Decimal quantity | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV09 | Scientific quantity | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV10 | Quoted Chinese comma quote and newline preserved | ["READY", "产品, \"甲\"\n第二行"]; workspace and history unchanged | ["READY", "产品, \"甲\"\n第二行"]; workspace and history unchanged | PASS |
| NUM0 | CSV quantity 9007199254740990; safe-integer maximum boundary | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| NUM1 | CSV quantity 9007199254740991; safe-integer maximum boundary | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| NUM2 | CSV quantity 9007199254740992; safe-integer maximum boundary | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| ROW0 | CSV row count 4999 around5000 maximum | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| ROW1 | CSV row count 5000 around5000 maximum | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| ROW2 | CSV row count 5001 around5000 maximum | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| BYTE0 | CSV bytes 499999 around500000 maximum | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| BYTE1 | CSV bytes 500000 around500000 maximum | "READY"; workspace and history unchanged | "READY"; workspace and history unchanged | PASS |
| BYTE2 | CSV bytes 500001 around500000 maximum | "INVALID"; workspace and history unchanged | "INVALID"; workspace and history unchanged | PASS |
| CSV11 | Template ZIP contains four data tables | [200, ["bom.csv", "materials.csv", "stocks.csv", "tasks.csv"]] | [200, ["bom.csv", "materials.csv", "stocks.csv", "tasks.csv"]] | PASS |

### 6.3 History cases

Table 6.3 History expected and observed results
| ID | Scenario and input | Expected | Observed |
| --- | --- | --- | --- |
| H00 | First save from null revision creates a source version | [200, "SAVED", true] | [200, "SAVED", true] | PASS |
| H01 | Invalid save preserves last valid revision | 200; INVALID; original revision unchanged | 200; INVALID; original revision unchanged | PASS |
| H02 | Matching revision permits new version | [200, "SAVED", true] | [200, "SAVED", true] | PASS |
| H03 | Stale revision fails without overwriting newer source | [409, "CONFLICT", 11] | [409, "CONFLICT", 11] | PASS |
| EX0 | MAKE download rows and batch ID; zero-risk header-only partition | 1; workspace and history unchanged | 1; workspace and history unchanged | PASS |
| EX1 | PURCHASE download rows and batch ID; zero-risk header-only partition | 1; workspace and history unchanged | 1; workspace and history unchanged | PASS |
| EX2 | ALLOCATION download rows and batch ID; zero-risk header-only partition | 2; workspace and history unchanged | 2; workspace and history unchanged | PASS |
| EX3 | TRACE download rows and batch ID; zero-risk header-only partition | 2; workspace and history unchanged | 2; workspace and history unchanged | PASS |
| EX4 | RISK download rows and batch ID; zero-risk header-only partition | 0; workspace and history unchanged | 0; workspace and history unchanged | PASS |
| EX5 | Export agrees with independent make10 and start date | [[10, "2026-11-18"]] | [[10, "2026-11-18"]] | PASS |
| H07 | Old complete snapshot and CSV unchanged after new plan | [true, true] | [true, true] | PASS |
| H08 | Calculating plans does not deduct persisted stock | [[0, 0], [0, 0]] | [[0, 0], [0, 0]] | PASS |
| HX0 | /api/history/missing | 404 | 404 | PASS |
| HX1 | /api/history/missing/csv/MAKE | 404 | 404 | PASS |
| HX2 | /api/history/4c25c33172a8470e97d2d50c9221eaa7/csv/OTHER | 400 | 400 | PASS |
| HX3 | /api/history?offset=-1 | 400 | 400 | PASS |
| HX4 | /api/history?offset=abc | 400 | 400 | PASS |
| PAGE0 | History offset0 with 101 saved plans | [200, 100, 100] | [200, 100, 100] | PASS |
| PAGE1 | History offset99 with 101 saved plans | [200, 2, null] | [200, 2, null] | PASS |
| PAGE2 | History offset100 with 101 saved plans | [200, 1, null] | [200, 1, null] | PASS |
| PAGE3 | History offset101 with 101 saved plans | [200, 0, null] | [200, 0, null] | PASS |
| PAGE4 | History offset102 with 101 saved plans | [200, 0, null] | [200, 0, null] | PASS |
| RESTART | Restart retains workspace and all saved history | [true, true] | [true, true] | PASS |

### 6.4 Transport cases

Table 6.4 Transport expected and observed results
| ID | Scenario and input | Expected | Observed |
| --- | --- | --- | --- |
| HTTP0 | Empty request body | 413 | 413 | PASS |
| HTTP1 | Malformed JSON | 400 | 400 | PASS |
| HTTP2 | Wrong content type | 415 | 415 | PASS |
| HTTP3 | HTTP UTF-8 body 1999999 bytes; status only above limit | [200, "INVALID"] | [200, "INVALID"] | PASS |
| HTTP4 | HTTP UTF-8 body 2000000 bytes; status only above limit | [200, "INVALID"] | [200, "INVALID"] | PASS |
| HTTP5 | HTTP UTF-8 body 2000001 bytes; status only above limit | [413, null] | [413, null] | PASS |

## 7 Browser workflows and regression evidence

The API cases exercise the complete running server. Three existing browser suites were also rerun with headless Microsoft Edge and isolated temporary databases. They use actual controls, file upload/download, page reload and server restart. These checks are supplementary scenarios, not a claim of exhaustive browser compatibility.

Table 7.1 Browser suite results
| Suite | Passed | Recorded time | Principal workflow |
| --- | --- | --- | --- |
| Workbench | 30/30 | 2026-10-22T04:26:36.482Z | Edit source, choose tasks, calculate, reject bad input, preserve large displayed integers and check narrow-screen layout |
| Persistence | 14/14 | 2026-10-22T04:26:41.137Z | Save, reload, view immutable history, handle stale writer and restart the service |
| CSV browser | 21/21 | 2026-10-22T04:28:19.331Z | Download templates, upload, preview, apply, save, calculate and download all five result types |

All 30 workbench, 14 persistence and 21 CSV browser checks passed. The CSV browser suite was rerun after the field-size fix. The 38 existing CSV parsing/API regression checks also passed after that fix. Counts from these suites overlap in business scenarios and must not be summed into a claim about unique requirements.

Table 7.2 Workbench check register
| No | Observed scenario | Result |
| --- | --- | --- |
| 1 | Initial material rows | PASS |
| 2 | Priority order | PASS |
| 3 | Higher priority B net production | PASS |
| 4 | Lower priority B net production | PASS |
| 5 | Edit invalidates old results | PASS |
| 6 | Old result tables removed | PASS |
| 7 | Edited LOW quantity recalculated | PASS |
| 8 | Decimal input rejected | PASS |
| 9 | Error location focuses field | PASS |
| 10 | Unsafe integer input rejected | PASS |
| 11 | Large calculated quantity displayed exactly | PASS |
| 12 | 物料 row addition | PASS |
| 13 | 物料 row deletion | PASS |
| 14 | BOM row addition | PASS |
| 15 | BOM row deletion | PASS |
| 16 | 库存 row addition | PASS |
| 17 | 库存 row deletion | PASS |
| 18 | 生产任务 row addition | PASS |
| 19 | 生产任务 row deletion | PASS |
| 20 | Empty task selection rejected | PASS |
| 21 | Invalid reserved stock surfaced | PASS |
| 22 | Two purchase date buckets | PASS |
| 23 | Later bucket buys zero | PASS |
| 24 | Early-date risk visible | PASS |
| 25 | Stale response rejected | PASS |
| 26 | Network failure allows retry | PASS |
| 27 | Retry succeeds | PASS |
| 28 | Mobile no page overflow | PASS |
| 29 | Mobile calculate reachable | PASS |
| 30 | No uncaught browser errors | PASS |

Table 7.3 Persistence check register
| No | Observed scenario | Result |
| --- | --- | --- |
| 1 | First save creates source version | PASS |
| 2 | Reload restores saved edit | PASS |
| 3 | Plan saved badge shown | PASS |
| 4 | History shows old LOW quantity | PASS |
| 5 | History does not replace current edit | PASS |
| 6 | History includes original source snapshot | PASS |
| 7 | Conflict keeps unsaved local edit | PASS |
| 8 | Conflict does not overwrite database | PASS |
| 9 | Invalid save keeps previous data | PASS |
| 10 | Explicit reload restores valid data | PASS |
| 11 | Server restart restores source | PASS |
| 12 | Server restart preserves history | PASS |
| 13 | Persistence toolbar and history fit mobile | PASS |
| 14 | No unhandled page errors | PASS |

Table 7.4 CSV browser check register
| No | Observed scenario | Result |
| --- | --- | --- |
| 1 | Template ZIP downloads | PASS |
| 2 | ZIP signature | PASS |
| 3 | Preview does not replace editor | PASS |
| 4 | Preview does not save database | PASS |
| 5 | Apply installs imported row | PASS |
| 6 | Apply leaves save explicit | PASS |
| 7 | Download identifies saved batch | PASS |
| 8 | CSV contains independent expected production | PASS |
| 9 | PURCHASE downloads UTF8 BOM | PASS |
| 10 | ALLOCATION downloads UTF8 BOM | PASS |
| 11 | TRACE downloads UTF8 BOM | PASS |
| 12 | RISK downloads UTF8 BOM | PASS |
| 13 | Edit clears stale export control | PASS |
| 14 | Historical download unaffected by new input | PASS |
| 15 | Bad CSV keeps original edit | PASS |
| 16 | Bad CSV cannot apply | PASS |
| 17 | Bad header error visible | PASS |
| 18 | Editor change invalidates preview | PASS |
| 19 | Invalid encoding cannot apply | PASS |
| 20 | Import toolbar fits narrow screen | PASS |
| 21 | No unhandled browser errors | PASS |

Browser evidence includes results/workbench-results.png, results/persistence-history.png, results/csv-workbench.png and the corresponding mobile screenshots. These images were captured from test databases; they are evidence of those scenarios, not user production records.

## 8 Findings corrections and residual observations

Table 8.1 Findings and disposition
| ID | Finding | Disposition |
| --- | --- | --- |
| DEF01 | A valid 499999-byte or 500000-byte CSV with one long name field returned CSV_SYNTAX. The underlying csv reader default field limit was 131072 characters. | Fixed csv_io.py to align the field parser limit with the existing 500000-byte file ceiling. BYTE0 and BYTE1 now pass; BYTE2 still rejects. Existing CSV and browser regressions pass. |
| OBS01 | The initial Q05 oracle applied the browser/CSV safe-integer ceiling to the native JSON calculation API. That API accepted the larger integer and returned exact calculated values. | Corrected the oracle using the entry-point contract. Q05 tests exact native JSON arithmetic; NUM0 to2 separately verify the CSV safe boundary. Browser regression checks its own limit. |
| OBS02 | An oversized 2000001-byte request intermittently caused Windows connection abortion while the server was returning413. It interrupted two earlier runner attempts. | Final full run observed413 and passed the status-only boundary criterion. A reliable complete error-body delivery is not established. The harness records body-read errors or a failed transport result rather than silently omitting the case. This compatibility observation is not marked fixed. |

The first attempt recorded 118 passing cases out of 121 recorded before interruption; three mismatches included the two CSV failures and the Q05 oracle issue. The preserved blackbox-e5-initial.json and that run directory retain this evidence. The final result contains completed=true and all125 cases. A partial cleanup report must never be mistaken for a completed test run.

The correction changes only CSV parser configuration and its shared byte-limit constant. No calculation rule, stock ordering or user database was changed. E3 and earlier reports are dated design snapshots; final report integration should refresh source line references and hashes affected by the CSV edit.

## 9 Result interpretation and limitations

The selected cases support the stated quantity, stock, BOM, date, import, persistence and export requirements. Expected values are concrete outputs derived before execution from the business rules. Where full snapshots are compared, a mismatch is visible even if headline quantities are unchanged. Invalid input tests also verify that rejection does not create a history batch.

Passing these cases does not prove correctness for every graph or all inputs. This phase does not exhaust concurrent HTTP clients, disk-full failures, every CSV encoding, every graph depth, alternative browsers or operating systems. Version-conflict behavior is tested with stale revisions and two browser pages, not a high-load concurrency benchmark. The all-member academic review and personal contribution statements remain pending.

Transport OBS02 is supplementary to the selected business cases but remains visible in the report. The final status-only pass does not erase an earlier intermittent failure or establish that every client receives the explanatory error body. A production deployment would require a separate server and compatibility acceptance scope; this project remains a local coursework workbench.

## 10 Reproducibility and evidence index

Table 10.1 Evidence locations relative to the project root
| Location | Content |
| --- | --- |
| material-planning/verify_blackbox.py | External HTTP runner and independent fixtures; no application imports |
| material-planning/results/blackbox-e5.json | Final completed case register, actual/expected results, source and harness hashes |
| material-planning/results/e5-runs/59ed88f176ed468792caaeea2e4256d1 | Exact request and response bytes, exchanges.json, test database and server log |
| specs/material-requirements-planning/e5/evidence | Frozen copies of the initial/final HTTP results and browser/CSV regression results |
| specs/material-requirements-planning/e5/verification-report.json | Document/evidence/source consistency checks and final artifact hash |
| specs/material-requirements-planning/e5/qa | Internal Word-exported PDF and page images used for visual review |

Run verify_blackbox.py with the recorded bundled Python runtime; it selects an unused local port and creates a fresh test directory. Run verify_persistence_ui.cjs and verify_csv_ui.cjs with the recorded Node runtime and bundled Playwright/Edge environment; the persistence script also runs the workbench suite. Then run verify_csv.py, rebuild this report, and repeat document verification and page inspection. The scripts stop only the servers they created.

The test run is reproducible in behavior, but batch IDs, revision IDs, port, timestamps and run directory names are intentionally fresh. Equality or invariance checks compare values within the same run. The saved artifacts allow exact reconstruction of a previously executed request.

CSV source SHA256: 4cf5f8c0899bb0cc40e2111c8006a5fba7f926727ed3b212e1ac82e71d51e23e

HTTP runner SHA256: f0315100f587d1347275cf94f57dde37b8ab365bfed1962ff1402ee8acb15de8

## 11 Group records to complete

The group has two members. The following records must describe work actually performed; automated technical execution is not evidence of who authored, reviewed or approved the assignment.

Table 11.1 Actual task allocation
| Member | Identity | Actual task and evidence |
| --- | --- | --- |
| A | [Name and student ID] | [Actual requirements analysis, partition design, case execution or report work; cite IDs and dates] |
| B | [Name and student ID] | [Actual boundary design, independent checking, browser testing or report work; cite IDs and dates] |

### 11.1 Literal review meeting record

Meeting date and place: [To be completed after the meeting]. Participants: [Both actual members]. Chair and recorder: [Actual names].

Review agenda: confirm selected subsystem contracts; check independent fixture calculations; verify partition and boundary choices; inspect DEF01 evidence and OBS02 limitation; confirm expected/actual tables and English wording. Discussion: [Actual questions, responses, decisions, corrections and responsible member]. Review outcome: [Actual outcome after corrections are checked].

### 11.2 Individual contributions

Member A: [Describe actual personal work, test IDs, evidence produced, corrections made and understanding of equivalence partitioning and boundary analysis].

Member B: [Describe actual personal work, independent checking, test IDs, evidence produced and lessons from testing].

### 11.3 Submission status

The English technical report and execution artifacts are prepared. Actual names, task allocation, meeting record and individual contributions are pending. No FTP submission or group approval is claimed. These administrative records must be completed before final coursework submission.

## 12 Source materials

[1] Course handout. Experiment 5 Using Black Box Testing in System Testing [Z]. Supplied original DOC, read on 22 October 2026.

[2] Project working documents. requirements.md, examples.md, E2 module structure, persistence-v0.4.md and csv-v0.5.md [R]. Local requirement and interface records.

[3] Project execution evidence. blackbox-e5.json, browser verification records and CSV regression record [CP]. Execution times and source hashes recorded in this report and its evidence directory.
