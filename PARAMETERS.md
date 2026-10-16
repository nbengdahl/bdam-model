# Parameter-table model interface

This guide is for people building case tables, sensitivity studies and external
optimizer integrations. For first-run setup and results, use
[END_USER_QUICK_START.md](END_USER_QUICK_START.md).
A row is a requested case, never an axis. The model does not insert a reference,
expand vectors, sample parameters, or assign objective penalties implicitly.

## Defaults and overrides

You only need to supply the parameters you want to change. The authoritative
scientific defaults are in [bdam_parameter_schema.json](bdam_parameter_schema.json),
under `parameters`: each field has a `default` value. The generated
[parameter reference](PARAMETER_REFERENCE.md) lists these defaults for readers.

For every case, values are resolved in this order:

1. Start with registry defaults.
2. Apply `shared` scientific settings from the study configuration.
3. Apply values supplied in that case's row, overriding either earlier source.
4. Resolve supported automatic (`null`) values using the final case settings.

For example, `geometry.dam_height_m` defaults to 1.5 m. If the study's `shared`
settings set it to 1.8 m, a row omitting it uses 1.8 m; a row specifying 2.0 m
uses 2.0 m. With neither override, it remains 1.5 m. Every row starts from the
same defaults/shared settings; values do not carry forward from previous rows.

In CSV tables, omit a column to inherit its value for all rows. A blank cell in
an included column generally fails validation; it does not mean "use default."
The explicit blank `monitoring_points_file` exception selects the monitoring
grid. Supported automatic values use the JSON token `null`; optional empty file
paths can use the JSON token `""`. Automatic values may depend on other case
parameters, as listed in the reference.

Start with [examples/paired_cases.csv](examples/paired_cases.csv), or generate a
complete template from a local package copy with
`python3 -m bdam template all-parameters.csv`.
Use shared settings or case rows for study-specific changes. If changing the
model's baseline defaults in source, keep the registry's `defaults` MATLAB mirror
and applicable `scalar_defaults` deprecated-adapter mirror consistent, then
regenerate the parameter reference. `MakeInputs.m` has no editable defaults block.
Existing frozen studies retain their captured source/settings; use a fresh study
to adopt changed registry defaults.

## Optional convergence-controlled spinup

Set `mf6_parameters.spinup_until_converged` to `true` in a case row or shared
settings (Python `True`, MATLAB logical `true`, CSV/JSON `true`). It defaults to
`false`, preserving the fixed spinup schedule. Enabled runs retain configured
fall/monthly warmup and replace `weekly_spinup_years` with an adaptive weekly
loop. `spinup_max_weekly_years` defaults to 10 and must be an integer at least 3;
this limit counts only weekly spinup years, excluding warmup and monitored years.
Every weekly year contains 52 steps totaling 365 days, even with daily monitoring.

Compare consecutive September year-end states, using the largest relative
change across all groundwater cells, all lakes and all UZF features separately:

`abs(new-old) / max(abs(new-reference), abs(old-reference), denominator_floor)`.

| Parameter under `mf6_parameters` | Default | Reference | Denominator floor |
| --- | ---: | --- | ---: |
| `spinup_head_relative_tolerance` | 0.001 (0.1%) | Each cell bottom | 1 m |
| `spinup_stage_relative_tolerance` | 0.01 (1%) | Each lake's lowest bed | 0.1 m |
| `spinup_water_content_relative_tolerance` | 0.005 (0.5%) | Zero | 0.05 m³/m³ |

Tolerances must be finite and positive. All three criteria must pass for two
consecutive year-pairs; the earliest stop is after three weekly years. Warmup
does not count toward comparisons. A failing year-pair resets the passing streak.
The criteria measure year-end repeatability, not agreement throughout the
seasonal cycle, calibration or physical accuracy. Solver and water-budget QA
remain unchanged. Denominator floors are fixed, documented constants.

For example:

```python
study.submit([{'case_id': 'adaptive',
               'mf6_parameters.spinup_until_converged': True}], 'adaptive')
```

Annual outputs appear in `Runs/spinup/weekly/year_NN`. Reports
`Runs/spinup_convergence.csv` and `.json` are updated after each weekly year,
along with `spinup_summary.csv`. They record relative/absolute maxima, controlling
MF6 zero-based indices (head: layer/row/column; stage/UZF: feature index),
thresholds, pass flags, consecutive-pass count and outcome. The first year is a
baseline with no comparison metrics. For heads/stages the absolute changes are
meters; for UZF they are m³/m³.

After convergence, monitored years inherit the last state. At the cap without
convergence, the case stops as **DNC (did not converge)**, retains diagnostics and
skips monitored years. Standalone execution exits with code 3. Studies report
`DNC` in Python/MATLAB results and `case_index.csv` and continue remaining rows;
they do not assign objective penalties. Batch CLI evaluation exits nonzero after
processing all rows if any row did not pass. DNC receives no successful completion
receipt and is distinct from input/solver failures. Re-evaluation may retry it.
The monthly-stop diagnostic remains warmup-only and cannot certify convergence.

Use fresh studies to adopt this source change. Full and compact successful reuse
recompute convergence metrics from retained annual final states. Compact results
keep reports and restart states; binary viewing still requires full retention.

## Local setup

Copy the complete package to local, nonsynchronized storage. Install the pinned
`requirements.txt` once for the Python interpreter used by both MATLAB and the
CLI. Put a local executable named `mf6` in `bin/` in the source or an ancestor.
MATLAB remains required for geometry and paired HDF5 preparation. Keep the source,
study, and active scratch/results directories local. Read `AGENTS.md` for model
calendar, boundary, solver, and completion requirements.

Run CLI commands from the local package directory. When an optimizer runs
elsewhere, add that directory to Python’s module path (`PYTHONPATH`).

## Python

```python
from bdam import Study, grid_cases, random_cases

study = Study('/local/study', {
    'shared': {'mf6_parameters': {'monthly_spinup_years': 4}},
    'execution': {'n_parallel_runs': 2, 'retention': 'full'},
})
study.submit([
    {'case_id': 'a', 'K_constant': 0.01, 'specific_yield': 0.1,
     'river_settings.downstream_segments': 1, 'metadata.label': 'paired A'},
    {'case_id': 'b', 'K_constant': 0.02, 'specific_yield': 0.2,
     'river_settings.downstream_segments': 3, 'geometry.dam_height_m': 1.4},
], 'iteration-1')
results = study.evaluate('iteration-1')

# An optimizer can now compute objectives from each successful result's
# scientific summary files, then submit its next candidates to this study.
study.submit([{'K_constant': 0.02}, {'K_constant': 0.04}], 'iteration-2')
next_results = study.evaluate('iteration-2')
```

Each result contains batch/case/execution IDs, resolved parameters, metadata,
status, structured errors, QA status, reuse information, summary locations, and
output paths. `evaluate` blocks until the selected batch finishes. It returns
per-case failures without numerical penalties; malformed batch requests,
missing runtime dependencies, or altered immutable snapshots raise exceptions.
`prepare(batch_id)` generates geometry and paired handoffs without simulation.
`collect(batch_id=None)` revalidates results and refreshes CSV/JSON reports.

Case IDs are unique within a batch; omitted IDs are assigned by row position.
Repeated physical configurations retain separate case results and may share one
validated execution. Labels and sampling metadata do not change scientific
identity. Use a new stochastic model input if you intend different realizations;
a repeated deterministic case is eligible for reuse.

`grid_cases(axes, fixed=None)` returns an explicit Cartesian design without an
added reference. `random_cases(bounds, count, seed, fixed=None)` generates
independent continuous uniform samples and records its seed, bounds and method.
Integer/categorical sampling, correlated designs and PSO remain external.

## CSV and CLI

```csv
case_id,K_constant,specific_yield,river_settings.downstream_segments,geometry.bottom_widths_m[1],metadata.label
a,0.01,0.1,1,2,paired A
b,0.02,0.2,3,3,paired B
```

```zsh
python3 -m bdam init /local/study --settings settings.json
python3 -m bdam submit /local/study cases.csv iteration-1
python3 -m bdam prepare /local/study iteration-1
python3 -m bdam evaluate /local/study iteration-1
python3 -m bdam collect /local/study
python3 -m bdam template all-parameters.csv
```

`settings.json` accepts `source`, `shared`, and `execution`. Source defaults to the
installed package directory. Execution settings are `n_parallel_runs` (default
1), `retention` (`full` by default, or `compact`), and `matlab` (default `matlab`,
or an explicit installation executable). Relative hydrograph/hydrofacies/monitoring paths
are resolved against `source`; each execution receives its own immutable copies.
New submissions generate geometry; supplying a geometry MAT file is rejected.

JSON case files contain an array of flat rows or objects with `case_id`,
`parameters`, and `metadata`. Complete native arrays are supported in JSON and
as JSON-valued CSV cells. Indexed columns are one-based. Do not supply both a
whole array and indexed assignments for that array in the same override layer.

Defaults resolve in this order: registry, shared scientific settings, row
overrides, dependent defaults. Omit columns to inherit values. Declared CSV
cells must be populated, except a blank `monitoring_points_file` selects the grid. Use the JSON token `null` for supported automatic
values, and the JSON token `""` for an intentionally empty optional file path.
Empty vectors are not automatically interpreted as candidate sets or defaults.
Monthly arrays keep twelve entries; layer arrays match the resolved layer count.
Automatic boundary conductivity follows each case's `K_constant`.

## MATLAB

```matlab
cases = table(["a";"b"],[0.01;0.02],[1;3], ...
    VariableNames=["case_id","K_constant","river_settings.downstream_segments"]);
result = evaluateBDamCases(cases,"/local/study","iteration-1", ...
    Settings=struct("execution",struct("n_parallel_runs",2)));
```

`Action="submit"`, `"prepare"`, `"evaluate"` (default), and `"collect"` map to the
same Python operations. `CASES` can also be a CSV/JSON path, read by the same Python parser.
Arbitrary table column names are preserved. A cell containing `[]` represents
an automatic value for supported automatic columns. Missing values are errors. Set
`BDAM_PYTHON` to the selected Python executable before launching MATLAB.

`MakeInputs.m` is a convenience entry point: set `BDAM_STUDY_ROOT`, `BDAM_CASES`
(CSV/JSON), and optionally `BDAM_BATCH_ID` (default `inputs`). `BDAM_CONFIG` is
the path to a JSON file containing shared scientific overrides with nested or
dotted names; `BDAM_PREVIEW=1` submits only. Without a study root it prepares
one valid scientific execution (the default if no cases file is set) and publishes the
usual `Geometry/` and `ModelInput/` standalone layout. `MakeGrid.m` remains a
standalone terrain preview using the same registry defaults. It no longer needs
to run before `MakeInputs.m`.

## Segmentation

`river_settings.downstream_segments` is a positive integer, default 2. Nominal
pool length is centerline distance from the downstream edge to the dam divided
by that count. Before dam installation this spacing extends upstream. Any
remaining upstream length enlarges the upstream-most pool rather than creating
a short extra pool. An upstream reach shorter than one interval forms one pool.
After installation the upstream pools merge into one pond; downstream pools
remain separate and surface-water volume is conserved.

Requests exceeding the downstream longitudinal cell count fail preparation.
Counts that create an empty interval also fail, even below that limit. The
preprocessor never lowers the requested count. Metadata records nominal edges,
actual cell-center extents, counts and lake roles. Only minimum-Y downstream
geometry is currently supported. Lake numbers identify features within a phase;
they do not identify the same location across installation or across cases.
Alternate segmentation requires its own scientific assessment.

## Persistence, concurrency, and migration

Study settings and submitted batches are immutable. Identical batch resubmission
is idempotent; changed content under the same ID is an error. New batch IDs append
cases without modifying earlier requests. Scientific source/input/runtime changes
produce different execution identities. Changing the study's copied MF6 executable
requires a new study. Matching completed results are revalidated before reuse.

Preparation is serial under one study lock; simulations use per-execution claims
and study-wide capacity slots, including multiple launchers. Do not edit execution
snapshots, generated handoffs, active results or lock files. Failed simulation
attempts and preparation retry diagnostics are retained. Full output is default;
compact output keeps scientific reports and restart states after validation but
cannot be opened in the binary Results Viewer.

Reports live in `results/BATCH/` or `results/all/`: `results.json`, `case_index.csv`
and `ensemble_summary.csv`. Every case appears in the index, including duplicates
and failures. Only validated successful cases contribute scientific summary rows.

`bdam_sweeps.py` is deprecated. Its `plan` command converts candidate vectors to
new explicit cases, translating legacy reference/skip rules in the adapter only.
It ignores the old shared geometry-file selection and generates geometry from
registry defaults unless geometry overrides are supplied through the new API.
Old saved campaign manifests are rejected by the new adapter; use their frozen
source snapshots to inspect/resume them. No automatic migration is performed.

Implementation evidence and observed numerical limits are recorded in
[PARAMETER_VALIDATION.md](PARAMETER_VALIDATION.md).

## Forcing transforms

`forcing_mode="periodic"` is the default. Each of `forcing_controls.inflow`,
`.precipitation` and `.et` has `magnitude_scale=1`, `shift_days=0`,
`width_factor=1` and automatic `center_day=null`. Positive shifts delay the
season; centers are elapsed water-year days (0 = October 1), with the first
baseline daily maximum used automatically.

Nonnegative cyclic Hermite curves join continuously in value and first derivative.
Their exact integrals supply STEPWISE period means, including the monthly and
weekly spinup calendars. Magnitude scales annual mass; timing and width preserve
it for the driver. Width above 1 broadens the seasonal excess above its baseline;
it is a circular time warp, not an exact standard-deviation multiplier. Inspect
`forcing_diagnostics.json` for actual annual integral and circular RMS width.
Land infiltration also uses calendar-month recharge efficiencies, so shifting
precipitation can change annual infiltration. Lake evaporation follows transformed
ET. Boundaries/outlet levels do not follow forcing transformations.

`forcing_mode="legacy"` retains the earlier stepwise construction and requires
identity transform controls. It remains available for deliberate comparisons.
Each case repeats its climatology each year; stochastic/interannual weather,
correlated designs, objective functions, PSO and distributed execution are external.

## Standalone configuration example

Write shared overrides to a local JSON file:

```json
{"K_constant": 0.06, "geometry": {"dam_height_m": 1.2}}
```

```sh
export BDAM_PYTHON="$(command -v python3)"
BDAM_CONFIG=/absolute/local/overrides.json matlab -batch "run('MakeInputs.m')"
```

MakeInputs environment variables are `BDAM_CONFIG` (shared JSON file path),
`BDAM_CASES` (CSV/JSON case file path), `BDAM_STUDY_ROOT` (local study directory),
`BDAM_BATCH_ID` (default `inputs`), `BDAM_PREVIEW=1` (submit only), and `BDAM_PYTHON`.
Existing study settings/batches are immutable. Changing a standalone configuration
under an already-used `Study/` requires a fresh package/run folder or an explicit
new study root. When a study root is set, use study evaluation afterward; the
standalone `Geometry/` and `ModelInput/` publication is not performed.

## Registry v4 cleanup and migration

The complete catalog is [PARAMETER_REFERENCE.md](PARAMETER_REFERENCE.md), generated
from `bdam_parameter_schema.json`. The `defaults` mirror supplies MATLAB and the
`scalar_defaults` mirror supports the deprecated adapter. Check them together
when changing defaults. No editable scientific input block remains in MakeInputs.

Removed fields are rejected: `initial_river_depth_above_outlet_bed_m`,
`pre_dam_outlet_width_m`, and `post_dam.initial_depth_above_dam_toe_m`. The first
two never controlled the coarse-river numerical inputs; river pools initialize
0.10 m above their lowest bed and channel widths use
`river_settings.manning_width_m`. The third was a preparation preview depth, not
the conservative installation state. Pond preparation now uses an internal
seed depth capped by dam height; installation always conserves pre-dam volume.

Strictly positive dam heights below 1 m can now prepare without overriding a
legacy preview. Zero height is not accepted as a dam geometry; a no-installation
monitoring case uses `mf6_parameters.post_dam_years=0`. Unity horizontal and
vertical conductivity multipliers are allowed to retain background aquifer
conductivity beneath the surface dam. These are preparation capabilities, not
a promise that every parameter combination converges.

Create new studies for the current v6 source/registry and v8 handoff. Preserve old immutable batches,
source snapshots and results with their original tools. No automatic manifest,
handoff or removed-control migration is performed. The default numerical model,
calendar, solver policy, boundaries and closure tolerances are unchanged.

## Choosing scientific inputs

The registry catalog supplies exact accepted fields/defaults and individual
bounds. These groups explain what the inputs control; they are distinct from
study scheduling and retention.

| Group | Meaning and interactions |
| --- | --- |
| `geometry.*` | Two nested trapezoidal channel sections, left/right floodplain slopes and step, domain/grid/origin, sinusoidal centerline, longitudinal grades, and dam height/location. Side slopes are horizontal run per unit rise. X is transverse; Y is longitudinal. The meander and channel must fit inside the domain. |
| `model_bottom_offset`, `n_layers`, `layer_growth_factor` | Bottom plane below the lowest terrain and geometric layer-thickness growth toward deeper layers. Choose a leakage-layer count no greater than `n_layers`; defaults require at least three layers unless that count is reduced. |
| `hydraulic_conductivity_mode` | `constant` uses K/K33 constants; `by_layer` uses top-to-bottom arrays; `hydrofacies_points` assigns the nearest horizontal point whose vertical interval contains a cell center, then maps class K/K33. This is deterministic nearest-point assignment, not geostatistical interpolation. |
| Layer arrays and hydrofacies records | Automatic layer arrays are 0.03 and 0.003 m/day repeated for the resolved layer count, independently of K_constant. Hydrofacies input is a CSV path or inline records with x/y, top/bottom elevation and class ID; class-property records supply K/K33 for every resulting class, including fallback. |
| `specific_yield`, `specific_storage`, `effective_porosity` | Drainable unconfined storage, elastic storage (1/m), and diagnostic saturated groundwater-volume porosity. These do not substitute for UZF residual/saturated water contents. |
| `channel_half_width_cells`, lakebed K/thickness | Channel mask around each row's transverse minimum and vertical LAK–GWF leakance (K/thickness, default 0.2/day). Connection footprints and storage footprints are distinct. |
| `river_settings.*` | Downstream pool count, Manning width/roughness, pond connection-height cutoff and river table storage extent. See the river guide for spacing, routing and footprint assumptions. |
| `geometry.dam_height_m`, `post_dam_weir_width_m`, `dam_settings.*` | Surface crest, active crest-transfer width, shallow under-dam K/K33 multipliers/mask, dam-toe sampling and pond storage-table resolution/extent. These do not directly simulate literal dam porosity or resolve flow inside a dam body. |
| Groundwater boundary controls | DRN discharge threshold or explicit constant GHB head relative to outlet bed, effective K and resistance length. Automatic boundary K follows K_constant even in by-layer/hydrofacies mode; set it explicitly when needed. |
| `groundwater_edge_flux.*` | Signed total m³/day on the bottom-layer −x, +x and +y edges, uniformly distributed by length; default zero. Separate WEL packages preserve corner contributions; no automatic flow reduction. |
| `external_outlet_height_above_bed_m` | Surface Manning invert above local outlet bed. Independent of groundwater levels and upstream flow; there is no hidden remote rating curve. |
| Precipitation, ET, recharge and streamflow | Twelve January–December precipitation totals and seasonal ET/recharge factors; synthetic mean inflow/ET and recharge/evaporation fractions. A positive 365-row normalized hydrograph supplies shape, not a field-calibrated absolute flow. |
| `mf6_parameters.uzf_*` | Residual/saturated/initial moisture, Brooks–Corey exponent, surface depression, ET extinction depth/content, trailing waves and wave-set numerical capacity. Wave capacity is numerical storage, not a calibration parameter. |
| Initial head and year counts | Regional-slope planar heads anchored at downstream channel bed + configured offset, no clipping to land. Independent spinup and monitored year counts; at least one monitored year is required. Zero post-dam years give no-installation monitoring. |

Atmospheric recharge/ET acts through UZF over land and rainfall/evaporation through
LAK over storage footprints; RCH/EVT are prohibited to prevent double counting.
Changing pond footprint changes the land/lake atmospheric partition. A fixed dry
storage footprint does not recover surface UZF automatically. Review this
assumption before interpreting rainfall, recharge or evaporation sensitivities.

Schema-valid scalar bounds do not guarantee geometric resolution or nonlinear
convergence for an entire case. Check preparation status, numerical QA, storage
adjustment, and matched no-dam controls before using summaries as optimizer objectives.

## Prescribed groundwater edge totals

Supply `groundwater_edge_flux.x_min_m3_per_day`,
`groundwater_edge_flux.x_max_m3_per_day` and
`groundwater_edge_flux.y_max_m3_per_day` as finite scalar totals in m³/day.
Defaults are zero. Positive values enter the domain; negative values leave.
Each total is distributed uniformly along its bottom-layer edge, independently
of the other edges and downstream DRN/GHB. Shared corner cells receive both
edge contributions. Values remain constant through all phases and restarts.

For example, a JSON case row can contain:

```json
{
  "groundwater_edge_flux.x_min_m3_per_day": 3,
  "groundwater_edge_flux.x_max_m3_per_day": -5,
  "groundwater_edge_flux.y_max_m3_per_day": 7
}
```

These are prescribed regional boundary fluxes represented by separate WEL
packages, with automatic flow reduction disabled. They are not inferred from
head, hydraulic conductivity or surface inflow. See the boundary contract for
budgets and interpretation. Existing studies retain their original snapshots;
regenerate inputs in a fresh study to use these parameters.

## Optional monitoring CSV

`monitoring_points_file` is a filename, default `""`. Relative paths are resolved
against the study source folder; absolute paths are accepted. The file is copied
and content-hashed with other scientific inputs. Changed contents create a new
execution identity. Blank or whitespace-only filenames, including blank case-CSV
cells, retain the existing four stream points plus six bottom-layer grid points.

A supplied CSV replaces only those six grid points. The four named stream
points remain at their existing locations and bottom layer. For example:

```json
{"monitoring_points_file": "examples/monitoring_points.csv"}
```

```csv
x,y,z,name
20,70,0.25,Shallow floodplain
20,70,4.5,Deeper floodplain
50,105,2,Upstream right bank
```

Headers are case-insensitive. X and Y use model coordinates in meters.
**Z is depth below ground in meters, not elevation or layer number.** Ground is
the terrain elevation of the containing horizontal cell. The point samples the
head of the layer containing ground elevation minus depth, without interpolation.
A point on an internal layer interface selects the deeper layer; terrain and
model-bottom faces are valid. Horizontal domain faces are valid; an internal
horizontal cell face selects the cell on the increasing-coordinate side.

Outside-X/Y, negative-depth and below-bottom points are omitted. Preparation
and monitored workspaces publish `monitoring_omitted.csv` with original data-row
numbers (first data row = 1), coordinates, names and reasons. Missing/unreadable
files, missing columns, nonfinite/nonnumeric coordinates, blank retained names
or retained names duplicated without regard to case are errors. Differently
named points may sample the same cell. An empty, header-only or entirely omitted
supplied file leaves the four stream points; it does not restore the grid.

Original names are preserved as viewer labels and as `original_name` in
`monitoring_targets.csv`. Native observation and summary identifiers are stable
`head_csv_0001`, etc., using the original data-row number; omitted rows leave
gaps. Summary columns append `_m`. Targets also record source, row, requested
depth, derived elevation, resolved cell and resolved cell-center elevation.
The omission report and metadata are also retained in the preparation manifest
and standalone HDF5 handoff. Use fresh studies/preparation for registry v6 /
handoff v8; existing frozen studies retain their original sources and inputs.
