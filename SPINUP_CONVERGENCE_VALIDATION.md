# Relative spinup convergence validation — October 16, 2026

Feature: optional September year-end relative-state convergence, two consecutive
passing comparisons, ten weekly years by default, and per-case DNC handling.
See [configuration and interpretation](PARAMETERS.md#optional-convergence-controlled-spinup).

## Automated checks

- Python: **102 passed**, `python3 -m unittest discover -v -p 'test_*.py'`.
  Covers relative thresholds/floors, datum invariance, controlling indices,
  invalid states, first-year baseline, streak resets, cap/DNC, restart transfer,
  daily-monitoring/weekly-spinup scheduling, warmup and diagnostic behavior,
  configuration/CSV booleans, standalone exit code, study continuation,
  report tampering, and recomputation during compact reuse. Existing fixed
  spinup, case-table, boundary and monitoring tests also pass.
- MATLAB: **22 passed, no skips**, covering `evaluateBDamCasesTest`,
  `adaptiveSpinupViewerTest`, and `testBDamResultsViewer`. Actual-output tests
  used the small adaptive execution below. Boolean settings and DNC round-trip
  through the MATLAB bridge; viewer ordering works with and without warmup.
- `studyResultsIntegrationTest`: **two assumption skips** because the bounded
  smoke execution deliberately has no production `completion.json`. Actual
  output loading/viewing is covered by the 22 passing tests above.
- MATLAB static analysis: no errors in the changed loader or new/changed tests;
  one existing informational array-growth notice in the loader.
- Generated parameter-reference consistency and `git diff --check` pass.

## Small numerical verification

Command from a local source copy:

```sh
MPLCONFIGDIR=/absolute/local/cache python3 tools/verify_spinup_convergence.py \
  /absolute/local/fresh-verification --matlab /Applications/MATLAB_R2025b.app/bin/matlab
```

The test uses a 15×20 grid, three layers, no fall/monthly warmup, three weekly
spinup years and one weekly pre-dam year. Geometry is 30×40 m at 2 m spacing,
without meanders and with smaller cross-section widths/depths. Post-dam handoffs
are prepared but no post-dam year is simulated. All three relative tolerances
are deliberately **1.0 for this test only**, bounding runtime at three weekly
years. Production defaults remain 0.001 / 0.01 / 0.005.

An independent fixed-duration control repeats the same three annual spinup
restarts and monitored calendar. **All 24 compared binary files are byte-identical**:
GWF heads/budget, LAK stage/budget and UZF water content/budget for four years.
Both arms retain 208 saved steps (52 per 365-day year); 416 total. Existing
normal-termination, output, solver and water-budget QA pass for every workspace.
Maximum reported whole-model budget discrepancy is about 0.01%, below the
unchanged 0.1% threshold. Adaptive summary has 157 rows; monitored summary has 53.

The final spinup comparison has relative maxima of approximately 0.011918 for
heads, 4.2244e-7 for stages and 0.0052062 for water content. This case therefore
**does not demonstrate convergence at the production thresholds in three years**;
it validates scheduling, measurement, early-stop mechanics and state equivalence.
Deterministic unit tests exercise production thresholds and DNC behavior.

Runtime: Python 3.14.6, NumPy 2.5.2, h5py 3.16.0, FloPy 3.10.0,
MATLAB R2025b, MODFLOW 6.7.0 (02/05/2026).

## Retained local evidence

- Root: `/private/tmp/bdam-spinup-20261016/`.
- Machine-readable receipt: `smoke-runtime/validation.json`.
- Adaptive execution:
  `smoke-runtime/study/executions/92562f24325062f841fdc790/BDam`.
- Fixed control: `smoke-runtime/fixed-control/`; the monitored control is
  `monitored_year_01`.
- Final Python log: `all-python-final.log`; numerical logs:
  `smoke-runtime.log` and `control-resume.log`.

Initial sandboxed MATLAB preparation exited silently; a normal-runtime retry
succeeded. The first control comparison exposed a verifier error: its monitored
year incorrectly reused the spinup forcing override. The verifier was corrected
to use the native monitored calendar, and only that control year was rerun with
`--resume-control`. The original `year_04` and failure log are retained.
No QA thresholds or model physics were relaxed. No production completion
receipt was written. No full default-size simulation was run.
