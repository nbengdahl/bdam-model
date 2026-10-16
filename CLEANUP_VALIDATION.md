# Cleanup assessment and validation — October 16, 2026

This record covers the `parameters-table` cleanup based on commit `b3e8bb5`.
Model source was reviewed in the shared checkout and executed only in a fresh
local copy. Prior runs, frozen studies and failure diagnostics were preserved.


The subsequent prescribed edge-flux feature is documented separately in
[EDGE_FLUX_VALIDATION.md](EDGE_FLUX_VALIDATION.md). The full-run equivalence
claims below apply to the cleanup before that feature was added.

## Documentation assessment before revision

| File | Intended reader / role | Assessment and revision |
| --- | --- | --- |
| `README.md` | Human project entry point | Mostly historical release operations under a new branch banner. Rewritten as current capabilities, defaults, two run paths and a guide index. |
| `END_USER_QUICK_START.md` | Human operator | Conflicting grid/calendar/lake descriptions, obsolete editable input blocks, mandatory MakeGrid and a personal viewer folder. Rewritten for generated geometry, local setup, outputs and recovery. |
| `PARAMETERS.md` | Human developer / optimizer user | Largely current. Corrected BDAM_CONFIG to a file path, clarified standalone/study behavior, added forcing, v4 migration and removed-control guidance. |
| `AGENTS.md` | Automated agents | Old release workflow contradicted its table appendix; stale test commands, paths and output/storage checklist. Replaced with current source map, invariants, run paths, checks and failure handling. |
| `SWEEPS.md` | Legacy-interface user | Active-looking commands described a removed MATLAB workflow. Replaced with the actual request adapter, explicit-case alternative and frozen-manifest policy. |
| `RIVER_REFINEMENTS.md` | Scientific/model developer | Fixed-count/two-pool claims and old geometry mixed with useful physics discussion. Updated configurable segmentation and restart behavior; retained dated formulation evidence. |
| `BOUNDARY_ASSUMPTIONS.md` | Scientific/model developer | Contract remains applicable. Corrected automatic boundary-K wording and case-based sensitivity procedure. |
| `PARAMETER_VALIDATION.md` | Historical implementation evidence | Useful v3 results; marked their scope explicitly and linked current validation. |
| `RELEASE_VALIDATION.md` | Historical release evidence | Retained numerical receipts; labeled historical and changed the personal viewer default to past tense. |
| `SWEEP_VALIDATION.md` | Historical sweep evidence | Retained older calendars, solver allowances and results under an explicit historical label. |
| `BOUNDARY_VALIDATION.md` | Historical boundary evidence | Retained measured sensitivities, limitations and original run identity under an explicit historical label. |
| `CHANGELOG.md` | Human/agent change history | Preserved prior entries, moved the document title to the top and added the cleanup/migration summary. |

`PARAMETER_REFERENCE.md` is a new human-readable catalog generated directly from
the registry by `tools/update_parameter_reference.py`. Its `--check` mode detects
staleness. This avoids maintaining another hand-written default/input table.

## Code and artifact changes

- Removed the unused `mergeBDamConfig.m`, unused Python imports, uncalled initial-
  head loader, test-only geometry fingerprint helper, and obsolete external
  baseline-import/old collector paths. Runtime no longer imports wildcard exports
  from the deprecated adapter; MATLAB records preparation receipts directly
  through `bdam_runtime.py`.
- Replaced pre-dam single-lake/post-dam downstream-lake scaffolding that was
  overwritten by coarse-river assembly with explicit lake templates. Removed
  unexported intermediate observation/lake-mask metadata and legacy MAT fallback.
- Registry v4 rejects three inactive scientific controls: intermediate river
  initial depth, intermediate pre-dam width and pond preview depth. Corrected
  catalog units. New cases need fresh source/registry; frozen studies stay intact.
- Removed old preview-depth and forced-conductivity-change assertions. Positive
  sub-meter dams and unity K/K33 multipliers now prepare; zero dam height is
  rejected explicitly. Default inputs/physics are preserved.
- Viewer defaults select the current package rather than a personal run folder.
  Optional actual-output tests use `BDAM_TEST_OUTPUT_ROOT`; the study integration
  tests retain their completion-receipt requirement.
- Expanded ignore rules for generated runtime receipts, caches and MATLAB editor
  backups. No simulation results or historical evidence were deleted. Active
  terrain import/export, both forcing modes and the documented vector adapter
  remain available.

## Completed validation

All checks passed on the cleaned source. Python 3.14.6, FloPy 3.10.0, h5py 3.16.0,
NumPy 2.5.2, MATLAB R2025b Update 7 and MODFLOW 6.7.0 were used. Package versions,
calendar, solver policy, UZF wave capacity and closure tolerances were unchanged.

| Check | Result |
| --- | --- |
| Python workflow, forcing, adapter, study and runtime suites | 81 passed |
| MATLAB geometry, segmentation, table and preparation contracts | 17 passed |
| MATLAB binary-reader/viewer suite with actual completed output | 15 passed; no skips |
| Actual completed-study loader/topology and viewer tests | 2 passed |
| MATLAB static analysis | No syntax errors; existing performance/suppression notices remain |
| Local documentation links and code fences | Passed |
| Registry-generated parameter catalog freshness | Passed |
| `git diff --check` | Passed |

The MATLAB counts represent 34 distinct tests. The viewer suite was also run
against the trusted baseline before the full regression, then against the new
study. The new preparation regression builds a 0.5 m dam with both conductivity
multipliers equal to 1 and verifies unchanged under-dam K/K33.

The full default ran through `Study.submit`, serial MATLAB preparation,
`Study.evaluate` and collection, with one simulation attempt:

- Six completed workspaces and 308 saved time steps; correct configured final
  times, restart states, binaries, observations, boundary audits, fluxes and summaries.
- Every numerical dataset matched the trusted baseline: 380 pre-dam and 266
  post-dam HDF5 datasets, including shape metadata, with no added/removed datasets.
- All **74 scientific CSV/binary files matched byte for byte**, including solver
  iteration CSVs and summaries. The six water-balance JSON records and the
  dam-installation storage audit also matched exactly.
- Maximum coupled discrepancy **2.31783558e-06%**, against
  the unchanged 0.1% tolerance. Installation surface-volume error remains
  -8.8817842e-16 m³.
- Study evaluation time **11.70 minutes**, excluding MATLAB preparation and
  final independent checks. Timing and source/manifest metadata are not numerical
  equivalence criteria.
- Re-evaluating the same batch revalidated/reused completion without launching
  MODFLOW or creating a second attempt. Current runtime source matches the
  immutable execution snapshot. Later documentation refinements do not change it.
- Actual study output loaded in MATLAB and the viewer, including dynamic
  eight-pool pre-dam series, final-frame maps and memory caching.
- No model process or active staging directory remained at completion.

Local evidence root: `/Users/nick.engdahl/BDamRuns/bdam-cleanup-20261016`.
The completed execution is `/Users/nick.engdahl/BDamRuns/bdam-cleanup-20261016/ValidationStudy/executions/6ab418d2f2a224dc14479d04/BDam`.
The trusted baseline is `/Users/nick.engdahl/BDamRuns/bdam-parameters-check-20261015/BDam`.
These workstation-local paths are receipts, not defaults or required fixtures.

Evidence includes `cleanup_verification.json`/`.log`, `handoff_comparison.json`,
`python_tests.log`, `matlab_checks.log`, `matlab_static.log`,
`final_matlab_integration.log`, `study_evaluation.log`, `verification_scripts/`,
and the new study's immutable configuration, source/input fingerprints,
preparation log, execution log, completion receipt and case reports. Generated
inputs/results remain local and are not committed to the synchronized source.

## Validation history

- [Parameter-table implementation](PARAMETER_VALIDATION.md): original v3 API,
  full default/alternate segmentation, serial/parallel/reuse and observed failures.
- [Release record](RELEASE_VALIDATION.md): v0.2.0 full run and v0.2.1 packaging scope.
- [Sweep record](SWEEP_VALIDATION.md): previous larger-grid campaigns and legacy
  serial/parallel evidence; not the current table runbook.
- [Boundary record](BOUNDARY_VALIDATION.md): earlier 50 × 100 grid and low-inflow
  sensitivity matrix; not a quantitative sensitivity claim for current defaults.

Numerical equivalence verifies this cleanup's default preservation. Scientific
interpretation remains governed by the current river/boundary contracts; no new
calibration or equilibrium claim is made.
