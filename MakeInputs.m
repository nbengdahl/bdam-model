%% Weekly pre-/post-dam BDA preparation and HDF5 export
% Run MakeGrid.m first. This script reads its versioned geometry database
% and writes paired FloPy inputs below ModelInput/pre_dam and ModelInput/post_dam.
% Native array convention: [x, y, layer], with layer index nz at the top.

clearvars
close all
clc

%% 1. USER-DEFINED PARAMETERS -- every editable input is marked #User_Defined
time_resolution = "weekly";       % #User_Defined: "weekly" or "daily"
script_root = fileparts(mfilename("fullpath"));
source_geometry_file = fullfile(script_root,"Geometry","BDamGeometry.mat"); % #User_Defined: MakeGrid output
longitudinal_direction = "y";     % #User_Defined: direction from upstream to downstream control

% Grid and aquifer geometry [m].  The bottom follows the DEM's mean
% longitudinal slope; layer thickness grows geometrically with depth.
model_bottom_offset = 5.0;         % #User_Defined: [m] below lowest DEM cell
n_layers = 10;                     % #User_Defined: groundwater layer count
layer_growth_factor = 1.35;        % #User_Defined: deeper/top layer-thickness ratio

% Background aquifer properties.  Values are transparent first-pass values,
% not field calibration.  All values are SI-compatible with meters and days.
hydraulic_conductivity_mode = "constant"; % #User_Defined: "constant", "by_layer", "hydrofacies_points"
specific_yield = 0.20;             % #User_Defined: [-]
specific_storage = 1.0e-5;         % #User_Defined: [1/m]
effective_porosity = 0.25;         % #User_Defined: [-], saturated groundwater-volume calculation
K_constant = 0.03;                 % #User_Defined: [m/day], current horizontal validation baseline
K33_constant = 0.003;              % #User_Defined: [m/day], current vertical validation baseline
K_by_layer_top_to_bottom = 0.03 * ones(1, n_layers); % #User_Defined: [m/day], used only by_layer mode
K33_by_layer_top_to_bottom = 0.003 * ones(1, n_layers); % #User_Defined: [m/day], used only by_layer mode
hydrofacies_points_file = "";      % #User_Defined: optional CSV, used only hydrofacies_points mode
hydrofacies_points = table();       % #User_Defined: optional in-script interval table
hydrofacies_fallback_id = 1;        % #User_Defined: class ID outside supplied intervals
hydrofacies_class_properties = table(1, 0.03, 0.003, ...
    VariableNames=["hydrofacies_id", "K_m_per_day", "K33_m_per_day"]); % #User_Defined: class-property lookup

% Surface-water, UZF, and external-boundary definition.  These are prepared
% here for review, not yet passed to FloPy.
channel_half_width_cells = 1;       % #User_Defined: channel cells each side of local DEM minimum
lakebed_thickness_m = 0.25;         % #User_Defined: [m], effective vertical lakebed thickness
lakebed_vertical_k_m_per_day = 0.05; % #User_Defined: [m/day], effective lakebed K
ghb_k_mean_m_per_day = K_constant;  % #User_Defined: [m/day], fixed K_mean in C=K_mean*A/L
downstream_control_distance_in_domain_lengths = 1.0; % #User_Defined: control/GHB distance = this * domain length
downstream_water_surface_slope_m_per_m = -0.005; % #User_Defined: stage gradient in the downstream flow direction [m/m]
downstream_control_base_depth_m = 0.10; % #User_Defined: [m], stage above local channel bed at zero flow
rating_curve_stage_range_m = 0.50; % #User_Defined: [m], annual low-to-high control-stage range
rating_curve_exponent = 0.60;      % #User_Defined: h proportional to normalized Q^exponent
forcing_interpolation = "STEPWISE"; % #User_Defined: MF6 time-series interpolation convention

% Synthetic Pullman/Rose Creek-area climatology. NOAA Pullman 2 NW 1991--2020
% precipitation normals underpin the monthly totals. Streamflow timing uses a
% cached USGS climatological shape; its imposed mean, ET, recharge, and lake
% evaporation remain explicitly synthetic assumptions for review.
pullman_monthly_precipitation_mm = [67.8;49.3;52.1;49.8;46.0;31.0;11.2;12.2;16.5;45.7;66.5;70.4]; % #User_Defined: NOAA normal-derived [mm/month]
synthetic_mean_streamflow_m3_per_day = 86.4; % #User_Defined: assumed 1 L/s mean small-stream inflow
usgs_hydrograph_file = fullfile(script_root,"usgs_13348000_hydrograph.csv"); % #User_Defined: normalized USGS-shaped 365-day climatology
synthetic_mean_land_et_m_per_day = 0.0020; % #User_Defined: assumed annual mean land ET (730 mm/year)
synthetic_land_et_monthly_factor = [0.18;0.22;0.40;0.70;1.10;1.55;1.80;1.60;1.20;0.70;0.35;0.20]; % #User_Defined: warm-season ET maximum
synthetic_recharge_fraction_of_precipitation = 0.18; % #User_Defined: assumed effective land recharge fraction
synthetic_recharge_monthly_factor = [1.20;1.20;1.10;1.00;0.85;0.60;0.25;0.25;0.45;0.85;1.10;1.20]; % #User_Defined: snow/wet-season recharge weighting
synthetic_lake_evaporation_fraction_of_land_et = 0.85; % #User_Defined: assumed open-water/land-ET conversion

% MF6-only soil, outlet, and numerical assumptions. These remain in MATLAB so
% the HDF5 handoff is the sole source of physical model inputs.
mf6_parameters = struct();
mf6_parameters.uzf_thtr = 0.05;    % #User_Defined: residual water content [-]
mf6_parameters.uzf_thts = 0.25;    % #User_Defined: saturated water content [-]
mf6_parameters.uzf_thti = 0.15;    % #User_Defined: initial water content [-]
mf6_parameters.uzf_eps = 3.5;      % #User_Defined: Brooks-Corey exponent [-]
mf6_parameters.uzf_surfdep_m = 0.05; % #User_Defined: surface depression depth [m]
mf6_parameters.uzf_extdp_m = 1.0; % #User_Defined: ET extinction depth [m]
mf6_parameters.uzf_extwc = 0.10;  % #User_Defined: ET extinction water content [-]
mf6_parameters.uzf_ntrailwaves = 7; % #User_Defined: MF6 UZF trailing-wave count
mf6_parameters.uzf_nwavesets = 20; % #User_Defined: MF6 UZF numerical wave-set capacity
mf6_parameters.external_weir_invert_depth_m = 0.05; % #User_Defined: below time-zero downstream control stage
mf6_parameters.initial_head_channel_offset_m = 0.25; % #User_Defined: initial water table above nearest channel bed [m]
mf6_parameters.initial_head_lateral_gradient_m_per_m = 0.02; % #User_Defined: initial water-table rise away from channel [m/m]
mf6_parameters.fall_average_spinup_years = 1; % #User_Defined: constant Sep--Nov-average forcing years, one step/year
mf6_parameters.monthly_spinup_years = 1; % #User_Defined: varying monthly-average forcing years
mf6_parameters.weekly_spinup_years = 1; % #User_Defined: varying weekly-average forcing years
mf6_parameters.pre_dam_years = 1; % #User_Defined: monitored annual years before dam installation
mf6_parameters.post_dam_years = 1; % #User_Defined: monitored annual years after dam installation; zero is a no-dam run

% Native LAK sharp-weir controls. MF6 WEIR uses invert and effective width;
% it does not expose a user discharge coefficient. Calibrate effective width.
pre_dam_outlet_width_m = 1.0;       % #User_Defined: [m], effective downstream outlet width
post_dam_weir_width_m = 2.0;        % #User_Defined: [m], assumed active BDA crest width

% Shared BDA representation settings. Dam orientation and crest height are
% inherited from MakeGrid's geometry database below.
dam_settings = struct();
dam_settings.leakage_half_width_cells = 1; % #User_Defined: BDA band half-width in channel cells
dam_settings.leakage_n_top_layers = 3; % #User_Defined: shallow layers with effective under-dam properties
dam_settings.k_multiplier = 5.0;   % #User_Defined: current horizontal under-dam multiplier
dam_settings.k33_multiplier = 5.0; % #User_Defined: current vertical under-dam multiplier
dam_settings.dam_line_sample_spacing_m = []; % #User_Defined: [] means min(dx,dy)/4
dam_settings.stage_table_rows = 81; % #User_Defined: stage-area-volume table rows
dam_settings.max_lake_extent_height_above_weir_m = 0.50; % #User_Defined: [m], required maximum connected pond extent above crest

%% 2. Post-dam initial water level
post_dam = struct();
post_dam.initial_depth_above_dam_toe_m = 1.0; % #User_Defined: [m] above sampled dam toe

%% 3. Load geometry and derive shared grid/layer/property fields
assert(any(time_resolution == ["weekly", "daily"]), "time_resolution must be weekly or daily.");
assert(any(longitudinal_direction == ["x", "y"]), "longitudinal_direction must be x or y.");
assert(n_layers >= 1 && mod(n_layers, 1) == 0 && layer_growth_factor >= 1, ...
    "n_layers must be a positive integer and layer_growth_factor must be >= 1.");
assert(model_bottom_offset > 0 && channel_half_width_cells >= 0 && ...
    mod(channel_half_width_cells, 1) == 0, "Invalid shared geometry parameter.");
assert(lakebed_thickness_m > 0 && lakebed_vertical_k_m_per_day > 0 && ...
    downstream_control_distance_in_domain_lengths > 0 && ghb_k_mean_m_per_day > 0, ...
    "Lakebed and GHB parameters must be positive.");
assert(all([mf6_parameters.fall_average_spinup_years, mf6_parameters.monthly_spinup_years, ...
    mf6_parameters.weekly_spinup_years] >= 0) && ...
    all(mod([mf6_parameters.fall_average_spinup_years, mf6_parameters.monthly_spinup_years, ...
    mf6_parameters.weekly_spinup_years], 1) == 0), ...
    "All staged spinup-year counts must be nonnegative integers.");
assert(mf6_parameters.initial_head_channel_offset_m >= 0 && ...
    mf6_parameters.initial_head_lateral_gradient_m_per_m >= 0, ...
    "Analytical initial-head offset and lateral gradient must be nonnegative.");
assert(mf6_parameters.uzf_ntrailwaves > 0 && ...
    mod(mf6_parameters.uzf_ntrailwaves, 1) == 0 && ...
    mf6_parameters.uzf_nwavesets > 0 && ...
    mod(mf6_parameters.uzf_nwavesets, 1) == 0, ...
    "UZF ntrailwaves and nwavesets must be positive integers.");
assert(mf6_parameters.pre_dam_years >= 0 && mod(mf6_parameters.pre_dam_years, 1) == 0 && ...
    mf6_parameters.post_dam_years >= 0 && mod(mf6_parameters.post_dam_years, 1) == 0, ...
    "pre_dam_years and post_dam_years must be nonnegative integers.");
assert(mf6_parameters.pre_dam_years + mf6_parameters.post_dam_years > 0, ...
    "At least one monitored pre- or post-dam year is required.");
assert(effective_porosity > 0 && effective_porosity <= 1, "Effective porosity must be in (0,1].");

input_geometry = load(source_geometry_file);
assert(isfield(input_geometry,"geometry_handoff") && ...
    string(input_geometry.geometry_handoff.schema_version) == "bdam-geometry-mat-v1", ...
    "Run MakeGrid.m first to create a bdam-geometry-mat-v1 database.");
assert(all(isfield(input_geometry, {'X', 'Y', 'dx', 'dy'})), ...
    "Geometry must contain X, Y, dx, and dy.");
assert(isfield(input_geometry,"parameters") && ...
    all(isfield(input_geometry.parameters, {'channel_longitudinal_slope', 'regional_longitudinal_slope'})), ...
    "Geometry must contain channel and regional longitudinal slopes.");
channel_longitudinal_slope = double(input_geometry.parameters.channel_longitudinal_slope);
regional_longitudinal_slope = double(input_geometry.parameters.regional_longitudinal_slope);
assert(isscalar(channel_longitudinal_slope) && isfinite(channel_longitudinal_slope) && ...
    isscalar(regional_longitudinal_slope) && isfinite(regional_longitudinal_slope) && ...
    sign(channel_longitudinal_slope) == sign(regional_longitudinal_slope), ...
    "Geometry longitudinal slopes must be finite scalars with matching directions.");
mf6_parameters.initial_head_upslope_reduction_m_per_m = ...
    0.5 * abs(channel_longitudinal_slope);
X = input_geometry.X; Y = input_geometry.Y; dx = input_geometry.dx; dy = input_geometry.dy;
if isfield(input_geometry, "ZTop")
    ZTop = input_geometry.ZTop;
elseif isfield(input_geometry, "Z")
    ZTop = squeeze(input_geometry.Z(:,:,end));
    fprintf("NOTE: Extracted ZTop from legacy Z; existing interfaces were intentionally ignored.\n");
else
    error("Geometry must contain ZTop (or legacy Z).");
end
[nx, ny] = size(ZTop);
assert(isfield(input_geometry,"post_dam") && isfield(input_geometry,"dam_settings"), ...
    "Geometry database is missing dam settings.");
post_dam.dam_endpoints_xy = input_geometry.post_dam.dam_endpoints_xy;
dam_settings.upstream_side = input_geometry.dam_settings.upstream_side;
dam_settings.crest_height_above_dam_toe_m = input_geometry.dam_settings.crest_height_above_dam_toe_m;
assert(isequal(size(X), size(Y), size(ZTop)) && dx > 0 && dy > 0, ...
    "X, Y, ZTop must have equal dimensions and dx/dy must be positive.");

[ZBot, average_longitudinal_slope] = makeBottomPlane(X, Y, ZTop, longitudinal_direction, model_bottom_offset);
total_model_thickness = ZTop - ZBot;
assert(min(total_model_thickness, [], "all") > 0, "Model bottom intersects top surface.");
Z = makeLayerInterfaces(ZTop, ZBot, n_layers, layer_growth_factor);
nz = n_layers;
ZCell = 0.5 * (Z(:,:,1:end-1) + Z(:,:,2:end));
[K_background, K33_background, hydrofacies_id] = makeProperties( ...
    hydraulic_conductivity_mode, K_constant, K33_constant, ...
    K_by_layer_top_to_bottom, K33_by_layer_top_to_bottom, hydrofacies_points_file, ...
    hydrofacies_points, hydrofacies_fallback_id, hydrofacies_class_properties, X, Y, ZCell);
Sy = specific_yield * ones(nx, ny, nz);
Ss = specific_storage * ones(nx, ny, nz);
Porosity = effective_porosity * ones(nx, ny, nz);
assert(specific_yield >= 0 && specific_yield <= 1 && specific_storage > 0, ...
    "Sy must be in [0,1] and Ss must be positive.");

% The channel is shared by both scenarios: local transverse DEM minimum plus
% a user-reviewed half width.  It defines the pre-dam LAK footprint.
channel_mask = makeChannelMask(ZTop, channel_half_width_cells);
reference_dam = makeDamDefinition(post_dam, dam_settings, X, Y, ZTop, dx, dy, nz);
[upstream_zone_mask, dam_distance] = damSideMask(X, Y, reference_dam.endpoint_1_xy, ...
    reference_dam.endpoint_2_xy, reference_dam.upstream_side);
downstream_zone_mask = ~upstream_zone_mask;
assert(all(xor(upstream_zone_mask, downstream_zone_mask), "all"), ...
    "Upstream/downstream validation zones must be mutually exclusive and exhaustive.");
monitoring = makeValidationMonitoring(X, Y, ZTop, channel_mask, upstream_zone_mask, ...
    downstream_zone_mask, reference_dam, longitudinal_direction, nz);

%% 4. Common time series, downstream control, and boundaries
calendar = makeCalendar(time_resolution);
forcing_time_days = [0; cumsum(calendar.perlen_days)];
forcing = makePullmanSyntheticForcing(forcing_time_days, ...
    pullman_monthly_precipitation_mm, synthetic_mean_streamflow_m3_per_day, usgs_hydrograph_file, ...
    synthetic_mean_land_et_m_per_day, ...
    synthetic_land_et_monthly_factor, synthetic_recharge_fraction_of_precipitation, ...
    synthetic_recharge_monthly_factor, synthetic_lake_evaporation_fraction_of_land_et, ...
    forcing_interpolation);

domain_length_m = domainLength(X, Y, longitudinal_direction);
ghb_external_flow_path_length_m = downstream_control_distance_in_domain_lengths * domain_length_m;
downstream_local_bed_elevation_m = downstreamChannelBedElevation(ZTop, longitudinal_direction);
rating_curve = makeSyntheticRatingCurve(downstream_local_bed_elevation_m, ...
    forcing.upstream_inflow_m3_per_day, downstream_control_base_depth_m, ...
    rating_curve_stage_range_m, rating_curve_exponent);
downstream_control_stage = ratingCurveStage(rating_curve, forcing.upstream_inflow_m3_per_day);
downstream_stage_timeseries = table(forcing_time_days, downstream_control_stage, ...
    VariableNames=["time_days", "stage_m_at_downstream_control"]);

% Downstream GHB cells occupy the outer longitudinal edge only. Their external
% flow-path length and hydraulic control location are exactly one domain length
% downstream by default (the #User_Defined multiplier above changes this).
[ghb_mask, ghb_table] = makeGhbInputs(X, Y, Z, K_background, ghb_k_mean_m_per_day, ...
    ghb_external_flow_path_length_m, downstream_water_surface_slope_m_per_m, ...
    downstream_stage_timeseries, longitudinal_direction, ghb_external_flow_path_length_m);
boundary_definition = struct();
boundary_definition.upstream_and_lateral = "NOFLOW";
boundary_definition.downstream = "GHB";
boundary_definition.downstream_ghb_mask = ghb_mask;
boundary_definition.ghb_cells = ghb_table;
boundary_definition.rating_curve = rating_curve;
boundary_definition.reference_head_timeseries = ghb_table.reference_head_timeseries;
boundary_definition.downstream_control_stage_timeseries = downstream_stage_timeseries;
boundary_definition.domain_length_m = domain_length_m;
boundary_definition.downstream_control_distance_m = ghb_external_flow_path_length_m;
boundary_definition.downstream_edge = downstreamEdgeDescription(ZTop, longitudinal_direction);

%% 5. Derive, review, and export both scenario handoffs
% Spinup is always run in the pre-dam state. The Python runner then advances
% the configured pre-dam and post-dam years in sequence using these two inputs.
for scenario_name = ["pre_dam", "post_dam"]
    K = K_background; K33 = K33_background;
    scenario = struct();
    scenario.name = scenario_name;
    scenario.shared_input_names = ["geometry", "layers", "background_properties", ...
        "channel_mask", "calendar", "forcing", "downstream_control", "boundary_conditions"];
    scenario.treatment_only_input_names = strings(0,1);

if scenario_name == "pre_dam"
    % The control is a single connected channel LAK.  Its initial level is the
    % common downstream rating-curve stage at time zero, not a dam-face value.
    control_stage_m = downstream_stage_timeseries.stage_m_at_downstream_control(1);
    pre_dam_mask = largestConnectedComponent(channel_mask);
    assert(any(pre_dam_mask, "all"), "The channel mask contains no connected pre-dam lake cells.");
    lakes = makeLakeDefinition("pre_dam_river", 1, pre_dam_mask, control_stage_m, ...
        ZTop, Z, dx, dy, lakebed_thickness_m, lakebed_vertical_k_m_per_day, []);
    outlets = table("pre_dam_river", "external", NaN, pre_dam_outlet_width_m, ...
        "pre_dam_external_weir", VariableNames=["provider_lake", "receiver", ...
        "invert_elevation_m", "width_m", "role"]);
    dam = emptyDamDefinition();
    BDA_LEAKAGE_FOOTPRINT = false(nx, ny);
    BDA_LEAKAGE_MASK = false(nx, ny, nz);
    lake_masks = struct("pre_dam_river", pre_dam_mask);
else
    dam = reference_dam;
    upstream_mask = upstream_zone_mask;
    upstream_lake_mask = connectedPondMask(ZTop, upstream_mask, dam_distance, dx, dy, dam.initial_stage_m);
    downstream_candidates = channel_mask & ~upstream_mask & ~dam.grid_mask;
    downstream_lake_mask = downstreamConnectedComponent(downstream_candidates, ZTop, longitudinal_direction);
    assert(any(upstream_lake_mask, "all"), "Post-dam initial stage creates no upstream connected lake cells.");
    assert(any(downstream_lake_mask, "all"), "Post-dam downstream lake mask is empty.");
    assert(~any(downstream_lake_mask & upstream_mask, "all"), ...
        "Downstream LAK contains cells on the upstream dam side.");
    assert(touchesDownstreamEdge(downstream_lake_mask, ZTop, longitudinal_direction), ...
        "Post-dam downstream lake is not connected to the downstream domain edge.");
    [stage_area_volume, stage_masks, maximum_lake_mask] = makeStageAreaVolume(ZTop, upstream_mask, dam_distance, dx, dy, dam);
    assert(~any(maximum_lake_mask & ~upstream_mask, "all"), ...
        "Upstream LAK contains cells on the downstream dam side.");
    assert(~any(maximum_lake_mask & downstream_lake_mask, "all"), ...
        "Maximum upstream and downstream LAK footprints overlap.");
    assert(any(ZTop(maximum_lake_mask) <= dam.initial_stage_m), ...
        "Upstream LAK has no cells wetted at its initial stage.");
    downstream_initial_stage = downstream_stage_timeseries.stage_m_at_downstream_control(1);
    assert(any(ZTop(downstream_lake_mask) <= downstream_initial_stage), ...
        "Downstream LAK has no cells wetted at its initial stage.");
    upstream_lake = makeLakeDefinition("upstream_impoundment", 1, maximum_lake_mask, ...
        dam.initial_stage_m, ZTop, Z, dx, dy, lakebed_thickness_m, lakebed_vertical_k_m_per_day, stage_area_volume);
    downstream_lake = makeLakeDefinition("downstream_river", 2, downstream_lake_mask, ...
        downstream_initial_stage, ZTop, Z, dx, dy, ...
        lakebed_thickness_m, lakebed_vertical_k_m_per_day, []);
    lakes = [upstream_lake, downstream_lake];
    outlets = table(["upstream_impoundment"; "downstream_river"], ...
        ["downstream_river"; "external"], [dam.crest_elevation_m; NaN], ...
        [post_dam_weir_width_m; pre_dam_outlet_width_m], ...
        ["post_dam_lak_weir_transfer"; "post_dam_external_outlet"], ...
        VariableNames=["provider_lake", "receiver", "invert_elevation_m", "width_m", "role"]);
    BDA_LEAKAGE_FOOTPRINT = channel_mask & dam_distance <= dam.leakage_half_width_cells * max(dx, dy);
    BDA_LEAKAGE_MASK = false(nx, ny, nz);
    top_native_layers = nz:-1:(nz - dam.leakage_n_top_layers + 1);
    BDA_LEAKAGE_MASK(:,:,top_native_layers) = repmat(BDA_LEAKAGE_FOOTPRINT, 1, 1, numel(top_native_layers));
    K(BDA_LEAKAGE_MASK) = K_background(BDA_LEAKAGE_MASK) * dam.k_multiplier;
    K33(BDA_LEAKAGE_MASK) = K33_background(BDA_LEAKAGE_MASK) * dam.k33_multiplier;
    assert(any(K(BDA_LEAKAGE_MASK) ~= K_background(BDA_LEAKAGE_MASK) | ...
        K33(BDA_LEAKAGE_MASK) ~= K33_background(BDA_LEAKAGE_MASK)), ...
        "Post-dam BDA hydraulic-property multipliers do not change any cells.");
    assert(all(K(~BDA_LEAKAGE_MASK) == K_background(~BDA_LEAKAGE_MASK), "all") && ...
        all(K33(~BDA_LEAKAGE_MASK) == K33_background(~BDA_LEAKAGE_MASK), "all"), ...
        "Post-dam hydraulic-property changes extend outside the BDA mask.");
    lake_masks = struct("upstream_impoundment_initial", upstream_lake_mask, "upstream_impoundment_maximum", maximum_lake_mask, ...
        "downstream_river", downstream_lake_mask, "upstream_stage_masks", stage_masks);
    scenario.treatment_only_input_names = ["post_dam lake geometry and routing", ...
        "BDA leakage-zone K and K33"];
end

all_lake_mask = false(nx, ny);
lake_connection_count = zeros(nx, ny);
for i_lake = 1:numel(lakes)
    all_lake_mask = all_lake_mask | lakes(i_lake).footprint_mask;
    lake_connection_count = lake_connection_count + double(lakes(i_lake).footprint_mask);
end
assert(all(lake_connection_count <= 1, "all"), ...
    "A groundwater cell is connected vertically to more than one LAK.");
uzf = makeUzfEligibility(all_lake_mask, nz);
% Atmospheric-flux rule: UZF is the only land recharge/ET pathway, while LAK
% is the only precipitation/evaporation pathway over lake footprints. RCH and
% EVT are intentionally prohibited to prevent duplicate atmospheric fluxes.
uzf.land_atmosphere_mask = ~all_lake_mask;
uzf.lake_atmosphere_mask = all_lake_mask;
assert(~any(uzf.land_atmosphere_mask & uzf.lake_atmosphere_mask, "all") && ...
    all(uzf.land_atmosphere_mask | uzf.lake_atmosphere_mask, "all"), ...
    "Land and lake atmospheric masks must be mutually exclusive and complete.");
assert(all(~uzf.eligible_mask(:,:,nz) | ~all_lake_mask, "all"), ...
    "Layer-1 UZF must be excluded at lake cells.");
if nz > 1
    assert(all(uzf.start_layer_number_top_down(all_lake_mask) == 2), ...
        "UZF below lake footprints must start in layer 2.");
else
    assert(all(isnan(uzf.start_layer_number_top_down(all_lake_mask))), ...
        "A one-layer model cannot host UZF below a layer-1 lake cell.");
end

%% 6. Reviewed output object for this scenario's FloPy adapter
preparation = struct();
preparation.metadata = struct("scenario", scenario_name, "units", "meters and days", ...
    "native_array_order", "[x,y,layer], top layer is nz", ...
    "floPy_export_status", "written_by_this_script");
preparation.parameters = struct("scenario", scenario, "post_dam", post_dam, "dam_settings", dam_settings, "mf6_parameters", mf6_parameters, ...
    "calendar", calendar, "forcing", forcing, "boundary_definition", boundary_definition);
preparation.grid = struct();
preparation.grid.X = X; preparation.grid.Y = Y; preparation.grid.dx_m = dx; preparation.grid.dy_m = dy;
preparation.grid.ZTop = ZTop; preparation.grid.ZBot = ZBot; preparation.grid.Z = Z; preparation.grid.ZCell = ZCell;
preparation.properties = struct();
preparation.properties.K = K; preparation.properties.K33 = K33;
preparation.properties.K_background = K_background; preparation.properties.K33_background = K33_background;
preparation.properties.Sy = Sy; preparation.properties.Ss = Ss; preparation.properties.hydrofacies_id = hydrofacies_id;
preparation.properties.Porosity = Porosity;
preparation.properties.BDA_LEAKAGE_FOOTPRINT = BDA_LEAKAGE_FOOTPRINT;
preparation.properties.BDA_LEAKAGE_MASK = BDA_LEAKAGE_MASK;
preparation.surface_water = struct();
preparation.surface_water.channel_mask = channel_mask; preparation.surface_water.lake_masks = lake_masks;
preparation.surface_water.lakes = lakes; preparation.surface_water.outlets = outlets; preparation.surface_water.dam = dam;
preparation.validation_zones = struct("upstream_mask", upstream_zone_mask, ...
    "downstream_mask", downstream_zone_mask, "reference_dam", reference_dam, ...
    "longitudinal_direction", longitudinal_direction);
preparation.uzf = uzf;
preparation.boundaries = boundary_definition;
preparation.monitoring = monitoring;
preparation.observation_targets = makeObservationTargets(scenario_name, lakes, outlets);

%% 7. Review figures and write this scenario handoff
makeReviewFigures(X, Y, ZTop, channel_mask, lakes, dam, BDA_LEAKAGE_FOOTPRINT, ...
    ghb_mask, uzf, monitoring, scenario_name);
makeForcingFigure(forcing);
printReviewSummary(preparation, calendar, downstream_water_surface_slope_m_per_m);
output_directory = fullfile(script_root,"ModelInput",scenario_name);
[h5_path,~] = ExportPreparationForFloPy(preparation,output_directory);
fprintf("BDam %s FloPy input written: %s\n",scenario_name,h5_path);
end

%% Local functions
function [ZBot, slope] = makeBottomPlane(X, Y, ZTop, direction, offset)
    [zmin, idx] = min(ZTop(:)); [i, j] = ind2sub(size(ZTop), idx);
    if direction == "y"
        coordinate = Y(1,:); profile = mean(ZTop, 1); reference = Y(i,j); coordinate_grid = Y;
    else
        coordinate = X(:,1)'; profile = mean(ZTop, 2)'; reference = X(i,j); coordinate_grid = X;
    end
    fit = polyfit(coordinate, profile, 1); slope = fit(1);
    ZBot = zmin - offset + slope .* (coordinate_grid - reference);
end

function Z = makeLayerInterfaces(ZTop, ZBot, n, growth)
    [nx, ny] = size(ZTop); fractions = growth .^ (0:n-1); fractions = fractions / sum(fractions);
    from_top = [0, cumsum(fractions)]; Z = zeros(nx, ny, n + 1); thickness = ZTop - ZBot;
    for ii = 1:n+1, Z(:,:,n + 2 - ii) = ZTop - from_top(ii) .* thickness; end
    Z(:,:,1) = ZBot;
end

function [K, K33, ids] = makeProperties(mode, kc, kvc, kb, kvb, point_file, points, fallback, classes, X, Y, ZCell)
    ids = fallback * ones(size(ZCell)); nz = size(ZCell,3);
    assert(any(mode == ["constant", "by_layer", "hydrofacies_points"]), "Unknown K mode.");
    switch mode
        case "constant"
            assert(kc > 0 && kvc > 0, "Constant K values must be positive."); K = kc * ones(size(ZCell)); K33 = kvc * ones(size(ZCell));
        case "by_layer"
            assert(numel(kb) == nz && numel(kvb) == nz && all(kb > 0) && all(kvb > 0), "Invalid by-layer K values.");
            K = zeros(size(ZCell)); K33 = K;
            for top = 1:nz, native = nz - top + 1; K(:,:,native) = kb(top); K33(:,:,native) = kvb(top); end
        case "hydrofacies_points"
            [ids, ~] = assignHydrofaciesToGrid(point_file, points, fallback, X, Y, ZCell);
            [K, K33] = mapHydrofaciesProperties(ids, classes);
    end
end

function mask = makeChannelMask(ZTop, half_width)
    [nx, ny] = size(ZTop); mask = false(nx, ny);
    for j = 1:ny
        [~, i] = min(ZTop(:,j)); mask(max(1,i-half_width):min(nx,i+half_width),j) = true;
    end
end

function calendar = makeCalendar(resolution)
    if resolution == "daily", perlen = ones(365,1); else, perlen = repmat(365/52, 52, 1); end
    % Each forcing period has exactly one MF6 time step. Weekly mode therefore
    % uses 52 seven-day solves, and daily mode uses 365 one-day solves.
    calendar = struct("resolution", resolution, "perlen_days", perlen, "nstp", ones(size(perlen)), ...
        "annual_duration_days", sum(perlen), "interpolation", "STEPWISE", ...
        "water_year_start_month", 10, "water_year_start_day", 1);
    assert(abs(calendar.annual_duration_days - 365) < eps(365), "Calendar must total exactly 365 days.");
end

function forcing = makePullmanSyntheticForcing(time, monthly_ppt_mm, mean_flow, hydrograph_file, ...
        mean_et, et_factor, recharge_fraction, recharge_factor, lake_evap_fraction, interpolation)
% Synthetic daily forcing representative of Pullman's wet cool season and dry,
% high-ET summer. It is intentionally not a site calibration dataset. The
% returned values are exact period averages, so a weekly MF6 period receives
% one average recharge, ET, precipitation, evaporation, and streamflow value.
    days_in_month = [31;28;31;30;31;30;31;31;30;31;30;31];
    assert(numel(monthly_ppt_mm) == 12 && numel(et_factor) == 12 && ...
        numel(recharge_factor) == 12 && all(monthly_ppt_mm >= 0) && mean_flow >= 0 && mean_et >= 0 && ...
        recharge_fraction >= 0 && lake_evap_fraction >= 0, "Invalid synthetic-forcing parameter.");
    hydrograph = readtable(hydrograph_file, TextType="string");
    assert(isequal(string(hydrograph.Properties.VariableNames), ["day_of_year","normalized_flow_factor"]) && ...
        height(hydrograph)==365 && isequal(hydrograph.day_of_year,(1:365)') && ...
        all(isfinite(hydrograph.normalized_flow_factor) & hydrograph.normalized_flow_factor>0), ...
        "USGS-shaped hydrograph must contain 365 positive day/factor rows.");
    flow_factor = hydrograph.normalized_flow_factor / mean(hydrograph.normalized_flow_factor);
    day_time = (0:364)'; month = monthIndex365(day_time);
    et_factor = normalizeMonthlyFactor(et_factor, days_in_month);
    precipitation_m_per_day_by_month = monthly_ppt_mm(:) / 1000 ./ days_in_month;
    daily_upstream_inflow = mean_flow * flow_factor;
    daily_land_et = mean_et * et_factor(month);
    daily_lake_precipitation = precipitation_m_per_day_by_month(month);
    daily_recharge = daily_lake_precipitation .* recharge_fraction .* recharge_factor(month);
    daily_lake_evaporation = lake_evap_fraction * daily_land_et;
    % Source climatologies are stored in January--December order. Model time
    % begins on October 1, so circularly rotate every time-varying input to an
    % October--September water year before aggregating daily/weekly periods.
    water_year_offset_days = sum(days_in_month(1:9));
    water_year_order = [water_year_offset_days + 1:365, 1:water_year_offset_days];
    daily_upstream_inflow = daily_upstream_inflow(water_year_order);
    daily_land_et = daily_land_et(water_year_order);
    daily_lake_precipitation = daily_lake_precipitation(water_year_order);
    daily_recharge = daily_recharge(water_year_order);
    daily_lake_evaporation = daily_lake_evaporation(water_year_order);
    upstream_inflow = averageDailySeries(daily_upstream_inflow, time);
    land_et = averageDailySeries(daily_land_et, time);
    lake_precipitation = averageDailySeries(daily_lake_precipitation, time);
    recharge = averageDailySeries(daily_recharge, time);
    lake_evaporation = averageDailySeries(daily_lake_evaporation, time);
    forcing = struct();
    forcing.time_days = time;
    forcing.upstream_inflow_m3_per_day = upstream_inflow;
    forcing.land_infiltration_m_per_day = recharge;
    forcing.land_et_m_per_day = land_et;
    forcing.lake_precipitation_m_per_day = lake_precipitation;
    forcing.lake_evaporation_m_per_day = lake_evaporation;
    forcing.interpolation = interpolation;
    forcing.calendar_basis = "October 1--September 30 water year";
    forcing.synthetic_source = "USGS 13348000 daily climatological flow shape scaled to 86.4 m3/day; Pullman precipitation and labeled synthetic atmospheric assumptions";
    forcing.hydrograph_file = hydrograph_file;
    forcing.monthly_precipitation_mm = monthly_ppt_mm(:);
    forcing.annual_precipitation_mm = sum(monthly_ppt_mm);
    duration = diff(time);
    forcing.mean_streamflow_m3_per_day = sum(upstream_inflow(1:end-1).*duration) / sum(duration);
    forcing.mean_land_et_m_per_day = sum(land_et(1:end-1).*duration) / sum(duration);
    forcing.mean_recharge_m_per_day = sum(recharge(1:end-1).*duration) / sum(duration);
    forcing.timeseries = table(time, upstream_inflow, recharge, land_et, lake_precipitation, lake_evaporation, ...
        VariableNames=["time_days", "upstream_inflow_m3_per_day", "land_recharge_m_per_day", ...
        "land_et_m_per_day", "lake_precipitation_m_per_day", "lake_evaporation_m_per_day"]);
end

function averages = averageDailySeries(daily_values, time)
    assert(iscolumn(daily_values) && numel(daily_values)==365 && numel(time)>=2 && ...
        all(diff(time)>0) && time(1)==0 && abs(time(end)-365)<1e-10, ...
        "Forcing periods must partition one 365-day year.");
    averages=zeros(size(time));
    for period=1:numel(time)-1
        start_day=time(period); end_day=time(period+1); total=0;
        for day=floor(start_day):ceil(end_day)-1
            overlap=max(0,min(end_day,day+1)-max(start_day,day));
            total=total+overlap*daily_values(mod(day,365)+1);
        end
        averages(period)=total/(end_day-start_day);
    end
    averages(end)=averages(end-1); % endpoint value is retained only for TS6 coverage
end

function month = monthIndex365(time)
    days_in_month = [31;28;31;30;31;30;31;31;30;31;30;31];
    day_of_year = mod(floor(time), 365); month = zeros(numel(time), 1);
    ends = cumsum(days_in_month);
    for q = 1:numel(time), month(q) = find(day_of_year(q) < ends, 1, "first"); end
end

function factor = normalizeMonthlyFactor(factor, days_in_month)
    factor = factor(:); factor = factor / (sum(factor .* days_in_month) / sum(days_in_month));
end

function length_m = domainLength(X, Y, direction)
    if direction == "y", length_m = max(Y(:)) - min(Y(:)); else, length_m = max(X(:)) - min(X(:)); end
    assert(isfinite(length_m) && length_m > 0, "Domain length must be finite and positive.");
end

function bed = downstreamChannelBedElevation(ZTop, direction)
    if direction == "y"
        if mean(ZTop(:,1), "all") <= mean(ZTop(:,end), "all"), bed = min(ZTop(:,1)); else, bed = min(ZTop(:,end)); end
    else
        if mean(ZTop(1,:), "all") <= mean(ZTop(end,:), "all"), bed = min(ZTop(1,:)); else, bed = min(ZTop(end,:)); end
    end
end

function curve = makeSyntheticRatingCurve(bed, flow_series, base_depth, stage_range, exponent)
    assert(all(isfinite(flow_series) & flow_series>0) && base_depth>=0 && stage_range>0 && exponent>0, ...
        "Invalid synthetic rating-curve parameter.");
    flow = quantile(flow_series,[0,0.25,0.5,0.75,1])'; flow=unique(flow);
    normalized=(flow-flow(1))/(flow(end)-flow(1));
    stage = bed + base_depth + stage_range * normalized.^exponent;
    assert(numel(flow)>=3 && all(diff(flow)>0) && abs((stage(end)-stage(1))-stage_range)<1e-12, ...
        "Synthetic rating curve must span the requested stage range.");
    curve = table(flow, stage, VariableNames=["flow_m3_per_day", "stage_m_at_downstream_control"]);
end

function stage = ratingCurveStage(curve, flow)
    required = ["flow_m3_per_day", "stage_m_at_downstream_control"];
    assert(istable(curve) && all(ismember(required, string(curve.Properties.VariableNames))) && size(curve, 1) >= 2, ...
        "rating_curve requires at least two flow/stage rows.");
    [q, order] = sort(curve.flow_m3_per_day); z = curve.stage_m_at_downstream_control(order);
    assert(all(isfinite(q)) && all(isfinite(z)) && all(diff(q) > 0), "Rating-curve flows must be finite and unique.");
    stage = interp1(q, z, flow, "linear", "extrap");
end

function [mask, table_out] = makeGhbInputs(X, Y, Z, Kfield, Kmean, L, slope, stage_ts, direction, control_distance_m)
    [nx, ny, nzp1] = size(Z); nz = nzp1 - 1; mask = false(nx,ny,nz);
    ZTop = Z(:,:,end);
    if direction == "y"
        if mean(ZTop(:,1), "all") <= mean(ZTop(:,end), "all"), edge = 1; outward_sign = -1; else, edge = ny; outward_sign = 1; end
        mask(:,edge,:) = true; boundary_coordinate = mean(Y(:,edge), "all");
    else
        if mean(ZTop(1,:), "all") <= mean(ZTop(end,:), "all"), edge = 1; outward_sign = -1; else, edge = nx; outward_sign = 1; end
        mask(edge,:,:) = true; boundary_coordinate = mean(X(edge,:), "all");
    end
    control_coordinate = boundary_coordinate + outward_sign * control_distance_m;
    [ii,jj,kk] = ind2sub(size(mask), find(mask));
    linear_index = sub2ind([nx, ny], ii, jj);
    if direction == "y", local_coordinate = Y(linear_index); else, local_coordinate = X(linear_index); end
    % The user-specified slope is along the downstream flow direction. Convert
    % it to the raw X/Y coordinate direction selected by the low-elevation end.
    head_series = stage_ts.stage_m_at_downstream_control' + (slope * outward_sign) .* (local_coordinate - control_coordinate);
    % Include every hydraulically valid boundary cell. Shallow cells whose
    % bottoms are above the controlled water surface cannot receive a GHB;
    % requiring every transverse column below prevents an accidental partial
    % side boundary while retaining a physically valid unconfined boundary.
    cell_bottom = zeros(numel(ii), 1);
    for q = 1:numel(ii), cell_bottom(q) = Z(ii(q),jj(q),kk(q)); end
    valid = all(head_series > cell_bottom + 1.0e-6, 2);
    ii = ii(valid); jj = jj(valid); kk = kk(valid); local_coordinate = local_coordinate(valid);
    head_series = head_series(valid,:); n = numel(ii);
    assert(n > 0, "No hydraulically valid downstream GHB cells remain.");
    if direction == "y", assert(numel(unique(ii)) == nx, "Downstream GHB must span every cross-domain X column.");
    else, assert(numel(unique(jj)) == ny, "Downstream GHB must span every cross-domain Y row."); end
    mask = false(nx,ny,nz); mask(sub2ind(size(mask),ii,jj,kk)) = true;
    area = zeros(n,1); kmean_cell = zeros(n,1);
    for q = 1:n
        vertical = Z(ii(q),jj(q),kk(q)+1) - Z(ii(q),jj(q),kk(q));
        if direction == "y", face_width = abs(X(min(nx,ii(q)+1),jj(q))-X(max(1,ii(q)-1),jj(q))) / min(2, nx-1); else, face_width = abs(Y(ii(q),min(ny,jj(q)+1))-Y(ii(q),max(1,jj(q)-1))) / min(2, ny-1); end
        area(q) = face_width * vertical; kmean_cell(q) = Kfield(ii(q),jj(q),kk(q));
    end
    conductance = Kmean * area / L;
    assert(all(isfinite(conductance) & conductance > 0), "GHB conductances must be finite and positive.");
    table_out = table(ii,jj,kk,area,kmean_cell,conductance, control_distance_m * ones(n,1), ...
        VariableNames=["i_x", "i_y", "native_layer", "connection_area_m2", "cell_K_m_per_day", "conductance_m2_per_day", "external_flow_path_length_m"]);
    table_out.reference_head_timeseries = num2cell(head_series, 2);
end

function description = downstreamEdgeDescription(ZTop, direction)
    if direction == "y"
        if mean(ZTop(:,1), "all") <= mean(ZTop(:,end), "all"), description = "minimum-y edge (lowest mean elevation)"; else, description = "maximum-y edge (lowest mean elevation)"; end
    else
        if mean(ZTop(1,:), "all") <= mean(ZTop(end,:), "all"), description = "minimum-x edge (lowest mean elevation)"; else, description = "maximum-x edge (lowest mean elevation)"; end
    end
end

function dam = makeDamDefinition(p, settings, X, Y, ZTop, dx, dy, nz)
    assert(isequal(size(p.dam_endpoints_xy), [2 2]), "dam_endpoints_xy must be a 2-by-2 [x,y] array.");
    p1 = p.dam_endpoints_xy(1,:); p2 = p.dam_endpoints_xy(2,:); vector = p2-p1; length_m = hypot(vector(1),vector(2));
    assert(length_m > 0 && all(p.dam_endpoints_xy(:,1) >= min(X(:)) & p.dam_endpoints_xy(:,1) <= max(X(:)) & ...
        p.dam_endpoints_xy(:,2) >= min(Y(:)) & p.dam_endpoints_xy(:,2) <= max(Y(:))), "Dam endpoints must be distinct and within the domain.");
    assert(any(settings.upstream_side == ["left", "right"]) && p.initial_depth_above_dam_toe_m >= 0 && settings.crest_height_above_dam_toe_m > 0 && ...
        p.initial_depth_above_dam_toe_m <= settings.crest_height_above_dam_toe_m && settings.leakage_half_width_cells >= 0 && ...
        settings.leakage_n_top_layers >= 1 && settings.leakage_n_top_layers <= nz && settings.k_multiplier > 0 && settings.k33_multiplier > 0, "Invalid post-dam parameter.");
    spacing = settings.dam_line_sample_spacing_m; if isempty(spacing), spacing = min(dx,dy)/4; end
    assert(isfinite(spacing) && spacing > 0 && settings.stage_table_rows >= 3 && ...
        isfinite(settings.max_lake_extent_height_above_weir_m) && settings.max_lake_extent_height_above_weir_m > 0, ...
        "Invalid dam sampling/table or maximum-lake-extent parameter.");
    f = linspace(0,1,max(2,ceil(length_m/spacing)+1))'; line = p1 + f .* vector;
    interp = griddedInterpolant(X,Y,ZTop,"linear","nearest"); zline = interp(line(:,1),line(:,2)); [toe,ind] = min(zline);
    dam = struct();
    dam.endpoint_1_xy=p1; dam.endpoint_2_xy=p2; dam.upstream_side=settings.upstream_side; dam.length_m=length_m;
    dam.line_xy=line; dam.line_ground_elevation_m=zline; dam.toe_xy=line(ind,:); dam.toe_elevation_m=toe;
    dam.crest_elevation_m=toe+settings.crest_height_above_dam_toe_m; dam.initial_stage_m=toe+p.initial_depth_above_dam_toe_m;
    dam.leakage_half_width_cells=settings.leakage_half_width_cells; dam.leakage_n_top_layers=settings.leakage_n_top_layers;
    dam.k_multiplier=settings.k_multiplier; dam.k33_multiplier=settings.k33_multiplier; dam.stage_table_rows=settings.stage_table_rows;
    dam.max_lake_extent_height_above_weir_m=settings.max_lake_extent_height_above_weir_m;
    dam.maximum_lake_extent_stage_m=dam.crest_elevation_m+settings.max_lake_extent_height_above_weir_m;
    dam.stage_table_maximum_m=dam.crest_elevation_m+2*settings.max_lake_extent_height_above_weir_m;
    dam.grid_mask=pointToSegmentDistance(X,Y,p1,p2)<=0.5*hypot(dx,dy);
end

function dam = emptyDamDefinition()
    dam = struct("endpoint_1_xy",[],"endpoint_2_xy",[],"upstream_side","", "length_m",0,"line_xy",[], ...
        "line_ground_elevation_m",[],"toe_xy",[],"toe_elevation_m",NaN,"crest_elevation_m",NaN,"initial_stage_m",NaN, ...
        "leakage_half_width_cells",0,"leakage_n_top_layers",0,"k_multiplier",1,"k33_multiplier",1,"stage_table_rows",0, ...
        "max_lake_extent_height_above_weir_m",0,"maximum_lake_extent_stage_m",NaN,"stage_table_maximum_m",NaN,"grid_mask",[]);
end

function [upstream, distance] = damSideMask(X,Y,p1,p2,side)
    v=p2-p1; cross=v(1).*(Y-p1(2))-v(2).*(X-p1(1)); upstream = cross>0; if side=="right", upstream=cross<0; end
    distance=pointToSegmentDistance(X,Y,p1,p2);
end

function [curve,masks,maximum_mask] = makeStageAreaVolume(ZTop, upstream, distance, dx, dy, dam)
    % The connected DEM pond is authoritative through the user-selected maximum
    % extent.  Above that stage, the LAK table retains the capped area and
    % adds volume linearly, preventing accidental expansion to the domain edge.
    n_base=max(2, round(0.75*(dam.stage_table_rows-1))+1);
    base_stage=linspace(dam.toe_elevation_m,dam.maximum_lake_extent_stage_m,n_base)';
    extended_stage=linspace(dam.maximum_lake_extent_stage_m,dam.stage_table_maximum_m, ...
        dam.stage_table_rows-n_base+1)';
    stage=[base_stage;extended_stage(2:end)]; n=numel(stage); cap_index=n_base;
    area=zeros(n,1); volume=area; count=zeros(n,1); edge=false(n,1); masks=cell(n,1);
    for q=1:cap_index
        masks{q}=connectedPondMask(ZTop,upstream,distance,dx,dy,stage(q)); count(q)=nnz(masks{q}); area(q)=count(q)*dx*dy;
        volume(q)=sum(max(stage(q)-ZTop,0).*masks{q},"all")*dx*dy; edge(q)=touchesDomainEdge(masks{q});
    end
    maximum_mask=masks{cap_index}; maximum_area=area(cap_index); maximum_volume=volume(cap_index);
    for q=cap_index+1:n
        masks{q}=maximum_mask; count(q)=count(cap_index); area(q)=maximum_area;
        volume(q)=maximum_volume+maximum_area*(stage(q)-stage(cap_index)); edge(q)=edge(cap_index);
    end
    assert(all(diff(stage)>0) && all(diff(volume)>=0) && all(area(cap_index:end)==maximum_area), ...
        "Lake table must have increasing stage/volume and constant capped area.");
    curve=table(stage,stage-dam.toe_elevation_m,area,volume,count,edge,stage>dam.maximum_lake_extent_stage_m, ...
        VariableNames=["stage_elevation_m","stage_above_toe_m","area_m2","volume_m3","cell_count","touches_domain_edge","above_maximum_extent"]);
end

function lake = makeLakeDefinition(name,id,mask,stage,ZTop,Z,dx,dy,lakebed_thickness,lakebed_k,table_curve)
    nz=size(Z,3)-1; layer1=nz; [ii,jj]=find(mask); n=numel(ii); assert(n>0, "Lake footprint must contain cells.");
    connection_area=dx*dy*ones(n,1); conductance=lakebed_k*(connection_area)/(lakebed_thickness);
    lake=struct(); lake.name=name; lake.lake_id=id; lake.footprint_mask=mask; lake.initial_stage_m=stage;
    lake.connection_layer_native=layer1*ones(n,1); lake.connection_i_x=ii; lake.connection_i_y=jj;
    lake.lakebed_thickness_m=lakebed_thickness; lake.lakebed_vertical_k_m_per_day=lakebed_k;
    lake.vertical_connection_area_m2=connection_area; lake.vertical_connection_conductance_m2_per_day=conductance;
    lake.stage_area_volume=table_curve; lake.land_elevation_m=ZTop(mask);
end

function uzf=makeUzfEligibility(lake_mask,nz)
    [nx,ny]=size(lake_mask); eligible=true(nx,ny,nz); eligible(:,:,nz)=~lake_mask;
    start=ones(nx,ny); start(lake_mask)=min(2,nz); if nz==1, start(lake_mask)=NaN; end
    uzf=struct(); uzf.eligible_mask=eligible; uzf.start_layer_number_top_down=start;
    uzf.rule="Exclude active layer-1 lake cells; begin below-lake UZF at layer 2.";
end

function monitoring = makeValidationMonitoring(X,Y,ZTop,channel,upstream,downstream,dam,direction,nz)
    dam_xy=0.5*(dam.endpoint_1_xy+dam.endpoint_2_xy);
    if direction=="y"
        coordinates=Y(1,:); dam_coordinate=dam_xy(2);
        upstream_indices=find(any(upstream,1)); downstream_indices=find(any(downstream,1));
    else
        coordinates=X(:,1)'; dam_coordinate=dam_xy(1);
        upstream_indices=find(any(upstream,2))'; downstream_indices=find(any(downstream,2))';
    end
    assert(~isempty(upstream_indices) && ~isempty(downstream_indices), "Dam reference must split the model into two nonempty zones.");
    [~,q]=min(abs(coordinates(upstream_indices)-dam_coordinate)); up_near=upstream_indices(q);
    [~,q]=max(abs(coordinates(upstream_indices)-dam_coordinate)); up_end=upstream_indices(q);
    [~,q]=min(abs(coordinates(upstream_indices)-0.5*(dam_coordinate+coordinates(up_end)))); up_half=upstream_indices(q);
    [~,q]=min(abs(coordinates(downstream_indices)-dam_coordinate)); down_near=downstream_indices(q);
    [~,q]=max(abs(coordinates(downstream_indices)-dam_coordinate)); down_end=downstream_indices(q);
    [~,q]=min(abs(coordinates(downstream_indices)-0.5*(dam_coordinate+coordinates(down_end)))); down_half=downstream_indices(q);
    stations=[up_half;up_near;down_near;down_half]; points=zeros(4,3); resolved=zeros(4,2);
    for q=1:4
        if direction=="y"
            j=stations(q); candidates=find(channel(:,j)); [~,local]=min(ZTop(candidates,j)); i=candidates(local);
        else
            i=stations(q); candidates=find(channel(i,:)); [~,local]=min(ZTop(i,candidates)); j=candidates(local);
        end
        points(q,:)=[X(i,j),Y(i,j),0]; resolved(q,:)=[i,j];
    end
    % Meandering reaches can project the two dam-adjacent station requests
    % onto one channel cell. Keep both named channel diagnostics; the six
    % distributed domain monitors added below are required to be unique.
    % The named channel stations are geometric diagnostics. On a strongly
    % curved reach their cell-center projection need not lie strictly on the
    % analytic dam-side mask; model validity does not depend on that label.
    names=["head_upstream_half";"head_dam_upstream_1cell"; ...
        "head_dam_downstream_1cell";"head_downstream_half"];
    x_targets=min(X(:)) + [0.25 0.75].*(max(X(:))-min(X(:)));
    y_targets=min(Y(:)) + [0.25 0.50 0.75].*(max(Y(:))-min(Y(:)));
    domain_points=zeros(6,3); domain_names=strings(6,1);
    index=1;
    for x_fraction=[25 75]
        for y_fraction=[25 50 75]
            domain_points(index,:)=[x_targets((x_fraction==[25 75])), ...
                y_targets((y_fraction==[25 50 75])), 0];
            domain_names(index)=sprintf("head_domain_x%02d_y%02d_bottom",x_fraction,y_fraction);
            index=index+1;
        end
    end
    monitoring=makeHeadMonitoring([points;domain_points],[names;domain_names],X,Y,nz);
    resolved=sub2ind(size(ZTop),monitoring.head_points_resolved_i_x,monitoring.head_points_resolved_i_y);
    assert(numel(unique(resolved(5:end)))==6, "The six domain monitor points must resolve to unique cells.");
end

function monitoring = makeHeadMonitoring(points, names, X, Y, nz)
    assert(all(isfinite(points),"all") && all(points(:,1)>=min(X(:)) & points(:,1)<=max(X(:)) & ...
        points(:,2)>=min(Y(:)) & points(:,2)<=max(Y(:))), "Head-monitor coordinates must be inside the model domain.");
    requested_layer=points(:,3);
    assert(all(mod(requested_layer,1)==0 & requested_layer>=0 & requested_layer<=nz), ...
        "Head-monitor layers must be integers: 0 for bottom or 1 through n_layers top-down.");
    resolved_layer=requested_layer; resolved_layer(resolved_layer==0)=nz;
    n=size(points,1); ix=zeros(n,1); iy=zeros(n,1);
    for q=1:n
        [~,idx]=min((X-points(q,1)).^2+(Y-points(q,2)).^2,[],"all","linear");
        [ix(q),iy(q)]=ind2sub(size(X),idx);
    end
    monitoring=struct(); monitoring.head_points_requested_xy_layer=points;
    monitoring.head_point_names=string(names(:)); monitoring.head_points_resolved_i_x=ix;
    monitoring.head_points_resolved_i_y=iy; monitoring.head_points_resolved_layer_top_down=resolved_layer;
    monitoring.head_points_resolved_xy=[X(sub2ind(size(X),ix,iy)),Y(sub2ind(size(Y),ix,iy))];
    monitoring.layer_convention="positive layers are top-down; layer 0 selects the bottom layer";
end

function targets=makeObservationTargets(scenario,lakes,outlets)
    lake_names=string({lakes.name})'; targets=table([lake_names; "groundwater"; "boundary"], ...
        [repmat("stage_storage_lak_gwf_exchange",numel(lakes),1); "heads_bda_cross_section"; "ghb_flow_total_budget"], ...
        VariableNames=["feature","required_output"]);
    for q=1:size(outlets, 1), targets=[targets; {outlets.role(q), "outlet_or_transfer_flow"}]; end %#ok<AGROW>
    if scenario=="post_dam", targets=[targets; {"bda_leakage_zone", "cross_section_groundwater_flow"}]; end %#ok<AGROW>
end

function makeReviewFigures(X,Y,ZTop,channel,lakes,dam,leakage,ghb,uzf,monitoring,scenario)
    figure("Color","w","Name","BDA preparation review","Units","inches","Position",[1 1 13 8]); tiledlayout(2,2,"TileSpacing","compact");
    nexttile; imagesc(X(:,1),Y(1,:),ZTop'); axis image xy; hold on; contour(X,Y,channel,[.5 .5],"c","LineWidth",1.5);
    for q=1:numel(lakes), contour(X,Y,lakes(q).footprint_mask,[.5 .5],"LineWidth",2); end
    if scenario=="post_dam", plot(dam.line_xy(:,1),dam.line_xy(:,2),"m-","LineWidth",2); end
    plotMonitoringPoints(monitoring,true);
    title("Lake footprints, channel, and monitoring points"); xlabel("X (m)"); ylabel("Y (m)"); colorbar;
    nexttile; imagesc(X(:,1),Y(1,:),double(leakage)'); axis image xy; hold on; plotMonitoringPoints(monitoring,false);
    title("Effective BDA leakage footprint (post-dam only)"); xlabel("X (m)"); ylabel("Y (m)"); colorbar;
    nexttile; imagesc(X(:,1),Y(1,:),double(ghb(:,:,end))'); axis image xy; hold on; plotMonitoringPoints(monitoring,false);
    title("Downstream layer-1 GHB cells"); xlabel("X (m)"); ylabel("Y (m)"); colorbar;
    nexttile; imagesc(X(:,1),Y(1,:),double(uzf.eligible_mask(:,:,end))'); axis image xy; hold on; plotMonitoringPoints(monitoring,false);
    title("Layer-1 UZF eligibility"); xlabel("X (m)"); ylabel("Y (m)"); colorbar;
end

function plotMonitoringPoints(monitoring,add_labels)
    xy=monitoring.head_points_resolved_xy;
    if add_labels
        descriptions=monitoring.head_point_names;
        point_handles=gobjects(size(xy,1),1);
        for q=1:size(xy,1)
            point_handles(q)=scatter(xy(q,1),xy(q,2),52,"o","MarkerFaceColor","w","MarkerEdgeColor","k", ...
                "LineWidth",1.25,"DisplayName",descriptions(q));
            text(xy(q,1),xy(q,2),"M"+string(q),"Color","k","FontWeight","bold", ...
                "HorizontalAlignment","center","VerticalAlignment","middle","FontSize",8, ...
                "HandleVisibility","off");
        end
        legend(point_handles,descriptions,"Location","southoutside","NumColumns",2);
    else
        scatter(xy(:,1),xy(:,2),52,"o","MarkerFaceColor","w","MarkerEdgeColor","k", ...
            "LineWidth",1.25,"HandleVisibility","off");
    end
end

function makeForcingFigure(forcing)
    series = forcing.timeseries;
    figure("Color","w","Name","Synthetic Pullman forcing review","Units","inches","Position",[1 1 12 7]);
    tiledlayout(3,1,"TileSpacing","compact");
    nexttile; plot(series.time_days,series.upstream_inflow_m3_per_day,"b-","LineWidth",1.25); grid on
    ylabel("Inflow (m^3/day)"); title("Synthetic Pullman/Rose Creek-area forcing: labeled assumptions, not calibration data")
    nexttile; plot(series.time_days,1000*series.land_recharge_m_per_day,"b-",series.time_days,1000*series.lake_precipitation_m_per_day,"c-"); grid on
    ylabel("Water input (mm/day)"); legend("Land recharge","Lake precipitation","Location","best")
    nexttile; plot(series.time_days,1000*series.land_et_m_per_day,"r-",series.time_days,1000*series.lake_evaporation_m_per_day,"m-"); grid on
    xlabel("Model time (days)"); ylabel("Loss (mm/day)"); legend("Land ET","Lake evaporation","Location","best")
end

function printReviewSummary(prep,calendar,slope)
    fprintf("\nBDA preparation review: %s\n",prep.metadata.scenario);
    fprintf("  Calendar: %s, %d stress periods, %.12g days/year\n",calendar.resolution,numel(calendar.perlen_days),calendar.annual_duration_days);
    fprintf("  Shared channel cells: %d; lake count: %d\n",nnz(prep.surface_water.channel_mask),numel(prep.surface_water.lakes));
    for q=1:numel(prep.surface_water.lakes)
        lake=prep.surface_water.lakes(q); dry=nnz(lake.land_elevation_m>lake.initial_stage_m);
        fprintf("  LAK %d fixed-footprint cells: %d; above initial stage: %d\n",q,nnz(lake.footprint_mask),dry);
    end
    fprintf("  Atmospheric formulation: UZF land cells %d; LAK cells %d; RCH/EVT prohibited\n", ...
        nnz(prep.uzf.land_atmosphere_mask),nnz(prep.uzf.lake_atmosphere_mask));
    fprintf("  Downstream GHB cells: %d; longitudinal water-surface slope: %.6g m/m\n",numel(prep.boundaries.ghb_cells.i_x),slope);
    fprintf("  GHB control distance: %.3f m (domain length %.3f m)\n",prep.boundaries.downstream_control_distance_m,prep.boundaries.domain_length_m);
    f=prep.parameters.forcing; fprintf("  Synthetic forcing means: Q %.3f m^3/day; recharge %.4g m/day; ET %.4g m/day\n",f.mean_streamflow_m3_per_day,f.mean_recharge_m_per_day,f.mean_land_et_m_per_day);
    fprintf("  Initial-head upslope reduction: %.6g m/m (half absolute channel bed slope)\n", ...
        prep.parameters.mf6_parameters.initial_head_upslope_reduction_m_per_m);
    if prep.metadata.scenario=="post_dam"
        d=prep.surface_water.dam; fprintf("  Dam endpoints: (%.3f, %.3f) to (%.3f, %.3f) m\n",d.endpoint_1_xy,d.endpoint_2_xy);
        fprintf("  Toe %.3f m; initial stage %.3f m; crest %.3f m\n",d.toe_elevation_m,d.initial_stage_m,d.crest_elevation_m);
        fprintf("  Effective BDA leakage cells: %d\n",nnz(prep.properties.BDA_LEAKAGE_MASK));
    end
    fprintf("  FloPy handoff: exported after this review summary.\n\n");
end

function distance=pointToSegmentDistance(x,y,p1,p2)
    v=p2-p1; t=((x-p1(1)).*v(1)+(y-p1(2)).*v(2))./sum(v.^2); t=min(max(t,0),1);
    distance=hypot(x-(p1(1)+t.*v(1)),y-(p1(2)+t.*v(2)));
end

function mask=connectedPondMask(land,upstream,distance,dx,dy,stage)
    candidate=upstream & land<=stage; seed=candidate & distance<=max(dx,dy); if ~any(seed,"all") && any(candidate,"all"), idx=find(candidate); [~,q]=min(distance(idx)); seed(idx(q))=true; end
    mask=floodFill4(candidate,seed);
end

function mask=largestConnectedComponent(candidate)
    remaining=candidate; mask=false(size(candidate)); best=0;
    while any(remaining,"all")
        seed=false(size(candidate)); seed(find(remaining,1,"first"))=true; component=floodFill4(remaining,seed);
        if nnz(component)>best, mask=component; best=nnz(component); end
        remaining(component)=false;
    end
end

function mask=downstreamConnectedComponent(candidate,ZTop,direction)
    seed=false(size(candidate));
    if direction=="y"
        if mean(ZTop(:,1),"all") <= mean(ZTop(:,end),"all"), seed(:,1)=candidate(:,1); else, seed(:,end)=candidate(:,end); end
    else
        if mean(ZTop(1,:),"all") <= mean(ZTop(end,:),"all"), seed(1,:)=candidate(1,:); else, seed(end,:)=candidate(end,:); end
    end
    assert(any(seed,"all"), "The shared channel does not reach the downstream domain edge.");
    mask=floodFill4(candidate,seed);
end

function touch=touchesDownstreamEdge(mask,ZTop,direction)
    if direction=="y"
        if mean(ZTop(:,1),"all") <= mean(ZTop(:,end),"all"), touch=any(mask(:,1),"all"); else, touch=any(mask(:,end),"all"); end
    else
        if mean(ZTop(1,:),"all") <= mean(ZTop(end,:),"all"), touch=any(mask(1,:),"all"); else, touch=any(mask(end,:),"all"); end
    end
end

function mask=floodFill4(candidate,seed)
    [nx,ny]=size(candidate); mask=false(nx,ny); queue=find(seed); mask(queue)=true; pos=1;
    while pos<=numel(queue)
        [i,j]=ind2sub([nx,ny],queue(pos)); pos=pos+1; ni=[i-1 i+1 i i]; nj=[j j j-1 j+1]; valid=ni>=1&ni<=nx&nj>=1&nj<=ny;
        add=sub2ind([nx,ny],ni(valid),nj(valid)); add=add(candidate(add)&~mask(add)); mask(add)=true; queue=[queue;add(:)]; %#ok<AGROW>
    end
end

function touch=touchesDomainEdge(mask)
    touch=any(mask(1,:),"all")||any(mask(end,:),"all")||any(mask(:,1),"all")||any(mask(:,end),"all");
end

function [ids,source]=assignHydrofaciesToGrid(point_file,points,fallback,X,Y,ZCell)
    if strlength(point_file)>0, assert(isfile(point_file),"hydrofacies_points_file does not exist."); points=readtable(point_file); source="CSV"; else, source="in-script table"; end
    required=["x_m","y_m","z_top_m","z_bottom_m","hydrofacies_id"]; assert(istable(points)&&all(ismember(required,string(points.Properties.VariableNames)))&&size(points, 1)>0,"Invalid hydrofacies points.");
    ids=fallback*ones(size(ZCell));
    for k=1:size(ZCell,3), for j=1:size(ZCell,2), for i=1:size(ZCell,1)
        z=ZCell(i,j,k); match=z<=max(points.z_top_m,points.z_bottom_m)&z>=min(points.z_top_m,points.z_bottom_m);
        if any(match), p=points(match,:); [~,q]=min((p.x_m-X(i,j)).^2+(p.y_m-Y(i,j)).^2); ids(i,j,k)=p.hydrofacies_id(q); end
    end,end,end
end

function [K,K33]=mapHydrofaciesProperties(ids,classes)
    required=["hydrofacies_id","K_m_per_day","K33_m_per_day"]; assert(istable(classes)&&all(ismember(required,string(classes.Properties.VariableNames)))&&size(classes, 1)>0,"Invalid hydrofacies classes.");
    [ok,row]=ismember(ids,classes.hydrofacies_id); assert(all(ok,"all"),"Every hydrofacies ID needs property values."); K=classes.K_m_per_day(row); K33=classes.K33_m_per_day(row); assert(all(K>0,"all")&&all(K33>0,"all"),"Hydrofacies K values must be positive.");
end
