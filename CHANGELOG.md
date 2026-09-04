# Changelog

All notable changes to BDam will be documented in this file.

## Unreleased

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

- The default balanced solver uses `COMPLEX` for the first solve from
  analytical initial conditions and `MODERATE` for restarted workspaces, with
  the existing strict convergence tolerances throughout;
  `--solver-profile conservative` uses `COMPLEX` for every solve.
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
