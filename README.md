# BDam model package

> **Release status:** BDam v0.1.0 is a usable but uncalibrated demonstration
> framework. It is not a calibrated field model, and its interfaces and model
> formulation may change before v1.0.0.

For an operating guide, complete input catalog, and safe model/agent
modification workflow, see `END_USER_QUICK_START.md`.

This is the clean, standardized starting point for BDam simulations. The
package contains source code and the normalized hydrograph input only. It does
not contain generated geometry, HDF5 handoffs, Python environments, or model
results.

The source repository is
[`nbengdahl/bdam-model`](https://github.com/nbengdahl/bdam-model). Releases use
semantic version tags and provide a versioned `BDam-vX.Y.Z.tar.gz` package for
the documented local-run workflow.

**AI agents:** read and follow `AGENTS.md` before taking any action. It is the
required operational runbook. Do not rely on inference when its checklist
provides an explicit instruction.

## Run only from a local filesystem

Extract or copy the complete package to a local, non-synchronized folder
before doing any setup or running MATLAB, Python, or MODFLOW 6. Do **not** run
the model inside Google Drive, OneDrive, Dropbox, iCloud Drive, a network
share, or any other cloud/file-provider folder. Large MODFLOW package files
can remain empty or incompletely finalized even when the solver reports normal
termination.

It is safe to store the unopened tarball in cloud storage. After a run is fully
complete, closed result files may also be copied to cloud storage for archival.
The active package, scratch directory, and `Runs` directory must remain local.

The recommended persistent location is a dedicated run folder under the
user's home directory. Verify that the selected location is not managed by a
cloud-sync or network-storage service.

Example local layout:

```text
~/BDamRuns/bdam-run-YYYYMMDD/
├── bin/
│   └── mf6
└── BDam/
    ├── MakeGrid.m
    ├── MakeInputs.m
    ├── build_bdam_simulation.py
    └── ...
```

The runner searches for `bin/mf6` in `BDam` and then in its
parent directories, so `BDam/bin/mf6` is also valid.

## Required software

- MATLAB, tested with R2025b. No optional MATLAB toolbox is required by the
  model scripts.
- Python 3.12 or newer, with `venv` and `pip`. The validated package used
  Python 3.12 for the release workflow; Python 3.14 is also tested in CI.
- Python packages pinned in `requirements.txt`:
  - FloPy 3.10.0
  - h5py 3.16.0
  - NumPy 2.5.2
- MODFLOW 6 executable, tested with MF6 6.7.0 (2026-02-05). Obtain the binary
  for the host operating system from the official USGS MODFLOW 6 distribution,
  name it `mf6`, and place it in one of the `bin` locations above.
- Local disk space. The default staged 1/1/1 spinup plus weekly 1/1 pre-/post-dam
  case produces about 2.1 GB in `Runs` and needs approximately 900 MB of scratch
  space while the combined spinup workspace is active.
  Reserve at least 4 GB, plus more if prior `Runs_backup_*` directories will be
  retained.

On macOS or Linux, make the MF6 binary executable and verify its version:

```zsh
chmod +x ../bin/mf6
../bin/mf6 -v
```

## Install Python dependencies once

Install all required packages once for the `python3` interpreter that will run
BDam. This user-level installation is reused by every model run and avoids a
thousands-of-files `.venv` inside every extracted package. BDam does not depend
on any particular Python distributor or operating-system package manager.

From any local `BDam` directory:

```zsh
python3 --version
python3 -m pip install --user -r requirements.txt
```

If the selected Python provider manages packages through its own persistent
environment, install the same `requirements.txt` there once and consistently
use that environment's `python3`. Do not create an environment in each run.

Run the fast Python checks. These tests do not launch MODFLOW:

```zsh
mkdir -p ../matplotlib-cache
MPLCONFIGDIR=../matplotlib-cache python3 -m unittest -v test_bdam_workflow.py
```

## Configure the simulation

The packaged terrain defaults define a 50-by-100-cell grid at 1 m spacing,
with X transverse to the channel and Y along the channel. The centerline uses
one 5 m-amplitude meander period over the 100 m reach, and the regional Y
slope is 0.005. These defaults are shared by `MakeGrid.m` and the
interactive MATLAB app.

To inspect or adjust the terrain interactively, launch the packaged app from
MATLAB while this directory is current:

```matlab
LaunchBDamTerrainApp
```

The app can export `BDamGeometry.mat` or a portable geometry ZIP. The standard
model workflow remains reproducible through `MakeGrid.m`; use that script
to build `Geometry/BDamGeometry.mat` before running `MakeInputs.m`.

To inspect a completed simulation, launch the results viewer:

```matlab
LaunchBDamResultsViewerApp
```

With no argument it preselects `../BDam_out` relative to the packaged source.
The viewer does not read any output until the user clicks Load. Pass another
complete output root to preselect it when needed:

```matlab
LaunchBDamResultsViewerApp("/absolute/path/to/completed/BDam")
```

The selected root must contain `Geometry/BDamGeometry.mat`, `Runs/`, the run
summary CSVs, annual or staged `bdam.hds` files, and their
`monitoring_targets.csv` files. The viewer reads these files without changing
them. Spinup files are optional when all three configured spinup counts were
zero; in that case the viewer offers only the monitored and all scopes, with
no timeline offset. Its upper panel plots selected monitoring series on at most two y-axis
unit families. A compact lower-panel assignment matrix independently chooses
depth to water or groundwater elevation for the required color raster and the
optional contours; conflicting selections swap cleanly. Negative depth means
groundwater head is above land surface. The time slider can span
spinup, the monitored pre-/post-dam comparison, or both, and the Play control
animates the saved head fields. A display-only map transpose swaps X and Y to
use wide plotting space more effectively; it is enabled automatically when
the domain's Y span is greater than its X span and can be toggled at any time.
When Load is clicked, the viewer preprocesses each unique binary head frame
into an in-memory 2-D groundwater-surface field. Runs requiring at most 512 MiB
are animated entirely from this cache; larger runs retain indexed on-demand
reading and report that fallback in the status panel. No cache files are
written to the output root.

Edit only the user-defined settings near the top of `MakeInputs.m` for
aquifer, forcing, and run configuration. The principal duration settings are:

```matlab
time_resolution = "weekly";  % "weekly" or "daily"
mf6_parameters.mean_forcing_spinup_years = 1;
mf6_parameters.monthly_spinup_years = 1;
mf6_parameters.weekly_spinup_years = 1;
mf6_parameters.pre_dam_years = 1;
mf6_parameters.post_dam_years = 1;
mf6_parameters.initial_head_channel_offset_m = 0.25;
mf6_parameters.initial_head_lateral_gradient_m_per_m = 0.02;
mf6_parameters.uzf_nwavesets = 20;
```

Spinup always uses the pre-dam condition. Its three year counts are independent
nonnegative integers and may all be zero. The runner never adds hidden years or
extends spinup automatically. It builds one continuous transient simulation in
`Runs/spinup/staged`, using the configured stages in this order:

1. Each mean-forcing year has 12 water-year calendar-month steps. Inflow, atmospheric
   rates, downstream stage, and all GHB heads stay at their duration-weighted
   annual means even though month lengths vary.
2. Each monthly year has 12 water-year calendar-month steps with duration-weighted monthly
   averages.
3. Each weekly year has 52 steps of `365/52` days with weekly averages.

Every configured stage repeats its October-to-September climatology. Model day
zero represents October 1; all time-varying inputs are circularly shifted from
their source calendar-year order, while internal elapsed-time counters remain
unchanged. All stages remain transient and preserve groundwater, lake, and UZF
storage continuously.
When all three counts are zero, the first monitored year starts directly from
the configured analytical initial heads, lake stages, and UZF water content;
no spinup workspace or `spinup_summary.csv` is produced. Otherwise, the final
staged state initializes the first pre-dam year exactly. Spinup always
ends at weekly resolution when a weekly stage is requested, even when monitored
years use daily resolution. The monitored duration is `pre_dam_years +
post_dam_years`; set `post_dam_years = 0` for a no-dam run.
The initial groundwater surface is anchored 0.25 m above the nearest channel
bed and rises laterally at 0.02 m/m by default. It is capped at land surface
and then reduced linearly moving upslope from the outlet. The reduction gradient
is derived automatically as half the absolute `channel_longitudinal_slope` in
the geometry database; changing that existing geometry input therefore changes
the initial-head correction without adding another user control. The result is
bounded above the model bottom and applied as one hydraulic head through each
vertical column. The channel offset and lateral gradient remain user-editable.

At dam installation, groundwater heads are carried forward without changing
lake-footprint cells. UZF water contents are mapped by grid cell, with the
configured initial water content used only for genuinely new UZF features,
and both post-dam lakes inherit the final pre-dam river stage. The downstream
external LAK outlet uses the same fixed model-edge invert before and after dam
installation; it is not varied with the inflow hydrograph.

MF6 reports zero water content for saturated or deactivated UZF features. A
restart `THTI` must remain between residual and saturated water content, so
those zero sentinels are restarted at residual water content; all nonzero
common-feature states are carried exactly.

Daily mode has exactly 365 one-day stress periods. Weekly mode has exactly 52
periods of `365/52` days. Both modes intentionally use exactly one MODFLOW
time step per forcing period. Weekly forcing is a duration-weighted period
mean. Agents must not add internal substeps or change these calendar rules to
work around convergence or output problems.

Change physical terrain/grid geometry only in `MakeGrid.m` and the helper
functions it calls. Do not hand-edit generated `Geometry`, `ModelInput`, or
`Runs` files.

## Build and run

Run these commands in order from the local package directory:

```zsh
matlab -batch "run('MakeGrid.m')"
matlab -batch "run('MakeInputs.m')"
python3 build_bdam_simulation.py ModelInput
```

For unattended or agent-operated runs, use the safer logged form below for
the final command. Unbuffered Python output exposes phase-level messages,
`MPLCONFIGDIR` avoids home-directory cache warnings, and `pipefail` preserves
the model command's failure status through `tee`:

```zsh
mkdir -p ../matplotlib-cache ../staging
set -o pipefail
MPLCONFIGDIR=../matplotlib-cache PYTHONUNBUFFERED=1 \
  python3 build_bdam_simulation.py ModelInput \
  --staging-root ../staging 2>&1 | tee ../model_runner.log
```

The default `balanced` solver profile uses the robust `COMPLEX` IMS preset for
the first solve from analytical initial conditions, then the faster `MODERATE`
preset for restarted workspaces. The strict head and flow closure tolerances
remain unchanged. If a restarted solve reports a solver convergence failure,
rerun the unchanged inputs with the conservative profile:

```zsh
python3 build_bdam_simulation.py ModelInput \
  --staging-root ../staging --solver-profile conservative
```

Detailed inner-iteration diagnostics are normally unnecessary. Add
`--solver-inner-output` only when diagnosing solver behavior. Every completed
workspace includes compact outer-iteration output and
`bdam.solver_stats.json`, which records the selected profile, UZF wave
capacity, solve time, iteration totals, MF6 version, and reported allocation.

The default UZF `NWAVESETS` value of 20 is numerical storage capacity, not a
physical or calibration parameter. If MF6 specifically reports that
`NWAVESETS` must be increased, change `mf6_parameters.uzf_nwavesets` in
`MakeInputs.m` to 40, regenerate both handoffs, and rerun. Increase it further
only if MF6 repeats that specific error; the runner never changes it or the
calendar automatically.

Representative pre-/post-dam benchmarks reduced MF6 solve time from
129.1/134.5 seconds with `COMPLEX` and 1000 wave sets to 71.7/68.7 seconds
with `MODERATE` and 20 wave sets. Reported allocation fell from roughly 11 GB
to 286--289 MB. Maximum benchmark head differences were 3 micrometres
pre-dam and 0.668 mm post-dam; lake-stage differences were below
1.4e-8 m and key-flux differences were below 0.006%. These measurements are
representative rather than performance guarantees for other hardware or
inputs.

The steps produce:

1. `MakeGrid.m` → `Geometry/BDamGeometry.mat`
2. `MakeInputs.m` → paired scenario handoffs at
   `ModelInput/pre_dam/preparation_handoff.h5` and
   `ModelInput/post_dam/preparation_handoff.h5`
3. `build_bdam_simulation.py` → staged/annual workspaces and summaries under `Runs`

By default, every annual MODFLOW workspace executes in a unique folder under
the operating system's local temporary directory. It is validated there,
copied into `Runs/<phase>/year_##`, and validated again before being exposed as
a completed annual workspace. To select a different **local** scratch disk:

```zsh
python3 build_bdam_simulation.py ModelInput --staging-root /local/scratch/bdam
```

Successful staging directories are removed. If execution or publication
fails, the error reports and retains the diagnostic staging path; a partial
copy remains hidden as `.year_##.publishing-*`. Do not use a cloud-synchronized
path for `--staging-root`.

Starting the workflow when a nonempty `Runs` directory already exists does not
overwrite or delete it. The runner first renames it to a timestamped
`Runs_backup_YYYYMMDD_HHMMSS` directory. Move or delete backups deliberately
when their results are no longer required; otherwise repeated runs can consume
substantial disk space.

Before launching the runner, check for existing model processes:

```zsh
pgrep -fl 'build_bdam_simulation.py|mf6' || true
```

Do not start a duplicate run. Multiple concurrent MF6 processes can make a
healthy run appear stalled. Identify any existing run directory and decide
deliberately whether to wait for it or terminate it; agents must obtain user
authorization before terminating an existing process.

In managed sandboxes, `pgrep` may be forbidden from reading the process list.
Request read-only process-inspection permission and use `ps -axo ...` as
described in `AGENTS.md`. This is an environment restriction, not a model
failure.

## Live progress and quiet terminals

The runner intentionally captures MODFLOW stdout so it can validate the
process exit code and final files. Therefore, a quiet terminal is not evidence
of a stalled run. Do not restart solely because no solver lines appear.

Each active annual workspace is under the selected staging root. Find it with:

```zsh
find ../staging -mindepth 1 -maxdepth 1 -type d -name 'bdam-*' -print
```

Live stress-period progress is recorded in that workspace's `bdam.lst`:

```zsh
rg -o 'STRESS PERIOD +[0-9]+' /absolute/active/workspace/bdam.lst | tail -1
ls -lh /absolute/active/workspace/bdam.lst
```

Do not use `mfsim.lst` for live progress; it primarily contains initialization
and the final termination marker. A year is not copied into `Runs` until its
staged workspace has finished and passed validation, so an empty `Runs`
directory during the first year is expected.

The runner may create the next annual staging directory a few seconds before
its `bdam.lst` exists. Guard progress checks with a file-existence test and
retry after this short transition. FloPy may also print an
`MFDataItemStructure object` line during setup; this is cosmetic diagnostic
noise, not a failure.

## Results and completion checks

For weekly runs, `Runs/weekly_summary.csv` contains only monitored pre-/post-dam
years. Daily runs write `Runs/daily_summary.csv`. Both include the post-spinup
initial condition, each completed forcing period, monitored heads and lake
stages, and flux rates and interval volumes. The flux fields include whole-model
`in_total`, `out_total`, and residuals; signed exchange from Lake 1 and Lake 2
to groundwater; and signed groundwater flow across the reference dam line.
Positive lake exchange is lake-to-groundwater, while positive cross-dam flow is
upstream-to-downstream. In pre-dam years, the single river/lake is divided at
the reference dam line and reported as upstream Lake 1 and downstream Lake 2
portions so the same columns are available before and after dam installation.

`Runs/spinup_summary.csv` separately records the analytical initial state and
all completed staged-spinup states and derived fluxes. Rows identify
`spinup_mean_forcing`, `spinup_monthly`, or `spinup_weekly`, the stage year,
stage-relative time, cumulative transient time, and interval duration. With the
default 1/1/1 settings it contains 77 rows: one initial state plus 12 mean,
12 monthly, and 52 weekly completed steps. Raw head, lake, and GHB observation
CSVs and `bdam.fluxes.csv` are generated at every saved step in the staged
spinup workspace and every pre-dam and post-dam annual workspace. Flux rates are m3/day and
interval-integrated volumes are m3.
When all spinup counts are zero, `Runs/spinup_summary.csv` and
`Runs/spinup/staged` are intentionally absent.

In the flux interface, `in_total` and `out_total` are coupled-system external
fluxes. Inputs are land infiltration, lake precipitation, upstream surface
inflow, and positive GHB inflow. Outputs are land ET, rejected infiltration,
lake evaporation, external surface outflow and withdrawals, and GHB outflow.
Internal LAK--GWF exchange, LAK-to-LAK routing, and storage terms are excluded.
The former GWF listing totals remain available as `gwf_budget_in_total` and
`gwf_budget_out_total`. `net_atmospheric_recharge` is land infiltration plus
lake precipitation minus land ET and lake evaporation. `combined_storage_change`
is positive for increasing combined GWF+UZF+LAK storage, and
`coupled_mass_residual` is external net inflow minus that storage change.
Each rate field has a matching interval-volume field. Positive Lake 1/Lake 2
exchange is lake-to-groundwater; positive cross-dam groundwater flow is
upstream-to-downstream.

With the current uncalibrated pond geometry, Lake 1 needs about 192 m3 of
storage, or 2.2 days at the 86.4 m3/day mean inflow, to rise from the inherited
pre-dam stage to the crest. Weekly mode therefore does not resolve that brief
filling transient; select daily mode when that transient matters. Each annual
workspace must have:

- `Normal termination of simulation.` in `mfsim.lst`;
- nonempty, readable GWF heads/budget, LAK stage/budget, and UZF
  water-content/budget files;
- a final saved time of 365 days; and
- `bdam.water_balance.json` with status `pass`; and
- `bdam.solver_stats.json` with normal termination and numerical provenance.

The runner enforces these checks before a year can initialize the next phase.
A normal-termination line alone is not accepted as proof of a valid run.

Routine managed-environment problems do not require model changes. If pip is
blocked from the network, request network permission and retry the unchanged
pinned install. If MATLAB silently exits in a sandbox, request access to its
normal runtime/license services and retry the unchanged batch expression.
Never use `sudo`, change dependency versions, edit generated files, weaken
validation, or change model/calendar settings to bypass an environment issue.

For comparisons between successful runs, numerical result binaries, summary
CSVs, monitoring CSVs, and water-balance JSON are authoritative. Generated
input text and listing files include timestamps, paths, and runtime details;
MATLAB and HDF5 containers can also differ physically while holding identical
values. See `AGENTS.md` for the exact reproducibility guidance.

## Clean regeneration

The following directories and files are generated and are not part of the
source package:

```text
Geometry/
ModelInput/
Runs/
Runs_backup_*/
__pycache__/
```

To start another simulation from the standardized package, extract a fresh
copy of the tarball into a new local folder and reuse the already-configured
`python3`. This avoids mixing handoffs or outputs between simulations without
duplicating installed Python packages in every run.

## Data provenance, citation, and license

The packaged `usgs_13348000_hydrograph.csv` is a normalized daily climatology
derived from U.S. Geological Survey station 13348000. Its source query,
derivation, retrieval date, and checksum are recorded in
`USGS_HYDROGRAPH_PROVENANCE.json`.

Citation metadata are provided in `CITATION.cff`. BDam is distributed under
the MIT License; see `LICENSE`.
