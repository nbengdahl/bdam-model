# Single-run MVR routing repair — 22 October 2026

Candidate 1 is ported from `parameters-table` commit
`cf30c931e20cc3de76adaa7242677925b812c837` onto `main` starting at
`5455d8bd6695e6c91c7585a34533f6efec55d3de`. The single-run entry point,
MATLAB preparation and HDF5-v6 contract are preserved. Parameter registries,
study infrastructure and prescribed edge WEL packages are not imported.

## Repair and limits

Stock MF6 6.7.0 MVR routes each internal lake outlet's full discharge to its
existing receiver, avoiding the native receiving-lake availability inconsistency
found in the supplied low-recharge case. The hydraulic Manning/WEIR controls,
terminal outlet, storage/exchange geometry and conductivity arrays are unchanged.
Native receivers are serialized as external so MVR supplies each credit once.
This does not add receiving-stage backwater coupling.

Every workspace records its physical chain and controls in
`bdam.lake_routing.json`, native transfers in `bdam.mvr.bud` when links exist,
and per-lake balances in `bdam.lake_routing_balance.csv`. Completion checks
independently revalidate these outputs without rewriting saved audits.

- MVR debit/credit agreement: **1e-8 m3/day**.
- User-approved final-update external residual: **1e-4 m3/day per internal
  outlet**. Both signs remain in gross external balances; internal transfers
  are excluded from external totals.
- Per-lake closure: **0.1% relative or 1e-8 m3/day absolute**, reporting both.
  The absolute allowance handles roundoff near zero flow.
- Whole-model and coupled external budget limits remain **0.1%**.
- LAK stage tolerance remains **5e-7 m**; IMS profiles, strict closures,
  2000 outer allowance, UZF capacities and calendars are unchanged.

Existing v6 handoffs retain their physical values. Running the updated builder
adopts MVR; historical completed direct-routing workspaces remain historical
outputs and do not acquire the new routing audits retroactively.

## Acceptance results

All runs used persistent nonsynchronized local storage and stock MF6 6.7.0.
No numerical failure required a model, tolerance or calendar change.

| Check | Result |
| --- | --- |
| Python suite | 45 passed |
| MATLAB conductivity, routing and viewer tests | 25 passed; zero failures or skips |
| Prepared dry-bottom, terrain-breakpoint and capped-storage checks | Passed for every lake |
| Prepared/serialized K/K33 and core/halo mask audit | Passed |
| Default workflow | Six workspaces, 308 saved endpoints |
| Spinup / monitored summary rows | 101 / 210 |
| Maximum GWF listing discrepancy | 0% at listing precision |
| Maximum coupled external discrepancy | 1.22335908e-6% |
| Maximum internal-outlet external residual | 2.11241331e-6 m3/day |
| MVR debit/credit error | 0 m3/day |
| Dam-installation volume error | 0 m3 |
| Exact inherited-state transitions | All five passed |
| MF6 solve time, summed over six workspaces | 245.36 seconds |
| Outer iterations / maximum per step | 4658 / 26 |

The unchanged default has 0 fall / 4 monthly / 1 weekly spinup years and two
pre-dam plus two post-dam monitored years. First monthly year: 12 endpoints
at day 365. Staged remainder: 88 endpoints at day 1460. Each monitored year:
52 endpoints at day 365. Completion checks cover readable GWF/LAK/UZF binaries,
counts/times, native and coupled budgets, monitoring, routing, solver provenance
and restartability. Groundwater heads and inherited lake stages match the
serialized next-workspace initial conditions exactly. UZF initial contents
match the existing cell mapping and residual/saturated sentinel handling.

`tools/verify_lake_drying.py` passes three solves with seven endpoints: exact
zero-volume/DHDRY states, persistent dryness, annual restart, dry installation,
pond rewetting and partial near-bed recession.

`tools/verify_lake_mover_drying.py` passes five solves with eleven endpoints:
all eight pre-dam pools and all three post-dam lakes start wet, deplete within
the unchanged stage closure, rewet from upstream and deplete again. Mixed wet/dry
neighbors, inherited restarts and wet installation pass. Positive trace water
is retained, never rounded to zero. These bounded seven-day diagnostics are
separate from production and produce no production completion receipts.

## Comparison with prior main

All **362 pre-dam and 252 post-dam numerical preparation datasets** match the
prior validated main preparation exactly. Shared serialized physical inputs,
forcing, storage tables, IMS and TDIS match after excluding generation comments.
The shared routing/audit functions match the accepted table-branch implementation
exactly. Solver settings, schedules, restart mapping and installation functions
are unchanged from main's baseline.

Outputs are not identical to direct routing. Maximum saved head difference is
**0.0125141 m**, during staged spinup; monitored post-dam maxima are below
0.001 m. Maximum lake-stage difference is **6.34862e-7 m**, also during spinup;
monitored differences are below 3.4e-10 m. Maximum raw UZF water-content
difference is **0.0601687**; common-nonzero differences and changed zero-status
records are reported separately. These are substantive numerical differences,
not timestamps or container layout. Detailed per-workspace and summary-field
differences are retained in the comparison receipt. Passing budgets establish
accounting and numerical acceptance, not calibration or identical spatial
groundwater/UZF behavior.

## Evidence and reproduction

Persistent root:
`/Users/nick.engdahl/BDamRuns/bdam-main-mvr-20261022`.

- `BDam/Runs`: complete default outputs.
- `evidence/acceptance-receipt.json`: consolidated results and provenance.
- `evidence/BDam-completion.json`: independent completion checks and source hashes.
- `evidence/input-parity.json`: preparation, serialized input and function comparisons.
- `evidence/output-comparison.json`: saved-state, summary and restart comparisons.
- `evidence/python-tests.log`, `matlab-preparation.log`, `matlab-final-tests.json`
  and `matlab-final-tests.log`: test evidence.
- `conductivity-audit/validation.json`: prepared/serialized arrays.
- `exact-dry-restart/validation.json`, `all-lake-drying/validation.json`: diagnostics.
- Reproduction scripts and initial comparison-wrapper diagnostics are retained
  in `evidence/`. The initial wrapper assumed the wrong IMS filename and could
  not parse blank initial-row numeric fields. Correcting those wrappers did
  not change source physics, generated inputs or results. An initial viewer
  run skipped its unavailable historical fixture; the final run exercised fresh
  actual outputs with zero skips.

Runtime: Python 3.14.6, FloPy 3.10.0, NumPy 2.5.2, h5py 3.16.0,
MATLAB R2025b and MF6 6.7.0 dated 02/05/2026. MF6 SHA-256:
`a0c46e7861175fbe6640f67181b62cdb7b6298b3363787b0ab37ba4ff770a636`.

Use AGENTS.md to prepare a fresh local copy, then run the Python suite,
MATLAB preparation/storage/tests, `tools/verify_conductivity_halo.py`, the
full default runner and both drying tools. Set `BDAM_TEST_OUTPUT_ROOT` to the
completed package root for viewer integration. Run simulations serially and
preserve diagnostic outputs on failure. This validation does not replace the
separate supplied-case acceptance evidence on `parameters-table`.
