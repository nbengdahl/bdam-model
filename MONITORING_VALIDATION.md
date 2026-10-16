# Monitoring CSV validation — October 16, 2026

The `parameters-table` monitoring addition uses registry v6 / HDF5 handoff v8.
Fresh studies/preparation are required. Existing frozen studies retain their
original code and inputs. Earlier [edge-flux](EDGE_FLUX_VALIDATION.md) and
[cleanup](CLEANUP_VALIDATION.md) receipts record their respective prior versions.

## Implemented contract

`monitoring_points_file` defaults to `""`. Omitted/blank/whitespace filenames
(including case-CSV cells and blank MATLAB string cells) preserve the original
four stream points plus six bottom-layer grid points. A supplied file replaces
only the six grid points. Relative paths use the study source folder; absolute
paths are accepted. Inputs are copied and hashed, including content-change
identity checks and immutable original copies.

CSV headers `x,y,z,name` are case-insensitive. X/Y are model meters; z is depth
below the containing model column's terrain, in meters. Resolve containing
horizontal cells and vertical layers; use the deeper layer on an internal
vertical interface and the increasing-coordinate cell on a horizontal face.
Exterior horizontal faces, terrain and model bottom are included. Floating-point
roundoff at faces is handled explicitly. Observations sample cell heads directly.

Outside-X/Y, negative-depth and below-bottom points are omitted and reported.
Missing/unreadable files, missing columns, nonfinite/nonnumeric coordinates,
blank retained names and retained names duplicated without regard to case fail.
Differently named points can share cells. Empty, header-only and all-outside
supplied files leave only the four stream points.

IDs use original data-row numbers, e.g. `head_csv_0003`; omitted rows leave gaps.
CSV names remain human labels. `monitoring_targets.csv` maps IDs to labels,
requested depths/elevations and resolved cells/center elevations.
`monitoring_omitted.csv` records original rows, coordinates, names and reasons;
it is published during preparation and in monitored workspaces. Standalone HDF5
retains target/omission metadata without its JSON companion. Completion checks
validate the published metadata against preparation. The loader checks pre/post
alignment including layers/elevations, and the viewer preserves CSV labels.

## Checks and numerical verification

- **90 Python tests pass**, including blank CSV cells, file snapshots, changed
  contents/absolute-path identity, original copy preservation, missing files,
  metadata labels/depths and omission audit validation.
- **25 MATLAB tests pass, with no failures or skips**, including default ten-point
  layout, depths/interfaces, exterior faces, decimal-spacing face ties,
  duplicate-cell points, malformed input, partial/all omissions, empty/header-only
  files, export, MATLAB case-table bridging, binary readers and actual viewer tests.
- Static checks of six edited MATLAB files report no syntax errors. One existing
  loader array-growth advisory remains. Parameter catalog freshness and
  `git diff --check` pass.
- Exactly **two numerical configurations** (grid and CSV), **one worker**, four
  native solves total. Each configuration has two one-day pre-dam and two one-day
  post-dam steps, conservative installation transfer, no full spinup/production.
- Grid has ten targets. CSV has four unchanged stream targets plus four file
  targets; three out-of-volume rows are omitted with reasons. Shallow/deep points
  in the same column resolve to different layers. Every saved observation matches
  its binary head-file cell. HDF5-only runtime metadata checks pass in both phases.
- **20 hydraulic state/budget/flux files match byte for byte** between grid
  and CSV configurations. All four workspaces pass strict numerical completion
  and coupled budget checks; maximum coupled discrepancy is **1.78884422e-05%**
  against the unchanged **0.1%** tolerance.
- Default regression also matches the preceding trusted short zero run exactly:
  **658 numerical HDF5 datasets** and **23 output files**, including default point-head
  observations and the full monitored summary. No reference rerun was needed.
- Actual CSV results load into the viewer with **5 frames**. Original labels,
  including `Shallow α`, appear in the variable list and selected map annotations.
  There are no production `completion.json` receipts for these short runs.

## Reproduction and retained evidence

From a fresh local nonsynchronized source copy:

```sh
python3 tools/verify_monitoring_points.py /absolute/local/fresh-verification \
  --matlab /Applications/MATLAB_R2025b.app/bin/matlab
```

The tool prepares exactly two cases, runs serially, compares physical outputs,
checks observations/HDF5 metadata, and verifies viewer labels. Existing output
folders are rejected to preserve evidence. It writes a short verification receipt,
never a production completion. Use `examples/monitoring_points.csv` for a small
user-facing input example; full conventions are in
[PARAMETERS.md](PARAMETERS.md#optional-monitoring-csv).

Evidence root: `/Users/nick.engdahl/BDamRuns/bdam-monitoring-csv-20261016`.
Receipt: `verification/monitoring_verification.json`; results:
`verification/short-results/{grid,csv}/`; viewer receipt:
`verification/viewer_verification.json`. Logs: `monitoring_verification.log`,
`python_tests_final.log`, `matlab_tests_final.log` and
`viewer_verification_final.log`; counts are in `matlab_test_summary.json`.
Final translated/decimal face checks are in `mapping_faces_final.log`.
The final report includes read-only revalidation with the final metadata checks.

Runtime: Python 3.14.6, FloPy 3.10.0, NumPy
2.5.2, h5py 3.16.0, MATLAB R2025b Update 7, MODFLOW 6.7.0.
No dependencies were installed or upgraded. The short runs verify monitoring
behavior and hydraulic equivalence; they do not certify a full-calendar study.
