> Historical validation record. Configurations, commands and machine-local paths
> below describe the dated source/run, not current branch defaults. Use
> [README.md](README.md) for current operation and [CLEANUP_VALIDATION.md](CLEANUP_VALIDATION.md)
> for the current validation index. Evidence and numerical values are retained.

# v0.2.0 integration validation — 14 October 2026

The parameter-sweep branch now includes main's coarse Manning river pools,
pond-only upper-bank exchange trimming, full DEM storage, conserved installation
restart and independent local DRN / optional constant GHB boundaries. Schema v6
inputs and campaign/parameter schemas v2 require fresh preparation. The existing
70 × 140 × 5 grid and periodic forcing are retained; spinup is 0/4/1 with weekly
two-year pre-dam and two-year post-dam monitoring.

All 53 fast workflow, river, forcing and campaign tests passed on the final merged
source. MATLAB regenerated the larger geometry and both handoffs in an isolated
local copy. Both FloPy packages passed build validation. The standard campaign
launcher then completed one full-output default baseline on its first attempt:
six validated workspaces, 308 saved endpoints, all required binaries, final times,
observation/flux CSVs, solver statistics, restart arrays and passing budget QA.
Maximum coupled external-budget discrepancy: 0.000575333149%. Installation
surface-storage error: 6.9388939e-18 m³. Campaign elapsed time:
640.3 seconds. No calendar, tolerance or solver changes
were needed. The new helper is included in scientific source fingerprints.
Repeating the campaign launch successfully revalidated and skipped the completed
member without creating another attempt or starting MODFLOW.

Pilot output root: `/Users/nick.engdahl/BDamRuns/sweeps-v0.2.0-pilot-20261014/campaign/members/43abb005e27066bd/BDam`.
Detailed receipt: `/Users/nick.engdahl/BDamRuns/sweeps-v0.2.0-pilot-20261014/integration_checks.json`.
Existing campaigns and snapshots were not edited. The simulation source was
fixed at preparation; later changes were documentation, launcher defaults and
planner validation allowing signed groundwater level offsets consistently with
the main MATLAB contract. Runtime physics code is unchanged.

This integration check covers the full default baseline and fast campaign tests.
The historical factorial serial/parallel comparison below was not rerun with
v0.2.0. It does not validate parameter rankings or losing/disconnected rivers.
See RIVER_REFINEMENTS.md for physical limits and matched-control evidence.

## Historical validation of earlier sweep physics

> Historical validation: the results below describe 3/2/2 spinup and a
> 1000-iteration cap. On 14 October 2026, solver infrastructure was aligned
> with main (2000 iterations; 0/5/2 monthly-first spinup). No new tests or
> simulations were run for that synchronization, per user instruction.

# Parameter-sweeps validation

Validated October 10, 2026 with MATLAB R2025b, Python 3.14.6, FloPy 3.10.0,
h5py 3.16.0, NumPy 2.5.2 and MF6 6.7.0 (2026-02-05).

## Result

The full default baseline and all four factorial members completed with passing
scientific QA. The serial and parallel baseline summary CSVs are byte-identical;
final groundwater heads, lake stages and UZF water contents match exactly for
both monitored pre-dam and both post-dam years. All outputs remain fully retained.

The branch remains `codex/parameter-sweeps` in the isolated local checkout
`/Users/nick.engdahl/BDamRuns/parameter-sweeps`. Main and its existing uncommitted
MakeInputs settings were preserved.

## Causes and fixes

- The new 70 x 140-cell, five-layer configuration exhausted the preset nonlinear
  iteration allowances. The first annual periodic solve required 548 iterations,
  beyond the former conservative limit of 100. The next fall-average step needed
  63, beyond the former balanced limit of 50. Both profiles now explicitly allow
  1000 outer iterations, retaining their original damping, inner solver settings,
  strict head/flow closure tolerances and one step per configured forcing period.
  The [MF6 IMS documentation](https://modflow6.readthedocs.io/en/latest/_mf6io/sln-ims.html)
  describes the preset iteration limits. Solver statistics record the allowance.
- A controlled run of the same expanded grid with legacy forcing also failed at
  100 annual iterations and passed at 505 with the larger allowance. The failure
  therefore persists independently of the periodic-forcing implementation.
- The earlier successful 50 x 100-cell, ten-layer configuration still converges
  in 28 annual iterations. Its saved final heads, lake stages and UZF contents
  reproduced exactly, with maximum absolute differences of zero.
- The planner had copied generated forcing JSON files from a previously prepared
  source checkout into immutable source snapshots. Preparation overwrote them,
  triggering an integrity failure. Generated requests, diagnostics and campaign
  artifacts are now excluded from source snapshots; actual source/input checks
  remain enforced.
- Integer and floating representations such as `1` and `1.0` produced different
  configuration hashes, duplicating a reference already in a Cartesian product.
  Registered scalar candidates now have a canonical numeric representation.

## Full baseline

Five layers; 70 x 140 cells at 1 m spacing; seven-day relaxation, 3/2/2 spinup,
and two monitored pre-dam plus two post-dam years. Validated saved-step counts:

| Workspace | Steps | Final elapsed days |
| --- | ---: | ---: |
| Initial relaxation | 1 | 7 |
| First fall-average year | 1 | 365 |
| Remaining staged spinup | 130 | 2190 |
| Each of four monitored years | 52 | 365 |

Total: 340 MF6 saved steps, 132 spinup-summary rows and 210 monitored-summary rows.
The member completed in 13.90 minutes, excluding MATLAB preparation. Maximum
coupled external-budget discrepancy was 0.00034820%, against the unchanged 0.1%
limit. Full retained campaign storage is approximately 3.8 GiB.

## Four-worker factorial

The full default calendar was retained. Axes were precipitation timing shifts
[0,14] days and inflow seasonal-width factors [1,1.2], producing exactly four
members with one default reference. `n_parallel_runs = 4` was used as requested.

| Member | Runtime (minutes) | Maximum outer iterations | Maximum coupled discrepancy (%) |
| --- | ---: | ---: | ---: |
| 61013b8fb7e8386b | 14.36 | 548 | 0.00034819 |
| 681430e841b59255 | 14.19 | 505 | 0.00035096 |
| 22b85740afb64b0f | 14.31 | 544 | 0.00032831 |
| 6a1f894230a74ade | 14.42 | 607 | 0.00033244 |

All four members passed all seven workspace checks, with 340 saved steps each.
The collector produced four passing index rows and 1368 scientific
ensemble-summary rows, including member IDs and both axis values.

Campaign wall time was 14.64 minutes, excluding serial
MATLAB preparation. Monitoring observed exactly 4 simultaneous MF6 processes,
with peak combined MF6 resident memory of
1.20 GiB. This memory figure excludes Python and MATLAB.
The full-output factorial retained approximately 15 GiB.

A second launcher joined the active campaign. Both launchers returned success,
each member retained exactly one execution attempt, and capacity never exceeded
four. Completed-member resume and validated baseline reuse were also exercised
successfully without launching another simulation.

## Forcing and fast verification

All 43 fast tests pass. Coverage includes Cartesian counts, native-array/scalar
registration, member-dependent defaults, invalid combinations, numeric identity,
baseline omission/reuse, snapshot integrity, inherited process locks, capacity,
resume, CSV collection and compact-retention receipts. Calendar tests retain
one time step per period and the requested default year counts. git diff --check
passes.

Forcing tests verify periodic values/slopes, nonnegativity, exact annual
conservation, boundary-crossing shifts, width direction and atmospheric coupling.
All four actual handoffs retain identical reference rating curves. Annual inflow
is 31,536 m3 in every variant. The width-factor change increases measured circular
seasonal RMS width from 49.85 to 55.96 days. The precipitation shift preserves
annual precipitation, while the existing seasonal recharge efficiency changes
annual land infiltration from 92.70 to 91.61 mm; this coupling is reported.

## Remaining scientific tuning

These runs establish numerical completion and execution reproducibility, rather
than certifying periodic groundwater equilibrium. Between the two monitored
pre-dam year ends, maximum head change in cells saturated at both ends is 4.30 cm
(RMS 2.55 cm). The corresponding post-dam changes are 13.08 cm (RMS 7.72 cm),
including the dam-response transient. Lake-stage changes are much smaller.
Assess spinup adequacy and useful parameter ranges before the large ensemble;
the requested 3/2/2 defaults were retained.

## Persistent evidence

All campaign paths are below `/Users/nick.engdahl/BDamRuns/parameter-sweeps-validation`:

- `fixed-baseline-v3/`: validated serial baseline, index, CSVs and interannual metrics.
- `fixed-factorial-v2/`: four full-output members, ensemble CSVs,
  `scientific_validation.json`, `execution_metrics.json` and launcher logs.
- `previous-configuration-comparison/`: exact earlier-configuration restart comparison.
- `legacy-comparison/solver-control/`: retained failed old-limit solve and passing control.
- `baseline-reuse/`: validated baseline reuse without a solver launch.
- Earlier failed/preparation-only campaigns remain intact for diagnosis.
