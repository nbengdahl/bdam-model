# Candidate 1 routing repair — accepted 2026-10-22

Implemented on `parameters-table`, based on commit
`1a573f48d132de1c10f3218eedf77b8435e1beb6`. Only this branch is changed.
Stock MF6 6.7.0 MVR supplies each internal lake's received water consistently
to the lake solve, availability calculation and residual check. The existing
Manning/WEIR laws, coefficients, storage/exchange geometry, under-dam K and
terminal outlet are preserved. No API backend or custom executable is used.

## Acceptance criteria

The user selected **1e-4 m3/day per internal outlet** for the signed external
residual following MF6's final outlet update. This supersedes the initial
Candidate 1 zero-residual audit of 1e-8 m3/day. Both signs remain in gross
external water balances; no residual is discarded or rounded away.

- MVR provider debit/receiver credit agreement remains 1e-8 m3/day.
- Native whole-model and coupled external budget limits remain 0.1%.
- Every lake's native budget uses 0.1% relative closure or 1e-8 m3/day absolute
  closure at near-zero flow. Both residual measures are reported. A percentage
  alone is unsuitable when flow and roundoff are both approximately zero.
- LAK stage tolerance remains 5e-7 m; IMS profiles, strict closures, 2000 outer
  allowance, wave capacity, calendars and adaptive criteria are unchanged.
- Revalidation checks native budgets and the saved audit without rewriting it,
  preserving completed-study hashes and immutable results.

## Complete workflows

Both supplied rows and their original hydrograph are unchanged. All 404 pre-dam
and 294 post-dam numerical preparation datasets match the original reproduced
cases exactly. Prepared/serialized conductivity audits pass, including the
supplied 1000 m/day core conductivity. Registry v7 and HDF5 v8 are unchanged;
use fresh studies to capture the new runner.

| Case | Workspaces / saved endpoints | Adaptive weekly years | Max coupled discrepancy (%) | Max external residual (m3/day) | Total outer iterations |
|---|---|---|---|---|---|
| `t_fail_fast_v2` | 10 / 464 | 4 | 2.0791622033e-5 | 7.8873474649e-5 | 7513 |
| `t_pass_near_limit` | 10 / 464 | 4 | 3.0928946085e-5 | 5.4913016356e-5 | 7892 |
| Default | 6 / 308 | fixed 0/4/1 | 2.5557547974e-6 | 1.3883714018e-6 | 4800 |

The formerly failing case completes its four monthly warmup years, establishes
two consecutive passing annual comparisons after four adaptive weekly years,
and finishes two monitored pre-dam and two post-dam years. The paired case
also completes. No DNC or numerical failure is accepted as completion.
MVR debit/credit discrepancy is exactly zero in all three workflows. Installation
storage errors are 8.88e-16 m3 for the failing case and zero for the paired and
default cases. Full output, solver, timing/count, budget, monitoring, restart,
provenance and completion/hash checks pass. Solve-workflow elapsed times were
about 24.4, 23.5 and 13.6 minutes respectively, with concurrent execution.

## Regression coverage and numerical differences

All **116 Python tests** and **45 unique MATLAB tests** pass, including all
16 viewer tests. The two actual-output viewer tests are also exercised against
the newly completed Candidate 1 default. Initial fixture-path skips were
resolved; no test failure or skip is treated as a pass.

The original three-solve regression passes with seven diagnostic endpoints
(49 days): genuine zero-volume/DHDRY states in all pools, dry restart, dry
installation, pond rewetting and recession. The additional five-solve stress
regression passes with eleven diagnostic endpoints (77 summed diagnostic days):
every pre/post lake starts wet, depletes within the existing LAK stage closure,
rewets from upstream input and recedes again. It covers mixed wet/dry neighbors,
inherited states and wet installation. Trace positive storage remains explicit;
it is not replaced by a zero value or dry sentinel. Extreme evaporation and
short schedules belong only to these diagnostics, never production forcing.

Default preparation inputs match the previous validated default exactly.
Results are not byte-identical: maximum saved head difference is 0.01155556 m,
maximum lake-stage difference is 4.9654e-10 m, and maximum raw UZF water-content
difference is 0.05122475. Raw UZF states include dry/deactivated zero states;
the detailed comparison also records nonzero-only differences and zero-status
changes. These state differences are retained as substantive comparison data,
not silently labeled roundoff. Each new run independently passes acceptance.

## Provenance and retained evidence

Persistent acceptance root:
`/Users/nick.engdahl/BDamRuns/bdam-candidate1-acceptance-20261022`

- `ACCEPTANCE_REPORT.md`, `acceptance-receipt.json`: results, budgets, iterations,
  output paths and independently revalidated completion receipts.
- `study/executions/1703cb062bd6c52bd8110255/BDam/Runs`: failing supplied case.
- `study/executions/a071981a3aa268866898bd71/BDam/Runs`: paired supplied case.
- `study/executions/3be95b26d29126fa7c0c933b/BDam/Runs`: complete default.
- `exact-dry-restart/`, `all-lake-drying-final/`: passing dry-state regressions.
- `all-lake-drying/`: preserved initial percentage-only audit failure at
  approximately 2.6e-10 m3/day absolute imbalance; not an accepted run.
- `python-tests-final-complete.log`, `matlab-tests.log`,
  `matlab-viewer-full.log`, `matlab-viewer-candidate1.log`: test evidence.
- `unchanged-inputs-and-physics.json`, `array-audits/`,
  `default-previous-run-comparison.json`: numerical-input, serialization and
  saved-state comparisons.

Immutable studies captured the MVR builder and selected external-residual
tolerance before later audit-only revisions. AST comparison confirms the
numerical builder, solver, calendar and restart functions match the snapshots.
The final validator independently rechecks every completed workspace without
altering those snapshots or outputs.

Original reproduction remains at
`/Users/nick.engdahl/BDamRuns/bdam-bug-20261022`. The initial Candidate 1 backup
remains at `/Users/nick.engdahl/BDamRuns/bdam-mvr-20261022/candidate1-backup`.
Candidate 2 (retained native receivers plus MVR) is rejected by its first
conservation gate and remains outside the source tree at
`/Users/nick.engdahl/BDamRuns/bdam-mvr-candidate2-20261022`.

Runtime: Python 3.14.6, FloPy 3.10.0, NumPy 2.5.2, h5py 3.16.0,
MATLAB R2025b, official stock MF6 6.7.0 (2026-02-05). Maximum simultaneous
MF6 solves was five, below the authorized eight.
