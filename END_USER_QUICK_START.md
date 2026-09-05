# BDam model end-user quick-start manual

## Purpose

This manual explains how to prepare, run, inspect, and modify the BDam
groundwater–surface-water model. It assumes familiarity with basic hydraulics,
groundwater flow, and mass balance, but it does not assume programming
expertise.

The model compares a connected pre-dam river with a post-dam system containing
an upstream impoundment, a downstream river reach, and a porous beaver-dam
analog (BDA). MATLAB prepares the terrain and physical inputs. Python and
FloPy translate those inputs into MODFLOW 6, run the simulations, carry state
between phases, and validate the results.

The packaged defaults are a transparent demonstration case, not a calibrated
field model. Site-specific use requires defensible terrain, aquifer properties,
forcing, lakebed properties, and boundary conditions.

## The model in one diagram

```text
Values selected by user
        │
        ├── terrain and dam geometry ──> MakeGrid.m
        │                                  │
        │                                  └── Geometry/BDamGeometry.mat
        │
        └── aquifer, boundary, forcing,
            soil, calendar, and run inputs ──> MakeInputs.m
                                                   │
                                                   ├── review plots
                                                   └── ModelInput/
                                                       ├── pre_dam/
                                                       └── post_dam/
                                                               │
                                                               v
                                                   build_bdam_simulation.py
                                                               │
                                                               v
                                                         MODFLOW 6
                                                               │
                                                               v
                                                            Runs/
```

There are only three normal build commands, and they must be run in order:

1. `MakeGrid.m` creates geometry.
2. `MakeInputs.m` creates reviewed pre-dam and post-dam handoffs.
3. `build_bdam_simulation.py` runs MODFLOW 6 and validates every completed
   workspace.

Do not edit `Geometry`, `ModelInput`, or `Runs` by hand. They are generated
products. Change their source inputs and regenerate them.

## Five data forms used in this model

| Data form | Plain-language meaning | Example |
|---|---|---|
| Constant | One number or choice used over an entire model or feature | Specific yield = 0.20 |
| Vector or table | A short ordered list or a table with named columns | Twelve monthly precipitation totals |
| Scalar field | One value at every horizontal grid cell; a 2-D map | Land-surface elevation `ZTop(x,y)` |
| Tensor field | One value at every grid cell and layer; a 3-D block | Horizontal hydraulic conductivity `K(x,y,layer)` |
| Time series | Values that change by day, week, month, or stress period | Upstream inflow in m3/day |

The user normally supplies constants, short vectors, and source tables.
MATLAB derives the scalar and tensor fields. This is intentional: a user
should not have to type thousands of grid-cell values unless a spatial data
set is being deliberately imported.

## Coordinate, layer, time, and sign conventions

These conventions must remain consistent throughout the workflow.

| Convention | Meaning |
|---|---|
| X direction | Transverse to the channel in the default geometry |
| Y direction | Longitudinal direction along the channel in the default geometry |
| MATLAB horizontal arrays | `[x,y]`: first index is X, second index is Y |
| MATLAB 3-D arrays | `[x,y,layer]`; native layer 1 is bottom and `nz` is top |
| MODFLOW arrays | `[layer,row,column]`; layer 1 is top |
| Length and elevation | meters |
| Time | days |
| Flow rate | m3/day |
| Model year | October 1 through September 30; exactly 365 days |
| Positive lake exchange | lake to groundwater |
| Positive cross-dam groundwater flow | upstream to downstream |

The Python runner performs the MATLAB-to-MODFLOW orientation conversion.
Do not manually transpose or flip exported arrays.

## Software and disk requirements

The validated package uses:

- MATLAB R2025b; no optional MATLAB toolbox is required;
- Python 3.12 or newer;
- FloPy 3.10.0, h5py 3.16.0, and NumPy 2.5.2 from `requirements.txt`;
- MODFLOW 6.7.0 dated 2026-02-05, installed as an executable named `mf6`;
- at least 4 GB of free local disk space for the default run.

Run the model only on a local, nonsynchronized filesystem. Do not actively
run it in Google Drive, OneDrive, Dropbox, iCloud Drive, or a network share.
Large model files can appear complete before a synchronization provider has
actually finalized them.

## Quick start: run the packaged default case

### 1. Make a clean local copy

Copy the unopened archive to a persistent local directory under the user's
home folder and extract it there. The suggested `~/BDamRuns` folder normally
survives restarts and keeps active model files separate from the source
archive. Verify that this folder is not redirected into cloud or network
storage.

Another persistent local folder may be used when preferred; substitute that
path consistently in the commands below and keep the same folder layout.

```zsh
mkdir -p "$HOME/BDamRuns/bdam-run-mycase"
cp /path/to/BDam-v0.1.0.tar.gz \
  "$HOME/BDamRuns/bdam-run-mycase/BDam-v0.1.0.tar.gz"
tar -xzf "$HOME/BDamRuns/bdam-run-mycase/BDam-v0.1.0.tar.gz" \
  -C "$HOME/BDamRuns/bdam-run-mycase"
cd "$HOME/BDamRuns/bdam-run-mycase/BDam"
```

### 2. Install MODFLOW and install Python packages once

Place a local copy of MODFLOW at `../bin/mf6`, then verify it.

```zsh
mkdir -p ../bin
cp /path/to/mf6 ../bin/mf6
chmod +x ../bin/mf6
../bin/mf6 -v

python3 --version
python3 -m pip install --user -r requirements.txt
mkdir -p ../matplotlib-cache
MPLCONFIGDIR=../matplotlib-cache \
  python3 -m unittest -v test_bdam_workflow.py
```

Install the requirements once for the selected `python3` and reuse that
interpreter for every BDam run. The Python installation may come from any
provider. If it uses its own persistent package environment, install
`requirements.txt` there once. Never create `.venv` inside an individual BDam
run. All fast tests must pass before a model run.

### 3. Build geometry and model inputs

Run from the extracted `BDam` directory:

```zsh
matlab -batch "run('MakeGrid.m')"
matlab -batch "run('MakeInputs.m')"
```

Review the MATLAB figures and console summaries. Confirm at least:

- the river follows the long Y axis;
- channel and lake masks occupy the expected cells;
- the dam crosses the channel at the intended station;
- both post-dam lakes exist and do not overlap;
- the downstream GHB lies on the low-elevation model edge;
- layer-1 UZF is absent beneath fixed LAK footprints;
- post-dam BDA K/K33 changes are limited to the intended under-dam band.

The pre-dam “Effective BDA leakage footprint” panel is blank by design. The
post-dam footprint is a narrow K/K33 treatment zone; it is not the lakebed
coupling footprint.

### 4. Check for an existing model process

```zsh
pgrep -fl 'build_bdam_simulation.py|mf6' || true
```

Do not start a second run if another real BDam Python or `mf6` process is
active. Decide whether to wait or stop it; never terminate someone else's run
without authorization.

### 5. Run and log the model

```zsh
mkdir -p ../staging
set -o pipefail
MPLCONFIGDIR=../matplotlib-cache PYTHONUNBUFFERED=1 \
  python3 build_bdam_simulation.py ModelInput \
  --staging-root ../staging 2>&1 | tee ../model_runner.log
```

The default sequence is one 7-day relaxation at September--November-average
forcing, one fall-average spinup year, one monthly spinup year, one weekly spinup year, one
monitored pre-dam year, and one monitored post-dam year. The relaxation runs
only when at least one fall-average spinup year is configured, and its final
groundwater, lake, and UZF state initializes the fall-average year. A quiet
terminal is normal because MF6 output is captured. Live progress is written to
`bdam.lst` in the active directory under `../staging`.

Each fall-average spinup year is exactly one 365-day stress period, one MODFLOW
time step, and one saved endpoint. Each monthly year has 12 periods/steps and
each weekly year has 52 periods/steps. Therefore a 1/1/1 spinup has 1, 12, and
52 saved stage endpoints; a 2/1/1 spinup has 2, 12, and 52. Do not subdivide a
spinup stage unless the user explicitly requests sub-steps.

For an initial-condition diagnostic, append `--stop-after-monthly-spinup` to
the Python command. It completes the configured annual and monthly spinup,
writes validated spinup outputs, and stops before weekly spinup and monitored
years. A monthly spinup year must be configured. Omit the flag for a full run;
the runner preserves the diagnostic outputs in its usual timestamped backup.

The runner uses robust MF6 `COMPLEX` settings for the relaxation from
planar initial conditions and for only the first 365-day annual solve.
That annual solve uses the `conservative` profile. Every remaining staged
spinup and monitored solve returns to the faster `balanced` profile and its
`MODERATE` preset, always with the same strict convergence tolerances. With no
spinup, the first monitored annual solve is conservative and later solves are
balanced. The runner prevents conservative settings from being selected for
the whole workflow. Add
`--solver-inner-output` only when detailed inner-iteration diagnostics are
needed.

On the packaged benchmark, the 20-wave balanced production solves took about
68--72 seconds instead of 129--135 seconds and reduced MF6's reported
allocation from roughly 11 GB to 286--289 MB. Runtime varies by computer.

### 6. Confirm completion

A successful default run contains:

```text
Runs/spinup/initial_relaxation/
Runs/spinup/first_annual/
Runs/spinup/staged/
Runs/pre_dam/year_01/
Runs/post_dam/year_01/
Runs/spinup_summary.csv
Runs/weekly_summary.csv
```

Each completed workspace must have normal termination, nonempty groundwater,
LAK, and UZF binary outputs, the configured final saved time, and
`bdam.water_balance.json` with `"status": "pass"`, and
`bdam.solver_stats.json` with normal termination. The runner enforces these
requirements before publishing a workspace.

The Results Viewer intentionally starts the Spinup timeline with the
post-relaxation state in `Runs/spinup/first_annual`, continues through
`Runs/spinup/staged`, and keeps the separately validated `initial_relaxation`
workspace available for audit.

## Graphical terrain application

Run this from MATLAB while the package directory is current:

```matlab
LaunchBDamTerrainApp
```

The application uses the same terrain builders and default values as
`MakeGrid.m`. It is useful for visual exploration and can export a MAT
geometry file or portable ZIP. The scripted workflow remains the reproducible
model-building path. Once settings are accepted, place them in
`MakeGrid.m` and run the three standard build commands.

## Graphical results viewer

After a run is complete and all result files are closed, open the viewer from
MATLAB while the package directory is current:

```matlab
LaunchBDamResultsViewerApp
```

The default field is `../BDam_out` relative to the package. Launching or
browsing only selects a folder; click Load before any output is read. To
preselect another run, pass its complete output root:

```matlab
LaunchBDamResultsViewerApp("/absolute/path/to/completed/BDam")
```

The root must contain `Geometry/BDamGeometry.mat` and `Runs/`, including the
monitored summary CSV and each completed workspace's `bdam.ic`, `bdam.hds`,
and `monitoring_targets.csv`. Spinup outputs are required only when at least
one spinup year was configured. The viewer never writes to these outputs.

The upper panel shows the complete selected monitoring series and a moving
current-time line. Any number of variables may be selected, but they may use
at most two unit families; the viewer assigns those families to the left and
right y-axes. Head-monitor locations are always shown on the lower map, and
selected head monitors are highlighted and optionally labeled.

The lower-panel assignment matrix has rows for signed depth to groundwater
and groundwater water-surface elevation, with columns for Color raster and
Contours. Exactly one raster quantity is always selected, while contours are
optional. Each column accepts at most one quantity, and selecting a conflicting
cell swaps assignments automatically. Depth is calculated as land elevation
minus the uppermost valid groundwater head.

Negative depth indicates head above land surface. Color and contour limits are
held fixed across the selected scope so animation frames remain comparable.
Use the scope menu to view Spinup, Monitored pre/post, or All phases; the All
timeline offsets monitored results by the final spinup time. With zero spinup,
the Spinup scope is omitted and All matches the monitored timeline. Frame zero
shows the actual initial condition from `bdam.ic`, followed by one frame for
each saved end-of-step head; a 52-week simulation therefore has 53 frames.
The slider,
previous/next buttons, playback rate, Play/Pause button, and Loop option all
operate on saved MF6 head times. The Transpose map axes option places Y on the
horizontal axis and X on the vertical axis without changing model data. It is
selected automatically when the domain's Y span exceeds its X span so long,
narrow domains fill the lower plot more effectively.

Load also preprocesses every unique saved head frame into an in-memory
groundwater-surface cube. The status panel reports the resulting cache size;
animation then uses array indexing rather than rereading `bdam.hds`. A 512 MiB
limit prevents unexpectedly large allocations. Runs above that limit remain
usable through indexed on-demand reads and display a performance warning. The
viewer does not create cache files or alter the selected output folder.

## Inputs the user selects

Every editable model-preparation input is near the top of either
`MakeGrid.m` or `MakeInputs.m`. Inputs marked “conditional” are
required only when that option is selected.

### Geometry: vector constants in `MakeGrid.m`

Each vector contains two values. For nested channel sections, the order is
lower section followed by upper section. For transverse floodplain slopes, the
order is left side followed by right side.

| Input | Default | Units | Engineering meaning and requirement |
|---|---:|---|---|
| `bottom_widths_m` | `[2 10]` | m | Bottom width of the lower and upper trapezoidal channel sections; positive |
| `depths_m` | `[1 1]` | m | Depth of each nested section; positive |
| `left_side_slopes` | `[0.25 1.5]` | m/m | Horizontal run per unit rise on the left side; positive |
| `right_side_slopes` | `[0.5 2.5]` | m/m | Horizontal run per unit rise on the right side; positive |
| `transverse_slopes` | `[0.01 0.02]` | m/m | Floodplain rise away from the outer banks on left and right sides |

### Geometry: scalar constants in `MakeGrid.m`

| Input | Default | Units | Engineering meaning and requirement |
|---|---:|---|---|
| `vertical_offset_m` | 0.25 | m | Floodplain step above the outer channel banks; nonnegative |
| `dam_max_m` | 1.5 | m | BDA crest height above the sampled dam toe; nonnegative |
| `domain_length_x_m` | 50 | m | Transverse domain width; positive and divisible by `spacing_x_m` |
| `domain_length_y_m` | 100 | m | Projected channel-reach length; positive and divisible by `spacing_y_m` |
| `spacing_x_m` | 1 | m | X cell width; positive |
| `spacing_y_m` | 1 | m | Y cell width; positive |
| `origin_x_m` | 0 | m | Minimum-X domain-edge coordinate |
| `origin_y_m` | 0 | m | Minimum-Y domain-edge coordinate |
| `sine_periods` | 1 | periods | Number of centerline meander periods; zero or a multiple of 0.5 |
| `sine_amplitude_m` | 5 | m | Lateral centerline amplitude; sign mirrors the meander |
| `regional_longitudinal_slope` | 0.005 | m/m | Regional ground-surface rise along the longitudinal coordinate |
| `channel_longitudinal_slope` | 0.0025 | m/m | Channel-bed rise per meter of centerline distance |
| `dam_relative_distance_upstream` | 0.25 | fraction | Dam station measured upstream from the downstream end; between 0 and 1 |

Regional and channel slopes must have the same sign, or both must be zero.
The meander plus outer channel width must fit inside the X domain.

### Model-control and aquifer constants in `MakeInputs.m`

| Input | Default | Units | Engineering meaning and requirement |
|---|---:|---|---|
| `time_resolution` | `"weekly"` | choice | `"weekly"` gives 52 periods/year; `"daily"` gives 365 |
| `source_geometry_file` | packaged geometry path | path | MAT file created by `MakeGrid.m` |
| `longitudinal_direction` | `"y"` | choice | Axis used to locate upstream/downstream boundaries; normally Y |
| `model_bottom_offset` | 5.0 | m | Model bottom below the lowest land-surface cell; positive |
| `n_layers` | 10 | count | Number of groundwater layers; positive integer |
| `layer_growth_factor` | 1.35 | ratio | Deeper-to-shallower thickness growth; at least 1 |
| `hydraulic_conductivity_mode` | `"constant"` | choice | `"constant"`, `"by_layer"`, or `"hydrofacies_points"` |
| `specific_yield` | 0.20 | fraction | Drainable water from unconfined storage; between 0 and 1 |
| `specific_storage` | 1.0e-5 | 1/m | Elastic storage per unit aquifer thickness; positive |
| `effective_porosity` | 0.25 | fraction | Used for saturated groundwater-volume calculations; greater than 0 and at most 1 |
| `K_constant` | 0.03 | m/day | Uniform horizontal hydraulic conductivity in constant mode; positive |
| `K33_constant` | 0.003 | m/day | Uniform vertical hydraulic conductivity in constant mode; positive |

Hydraulic conductivity is the most important calibration group for
groundwater response. Do not treat the defaults as measured values.

### Conditional aquifer vectors and tables

| Input | Used when | Required form |
|---|---|---|
| `K_by_layer_top_to_bottom` | mode is `"by_layer"` | One positive m/day value per layer, ordered top to bottom |
| `K33_by_layer_top_to_bottom` | mode is `"by_layer"` | One positive m/day value per layer, ordered top to bottom |
| `hydrofacies_points_file` | mode is `"hydrofacies_points"` | Path to a nonempty CSV, or leave empty and provide `hydrofacies_points` |
| `hydrofacies_points` | mode is `"hydrofacies_points"` | MATLAB table with `x_m`, `y_m`, `z_top_m`, `z_bottom_m`, `hydrofacies_id` |
| `hydrofacies_fallback_id` | mode is `"hydrofacies_points"` | Class assigned where no supplied vertical interval matches |
| `hydrofacies_class_properties` | mode is `"hydrofacies_points"` | Table with `hydrofacies_id`, `K_m_per_day`, `K33_m_per_day`; every resulting ID must appear |

For point-based hydrofacies, the model assigns each cell center to the nearest
horizontal point whose vertical interval contains that center. This is a
nearest-point classification, not geostatistical interpolation.

### Surface-water and downstream-boundary constants

| Input | Default | Units | Engineering meaning and requirement |
|---|---:|---|---|
| `channel_half_width_cells` | 1 | cells | Adds this many cells on each side of each cross-section's DEM minimum |
| `lakebed_thickness_m` | 0.25 | m | Effective thickness controlling vertical LAK–groundwater leakage; positive |
| `lakebed_vertical_k_m_per_day` | 0.05 | m/day | Effective lakebed vertical K; positive |
| `ghb_k_mean_m_per_day` | `K_constant` | m/day | K used in downstream GHB conductance `C = K A/L`; positive |
| `downstream_control_distance_in_domain_lengths` | 1.0 | ratio | External control distance divided by modeled reach length; positive |
| `downstream_water_surface_slope_m_per_m` | -0.005 | m/m | External water-surface gradient in downstream flow direction |
| `downstream_control_base_depth_m` | 0.10 | m | Downstream control depth above local channel bed at minimum flow |
| `rating_curve_stage_range_m` | 0.50 | m | Difference between low- and high-flow control stages; positive |
| `rating_curve_exponent` | 0.60 | exponent | Shape of synthetic stage–flow relation; positive |
| `forcing_interpolation` | `"STEPWISE"` | choice | MODFLOW time-series interpolation; retain stepwise for period means |
| `pre_dam_outlet_width_m` | 1.0 | m | Effective width of the downstream sharp-weir outlet; positive |
| `post_dam_weir_width_m` | 2.0 | m | Effective active width of the BDA crest transfer; positive |

Lakebed leakance passed to MODFLOW is
`lakebed_vertical_k_m_per_day / lakebed_thickness_m`. The default is
`0.05 / 0.25 = 0.2 day^-1`.

### Forcing constants and vectors

| Input | Default or form | Units | Meaning and requirement |
|---|---:|---|---|
| `pullman_monthly_precipitation_mm` | 12 monthly totals | mm/month | January–December precipitation; all values nonnegative |
| `synthetic_mean_streamflow_m3_per_day` | 86.4 | m3/day | Annual mean upstream inflow used to scale the hydrograph shape |
| `usgs_hydrograph_file` | packaged CSV | path | Exactly 365 rows with `day_of_year` and positive `normalized_flow_factor` |
| `synthetic_mean_land_et_m_per_day` | 0.0020 | m/day | Annual duration-weighted mean land ET |
| `synthetic_land_et_monthly_factor` | 12 factors | relative | January–December ET shape; normalized internally |
| `synthetic_recharge_fraction_of_precipitation` | 0.18 | fraction | Precipitation fraction available as effective land recharge |
| `synthetic_recharge_monthly_factor` | 12 factors | relative | January–December seasonal recharge weighting |
| `synthetic_lake_evaporation_fraction_of_land_et` | 0.85 | fraction | Converts land ET series into lake evaporation series |

The source climatologies are entered in January–December order and rotated
internally to an October–September water year. Weekly values are exact
duration-weighted means; they are not simple seven-row averages at the year
boundary.

Required hydrograph CSV structure:

```csv
day_of_year,normalized_flow_factor
1,0.95
2,0.87
...
365,0.90
```

The factors are normalized internally to a mean of one, then multiplied by
`synthetic_mean_streamflow_m3_per_day`.

### UZF soil, initial-state, and run-duration constants

| Input | Default | Units | Meaning and requirement |
|---|---:|---|---|
| `uzf_thtr` | 0.05 | water fraction | Residual water content |
| `uzf_thts` | 0.25 | water fraction | Saturated water content |
| `uzf_thti` | 0.15 | water fraction | Initial UZF water content; between residual and saturated |
| `uzf_eps` | 3.5 | exponent | Brooks–Corey unsaturated-flow exponent |
| `uzf_surfdep_m` | 0.05 | m | Surface depression depth before rejected infiltration |
| `uzf_extdp_m` | 1.0 | m | ET extinction depth |
| `uzf_extwc` | 0.10 | water fraction | ET extinction water content; not below residual content |
| `uzf_ntrailwaves` | 7 | count | UZF trailing-wave numerical capacity |
| `uzf_nwavesets` | 20 | count | UZF wave-set numerical capacity; increase to 40 if MF6 reports insufficient capacity |
| `external_weir_invert_depth_m` | 0.05 | m | External LAK outlet invert below time-zero downstream stage |
| `initial_head_channel_offset_m` | 0.1 | m | Initial plane above the lowest channel cell at the downstream grid edge |
| `initial_head_regional_slope_m_per_m` | from geometry | m/m | Automatically exported signed regional slope; initial plane is constant transversely |
| `fall_average_spinup_years` | 1 | years | Constant September--November-average forcing spinup years |
| `monthly_spinup_years` | 1 | years | Monthly-climatology spinup years |
| `weekly_spinup_years` | 1 | years | Weekly-climatology spinup years |
| `pre_dam_years` | 1 | years | Monitored pre-dam years |
| `post_dam_years` | 1 | years | Monitored post-dam years; zero gives a no-dam monitored run |

All year counts are nonnegative integers, and at least one monitored pre- or
post-dam year is required. Do not add hidden spinup or extra MODFLOW time steps
to resolve convergence problems.

`uzf_ntrailwaves` and `uzf_nwavesets` must be positive integers. They control
UZF numerical capacity rather than soil physics. If MF6 specifically reports
that `NWAVESETS` must be increased, change the value from 20 to 40 in
`MakeInputs.m`, regenerate the paired handoffs, and rerun. Increase it further
only if the same MF6 error recurs. The workflow does not change this value
automatically.

### BDA treatment constants

| Input | Default | Units | Meaning and requirement |
|---|---:|---|---|
| `leakage_half_width_cells` | 1 | cells | Half-width of the channel-centered under-dam property band |
| `leakage_n_top_layers` | 3 | layers | Number of shallow groundwater layers receiving BDA multipliers |
| `k_multiplier` | 5.0 | ratio | Horizontal K multiplier inside the BDA treatment mask |
| `k33_multiplier` | 5.0 | ratio | Vertical K multiplier inside the BDA treatment mask |
| `dam_line_sample_spacing_m` | empty | m | Dam-toe sampling interval; empty uses one-quarter of minimum grid spacing |
| `stage_table_rows` | 81 | rows | Resolution of post-dam stage–area–volume table; at least 3 |
| `max_lake_extent_height_above_weir_m` | 0.50 | m | Highest connected upstream footprint represented above crest |
| `initial_depth_above_dam_toe_m` | 1.0 | m | Initial post-dam upstream water depth; between zero and crest height |

The BDA leakage mask changes aquifer K and K33. It does not switch LAK–GWF
coupling on or off. Every fixed lake-footprint cell receives a separate
vertical LAK connection controlled by lakebed K and thickness.

## Derived fields required by the model

The following data are required by the Python runner, but they are derived by
MATLAB rather than manually entered. They are stored in paired HDF5 handoffs.

### Derived scalar constants and feature constants

| Group | Examples | Derived from |
|---|---|---|
| Grid constants | `dx_m`, `dy_m`, domain length | Geometry dimensions and spacing |
| Calendar constants | water-year start month/day | Fixed October 1 convention |
| Lake constants | lake count, initial stage, lakebed thickness and K | Lake masks, terrain, and user constants |
| Dam constants | crest elevation, maximum represented stage | Geometry and BDA settings |
| Boundary constants | downstream control distance | Domain length and distance multiplier |
| MF6 constants | UZF parameters, head controls, phase-year counts | User-selected `mf6_parameters` |

### Derived vectors, tables, and connectivity lists

| Group | Contents | Purpose |
|---|---|---|
| Calendar vectors | `perlen_days`, `nstp` | Stress-period length and one time step per period |
| Rating curve | flow and downstream-control stage | Converts inflow to external control stage |
| Lake connections | X index, Y index, native layer for every lake cell | Defines vertical LAK–GWF connections |
| Stage–area–volume table | stage, area, and volume | Represents upstream impoundment storage |
| Outlet widths | pre-dam external and post-dam transfer/outlet widths | LAK sharp-weir controls |
| GHB cell table | indices, conductance, path length | Defines downstream groundwater boundary |
| Monitoring table | requested coordinates, resolved indices, layer | Defines head observations and cross-dam diagnostics |
| Dam endpoints | two XY points | Divides upstream and downstream zones |

### Derived 2-D scalar fields

All have MATLAB shape `[nx,ny]` unless noted.

| Field | Meaning |
|---|---|
| `X`, `Y` | Horizontal cell-center coordinates |
| `ZTop` | Land-surface and groundwater-model top elevation |
| `ZBot` | Groundwater-model bottom elevation |
| `channel_mask` | Channel cells based on each cross-section's local terrain minimum |
| Lake footprint masks | Fixed cells connected vertically to each LAK feature |
| `BDA_LEAKAGE_FOOTPRINT` | Plan-view under-dam K/K33 treatment cells; post-dam only |
| Upstream/downstream masks | Validation and cross-dam flow zones |
| Land/lake atmosphere masks | Exclusive assignment of UZF versus LAK atmospheric forcing |
| UZF start-layer map | First eligible UZF layer at each horizontal cell |

### Derived 3-D tensor fields

These have MATLAB shape `[nx,ny,n_layers]`, except `Z`, which has
`n_layers + 1` interfaces.

| Field | Meaning |
|---|---|
| `Z` | Bottom-to-top layer-interface elevations |
| `ZCell` | Cell-center elevation in every groundwater layer |
| `K_background`, `K33_background` | Pre-treatment horizontal and vertical conductivity |
| `K`, `K33` | Scenario conductivity after any BDA multipliers |
| `Sy`, `Ss` | Specific-yield and specific-storage tensors |
| `Porosity` | Effective-porosity tensor |
| `BDA_LEAKAGE_MASK` | Three-dimensional under-dam treatment zone |
| Downstream GHB mask | Groundwater cells assigned to the external boundary |
| UZF eligibility mask | Layers allowed to contain UZF features |

### Derived time series and time-dependent matrices

| Series | Units | Spatial form |
|---|---|---|
| `time_days` | days | Common period-edge vector |
| Upstream inflow | m3/day | One series entering Lake 1 |
| Land recharge/infiltration | m/day | Applied by UZF over land cells only |
| Land ET | m/day | Applied by UZF over land cells only |
| Lake precipitation | m/day | Applied by LAK over fixed lake footprints only |
| Lake evaporation | m/day | Applied by LAK over fixed lake footprints only |
| Downstream control stage | m | One external surface-water control series |
| GHB reference heads | m | Matrix with one row per GHB cell and one column per period edge |

RCH and EVT packages are intentionally prohibited. Atmospheric water is
partitioned between UZF land cells and LAK cells so precipitation, recharge,
ET, and evaporation are not counted twice.

## Which file should be changed?

| Desired change | Source file(s) | Regeneration required |
|---|---|---|
| Domain size, cell spacing, cross section, meander, terrain slopes, dam station or height | `MakeGrid.m`; synchronize `BDamTerrainApp.m` if changing defaults | Geometry, both handoffs, full run |
| Aquifer layers, K, K33, storage, porosity, lakebed, boundaries, forcing, UZF, run years | User-defined section of `MakeInputs.m` | Both handoffs and full run |
| Hydrograph shape | Referenced 365-row CSV | Both handoffs and full run |
| New derived MATLAB field | `MakeInputs.m` and usually `ExportPreparationForFloPy.m` | Both handoffs; update Python/tests if consumed |
| New HDF5 handoff field | `ExportPreparationForFloPy.m` and `build_bdam_simulation.py` | Both handoffs, tests, full run |
| MODFLOW package construction or restart behavior | `build_bdam_simulation.py` | Tests and full run |
| New summary or diagnostic output | `build_bdam_simulation.py` | Tests and representative full run |
| Run procedure or completion rules | `README.md`, `AGENTS.md`, and this manual | Documentation review |

Never solve an input problem by editing an HDF5 handoff or a MODFLOW input
file. That breaks reproducibility and will be overwritten on regeneration.

## A practical workflow for changing the model

1. Write the engineering question in physical terms and identify the units.
2. Locate the owning source file using the table above.
3. Change the smallest set of user-facing inputs needed to represent the
   hypothesis.
4. Run `MakeGrid.m` if geometry changed.
5. Run `MakeInputs.m` and inspect every review figure and summary.
6. Check that the pre-dam and post-dam manifests have the expected grid shape,
   lake count, calendar, and forcing description.
7. Run the fast Python tests.
8. Make a clean, full model run on local storage.
9. Require all completion checks and passing water balances.
10. Compare summary CSVs and numerical outputs, not file timestamps or HDF5
    byte-for-byte identity.
11. Record the changed input, previous value, new value, units, evidence, and
    scientific reason.

Change one conceptual group at a time when possible. For example, calibrate
background K separately from lakebed leakance so their effects can be
distinguished.

## How to direct an AI agent to learn and modify the framework

Give the agent a bounded engineering objective and require it to learn the
data path before editing. A good starting instruction is:

> Read `AGENTS.md`, `README.md`, and `END_USER_QUICK_START.md` completely.
> Trace the requested input from its user-defined source through
> `MakeGrid.m` or `MakeInputs.m`, the exported HDF5 field, the
> FloPy/MODFLOW package, and the validated output. Report the current behavior
> and proposed source files before changing physical assumptions. Do not edit
> generated `Geometry`, `ModelInput`, or `Runs` files. Preserve the 365-day
> October–September calendar and one MODFLOW time step per forcing period.
> After an approved change, regenerate in order, run fast tests, perform the
> required local full run, and apply every completion check in `AGENTS.md`.

For a code-level change, ask the agent to answer these questions first:

1. Is this a user input, a derived MATLAB field, a handoff field, a MODFLOW
   package value, or an output diagnostic?
2. What are its units, dimensions, orientation, and valid range?
3. Is it shared by both scenarios or treatment-only?
4. What other fields are derived from it?
5. How will pre-dam/post-dam state transfer be affected?
6. What assertion, fast test, and full-run evidence will prove correctness?

### Required agent reading order

1. `AGENTS.md`: operational and completion rules.
2. `README.md`: package architecture and result interpretation.
3. This manual: user inputs and engineering meaning.
4. `MakeGrid.m`, `buildBDamCrossSection.m`, and `buildBDamTerrain.m` for
   geometry work.
5. The user-defined section and relevant helper in `MakeInputs.m` for
   physical-input work.
6. `ExportPreparationForFloPy.m` for the MATLAB-to-HDF5 contract.
7. `build_bdam_simulation.py` for orientation conversion, MODFLOW package
   construction, restart/state transfer, monitoring, and validation.
8. `test_bdam_workflow.py` for fast behavioral contracts.

An agent should not start by reading generated MODFLOW files and guessing
where a value came from. It should trace from the source parameter forward.

## Result files to inspect first

| File | What it answers |
|---|---|
| `Runs/weekly_summary.csv` or `daily_summary.csv` | How heads, lake stages, storage, and fluxes change before and after the BDA |
| `Runs/spinup_summary.csv` | Whether the staged initial-condition sequence is stabilizing |
| `bdam.water_balance.json` | Whether numerical and coupled-system water-balance checks pass |
| `bdam.solver_stats.json` | Solver profile, wave capacity, solve time, iteration totals, MF6 version, and reported memory allocation |
| `bdam.solver.outer.csv` | Compact outer-iteration convergence history |
| `bdam.heads.csv` | Groundwater heads at named monitoring locations |
| `bdam.lake_fluxes.csv` | LAK stage, storage, outlets, and native lake observations |
| `bdam.ghb_flux.csv` | Total exchange at the downstream groundwater boundary |
| `bdam.fluxes.csv` | Comparable external fluxes, storage changes, lake–groundwater exchange, and cross-dam groundwater flow |
| `bdam.hds` | Full binary groundwater-head field for maps and sections |
| `bdam.cbc` | Full groundwater cell-budget data |
| `bdam.lak.stage`, `bdam.lak.bud` | Binary lake stages and lake budgets |
| `bdam.uzf.wc`, `bdam.uzf.bud` | Unsaturated-zone water content and budget |

Start with the summary CSV and water-balance JSON. Use large binary files only
when spatial detail is needed.

## Interpretation cautions

- A normal MODFLOW termination line is necessary but not sufficient. Require
  all validated outputs and passing water-balance JSON.
- The default forcing and many material properties are synthetic assumptions,
  not a site calibration.
- Weekly mode cannot resolve transients much shorter than about seven days.
  Use daily mode when short pond-filling or drawdown behavior matters.
- Fixed maximum LAK footprints remain connected to groundwater and excluded
  from layer-1 UZF even when some cells are above the current lake stage.
- The BDA leakage mask changes shallow aquifer K and K33; it is not the LAK
  coupling mask.
- Pre-dam output uses one river LAK. Its exchange is divided at the reference
  dam line in summaries so Lake 1/Lake 2 columns remain comparable across the
  dam-installation transition.
- At installation, groundwater heads are preserved, common UZF water content
  is mapped by cell, and both post-dam lakes inherit the final pre-dam river
  stage.
- Existing nonempty `Runs` are renamed to a timestamped backup rather than
  overwritten. Repeated runs can consume substantial disk space.

## Minimum documentation for a defensible case

For every scenario or calibration trial, record:

| Item | Minimum documentation |
|---|---|
| Objective | Engineering question and comparison being tested |
| Package identity | Archive name, checksum or version, and extraction path |
| Geometry | Domain, grid spacing, cross section, meander, slopes, and dam geometry |
| Aquifer | Layering, K/K33 method, Sy, Ss, porosity, and data sources |
| Surface water | Channel width rule, lakebed thickness/K, outlet widths, dam settings |
| Boundaries | GHB location, path length, K, stage slope, and rating-curve assumptions |
| Forcing | Hydrograph source, scaling, precipitation, ET, recharge, and water-year alignment |
| Initial state and spinup | Head assumptions and years in each spinup stage |
| Software | MATLAB, Python, FloPy, h5py, NumPy, and MODFLOW versions |
| Validation | Fast-test result, termination checks, final saved times, water-balance status |
| Results | Absolute output path, summary files, warnings, and retained diagnostic workspace |
| Change history | Old/new value, units, reason, evidence, and person or agent making the change |

This record is as important as the numerical output. It makes the model
reviewable, repeatable, and suitable for engineering discussion.
