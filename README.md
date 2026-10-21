# BDam model package

## Dam height parameter

Use `dam_height_m` for the dam height in meters above the sampled dam toe
(default 1.5 m). This is the dam height itself. Update saved parameter
files to use the current field name; the numerical value and dam geometry
calculation are unchanged.

## River formulation (v0.2.1)

The default uses coarse Manning-connected LAK river pools: eight before the dam,
then one pond and two downstream pools on the default terrain. Upper pond banks
are excluded from groundwater exchange, while full connected topography supplies
storage. Installation conserves surface volume. See [RIVER_REFINEMENTS.md](RIVER_REFINEMENTS.md)
for settings, validation evidence, observation meanings and remaining limitations.
Historical v0.2.0 full-run validation and the scope of the v0.2.1 changes are
recorded in [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md).
The current workflow is 0 fall / 4 monthly / 1 weekly spinup years and two weekly
pre-dam plus two post-dam years. Historical timing/head benchmarks below describe
earlier formulations and are retained only as historical evidence.


> **Release status:** BDam v0.2.1 is a usable but uncalibrated demonstration
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

## Downstream boundary assumptions

The monthly-first default passes full numerical validation and is 58% faster
in spinup in the tested configuration. Boundary resistance and the lumped
river representation still limit physical interpretation. See
[BOUNDARY_VALIDATION.md](BOUNDARY_VALIDATION.md) for results and sensitivities.
The selected river formulation and its validation are described in
[RIVER_REFINEMENTS.md](RIVER_REFINEMENTS.md).

The default downstream groundwater boundary is **outflow-only DRN**, with its
discharge threshold at the channel-bed elevation on the modeled outlet edge.
It cannot inject groundwater. The external surface Manning invert is independently
set to that local bed plus `external_outlet_height_above_bed_m` (default zero).
Lake stages evolve from the simulated budget; no remote river stage or
upstream-flow-derived groundwater head is imposed. Coarse pools initialize 0.10 m above their own lowest bed; subsequent stages
evolve from the simulated water budget.

`groundwater_boundary_mode = "constant_ghb"` is an explicit sensitivity option
that allows bidirectional exchange at an assumed constant head, set by
`constant_ghb_head_above_outlet_bed_m`. It does not change the surface outlet.
Boundary resistance remains an uncalibrated effective `C = K A/L` assumption,
not a claim about an observed control outside the domain. Drainage excludes
regional groundwater inflow and external surface backwater; it is not a
universal substitute for site boundary data.

Handoff schema **v6** requires explicit local boundary mode, reference levels
and surface outlet inverts. Regenerate old handoffs using MakeGrid then
MakeInputs. Each workspace includes `boundary_assumptions.json`, and
`bdam.groundwater_boundary_flux.csv` reports signed net exchange. In
`bdam.fluxes.csv` and summaries, `groundwater_boundary_inflow` and
`groundwater_boundary_outflow` are gross sums by cell sign. `ghb_inflow` and
`ghb_outflow` refer only to opt-in GHB; they are zero in DRN mode, which reports
`drain_outflow` separately. Total external budgets include the active boundary.

Before interpreting local heads, test resistance, drainage level, constant GHB
and domain extent. See [BOUNDARY_ASSUMPTIONS.md](BOUNDARY_ASSUMPTIONS.md) for the
package audit, limitations and sensitivity procedure. Earlier numerical
benchmarks in this README predate v0.2.0 and must not be treated as current values.

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
- Local disk space. The tested 0/4/1 monthly-first spinup plus weekly 2/2 pre-/post-dam
  five-layer case produces about 1.7 GB in `Runs` and needs approximately 900 MB of scratch
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
MPLCONFIGDIR=../matplotlib-cache python3 -m unittest -v test_bdam_workflow.py test_coarse_river.py test_lake_drying.py
```

## Configure the simulation

Regenerate geometry and both handoffs after updating this source. LAK storage
tables must start at the lowest connected terrain elevation with zero volume
and positive onset area. Pond tables include terrain breakpoints in addition
to the configured base samples. The runner rejects trapped storage before
starting MF6 and converts MF6 dry-stage flags to physical bed elevations for
summaries and restarts, including dam installation.
LAK's maximum stage change is `5e-7` m, shared with `parameters-table`;
see [LAK validation](LAK_DRYING_VALIDATION.md) for numerical checks.

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

With no argument it preselects `~/BDamRuns/bdam-q0p1-20261015/BDam`, the validated 0.1 m3/s mean-inflow run.
The default curves are the four named channel groundwater heads and Lake 1
and Lake 2 stages. Lake IDs change meaning at dam installation: pre-dam,
Lakes 1--8 run upstream to downstream; post-dam, only Lake 1 (the sole
upstream pond) and Lakes 2 and 3 (the two downstream pools) exist. The same
lake number does not track the same physical feature across that transition.
The viewer does not read any output until the user clicks Load. Pass another
complete output root to preselect it when needed:

```matlab
LaunchBDamResultsViewerApp("/absolute/path/to/completed/BDam")
```

The selected root must contain `Geometry/BDamGeometry.mat`, `Runs/`, the run
summary CSVs, and each annual or staged workspace's `bdam.ic`, `bdam.hds`, and
`monitoring_targets.csv` files. The viewer reads these files without changing
them. Frame zero is the actual initial condition from `bdam.ic`; each saved
end-of-step head is the following frame. A 52-week simulation therefore has
53 frames spanning day zero through the end of week 52. Spinup files are
optional when all three configured spinup counts were
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
mf6_parameters.fall_average_spinup_years = 0;
mf6_parameters.monthly_spinup_years = 4;
mf6_parameters.weekly_spinup_years = 1;
mf6_parameters.pre_dam_years = 2;
mf6_parameters.post_dam_years = 2;
mf6_parameters.initial_head_channel_offset_m = 0.1;
mf6_parameters.uzf_nwavesets = 20;
```

The current configuration uses four monthly-climatology spinup years, then
one weekly year, with no annual constant-forcing phase. The first spinup
workspace retains the historical directory name `first_annual`, but contains
12 monthly periods, not one annual step. No 7-day fall relaxation is added
when fall-average years are zero. Optional fall-average spinup is still
available explicitly, but is not the recommended starting sequence.

Spinup always uses the pre-dam condition. Its three year counts are independent
nonnegative integers and may all be zero. The runner never adds hidden years or
extends spinup automatically. When at least one fall-average year is requested,
the runner first solves one 7-day transient period at the same constant
September--November-average forcing in `Runs/spinup/initial_relaxation`. Its final groundwater,
lake, and UZF state initializes the continuous staged simulation in
`Runs/spinup/first_annual`. Its final state initializes
`Runs/spinup/staged`, which contains the remainder of the configured stages in this order:

1. Each fall-average year is one 365-day stress period with exactly one
   MODFLOW time step and one saved annual endpoint. Inflow and atmospheric rates
   are held at the simple mean of their September, October, and November
   monthly values. Groundwater reference levels remain fixed in every phase.
2. Each monthly year has 12 water-year calendar-month steps with duration-weighted monthly
   averages.
3. Each weekly year has 52 steps of `365/52` days with weekly averages.

Every configured stage repeats its October-to-September climatology. Model day
zero represents October 1; all time-varying inputs are circularly shifted from
their source calendar-year order, while internal elapsed-time counters remain
unchanged. All stages remain transient and preserve groundwater, lake, and UZF
storage continuously.
When all three counts are zero, the first monitored year starts directly from
the configured planar initial heads, lake stages, and UZF water content;
no spinup workspace or `spinup_summary.csv` is produced. Otherwise, the final
staged state initializes the first pre-dam year exactly. Spinup always
ends at weekly resolution when a weekly stage is requested, even when monitored
years use daily resolution. The monitored duration is `pre_dam_years +
post_dam_years`; set `post_dam_years = 0` for a no-dam run.
The initial groundwater surface is a plane with the signed regional longitudinal
slope from the geometry database. At the downstream grid edge, it is anchored
0.1 m above the lowest channel cell. It is constant transversely and uses the
same head through each vertical column. There is no lateral rise, upslope
correction, or land-surface clipping. A plane at regional grade cannot remain
exactly 0.1 m above every channel cell when the channel has a different grade;
the offset is defined at the downstream channel bottom. The handoff exports
`initial_head_regional_slope_m_per_m` automatically from the geometry.
Regenerate both handoffs with `MakeInputs.m` after updating older packages.

To test initial conditions only through the configured monthly spinup, use
`--stop-after-monthly-spinup`. This retains the relaxation and annual/monthly
steps exactly, writes validated spinup outputs and `spinup_summary.csv`, and
stops before weekly spinup and monitored years. It requires a nonzero monthly
spinup count. Omit the flag for the complete configured model run.

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

The runner uses robust `COMPLEX` IMS settings for the 7-day relaxation and
the first modeled year. That first-year solve is recorded with the
`conservative` profile. Every remaining staged-spinup and monitored solve uses
the faster `balanced` profile and its `MODERATE` preset. If no spinup is
configured, the first monitored annual solve is conservative and all later
solves are balanced. The strict head and flow closure tolerances remain
unchanged. The runner prevents `conservative` from being selected globally.

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
upstream-to-downstream. In pre-dam years, all pools are aggregated geographically at
the reference dam line into upstream Lake 1 and downstream Lake 2 exchange
totals in both phases. Native LAK IDs identify individual pools and change
meaning at installation; native stages are not geographic exchange totals.

`Runs/spinup_summary.csv` separately records the state supplied to the staged
workspace—post-relaxation when a fall-average year is configured, otherwise
the planar state—and all completed staged-spinup states and derived fluxes. Rows identify
`spinup_fall_average`, `spinup_monthly`, or `spinup_weekly`, the stage year,
stage-relative time, cumulative transient time, and interval duration. With the
current 0/4/1 monthly-first settings it contains 101 rows: one initial state
plus 48 monthly and 52 weekly completed steps. Raw head, lake, and groundwater-boundary observation
CSVs and `bdam.fluxes.csv` are generated at every saved step in the spinup
workspaces and every pre-dam and post-dam annual workspace. Flux rates are m3/day and
interval-integrated volumes are m3.
When all spinup counts are zero, `Runs/spinup_summary.csv` and
both `Runs/spinup/first_annual` and `Runs/spinup/staged` are intentionally absent.
The relaxation workspace retains its own validated binary, observation, flux,
water-balance, and solver-statistics outputs. The Results Viewer begins its
Spinup timeline at the post-relaxation state in `Runs/spinup/first_annual`
and continues through `Runs/spinup/staged` when a remainder exists.

In the flux interface, `in_total` and `out_total` are coupled-system external
fluxes. Inputs are land infiltration, lake precipitation, upstream surface
inflow, and gross groundwater-boundary inflow. Outputs are land ET, rejected
infiltration, lake evaporation, external surface outflow and withdrawals, and
gross groundwater-boundary outflow. Opposing boundary-cell flows are summed
separately; netting never hides the gross exchanges.
Internal LAK--GWF exchange, LAK-to-LAK routing, and storage terms are excluded.
The former GWF listing totals remain available as `gwf_budget_in_total` and
`gwf_budget_out_total`. `net_atmospheric_recharge` is land infiltration plus
lake precipitation minus land ET and lake evaporation. `combined_storage_change`
is positive for increasing combined GWF+UZF+LAK storage, and
`coupled_mass_residual` is external net inflow minus that storage change.
Each rate field has a matching interval-volume field. Positive Lake 1/Lake 2
exchange is lake-to-groundwater; positive cross-dam groundwater flow is
upstream-to-downstream.

Pond filling depends on the inherited simulated pre-dam stage and local outlet
configuration. Weekly mode cannot resolve transients shorter than a week;
select daily mode when that filling transient matters. Each annual
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
