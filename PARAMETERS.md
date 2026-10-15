# Parameter-table model interface

This branch is the durable case interface for ensembles and external optimizers.
A row is a requested case, never an axis. The model does not insert a reference,
expand vectors, sample parameters, or assign objective penalties implicitly.

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
     'river_settings.downstream_segments': 3, 'geometry.dam_max_m': 1.4},
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
or an explicit installation executable). Relative hydrograph/hydrofacies paths
are resolved against `source`; each execution receives its own immutable copies.
New submissions generate geometry; supplying a geometry MAT file is rejected.

JSON case files contain an array of flat rows or objects with `case_id`,
`parameters`, and `metadata`. Complete native arrays are supported in JSON and
as JSON-valued CSV cells. Indexed columns are one-based. Do not supply both a
whole array and indexed assignments for that array in the same override layer.

Defaults resolve in this order: registry, shared scientific settings, row
overrides, dependent defaults. Omit columns to inherit values. Declared CSV
cells must be populated. Use the JSON token `null` for supported automatic
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
(CSV/JSON), and optionally `BDAM_BATCH_ID` (default `inputs`). `BDAM_CONFIG`
contains shared scientific overrides with nested or dotted names; `BDAM_PREVIEW=1` submits only. Without a
study root or cases file it prepares a single default case and publishes the
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
