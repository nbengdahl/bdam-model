# Agent runbook: parameters-table branch

Read `README.md`, `END_USER_QUICK_START.md` and `PARAMETERS.md` before running or
changing the model. Use `PARAMETER_REFERENCE.md` and the registry for exact inputs;
read the river/boundary contracts for scientific changes. Validation receipts are
dated evidence, not current configuration instructions.

## Scope and invariants

1. Execute MATLAB, Python and MODFLOW only from local, nonsynchronized storage.
   Source may be edited/stored in Google Drive, but active source copies, studies,
   staging and results must be local. Prefer a fresh persistent `~/BDamRuns/` copy.
2. Use one persistent Python 3.12+ interpreter with the pinned requirements.
   Reuse installed compatible packages. Do not create per-run environments,
   install into synchronized source, use sudo, or override a provider's package
   protection. A shared persistent environment outside run folders is acceptable.
3. Use defaults unless the user authorizes scientific changes. Never hand-edit
   generated geometry, HDF5, MODFLOW inputs, frozen snapshots or results. Code
   cleanup must preserve default numerical inputs and outputs.
4. Preserve meters/days, the 365-day October–September water year, and exactly
   one time step per forcing period. Fall-average years have 1 step, monthly
   years 12, weekly years 52, daily monitored years 365. A configured fall phase
   adds one seven-day relaxation with 1 step. No hidden years or substeps.
5. The default is local outflow-only DRN; constant GHB is explicit. Never infer
   a downstream head/stage from upstream inflow or derive the surface outlet
   from a groundwater reference level. Sum gross boundary flows by cell sign.
6. Keep strict closure/budget tolerances and the runner's solver policy:
   conservative first modeled year, balanced subsequent solves, robust initial
   relaxation when configured, 2000 outer-iteration allowance. Do not apply
   conservative globally or change calendars to force convergence.
7. No duplicate standalone model run. Inspect processes before starting MF6;
   identify any active run and ask the user whether to wait or otherwise resolve
   it. Do not kill existing processes without authorization. Study members may
   run concurrently through `Study.evaluate`, bounded by shared locks/slots.
8. A quiet terminal is normal. Monitor active `bdam.lst`, file growth and CPU.
   Never restart a progressing solve. Preserve failure diagnostics and backups;
   do not delete immutable requests, lock files or prior runs to force progress.
9. Normal termination alone is insufficient. Apply the completion checks below.
   Failed tests/assertions, MF6 failures or failed scientific QA block acceptance;
   diagnose source defects within the authorized task, but do not relax validation
   or physical assumptions to obtain a pass.

## Source map and edit boundaries

| Area | Owners |
| --- | --- |
| Scientific registry and case resolution | `bdam_parameter_schema.json`, `bdam.py` |
| Study snapshots, preparation, claims, retention and receipts | `bdam_runtime.py` |
| MATLAB table bridge and convenience entry point | `evaluateBDamCases.m`, `bdam_matlab_bridge.py`, `MakeInputs.m` |
| Terrain/geometry and preview app | `buildBDamGeometry.m`, `buildBDamTerrain.m`, `buildBDamCrossSection.m`, `saveBDamGeometry.m`, `BDamTerrainApp.m` |
| Monitoring locations, depth/cell mapping | `makeBDamMonitoring.m` |
| Layers, material properties, boundaries and handoffs | `prepareBDamMember.m`, `ExportPreparationForFloPy.m` |
| Pools, storage, outlet selection and segmentation | `makeCoarseRiverScenario.m`, `bdamRiverPoolEdges.m` |
| Periodic drivers and MATLAB forcing bridge | `bdam_forcing.py`, `makeBDamPeriodicForcing.m` |
| MF6 packages, schedule/restarts and numerical QA | `build_bdam_simulation.py` |
| Completed-run loader, binary readers and viewer | `loadBDamResults.m`, `BDamMF6HeadReader.m`, `readBDamMF6InitialWaterSurface.m`, `BDamResultsViewerApp.m` |

Scientific defaults are the per-field `default` values in
`bdam_parameter_schema.json` -> `parameters`. Resolve each case independently:
registry defaults -> shared scientific settings -> case-row overrides ->
supported automatic/dependent values. Omitted columns inherit; ordinary blank
CSV cells fail, while blank `monitoring_points_file` explicitly selects the grid.
Never fill omitted inputs from an earlier row. Prefer shared/row overrides for
study-specific changes; baseline edits must update the mirrors and reference.
The human explanation and worked example are in
`PARAMETERS.md#defaults-and-overrides`; the sample table is
`examples/paired_cases.csv`.

The registry's `parameters` is authoritative; `defaults` is its MATLAB mirror,
`scalar_defaults` supports only the deprecated vector adapter. Keep mirrors
consistent. Regenerate `PARAMETER_REFERENCE.md` with
`python3 tools/update_parameter_reference.py` after registry changes. Display-only
app settings are not scientific fields. Never use configuration `eval`.

Current parameter registry is v6; the HDF5 preparation schema is v8. Removed fields
`initial_river_depth_above_outlet_bed_m`, `pre_dam_outlet_width_m` and
`post_dam.initial_depth_above_dam_toe_m` must be rejected. River depth is a fixed
0.10 m initial condition; channel widths use `river_settings.manning_width_m`.
Pond installation conserves inherited volume, independently of preparation seeds.
Positive dam heights below 1 m and unity K/K33 multipliers must prepare normally.

Cases are explicit rows. Core submission must not add references, expand scalar
vectors as axes, drop duplicate/invalid cases, sample, or assign objective penalties.
Unknown fields and supplied geometry-file inputs are rejected. Preserve native
arrays and one-based indexed columns. Capacity/retention/MATLAB executable are
study execution settings, never scientific case columns.

Keep studies/batches immutable. Use fresh studies for incompatible schema/runtime
changes; old snapshots require their own tools. Reuse needs matching scientific
provenance and revalidated completion receipts. Failed preparation/simulation
attempts remain available. Do not edit a frozen execution to adopt newer source.

## Local setup and checks

Copy the complete branch to a new local folder, including `examples/`, `tests/`
and `tools/`, but excluding `.git`, environments and generated output. Do not
assume a released v0.2.1 archive contains this unreleased interface. Verify local
storage and space (`df -h .`): budget at least 6 GiB for a default run plus more
for parallel executions, backups and failed attempts. The October 15 default
retained about 3.4 GiB in `Runs`.

Put a local executable named `mf6` in `bin/` inside the package or an ancestor;
copy rather than reference one in synchronized storage. Record its version.
MODFLOW 6.7.0 is the validation reference; a user-authorized different executable
is acceptable if its version is reported and all checks pass.

From the local package:

```sh
python3 --version
python3 -m pip show flopy h5py numpy
../bin/mf6 -v
export BDAM_PYTHON="$(command -v python3)"
mkdir -p ../matplotlib-cache
MPLCONFIGDIR=../matplotlib-cache \
  python3 -m unittest discover -v -p 'test_*.py'
```

If required pinned packages are missing, install `requirements.txt` once into
the selected persistent environment. Request network access when an install is
blocked by the environment; do not change versions to bypass it.

MATLAB contracts and viewer tests:

```matlab
r = runtests({'tests/makeBDamMonitoringTest.m', ...
    'tests/makeCoarseRiverScenarioTest.m', ...
    'tests/bdamRiverPoolEdgesTest.m','tests/evaluateBDamCasesTest.m', ...
    'tests/prepareBDamMemberTest.m','testBDamResultsViewer.m'});
assert(~any([r.Failed]));
```

Set `BDAM_TEST_OUTPUT_ROOT` to a completed full-retention output root to exercise
the viewer's two optional actual-output tests. Without it, report those skips.
`tests/studyResultsIntegrationTest.m` additionally needs a completed **study**
execution with `completion.json`. Run it for study changes against a fresh case.
Static MATLAB checks (`checkcode`) should have no syntax errors; distinguish
performance notices from model/assertion failures. Run `git diff --check`.

Before standalone simulation:

```sh
pgrep -fl 'build_bdam_simulation.py|mf6' || true
```

If process inspection is blocked (`sysmon` / `Cannot get process list`), request
read-only process access and use:

```sh
ps -axo pid,ppid,state,etime,%cpu,%mem,command | \
  rg 'build_bdam_simulation|/mf6' | rg -v 'rg ' || true
```

## Build/run order

Choose one supported path; do not mix independent runners on one output root.

- Standalone: `matlab -batch "run('MakeInputs.m')"`, then the logged Python
  runner below. MakeInputs generates geometry itself; MakeGrid is optional.
- Study: submit rows, `Study.prepare(batch_id)` if preparation-only inspection is
  needed, then `Study.evaluate(batch_id)`. Evaluate prepares automatically.
  `python3 -m bdam` and `evaluateBDamCases` expose the same operations.

Do not continue unless geometry and paired pre/post `preparation_handoff.h5`
files exist and are nonempty. Study preparation must have valid `prepared.json`.
Review grid/layers, dynamic topology, outlet direction, atmospheric masks and
BDA K/K33 locality. Use `PARAMETERS.md` for environment variables/configuration.

```sh
mkdir -p ../staging
set -o pipefail
MPLCONFIGDIR=../matplotlib-cache PYTHONUNBUFFERED=1 \
  python3 build_bdam_simulation.py ModelInput --staging-root ../staging \
  2>&1 | tee ../model_runner.log
```

MATLAB silently exiting 1 in a sandbox may reflect runtime/license restrictions.
Locate the installed executable, retry the unchanged batch expression once with
normal runtime/license access, then report a persistent failure. Do not edit
scientific scripts to work around environment access.

For study progress inspect `executions/ID/BDam/status.json`,
`attempt-NNN/model_runner.log` and that attempt's staging `bdam.lst`. A member
can wait quietly for a slot. Full retention is default; compact is explicit and
cannot be opened in the binary viewer.

## Monitor and complete

Inspect the active staging folder; guard for a missing file during transitions:

```sh
for workspace in ../staging/bdam-*; do
  if [ -s "$workspace/bdam.lst" ]; then
    rg -o 'STRESS PERIOD +[0-9]+' "$workspace/bdam.lst" | tail -1
    ls -lh "$workspace/bdam.lst"
  fi
done
```

For study runs, use the attempt's staging path. File growth and an active MF6
process indicate progress. If files stay unchanged and MF6 uses no CPU across
repeated checks, collect listing tails, paths and process evidence; do not
restart blindly. `mfsim.lst` is not the live progress log. FloPy's
`MFDataItemStructure object` line is harmless diagnostic output.

The full default has six workspaces: `spinup/first_annual` (12 steps, 365 days),
`spinup/staged` (88 steps, 1460 days), and `pre_dam/year_01`, `year_02`,
`post_dam/year_01`, `year_02` (52 steps and 365 days each). No relaxation exists
with zero fall-average years. For nondefaults derive counts/times from
`bdam_runtime.expected_workspaces`, not a hardcoded default checklist.

Every workspace must have normal termination; nonempty readable GWF heads/budget,
LAK stage/budget and UZF water-content/budget binaries; correct saved times/counts;
passing `bdam.water_balance.json`; valid solver statistics; raw head/lake/boundary
observations; `bdam.fluxes.csv`; `bdam.specified_groundwater_flux.csv`; and
`boundary_assumptions.json`. Monitored workspaces also require
`monitoring_targets.csv` and `monitoring_omitted.csv`. Confirm the
selected boundary and independent surface outlet persist through all restarts.
Require spinup/monitored summaries when configured and a conserved dam-installation
audit when installation occurs. The default has 308 saved steps, 101 spinup and
210 monitored summary rows. Ensure no run process remains active at completion.
An exit code of zero plus these checks is success; no extra final phrase is required.

If MF6 explicitly exhausts UZF `NWAVESETS`, use a new case/shared override of
`mf6_parameters.uzf_nwavesets=40`, regenerate and rerun. Never increase it
silently or change the calendar. Keep the original failure evidence.

Report absolute output paths, source/configuration, interpreter/package/MATLAB/MF6
versions, tests/skips, saved counts/times, budgets, warnings and retained diagnostics.
For code changes affecting preparation or runtime, normally perform a complete default
run and compare scientific inputs/outputs against a trusted baseline. The prescribed
edge-flux feature has user-authorized short verification: exactly four case
configurations (zero, positive, negative, mixed), each with two one-day pre-dam
and two one-day post-dam steps; no full spinup/production run. A zero-flux
reference comparison belongs to the zero case. Use `tools/verify_edge_fluxes.py`
from a local copy. Its worker count defaults to one and cannot exceed four.
Short-run results must not produce production `completion.json` receipts.
Ordinary studies default to one worker; explicit larger scientific studies remain
allowed. For docs-only or unrelated UI edits, use checks appropriate to the
changed behavior.
Compare HDF5 datasets, not container bytes; numerical CSV/binary differences are
substantive. Ignore only known timestamps, paths and elapsed-time text. Never
weaken QA to obtain agreement.

## Adaptive spinup verification

`mf6_parameters.spinup_until_converged` defaults to false. Enabled runs retain
fall/monthly warmup and use annual `spinup/weekly/year_NN` workspaces with 52
steps each. Derive actual counts from `bdam_runtime.expected_workspaces` and the
validated convergence report. DNC is not a solver failure or successful completion;
skip its monitored years, preserve diagnostics, and continue other study members.

This feature has user-authorized bounded verification: tiny synthetic/mocked
tests plus `tools/verify_spinup_convergence.py` from a local source copy. The
verifier uses a 15×20×3 grid, three weekly spinup years and one monitored year,
with deliberately loose test-only tolerances and an equivalent fixed-duration
annual-restart control. Keep the full weekly calendar and strict solver/budget
checks. Do not issue production completion receipts for this smoke verification.
No full default-size run is required for this feature.

## Prescribed groundwater edge fluxes

`groundwater_edge_flux.{x_min,x_max,y_max}_m3_per_day` are finite signed total
m3/day values, all zero by default. Uniformly distribute each total along only
the bottom layer of its edge; retain independent corner contributions. MF6
packages are WEL_X_MIN, WEL_X_MAX and WEL_Y_MAX, with no automatic flow reduction.
The +y edge maps to MF6 row zero, native bottom layer 1 to MF6 layer nlay-1.
Downstream DRN/GHB remains independent. Gross combined groundwater budgets
include both downstream and prescribed edges; downstream observations and
DRN/GHB-specific fields retain their downstream-only meaning. Check actual WEL
budgets against input totals; never reduce prescribed extraction to obtain a pass.

## Monitoring CSV contract and bounded verification

`monitoring_points_file` defaults to blank. Blank/whitespace case-table cells
select the unchanged four-stream + six-grid layout. A nonblank path is resolved
against source, copied and hashed like other scientific files. Missing files
fail; supplied empty/header-only/all-outside files retain only four stream points.
Keep CSV x/y in model meters; z is depth below the containing column's terrain.
Use containing cells, select the deeper layer on internal interfaces, and include
outer domain/top/bottom faces. Omit out-of-volume points with row/reason audits;
reject malformed coordinates and invalid/duplicate retained names. Multiple
named observations may share a cell. Preserve original labels; IDs use original
row numbers as head_csv_NNNN and summary columns add _m. Keep the four stream
IDs and bottom-layer selection unchanged. The standalone HDF5 must preserve
all target/omission metadata without its JSON companion. Check viewer labels
and pre/post alignment including layers/elevations.

This feature has user-authorized short verification: run exactly the grid and
CSV configurations with `tools/verify_monitoring_points.py`, serially, each with
two one-day pre-dam and two one-day post-dam steps. No full spinup/production
run is required. Results must remain separate from production completion
receipts. Check exact hydraulic-state/budget equivalence between both cases;
only monitoring outputs may differ. See `MONITORING_VALIDATION.md` for evidence.

## Dam height input naming

The current input is `geometry.dam_height_m`, in meters above the sampled dam toe.
Use this name in parameter objects, defaults, examples and guides.
A pure naming/documentation change requires static consistency checks;
do not run preparation or the numerical model solely for this rename.
