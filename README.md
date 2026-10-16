# BDam: parameter-table branch

## Dam height parameter

Use `geometry.dam_height_m` for the dam height in meters above the sampled dam toe
(default 1.5 m). This is the dam height itself. Update saved parameter
files to use the current field name; the numerical value and dam geometry
calculation are unchanged.

BDam compares groundwater and surface-water behavior before and after installation
of a beaver dam analog (BDA). MATLAB generates terrain and physical inputs;
Python/FloPy builds and runs MODFLOW 6, carries state between phases, checks
water budgets, and collects scientific summaries. This unreleased branch adds
persistent explicit-case studies to the v0.2.1 model. It is a demonstration
framework with synthetic forcing and assumed material properties.

## Start here

| Reader or task | Guide |
| --- | --- |
| First run, installation, results, troubleshooting | [End-user quick start](END_USER_QUICK_START.md) |
| Python, CSV/JSON or MATLAB case tables; successive optimizer batches | [Parameter-table interface](PARAMETERS.md) |
| Every accepted scientific field, default, type and unit | [Parameter reference](PARAMETER_REFERENCE.md) |
| River geometry, storage, routing and interpretation | [River formulation](RIVER_REFINEMENTS.md) |
| Groundwater edge fluxes, DRN/GHB and surface outlet | [Boundary contract](BOUNDARY_ASSUMPTIONS.md) |
| Automated agents modifying or running the model | [Agent runbook](AGENTS.md) |
| Current validation and historical evidence | [Edge-flux verification](EDGE_FLUX_VALIDATION.md), [cleanup and validation index](CLEANUP_VALIDATION.md) |
| Previous vector-sweep requests | [Deprecated adapter and migration](SWEEPS.md) |

## Current defaults

Scientific defaults are defined in `bdam_parameter_schema.json`, in each
`parameters` entry's `default` field. Browse them in the generated
[parameter reference](PARAMETER_REFERENCE.md). Each case starts from those
defaults, applies any shared study settings, then applies its own table-row
values. Omitted columns inherit the resulting values; ordinary blank cells
are errors. See [defaults and overrides](PARAMETERS.md#defaults-and-overrides)
for automatic values, blank-file exceptions and a worked example.

- 70 × 140 cells at 1 m spacing; five groundwater layers.
- Eight Manning-connected river pools before installation; one upstream pond
  and two downstream pools afterward. Positive integer downstream counts are
  configurable, subject to grid resolution and successful model validation.
- Local outflow-only DRN groundwater boundary; independent free surface outlet.
  Constant GHB is an explicit sensitivity option. Signed bottom-layer groundwater
  totals on −x, +x and +y default to zero and use separate WEL packages.
- Mean synthetic upstream inflow 8640 m³/day (0.1 m³/s); repeating seasonal
  precipitation, ET and inflow with optional magnitude, timing and width controls.
- 0 fall-average / 4 monthly / 1 weekly spinup years, followed by 2 pre-dam and
  2 post-dam years at weekly resolution. Daily monitored output is optional.
- Full output retention; one active simulation per study by default.

A default run has six workspaces and 308 saved time steps. The October 15 local
verification retained about 3.4 GiB in `Runs`; reserve at least 6 GiB for one run
plus staging, and more for multiple executions, backups or retained failures.
Runtime and peak storage depend on configuration and hardware.

## Two ways to run

Run only from local, nonsynchronized storage. A Google Drive source copy is for
storage/editing; copy it before executing MATLAB, Python or MODFLOW. Install
`requirements.txt` once for a persistent Python 3.12+ interpreter, use MATLAB
(tested R2025b), and place an executable named `mf6` in a local `bin/` directory
inside the package or an ancestor. MODFLOW 6.7.0 is the validation reference;
record the actual version used.

For one default run, from the local package directory:

```sh
export BDAM_PYTHON="$(command -v python3)"
matlab -batch "run('MakeInputs.m')"
mkdir -p ../matplotlib-cache ../staging
set -o pipefail
MPLCONFIGDIR=../matplotlib-cache PYTHONUNBUFFERED=1 \
  python3 build_bdam_simulation.py ModelInput --staging-root ../staging \
  2>&1 | tee ../model_runner.log
```

`MakeInputs.m` generates geometry and paired handoffs; `MakeGrid.m` is an
optional standalone terrain preview, not a prerequisite. Check for another model
process before launching a standalone run; see the quick start.

For multiple cases or an external optimizer:

```python
from bdam import Study

study = Study('/absolute/local/my-study')
study.submit([
    {'case_id': 'reference'},
    {'case_id': 'higher_K', 'K_constant': 0.06},
], 'batch-1')
results = study.evaluate('batch-1')
```

Each row is one case. There is no automatic reference, parameter expansion,
sampling, or objective penalty. Repeated scientific configurations may reuse a
validated execution while retaining separate case records. See `PARAMETERS.md`
for parallel execution, generated designs, MATLAB/CLI equivalents, failures,
immutability, retention and reporting.

A ready-to-edit two-case CSV is [examples/paired_cases.csv](examples/paired_cases.csv).
From a local package copy, `python3 -m bdam template all-parameters.csv` generates
a template containing all scientific parameters.

## Results and physical scope

Start with `Runs/spinup_summary.csv`, `Runs/weekly_summary.csv` (or
`daily_summary.csv`), each workspace's `bdam.water_balance.json`, and
`bdam.solver_stats.json`. Native LAK IDs change meaning across installation;
derived upstream/downstream exchange totals retain their geographic meaning.

```matlab
LaunchBDamResultsViewerApp("/absolute/local/completed/BDam")
```

The viewer loads full-retention outputs after **Load** is clicked. It includes
initial conditions, phase scopes, dynamic lake series, maps, contours and
animation. With no argument it selects the local package directory; it does not
assume a particular user's completed run exists.

The model conserves surface volume when pools merge and carries groundwater
heads and common UZF states between phases. Coarse pools have uniform stages
and no receiving-pool backwater feedback. Dry portions of maximum storage
footprints omit surface UZF. Numerical closure and spinup duration do not by
themselves establish calibration, equilibrium or boundary insensitivity; see the
river and boundary guides for the assumptions relevant to interpretation.

## Development and provenance

From a local package directory:

```sh
MPLCONFIGDIR=/absolute/local/cache python3 -m unittest discover -v -p 'test_*.py'
```

MATLAB and complete-run acceptance procedures are in `AGENTS.md`. Defaults and
validation live in `bdam_parameter_schema.json`; generated geometry, inputs,
studies, environments and results are excluded from Git. Frozen studies retain
their source snapshots and must not be edited to adopt newer code.

The packaged hydrograph shape is derived from USGS station 13348000;
`USGS_HYDROGRAPH_PROVENANCE.json` records its query, derivation and checksum.
Software citation metadata are in `CITATION.cff`; the license is MIT (`LICENSE`).
The release metadata identifies v0.2.1; branch changes are recorded separately in
[CHANGELOG.md](CHANGELOG.md).
