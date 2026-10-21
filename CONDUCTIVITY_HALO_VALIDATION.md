# Under-dam conductivity halo — 21 October 2026

Historical comparison: the numerical results below used the earlier
multiplier-derived 0.15 m/day core. The current default is the independent
`under_dam_k_m_per_day = 1.0`; these results do not validate that new default.
See `UNDER_DAM_K_VALIDATION.md` for its separate validation.

Implemented on `main`, based on `1327c77082561e586cba97155a8e77f29b0cf653`.
Changes are uncommitted. The merged pond, LAK/UZF geometry, groundwater
boundaries, production calendar and numerical controls are unchanged.

## Treatment

The original core footprint is preserved exactly. Its K and K33 now both
equal five times each cell's background horizontal K. A one-cell,
eight-neighbor plan-view expansion adds a disjoint halo in the same top three
layers, including cells outside the channel and clipping at domain edges.
Each halo component is the arithmetic midpoint between its local background
and the scalar treatment K. `leakage_halo_cells = 0` disables only the halo.

On the default geometry there are 6 core and 14 halo cells per treated layer
(18 core and 42 halo cells in three dimensions). Core K = K33 = 0.15 m/day;
halo K = 0.09 and K33 = 0.0765 m/day. The background remains K = 0.03 and
K33 = 0.003 m/day. Counts depend on the actual dam/channel geometry.

Separate core/halo masks and footprints are additive schema-v6 audit fields.
The existing treatment masks are their union. Old handoffs retain their
original numerical arrays; regenerate inputs to obtain the new treatment.

## Comparison

All runs used persistent nonsynchronized local storage:
`/Users/nick.engdahl/BDamRuns/bdam-halo-20261021`.

The halo case completed the full 0/4/1 spinup plus two pre-dam and two
post-dam weekly years: six workspaces and 308 saved endpoints. Archived
baseline and isotropy-only controls each continued for two post-dam years
from the same validated final pre-dam groundwater, lake and UZF checkpoint.
They are comparison continuations, not independent complete workflows.

| Configuration | Year-2 total cross-dam flow (m³) | Core-location flow (m³) | Halo-location flow (m³) | Outer iterations, both post-dam years |
|---|---:|---:|---:|---:|
| Archived baseline, anisotropic core | 82.135327 | 16.608192 | 3.580521 | 1109 |
| Isotropic core, no halo | 87.157378 | 22.985563 | 3.742821 | 1102 |
| Isotropic core plus halo | 130.259186 | 47.092643 | 19.291596 | 1106 |

Positive flow is upstream-to-downstream. Common face groups are used in all
cases: a face touching core takes precedence, then halo, then background.
These disjoint groups, split by all five layers, reproduce the existing
total cross-dam diagnostic at every endpoint. Halo-location flow in the
baseline/control refers to cells that still have background conductivity.

The halo adds 43.101808 m³/year (+49.45%) to total cross-dam groundwater flow
relative to isotropy alone. Flow through common core-plus-halo locations
increases from 26.728384 to 66.384239 m³/year (+148.37%). This supports
footprint sensitivity in this configuration. The two-year outer-iteration
counts show no material solver improvement. MF6 solve times were 61.96 s
with the halo and 64.04 s with isotropy alone; single-run timing differences
are not evidence of a general speed improvement.

Year-2 external surface outflow changes by only +2.305335 m³ out of about
3.153 million m³. Under-dam flow is an internal exchange, not an equivalent
increase in external discharge. The maximum absolute final whole-grid head
difference between halo and isotropy-only cases is 0.249415 m. These are
uncalibrated-model results and do not establish field realism or prove area
is the only limitation.

## Validation

- All 36 existing Python tests and eight MATLAB helper/routing test cases pass.
  Helper cases cover irregular/diagonal footprints, shifted placements,
  boundary clipping, unchanged depth, heterogeneous backgrounds and halo-off.
- All 354 shared pre-dam HDF5 datasets match across configurations. Post-dam
  differences are confined to K/K33 and treatment masks. The old core mask
  matches the new core exactly. Independent MF6 input builds/reloads verify
  prepared and serialized halo/isotropy-control conductivities.
- Prepared lake-storage checks pass. All three existing drying/restart/
  installation/rewetting solves pass seven seven-day diagnostic endpoints.
  Maximum coupled discrepancy is 0.00528899%, below the unchanged 0.1% limit.
- All ten production/comparison workspaces pass normal termination, readable
  required binaries, saved counts/times, strict budgets, observations and
  restart validation. Wet installation conserves 2.944210461465763 m³ with
  zero error. LAK tolerance remains 5e-7 m and the outer cap remains 2000;
  calendars, closures and IMS profiles were not changed.

Runtime: MATLAB R2025b, Python 3.14.6, FloPy 3.10.0, NumPy 2.5.2, h5py 3.16.0,
MF6 6.7.0 (02/05/2026). No API dependency or backwater code was introduced.

## Evidence and reproduction

The local `evidence/REPORT.md` contains plots and the complete comparison.
`annual_comparison.csv`, `effect_differences.csv`, `weekly_comparison.csv` and
`cross_dam_by_layer_region.csv` contain stages/storage, groundwater heads,
surface and groundwater fluxes, ET, infiltration, budget and solver metrics.
`completion_checks.json`, `input_parity.json`, array-validation receipts,
the shared checkpoint, source/runtime provenance and campaign/analysis
scripts are retained alongside it. Numerical results remain in each
configuration's `Runs` directory; drying evidence is in `drying/`.

For a fresh local source copy, run MakeGrid then MakeInputs, the Python suite,
`runtests({'tests/applyBDamConductivityTest.m','tests/makeCoarseRiverScenarioTest.m'})`,
`verifyPreparedLakeStorage('ModelInput')`, and
`python3 tools/verify_conductivity_halo.py ../unique-array-audit`.
The audit builds and reloads inputs without launching MF6. Existing
`tools/verify_lake_drying.py` performs the separate bounded drying regression.
The retained campaign script records the exact serial full-run/control
procedure and shared-state lineage. Follow AGENTS.md for execution setup,
process checks and completion requirements.
