# Changelog

All notable changes to BDam will be documented in this file.

## Unreleased

### Changed

- Python requirements are now installed once for the user's selected
  persistent `python3` and reused across runs. The documented workflow no
  longer creates a separate virtual environment inside every run directory.
- Agent instructions explicitly prohibit per-run Python environments and do
  not assume a particular Python distributor or operating-system package
  manager.

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
