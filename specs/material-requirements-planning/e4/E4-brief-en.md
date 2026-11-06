# E4 White Box Testing Starter

Version 0.1. Short initial implementation and test record.

## Implemented scope

Four procedural functions are now executable in material-planning/core.py: M33 allocate_stock, M43 round_purchase_qty, M52 subtract_calendar_days and M53 flag_early_dates. They use the Python standard library and plain records. Python remains the provisional implementation language.

This starter contains a white-box analysis of M43 under its validated-input preconditions. The other implemented functions have regression checks, not complete five-criterion white-box coverage. Full BOM expansion, task orchestration, planned-surplus purchasing, storage and the user interface are not implemented. The demo uses prepared component requirements; it is not a complete CASE01 or CASE04 run.

## Actual execution evidence

Executed at: 2026-09-26T21:35:43.423930+08:00

Python: 3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]

Platform: Windows-11-10.0.26200-SP0

core.py SHA256: 01f67b289617224e6b10e39b189482f32806580538c7c6208c1496f0cd658ca8

Actual result: 38/38 checks passed. Inputs, independent expected values, actual values and individual pass results are retained in material-planning/results/verification.json. The separate demo displays HIGH receiving 20 existing B, LOW receiving 0, a D recommendation of 700 for gap 620 with multiple 100, and a one-day early-date risk.

The check count is not a coverage percentage. It includes quantity checks, unchanged-input checks, invalid-input rejection, date behavior and one trace-based statement check.

## Selected module M43

Purpose: calculate a purchase quantity after eligible planned surplus has already been deducted.

Preconditions: remaining_gap and minimum_qty are nonnegative integers; purchase_multiple is a positive integer. Booleans and decimals are rejected. Input validation helpers are outside the selected M43 white-box boundary.

Postconditions: gap zero gives quantity zero. Otherwise quantity is at least both gap and minimum and is a multiple of purchase_multiple. Integer arithmetic avoids floating-point rounding.

~~~text
validate the three integer preconditions
IF remaining_gap == 0:
    RETURN 0
target = MAX(remaining_gap, minimum_qty)
lot_count = (target + purchase_multiple - 1) DIV purchase_multiple
RETURN lot_count * purchase_multiple
~~~

The only explicit decision in this function body is D1: remaining_gap == 0. The only atomic condition is C1, identical to D1. MAX is a library operation, not an additional explicit branch in this submitted procedure.

## Minimal valid domain coverage set

| Case | Gap | Minimum | Multiple | Expected | Actual | C1 |
|---|---|---|---|---|---|---|
| P00 | 0 | 100 | 10 | 0 | 0 | True |
| P01 | 620 | 100 | 100 | 700 | 700 | False |

P00 executes source lines 90, 91, 92, 93, 94.

P01 executes source lines 90, 91, 92, 93, 95, 96, 97.

These line sequences were recorded during real calls using a Python execution trace, not inferred from expected results.

## Five coverage criteria for the selected scope

| Criterion | Evidence from P00 and P01 | Scope limitation |
|---|---|---|
| Statement coverage | The union executes all 8 executable statement lines identified in M43: 90, 91, 92, 93, 94, 95, 96, 97. The verification script checks exact set equality. | Excludes function declaration/docstring and called helper internals. |
| Branch coverage | P00 takes D1 True; P01 takes D1 False. Both branches are observed in the traces. | Explicit M43 decision under valid inputs. |
| Condition coverage | C1 is True in P00 and False in P01. | There is only one atomic condition in this module. |
| Condition combination coverage | The complete combination set for one condition is True and False; both are covered. | No artificial multi-condition claim is made. |
| Path coverage | P00 follows validate, D1 True, return zero; P01 follows validate, D1 False, compute and return. These are both feasible normal paths. | No loops in M43. Exceptions for violated preconditions and library internals are outside these two normal paths. |

Two cases are minimal for these five criteria on this valid-domain body: one case cannot make the same decision both True and False in a single invocation. Additional cases below improve boundary checks but are not needed to add a third normal M43 control path.

## Additional checks actually executed

Purchase cases include a minimum larger than the gap, exact minimum, one above minimum, a minimum not divisible by the multiple, unit multiple, and an integer larger than the exact IEEE-754 integer range. Invalid cases include negative gap, zero multiple, decimal gap and Boolean input.

Inventory checks cover zero stock, one short, exact stock, excess stock, source attribution across two BOM paths, reversed source row order, shared working balance across two calls, material mismatch and inconsistent origins. Date checks cover zero lead time, year crossing, leap-year crossing, range overflow, invalid date, invalid format and negative lead. Risk checks cover before, equal to and after baseline, empty events and unchanged input records.

These regression checks do not prove the entire application correct or fulfill E5 system testing.

## Error behavior at the current stage

A leaf precondition violation raises ValueError. This is a developer contract check at the current stage; the future M22 input layer must turn invalid user records into located issues before calling these leaves. M52 returns a structured DATE_RANGE error when a valid date and lead time imply an unrepresentable computed date. No leaf writes stock or a database.

## Remaining E4 work

1. Confirm group size N and select at least N suitable modules for the final experiment. One fully analyzed starter module does not establish the required count.
2. Add five-criterion analysis for further implemented modules. Loops in allocation and risk functions have unbounded iteration counts; define a justified path scope and identify infeasible paths rather than claiming exhaustive coverage.
3. Complete the remaining planner modules and retain any newly discovered defects and fixes.
4. Record actual member assignments, a real all-member review and individual contributions.
5. Confirm final course formatting, naming and submission requirements.

No full E4 completion, E5 completion or FTP submission is claimed.
