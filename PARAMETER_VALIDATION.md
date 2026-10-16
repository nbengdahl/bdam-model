> Historical implementation validation of registry v3 (October 15, 2026).
> The v4 cleanup removes inactive controls and obsolete preparation/runtime code.
> See [CLEANUP_VALIDATION.md](CLEANUP_VALIDATION.md) for the current evidence and
> [PARAMETERS.md](PARAMETERS.md) for current operations. Original results follow.

# Parameter-table implementation validation

Validated 2026-10-15 on `parameters-table`, based on `parameter-sweeps` commit
`4dfb99f`. Model runs and diagnostics were kept in local nonsynchronized storage.

## Contract and integration checks

- 81 fast Python tests passed, including case resolution, table interchange,
  NumPy candidates, immutable batches, input/source/runtime identity, duplicate
  cases, failure records, concurrency locks, retention, collection and reuse.
- 16 MATLAB geometry/segmentation/table contract tests passed, including counts
  1/2/3, upstream remainder handling, insufficient grid resolution, automatic
  values, indexed names and Unicode metadata.
- Existing viewer suite: 13 passed; two optional historical-fixture tests filtered
  because that fixture was unavailable in the isolated validation copy.
- Actual completed-case integration: loader and viewer passed for both the smaller
  one-segment case and the full-size three-segment case (11 pre-dam pools and
  one pond plus three downstream pools after installation).
- Standalone `MakeInputs.m` generated geometry and paired handoffs without running
  `MakeGrid.m` first. CSV preview preserved an existing study's two-worker capacity.
- MATLAB static checks found no syntax errors. Existing pool-array growth and
  unused-argument notices remain; solver and numerical checks were not weakened.
- `git diff --check` passed.

## Full-calendar numerical results

Every successful case retained the default 0 fall / 4 monthly / 1 weekly spinup
plus 2 pre-dam and 2 post-dam years: six workspaces and 308 saved time steps.
All completed workspaces passed the existing output, final-time, solver and
water-balance validation. Coupled-budget tolerance remains 0.1 percent.

| Configuration | Runtime, minutes | Saved steps | Maximum coupled discrepancy, percent |
| --- | ---: | ---: | ---: |
| Fresh parameter-sweeps baseline | 11.48 | 308 | 2.3178356e-06 |
| Default: 2 segments | 11.53 | 308 | 2.3178356e-06 |
| Full-size: 1 segment | 11.56 | 308 | 2.5746695e-06 |
| Full-size: 3 segments, changed dam geometry | 10.54 | 308 | 3.1243817e-06 |
| Smaller geometry, serial: 1 segment | 2.40 | 308 | 2.3120506e-06 |
| Smaller geometry, parallel: 1 segment | 2.41 | 308 | 2.3120506e-06 |

The full-size geometry was 70 × 140 cells with five layers. The three-segment
variant used dam height 1.4 m and relative upstream location 0.27. Smaller pilots
used 50 × 60 cells, meander amplitude 2 m and dam location 0.30, retaining five
layers and the complete default calendar. Timing excludes serial MATLAB
preparation and is specific to this machine and concurrent workload.

All 374 baseline pre-dam and 260 baseline post-dam HDF5 datasets matched exactly
for the equivalent default case. Its 74 scientific CSV/binary result files also
matched the fresh branch baseline byte for byte. Timestamp-bearing listings,
geometry container bytes and elapsed runtime are not scientific comparisons.

The successful smaller one-segment case produced 74 byte-identical scientific
CSV/binary files under serial and parallel scheduling. Duplicate rows retained
separate result records. A second optimizer-style batch reused its validated
execution with exactly one recorded simulation attempt.

## Observed failures

The smaller three-segment configuration with K = 0.04 m/day and specific yield
0.15 failed MF6 LAK convergence at stress period 24 of staged spinup, under both
serial and parallel scheduling. This configuration remains a recorded failure;
no solver profile, closure tolerance, calendar or physics was changed to force
completion. It does not establish that three segments generally fail: the
full-size three-segment case above completed successfully.

Requests for 100 downstream segments on the smaller geometry failed preparation
with an explicit report of 17 available downstream longitudinal channel cells.
Invalid cases stayed in the case index and were excluded from scientific summary
rows; valid cases continued. Failed simulation staging and preparation retry
artifacts were preserved.

## Evidence and reproducibility

The local evidence root is:

`/private/tmp/bdam-parameters-validation-20261015`

It contains `validation_summary.json`, `baseline_comparison.json`,
`handoff_comparison.json`, `scheduling_comparison.json`, `optimizer_reuse.json`,
Python test logs, MATLAB preparation/entry-point logs, immutable execution
snapshots, successful results and retained failed diagnostics. Runtime provenance
and scientific source/input fingerprints are recorded inside each execution.

The full-size runs used frozen development snapshots. Subsequent entry-point,
metadata and reporting refinements were checked separately with contract tests,
actual MATLAB preparation and collection of completed outputs. The earliest
full-size batch predates the final manifest-integrity field; retain its frozen
tools rather than treating that evidence folder as a new production study.
Create fresh studies with the completed branch interface.

MODFLOW 6 was 6.7.0 (2026-02-05), MATLAB R2025b Update 7, and the selected persistent
Python interpreter was 3.14 with the pinned model dependencies. No validation
model process remained active at completion. Numerical completion does not
establish calibration or periodic groundwater equilibrium.
