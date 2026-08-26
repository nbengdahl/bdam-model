# Changelog

All notable changes to BDam will be documented in this file.

## Unreleased

### Added

- A MATLAB results viewer for completed runs, including indexed MF6 head-file
  reading, spinup/monitored/all timeline scopes, dual-unit monitoring plots,
  assignable groundwater depth/elevation rasters and contours, automatic
  long-domain map transposition, explicit output loading, in-memory head-field
  preprocessing, persistent graphics updates, and fixed-rate animation controls
  through 20 frames per second.

### Changed

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
