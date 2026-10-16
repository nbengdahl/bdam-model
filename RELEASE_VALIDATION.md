> Historical validation record. Configurations, commands and machine-local paths
> below describe the dated source/run, not current branch defaults. Use
> [README.md](README.md) for current operation and [CLEANUP_VALIDATION.md](CLEANUP_VALIDATION.md)
> for the current validation index. Evidence and numerical values are retained.

# Release validation

## v0.2.1 — 15 October 2026

This release includes the subsequent mean-inflow default change to 0.1 m3/s,
results-viewer defaults, lake-numbering documentation and downstream
channel-bed outlet-invert correction. See `CHANGELOG.md` for details.
The full-run results below apply to the historical v0.2.0 tag and must not
be presented as validation of the later inflow and outlet changes. No new
full MODFLOW validation was performed as part of release packaging.

The v0.2.1 viewer default was `~/BDamRuns/bdam-q0p1-20261015/BDam`.
The historical output root below remains available through an explicit
argument to `LaunchBDamResultsViewerApp`.

## v0.2.0 validation — 14 October 2026

The promoted package completed a fresh default run with MATLAB R2025b, Python
3.12.1, FloPy 3.10.0, h5py 3.16.0, NumPy 2.5.2 and MODFLOW 6.7.0. Geometry and
both schema-v6 handoffs were regenerated in order in local storage.

Configuration: default 50 × 100 × 5 groundwater grid, eight pre-dam river pools,
one post-dam pond plus two downstream pools; full DEM storage and pond-only
upper-bank exchange trimming. The calendar was 0 fall / 4 monthly / 1 weekly
spinup years, followed by two weekly pre-dam and two weekly post-dam years.
No extra time steps or solver/closure changes were introduced.

All six workspaces passed the complete runner checks: normal termination,
nonempty required binaries with correct final times, water-balance QA, solver
statistics, monitoring, fluxes and restart states. There were 308 saved endpoints:
12 first-year monthly, 88 remaining spinup and 208 monitored weekly steps.
Maximum coupled external-budget discrepancy was 0.000371987%. The surface-storage
installation audit passed the 1e-8 m³ conservation tolerance.

All 36 required binary outputs were byte-identical to the independently validated
candidate. Eleven MATLAB reader/loader tests passed. The actual new results loaded
with 101 spinup frames, 209 monitored frames and 309 combined frames spanning
3,285 days; head fields matched monitoring values at pre/post transition and final
frames. The interactive GUI itself was not exercised. There are 210 monitored
summary rows because both phase initial states are retained; the viewer shares
their transition frame.

The 32 Python workflow, boundary, routing and storage-restart tests passed.
Comparative no-dam evidence and physical limits are in `RIVER_REFINEMENTS.md`.
This release run does not add another no-dam continuation or establish equilibrium.

## Inspect the completed run

Local output root:
`~/BDamRuns/bdam-v0.2.0-20261014/BDam`

At the v0.2.0 tag, `LaunchBDamResultsViewerApp` selected this root; click
**Load**. On the current branch, pass this output root explicitly to inspect the
historical run.

Detailed local receipts are `completion_checks.json`, `results_loader_checks.json`,
`model_runner.log` and `loader_validation.log` in the parent run directory.
Generated inputs and results are not committed to the source repository.
