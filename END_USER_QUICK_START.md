# Running and inspecting BDam

This guide is for people preparing or inspecting simulations. Use
[PARAMETERS.md](PARAMETERS.md) for case tables and optimizer integration,
[PARAMETER_REFERENCE.md](PARAMETER_REFERENCE.md) for scientific inputs, and
[AGENTS.md](AGENTS.md) for automated-agent operations and development rules.

## 1. Prepare a local installation

Copy the complete branch checkout or extract its archive into a new local,
nonsynchronized folder. A released v0.2.1 archive does not necessarily contain
this unreleased parameter-table interface. Use the branch source for this guide.
Do not execute from Google Drive, Dropbox, OneDrive, iCloud or a network share.

Example layout:

```text
~/BDamRuns/my-run/
  bin/mf6
  BDam/                 complete branch source
  matplotlib-cache/
  staging/
```

If copying a synchronized checkout, copy its source files, examples and tests
into `BDam/`; exclude `.git`, environments and generated runs/studies. Keep prior
results and failed-run diagnostics intact. Confirm available disk space with
`df -h .`. Allow at least 6 GiB for a default run and staging; the 70 × 140 × 5
October 15 run retained about 3.4 GiB of results. Parallel studies need storage
for each retained execution and its active staging.

Requirements:

- MATLAB, tested R2025b Update 7; no optional model toolbox is required.
- Python 3.12+; use the same interpreter for CLI commands and MATLAB's bridge.
- FloPy 3.10.0, h5py 3.16.0 and NumPy 2.5.2 (`requirements.txt`).
- A host-compatible MODFLOW executable named `mf6` in `BDam/bin/` or an
  ancestor's `bin/`. Validation used 6.7.0 (2026-02-05); record the actual version.

Install packages once in a persistent environment, not inside each run:

```sh
python3 --version
python3 -m pip install --user -r requirements.txt
../bin/mf6 -v
export BDAM_PYTHON="$(command -v python3)"
mkdir -p ../matplotlib-cache
MPLCONFIGDIR=../matplotlib-cache \
  python3 -m unittest discover -v -p 'test_*.py'
```

If packages are already installed at the pinned versions, reuse them. For an
externally managed Python installation, use its persistent environment mechanism
or a shared environment outside the run tree; do not override its package
protection just to repeat an installation. Record the selected interpreter and
reuse it for every command. `BDAM_PYTHON` is the path to that interpreter.

## 2. Prepare the default inputs

From the local `BDam` directory:

```sh
matlab -batch "run('MakeInputs.m')"
```

With no BDAM configuration variables set, this submits and prepares one default
case in `Study/`, then publishes standalone geometry and handoffs under:

```text
Geometry/BDamGeometry.mat
ModelInput/pre_dam/preparation_handoff.h5
ModelInput/post_dam/preparation_handoff.h5
```

`MakeGrid.m` separately previews registry-default terrain and writes a geometry
MAT file. It is optional; MakeInputs generates fresh geometry. Editing a prior
MAT file or exporting terrain from the app does not override a case's generated
geometry. Supply accepted `geometry.*` parameters instead.

Review the preparation figures, console output and adjacent
`preparation_manifest.json` files: 70 × 140 cells, five layers, eight pre-dam
pools, one pond plus two downstream pools, correct dam position, local drain
boundary, and mutually exclusive land/lake atmospheric masks. Review figures
are shown by standalone MakeInputs; study preparation runs without figures.
All active arrays use meters and days.

## 3. Run the complete default

Check for an existing model process first:

```sh
pgrep -fl 'build_bdam_simulation.py|mf6' || true
```

If another standalone run is active, identify its folder and wait or resolve
its ownership before starting another. Do not terminate someone else's process.
Managed environments may require read-only permission to inspect processes;
`AGENTS.md` provides the `ps` fallback.

```sh
mkdir -p ../staging
set -o pipefail
MPLCONFIGDIR=../matplotlib-cache PYTHONUNBUFFERED=1 \
  python3 build_bdam_simulation.py ModelInput --staging-root ../staging \
  2>&1 | tee ../model_runner.log
```

The runner backs up an existing nonempty `Runs` directory before a new standalone
run. It stages each workspace locally, validates it, publishes it into `Runs`,
then checks the published copy. Successful staging is removed; failures retain
diagnostics. Do not manually edit generated inputs, results or lock files.

The default uses zero fall-average, four monthly and one weekly spinup years,
then two pre-dam and two post-dam weekly years:

| Workspace | Saved steps | Local final time (days) |
| --- | ---: | ---: |
| `Runs/spinup/first_annual` | 12 | 365 |
| `Runs/spinup/staged` | 88 | 1460 |
| `Runs/pre_dam/year_01` | 52 | 365 |
| `Runs/pre_dam/year_02` | 52 | 365 |
| `Runs/post_dam/year_01` | 52 | 365 |
| `Runs/post_dam/year_02` | 52 | 365 |

That is 308 endpoints across nine model years. `first_annual` is a historical
folder name; its default calendar is monthly. There is no initial relaxation
with zero fall-average years. Explicit fall-average spinup adds one seven-day
relaxation and one annual step per fall-average year. Monthly years have 12
steps, weekly years 52, and daily monitored years 365. Every forcing period
has exactly one MF6 time step. The model year is October 1–September 30, always
365 days; source January–December climatologies are rotated internally.

The first modeled year uses conservative IMS settings; later solves use balanced
settings, with the same strict closure tolerances. The runner manages this policy.
Do not globally select conservative settings or subdivide time steps to force
convergence. `--stop-after-monthly-spinup` is an explicit standalone diagnostic
that stops before weekly spinup and monitoring; it is not a complete default run.

## 4. Monitor and confirm completion

A quiet terminal is normal: MF6 stdout is captured. Inspect the active
`../staging/bdam-*/bdam.lst`, its size, output growth and solver CPU activity.
`mfsim.lst` mainly reports startup and final termination, so it is not the live
progress log. A new staging folder can briefly lack `bdam.lst` between phases.
An empty `Runs` during the first staged solve does not imply failure.

For every completed workspace require:

- `Normal termination of simulation.` in `mfsim.lst`.
- Nonempty, readable `bdam.hds`, `bdam.cbc`, `bdam.lak.stage`, `bdam.lak.bud`,
  `bdam.uzf.wc` and `bdam.uzf.bud`, with the configured final times and counts.
- Passing `bdam.water_balance.json`, valid `bdam.solver_stats.json`, point
  observations, `bdam.fluxes.csv`, `boundary_assumptions.json` and
  `bdam.groundwater_boundary_flux.csv`.
- `Runs/spinup_summary.csv` and `Runs/weekly_summary.csv` for the default;
  no model process remains active when the runner exits successfully.

The default summaries contain 101 spinup rows and 210 monitored rows. Both
monitored phase initial states are retained in the summary; the viewer shares
that transition frame and displays 209 monitored / 309 all-phase frames.
A termination marker by itself is insufficient; the runner enforces the other
checks. No extra final success phrase is required.

## 5. Read the results

| File | Purpose |
| --- | --- |
| `spinup_summary.csv` | Conditioning history and interannual state changes |
| `weekly_summary.csv` / `daily_summary.csv` | Monitored pre/post heads, stages, storage and fluxes |
| `bdam.water_balance.json` | GWF, lake-routing and coupled-system budget checks |
| `bdam.solver_stats.json` | Solver profile, tolerances, iterations, wave capacity and MF6 version |
| `bdam.heads.csv` | Named point groundwater heads |
| `bdam.lake_fluxes.csv` | Native per-lake stage, storage and flow observations |
| `bdam.groundwater_boundary_flux.csv` | Signed net downstream DRN or GHB flow |
| `bdam.specified_groundwater_flux.csv` | Signed bottom-layer −x, +x and +y edge totals and interval volumes |
| `bdam.fluxes.csv` | Coupled external fluxes, storage and geographic exchange totals |
| `boundary_assumptions.json` | Actual groundwater boundary and independent surface outlet |
| `dam_installation_storage_audit.json` in `Runs/` | Conservative pool-to-pond transition |

Rates are m³/day and interval volumes m³. Supplied atmospheric depths are m/day;
realized LAK atmospheric observations are volumetric. `in_total` and `out_total`
are external coupled-system totals; internal lake–groundwater exchange and
lake-to-lake transfers are excluded. Positive lake exchange means lake to
groundwater; positive cross-dam groundwater flow means upstream to downstream.
Groundwater boundary inflow/outflow are gross sums by cell sign, not netted totals.

MATLAB arrays are `[x,y,layer]`, with the bottom native layer first; MODFLOW
arrays are `[layer,row,column]`, top layer first. The adapter converts orientation
once. Do not flip generated arrays manually.

## 6. Explore in MATLAB

```matlab
LaunchBDamTerrainApp
LaunchBDamResultsViewerApp("/absolute/local/completed/BDam")
```

The terrain app previews and exports terrain (MAT or portable geometry ZIP) and
imports its own parameter exports. It shares registry geometry defaults but
is not an ensemble runner. Cases rebuild terrain from `geometry.*` inputs.

The results viewer reads a completed standalone root or a study execution's
`BDam/` root with full retention. It selects a folder first; **Load** reads it.
With no argument, the local package folder is selected. Native lake series are
discovered dynamically. Lake numbers identify different locations before/after
installation: default pre-dam Lakes 1–8 are upstream-to-downstream pools;
post-dam Lake 1 is the pond and Lakes 2–3 are downstream pools.

The viewer offers Spinup, Monitored and All scopes (Spinup is absent when
intentionally disabled), initial-condition frames, dual-unit time-series plots,
depth-to-groundwater or head rasters/contours, map transpose and animation up to
20 frames/s. Negative depth means heads above terrain. It caches up to 512 MiB
of water surfaces; larger runs use indexed reads. Compact-retention results
omit required binaries and cannot be opened in this viewer.

## Change inputs and recover from problems

For configuration, submit explicit cases or use a JSON shared-settings file via
`BDAM_CONFIG`; see `PARAMETERS.md`. Do not edit user-defined sections in
MakeInputs/MakeGrid: their defaults now come from the registry. Unknown and
removed fields are rejected. Use a fresh study for changed source/runtime or
study settings; retain frozen executions for reproducibility.

- MATLAB silent exit in a sandbox: retry the unchanged expression once with
  normal runtime/license access; do not change scripts to bypass access issues.
- FloPy prints `MFDataItemStructure object`: cosmetic diagnostic noise.
- No files change and MF6 is idle across repeated checks: retain listing tails,
  process evidence and staging path; investigate before restarting.
- Failed test, preparation assertion, MF6 failure or failed output/budget QA:
  preserve the evidence. Do not weaken calendars, physical inputs or validation.
- MF6 explicitly requests more UZF wave storage: set
  `mf6_parameters.uzf_nwavesets` from 20 to 40 in a new case/shared configuration,
  regenerate, then rerun. Do not increase it automatically.

Physical interpretation, including fixed footprints, coarse stages, drainage,
backwater and ongoing storage adjustment, is documented in
[RIVER_REFINEMENTS.md](RIVER_REFINEMENTS.md) and
[BOUNDARY_ASSUMPTIONS.md](BOUNDARY_ASSUMPTIONS.md).

`bdam.specified_groundwater_flux.csv` gives realized signed totals and interval
volumes for the three bottom-layer groundwater edges. The existing
`bdam.groundwater_boundary_flux.csv` remains downstream-only. Combined groundwater
inflow/outflow in `bdam.fluxes.csv` includes both. All edge defaults are zero;
see [PARAMETERS.md](PARAMETERS.md) for the three input names.

## Short edge-flux verification

The default study worker count remains one. Feature verification uses only four
configurations (zero, inflow, outflow, mixed) on the default grid, with two daily
steps before and two after installation, without spinup. Run
`python3 tools/verify_edge_fluxes.py /absolute/local/fresh-verification`
from a local source copy; add `--matlab /path/to/matlab` if needed. The
`--workers` option accepts 1–4 and defaults to 1. An optional zero-case baseline
comparison is documented by `--help`. Outputs and `edge_flux_verification.json`
are kept outside production Runs and never certify a full-calendar study.
