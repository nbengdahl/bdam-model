# Prescribed groundwater edge flux validation — October 16, 2026

This receipt covers the `parameters-table` edge-flux feature after the earlier
cleanup. Registry v5 and HDF5 handoff v7 require fresh studies/preparation.
The earlier [cleanup receipt](CLEANUP_VALIDATION.md) records the preceding full
calendar comparison; the current feature intentionally uses short verification.

## Capability and defaults

Three finite scalar totals in m³/day are accepted:
`groundwater_edge_flux.x_min_m3_per_day`,
`groundwater_edge_flux.x_max_m3_per_day` and
`groundwater_edge_flux.y_max_m3_per_day`. All default to zero; positive enters,
negative leaves. Each total is distributed uniformly along its bottom-layer
edge (140, 140 and 70 cells on the default grid). Separate WEL_X_MIN,
WEL_X_MAX and WEL_Y_MAX packages preserve corner contributions, coexist with
downstream DRN/GHB, and disable automatic flow reduction. MF6 bottom layer is
zero-based layer 4; +y is row 0. Production calendars and solver tolerances
are unchanged. The ordinary study default remains one worker; explicit larger
scientific studies remain allowed.

`bdam.specified_groundwater_flux.csv` reports signed actual edge rates and
interval volumes. Combined groundwater budgets include downstream and edges;
DRN/GHB-specific fields and the downstream observation CSV retain their local
meaning. Native WEL totals are checked against the requested totals.

## Verification performed

Exactly four feature configurations used default geometry, two one-day pre-dam
steps, conservative installation transfer, then two one-day post-dam steps.
One solver ran at a time. This is eight feature solves and 16 saved endpoints.
The zero configuration was also replayed with preserved pre-feature source
(two reference solves) for regression comparison. No full spinup/production
suite was run. Short results have no production `completion.json` receipt.

| Configuration | −x / +x / +y total m³/day | Maximum coupled discrepancy | Result |
| --- | --- | --- | --- |
| zero | 0 / 0 / 0 | 1.78884422e-05% | pass |
| inflow | 3 / 5 / 7 | 3.32902822e-06% | pass |
| outflow | -3 / -5 / -7 | 3.38882081e-06% | pass |
| mixed | 3 / -5 / 7 | 3.88450956e-06% | pass |

- All eight feature workspaces passed normal termination, binary/restart,
  monitoring, strict budget and solver-statistics validation.
- Actual cell-resolved WEL budgets match each requested edge total at every
  endpoint, with correct bottom-layer placement and equal cell allocation.
- The mixed case retains 10 m³/day gross prescribed inflow and 5 m³/day gross
  prescribed outflow before corner cancellation. Downstream observations,
  aggregate rates/volumes and summary fields pass independent checks.
- Maximum coupled discrepancy is **1.78884422e-05%**, below the unchanged
  **0.1%** tolerance. Maximum installation volume error is 4.45e-16 m³.
- **646 pre-existing numerical HDF5 datasets match exactly**; the only added
  datasets are the three edge totals plus their shapes in each phase (12 total).
- **16 physical state/budget/observation files match byte for byte** between
  the new zero case and its pre-feature replay. All **24 original
  GWF budget arrays** also match exactly; WEL records are the expected addition.
- **87 Python tests and 3 focused MATLAB tests pass**. Static MATLAB checks of
  the two edited preparation/export files report no findings. Parameter-reference
  freshness and `git diff --check` pass. Worker count 5 is rejected before
  preparation or simulation; the verification tool accepts only 1–4, default 1.

## Reproduction and evidence

Run from a fresh local nonsynchronized copy:

```sh
python3 tools/verify_edge_fluxes.py /absolute/local/fresh-verification \
  --matlab /Applications/MATLAB_R2025b.app/bin/matlab --workers 1 \
  --baseline-source /absolute/local/preserved-pre-feature-source
```

Baseline source is optional for subsequent feature-only checks; it must be the
preserved pre-feature source for regression comparison. Existing verification
folders are rejected to preserve prior evidence. Do not use smoke outputs as
full-calendar production completions.

Local evidence root: `/Users/nick.engdahl/BDamRuns/bdam-edge-flux-20261016`.
The machine-readable receipt is `verification/edge_flux_verification.json`;
feature results are under `verification/short-results/`, reference results under
`verification/zero-reference-results/`. Logs are `edge_verification.log`,
`python_tests_pass.log`, `matlab_contracts.log` and `worker_limit_check.log`.
Final supplemental reporting/input checks are in
`verification/supplemental_checks.json`.

Runtime: Python 3.14.6, FloPy 3.10.0,
NumPy 2.5.2, h5py 3.16.0, MATLAB R2025b Update 7,
MODFLOW 6.7.0. No dependencies were installed or upgraded.

These short cases verify implementation and regression behavior. They do not
establish long-term equilibrium, calibration or feasibility of arbitrary large
withdrawals. Infeasible prescribed extraction must fail validation rather than
silently reduce its requested rate.
