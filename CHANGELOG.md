# Changelog

## 0.2.0 — 2026-10-14

- Promote validated coarse Manning river pools, two downstream segments and pond-only upper-bank exchange trimming with full DEM storage.
- Conserve surface volume at installation, preserve geographic exchange totals and document phase-dependent native LAK IDs.
- Require regenerated schema v6 handoffs with independent storage/exchange masks and outlet laws.
- Record comparative validation and physical limits in RIVER_REFINEMENTS.md; retain strict solver, budget and calendar checks.


- Use monthly-first spinup: replace the two configured constant fall-average
  years with two additional monthly-climatology years, preserving five total
  spinup years (0 fall, 4 monthly, 1 weekly). Benchmark against the retained
  annual-start case; the first year contains 12 monthly periods.
- Extend the sweep approach to a 2000-outer-iteration allowance for both IMS
  profiles; retain damping, strict closure tolerances and the existing calendar.
  Record the configured allowance in solver statistics.
- Replace the hydrograph-derived remote-stage GHB default with a local
  outflow-only DRN boundary. Keep constant GHB as an explicit sensitivity mode.
- Separate surface outlet invert and initial river depth from groundwater
  reference levels; derive each from modeled outlet terrain and explicit inputs.
- Remove remote rating-curve and downstream-slope assumptions from preparation,
  export and runtime schedules. Handoff v5 rejects legacy inputs and requires
  regeneration rather than silently adopting changed physics.
- Report gross groundwater inflow/outflow by cell sign, retain GHB-only fields,
  add drain outflow and per-workspace boundary assumption diagnostics.
- Add boundary tests and document limitations and required sensitivity checks.

- Replace the nearest-channel initial head field with a regional-slope plane,
  anchored 0.1 m above the downstream channel bottom; remove lateral rise,
  upslope correction, and terrain clipping. Regenerate older HDF5 handoffs.
- Add `--stop-after-monthly-spinup` for initial-condition diagnostics without
  running weekly spinup or monitored years.
- Test all fall forcing averages against their September/October/November
  monthly values and the relaxation forcing, plus signed X/Y initial planes.


All notable changes to BDam will be documented in this file.

## Earlier unreleased development

### Added

- A 7-day transient initial relaxation at September--November-average
  forcing now precedes configured fall-average spinup years. Its final
  groundwater, lake, and UZF state initializes the unchanged staged spinup.
- Balanced and conservative IMS solver profiles, compact outer-iteration
  diagnostics, optional detailed inner-iteration output, and per-workspace
  `bdam.solver_stats.json` provenance.
- A MATLAB results viewer for completed runs, including indexed MF6 head-file
  reading, spinup/monitored/all timeline scopes, dual-unit monitoring plots,
  assignable groundwater depth/elevation rasters and contours, automatic
  long-domain map transposition, explicit output loading, in-memory head-field
  preprocessing, persistent graphics updates, and fixed-rate animation controls
  through 20 frames per second.

### Changed

- Results Viewer frame zero now reads the actual `bdam.ic` initial condition;
  an N-step scope exposes N+1 frames, including 53 frames for a 52-week run.
- The runner uses robust `COMPLEX` settings for the initial relaxation and
  the first 365-day annual solve, then automatically returns to balanced
  `MODERATE` settings for the remaining staged spinup and monitored years.
  The first annual spinup workspace is retained separately so its solver
  profile and runtime remain auditable, and global conservative runs are
  prevented.
- Default UZF `NWAVESETS` is reduced from 1000 to 20. Both UZF wave-capacity
  inputs must be positive integers, and MF6 capacity failures now recommend
  regenerating inputs with 40 wave sets.
- Representative pre-/post-dam benchmarks improved from 129.1/134.5 seconds
  and roughly 11 GB allocated to 71.7/68.7 seconds and 286--289 MB allocated,
  while retaining strict convergence tolerances.
- Fall-average spinup years use a single 365-day stress period, time step, and
  output with the simple mean of the September, October, and November monthly
  values. Monthly and weekly years remain exactly 12 and 52 steps. The renamed
  `fall_average_spinup_years` input advances the preparation schema to v4.
- Python requirements are now installed once for the user's selected
  persistent `python3` and reused across runs. The documented workflow no
  longer creates a separate virtual environment inside every run directory.
- Agent instructions explicitly prohibit per-run Python environments and do
  not assume a particular Python distributor or operating-system package
  manager.
- The results loader and viewer now accept intentionally absent spinup outputs
  when all staged-spinup counts are zero; monitored and all timelines begin at
  day zero without exposing an invalid Spinup scope.
- Animation frame positions are zero-based, and Spinup/All map color limits
  ignore the first spinup frame so the initial state does not mask later change.

## [0.1.0] - 2026-08-24

### Added

- First public release of the BDam MATLAB, FloPy, and MODFLOW 6 workflow.
- Reproducible paired pre-dam and post-dam simulations with staged spinup.
- Automated output, restart-state, calendar, and water-balance validation.
- Interactive and scripted terrain generation.
- Pinned Python dependencies, fast tests, end-user documentation, and an
  agent operating runbook.

### Release status

This release is a transparent, uncalibrated demonstration framework. The
interfaces and model formulation may change before v1.0.0.

[0.1.0]: https://github.com/nbengdahl/bdam-model/releases/tag/v0.1.0
