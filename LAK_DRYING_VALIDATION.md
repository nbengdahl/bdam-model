# LAK dry-out port to main — 21 October 2026

Port reference: parameters-table commit `297bada`. Target: main, based on
`d3f3d77`. Both branches now use the user-selected LAK maximum stage change
of **5e-7 m**. This retains identical shared MF6 settings and main's single-run
interface. The spinup remains **0/4/1**, with no annual fall-average steps;
the historical `first_annual` folder contains 12 monthly steps.

## Implemented

- Start the DEM pond table at the actual lowest connected terrain bed, with
  zero volume and positive onset area. Include every terrain breakpoint as
  well as the configured base sampling. Retain the constant-area upper cap.
- Reject trapped storage at preparation and Python build time.
- Decode exact MF6 DHDRY (`-1e30`) stages to physical lake beds for summaries,
  final-state validation, restarts and conservative dam installation. Reject
  other invalid or inactive states.
- Explicitly set and record the LAK maximum stage change at 5e-7 m.

Main retains its schema-v6 handoffs, editable MakeInputs variables, 50×100×5
default grid, legacy hydrograph/atmospheric forcing, fixed spinup and single-run
CLI. No study table, sweep runner, edge WEL packages or adaptive spinup were
introduced. IMS profiles, closure thresholds, 2000 outer-iteration allowance,
0.1% budget checks and production calendars are unchanged.

## Final validation at 5e-7 m

Fresh local output root:
`/Users/nick.engdahl/BDamRuns/bdam-lak-5e7-20261021/main`.
MakeGrid → MakeInputs regenerated both handoffs; the actual pond dry-bottom,
terrain-breakpoint and capped-storage checks pass. All 36 Python tests pass,
including the exact recorded 5e-7 tolerance check.

The complete default workflow passes: six workspaces, 308 saved endpoints,
101 spinup-summary rows and 210 monitored-summary rows. Independent completion
checks verify required binaries, saved times/counts, explicit LAK input and
solver-record tolerance, strict budgets, monitoring and restart states.
Maximum coupled budget discrepancy is **0.0000033450487344830406%**, below
the unchanged 0.1% limit. Dam installation conserves 2.944210461465763 m³
with zero error. See `completion_checks.json` and `model_runner.log`.

All three drying/restart/installation/rewetting solves pass (seven seven-day
steps, 49 days). The pond cycle is 0 → 0.611019540068 → 0.00179118689926 → 0 m³,
with genuine MF6 dry flags. Maximum diagnostic coupled discrepancy is
**0.005110462200753013%**. See `drying/validation.json` and `drying.log`.

Matched-input numerical serialization against the updated parameters-table
source passes for both phases, including LAK at 5e-7 (`parity/parity.json`).
The reference-only zero edge WEL packages remain explicitly excluded.
Compared with the previous 3e-7 candidate across every saved endpoint,
maximum head difference is 4.020084265476953e-10 m and maximum lake-stage
difference is 4.753142324176451e-16 m. These are measured differences, not
a claim of binary identity. Runtime versions are the same as recorded below.

## Earlier tolerance controls

The exact parameters-table LAK setting, `maximum_stage_change=1e-7`, passes
matched-input serialization but fails main's default staged spinup at the
31-day period ending at local day 700 (period 23 of spinup remainder).
MF6 identifies lake 2's residual, which plateaus near 0.00747 m after 2000
outer iterations. No UZF wave-capacity error was reported.

One-period replays from the valid saved state at day 669 isolate this setting:

| LAK control | Result |
| --- | --- |
| 1e-7, 1000 local iterations, diagnostic outer cap 100 | Fails |
| 1e-9, production outer cap 2000 | Fails |
| Original MF6 1e-5, diagnostic outer cap 100 | Passes |
| 3e-7, 1e-6, 3e-6, diagnostic outer cap 100 | Each passes |

MF6 6.7.0 uses this parameter for its finite-difference stage increment and
local convergence/bisection criteria. These controls establish sensitivity,
not a general proof that any one tolerance works for every physical setup.
Increasing the iteration budget is insufficient. The 3e-7 candidate retains
a much smaller increment than the original 1e-5 default and passes the
near-dry regression described below. Both branches now use 5e-7 following
the user's selection. The earlier 3e-7 runs
were explicit diagnostic overrides; their evidence below is historical.

## Earlier validation at 1e-7 and 3e-7 m

All execution used local nonsynchronized storage:
`/Users/nick.engdahl/BDamRuns/bdam-main-lak-20261021`.
MF6 version: 6.7.0 (02/05/2026). Source changes require regenerated inputs.

- 36 Python tests pass (`python-tests.log`).
- MakeGrid → MakeInputs completed in order; both actual handoffs pass the
  dry-bottom, terrain-breakpoint, first-interval storage and upper-cap checks.
  Existing MATLAB coarse-river tests pass (`preparation.log`).
- Matched-input comparison against the committed parameters-table source
  passes for pre/post numerical MF6 input files and eight shared numerical
  functions (`parity/parity.json`). The reference-only zero WEL packages are
  explicitly excluded; branch defaults are not claimed identical.
- Three short 3e-7 MF6 solves pass, with seven saved seven-day steps spanning
  49 days: dry state, restart, empty dam installation, rewetting, partial
  recession and complete depletion (`drying_3e-7/validation.json`). Pond
  volumes are 0, 0.611019540068, 0.00179118689926 and 0 m³ in the post-dam
  cycle. Installation conserves exactly zero volume. Maximum coupled budget
  discrepancy is 0.005110462200753013%, below the unchanged 0.1% criterion.
- On main's grid one dry river pool reports about 4.34e-19 m³ because DIS and
  TAB6 serialize bed elevations differently. The diagnostic requires both
  the actual MF6 DHDRY flag and volume within eight bed ULPs times onset
  area. It does not classify a positive physical water depth as dry or
  modify observations. Restart/audit volumes at the handoff bed are zero.

The complete unchanged default calendar passes at the candidate 3e-7 setting:
six workspaces, 308 saved endpoints, all required binaries/restart states,
normal termination, monitoring, boundary audits, and strict budget checks.
The maximum coupled external discrepancy is 0.0000033450469674006173%.
The wet installation audit conserves 2.9442104614657545 m³ with zero error.
The candidate-only receipt is `candidate_3e-7_completion_checks.json`; this
does not validate other tolerance settings, including the final 5e-7 setting.

Runtime versions are MATLAB R2025b, Python 3.14.6, NumPy 2.5.2, FloPy 3.10.0
and h5py 3.16.0. The viewer suite has no failed test cases; two optional
historical BDam_out integration fixtures are unavailable and were filtered.
The wrapper's assertion that every case passed consequently failed. This is
reported separately from the new candidate's actual-results loader check.
That actual-results check passes: 101 spinup frames, 209 monitored frames,
309 combined frames over 3285 days, with binary heads matching monitoring
values at the first monitored endpoint and final endpoint (`candidate-loader.log`).
No model process remains active.

## Reproduce

From a local nonsynchronized source copy, after MakeGrid and MakeInputs:

```sh
MPLCONFIGDIR=../matplotlib-cache python3 -m unittest discover -v
matlab -batch "addpath('tests'); verifyPreparedLakeStorage('ModelInput')"
python3 tools/verify_lake_drying.py ../unique-drying-test
python3 tools/verify_lak_parity.py ../unique-parity-test --reference /local/parameters-table/source
```

The drying tool performs three bounded diagnostic simulations with explicit
test forcing; it does not replace the production schedule or a default-run
acceptance check. The parity tool builds inputs without running MF6.
Retained failures are under `staging` and `controls`, with control JSON
receipts and logs at the local validation root. Do not delete them.
