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
n_layers = 5;                     % #User_Defined: groundwater layer count
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
groundwater_boundary_mode = "drain"; % #User_Defined: "drain" (outflow only) or "constant_ghb" (assumed bidirectional exchange)
groundwater_boundary_k_m_per_day = []; % #User_Defined: [m/day], effective boundary K in C=K*A/L
groundwater_boundary_resistance_in_domain_lengths = 1.0; % #User_Defined: effective resistance length/domain length; not a remote control location
drain_elevation_above_outlet_bed_m = 0.0; % #User_Defined: [m], local discharge threshold relative to modeled outlet bed
constant_ghb_head_above_outlet_bed_m = 0.10; % #User_Defined: [m], explicit assumed head, only used in constant_ghb mode
external_outlet_height_above_bed_m = 0.0; % #User_Defined: [m], independent Manning outlet invert above modeled outlet bed
initial_river_depth_above_outlet_bed_m = 0.10; % Legacy preparation preview; coarse pools initialize 0.10 m above their local low bed.
forcing_interpolation = "STEPWISE"; % #User_Defined: MF6 time-series interpolation convention

% Synthetic Pullman/Rose Creek-area climatology. NOAA Pullman 2 NW 1991--2020
% precipitation normals underpin the monthly totals. Streamflow timing uses a
% cached USGS climatological shape; its imposed mean, ET, recharge, and lake
% evaporation remain explicitly synthetic assumptions for review.
pullman_monthly_precipitation_mm = [67.8;49.3;52.1;49.8;46.0;31.0;11.2;12.2;16.5;45.7;66.5;70.4]; % #User_Defined: NOAA normal-derived [mm/month]
synthetic_mean_streamflow_m3_per_day = 8640; % #User_Defined: assumed 0.1 m3/s (100 L/s) mean upstream inflow
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
mf6_parameters.initial_head_channel_offset_m = 0.1; % #User_Defined: plane above downstream channel bottom [m]
mf6_parameters.fall_average_spinup_years = 0; % #User_Defined: optional constant fall-average years; disabled for monthly-first spinup
mf6_parameters.monthly_spinup_years = 4; % #User_Defined: varying monthly-average forcing years; replaces the two annual fall years
mf6_parameters.weekly_spinup_years = 1; % #User_Defined: varying weekly-average forcing years
mf6_parameters.pre_dam_years = 2; % #User_Defined: monitored annual years before dam installation
mf6_parameters.post_dam_years = 2; % #User_Defined: monitored annual years after dam installation; zero is a no-dam run

% Coarse river: two halves between the outlet and dam. Groundwater
% connections on the upper pond walls are excluded; full DEM storage retained.
river_settings = struct();
river_settings.downstream_segments = 2; % #User_Defined: validated two-pool configuration
river_settings.manning_width_m = 2.0; % #User_Defined: effective flowing-channel width [m]
river_settings.manning_roughness = 0.04; % #User_Defined: effective Manning roughness
river_settings.pond_exchange_height_above_thalweg_m = 1.25; % #User_Defined: pond bank connection cutoff [m]
river_settings.river_storage_height_above_highest_bed_m = 0.50; % #User_Defined: connected river storage-table extent [m]

% Native LAK sharp-weir controls. MF6 WEIR uses invert and effective width;
% it does not expose a user discharge coefficient. Calibrate effective width.
pre_dam_outlet_width_m = 1.0;       % Legacy intermediate placeholder; effective river width is river_settings.manning_width_m.
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
post_dam.initial_depth_above_dam_toe_m = 1.0; % Legacy preview only; installation conserves surface volume.

%% Sweep execution and forcing controls
n_parallel_runs = 1; % #User_Defined: positive integer; never a sweep axis
forcing_mode = "periodic"; % #User_Defined: "periodic" or "legacy"
forcing_controls = struct();
forcing_controls.precipitation = struct("magnitude_scale",1,"shift_days",0,"width_factor",1,"center_day",[]);
forcing_controls.et = struct("magnitude_scale",1,"shift_days",0,"width_factor",1,"center_day",[]);
forcing_controls.inflow = struct("magnitude_scale",1,"shift_days",0,"width_factor",1,"center_day",[]);
% Each numeric scalar parameter above may instead be a vector of candidates.
% Existing monthly/layer vectors remain arrays. Optional JSON overrides use
% BDAM_CONFIG; a campaign is planned/prepared, not launched, by this script.
config = struct();
config.time_resolution = time_resolution;
config.source_geometry_file = source_geometry_file;
config.longitudinal_direction = longitudinal_direction;
config.model_bottom_offset = model_bottom_offset;
config.n_layers = n_layers;
config.layer_growth_factor = layer_growth_factor;
config.hydraulic_conductivity_mode = hydraulic_conductivity_mode;
config.specific_yield = specific_yield;
config.specific_storage = specific_storage;
config.effective_porosity = effective_porosity;
config.K_constant = K_constant;
config.K33_constant = K33_constant;
config.K_by_layer_top_to_bottom = K_by_layer_top_to_bottom;
config.K33_by_layer_top_to_bottom = K33_by_layer_top_to_bottom;
config.hydrofacies_points_file = hydrofacies_points_file;
config.hydrofacies_points = hydrofacies_points;
config.hydrofacies_fallback_id = hydrofacies_fallback_id;
config.hydrofacies_class_properties = hydrofacies_class_properties;
config.channel_half_width_cells = channel_half_width_cells;
config.lakebed_thickness_m = lakebed_thickness_m;
config.lakebed_vertical_k_m_per_day = lakebed_vertical_k_m_per_day;
config.forcing_interpolation = forcing_interpolation;
config.pullman_monthly_precipitation_mm = pullman_monthly_precipitation_mm;
config.synthetic_mean_streamflow_m3_per_day = synthetic_mean_streamflow_m3_per_day;
config.usgs_hydrograph_file = usgs_hydrograph_file;
config.synthetic_mean_land_et_m_per_day = synthetic_mean_land_et_m_per_day;
config.synthetic_land_et_monthly_factor = synthetic_land_et_monthly_factor;
config.synthetic_recharge_fraction_of_precipitation = synthetic_recharge_fraction_of_precipitation;
config.synthetic_recharge_monthly_factor = synthetic_recharge_monthly_factor;
config.synthetic_lake_evaporation_fraction_of_land_et = synthetic_lake_evaporation_fraction_of_land_et;
config.groundwater_boundary_mode = groundwater_boundary_mode;
config.groundwater_boundary_k_m_per_day = groundwater_boundary_k_m_per_day;
config.groundwater_boundary_resistance_in_domain_lengths = groundwater_boundary_resistance_in_domain_lengths;
config.drain_elevation_above_outlet_bed_m = drain_elevation_above_outlet_bed_m;
config.constant_ghb_head_above_outlet_bed_m = constant_ghb_head_above_outlet_bed_m;
config.external_outlet_height_above_bed_m = external_outlet_height_above_bed_m;
config.initial_river_depth_above_outlet_bed_m = initial_river_depth_above_outlet_bed_m;
config.river_settings = river_settings;
config.mf6_parameters = mf6_parameters;
config.pre_dam_outlet_width_m = pre_dam_outlet_width_m;
config.post_dam_weir_width_m = post_dam_weir_width_m;
config.dam_settings = dam_settings;
config.post_dam = post_dam;
config.n_parallel_runs = n_parallel_runs;
config.forcing_mode = forcing_mode;
config.forcing_controls = forcing_controls;
config.hydrofacies_points = table2struct(hydrofacies_points);
config.hydrofacies_class_properties = table2struct(hydrofacies_class_properties);
if strlength(string(getenv("BDAM_CONFIG"))) > 0
    config = mergeBDamConfig(config,jsondecode(fileread(getenv("BDAM_CONFIG"))));
end
% The Python planner resolves the scalar registry, validates all combinations,
% and creates an immutable snapshot/manifest before any MF6 simulation starts.
campaign_root = string(getenv("BDAM_CAMPAIGN_ROOT"));
if campaign_root == ""
    campaigns = fullfile(script_root,"Campaign");
    if ~isfolder(campaigns), mkdir(campaigns); end
    campaign_root = string(tempname(campaigns));
end
if ~isfolder(campaign_root), mkdir(campaign_root); end
request_path = string(tempname(campaign_root)) + ".json";
writeBDamJson(request_path,config);
python = string(getenv("BDAM_PYTHON")); if python == "", python = "python3"; end
flags = "";
if string(getenv("BDAM_SKIP_BASELINE")) == "1", flags = flags + " --skip-baseline"; end
command = sprintf('"%s" "%s" plan "%s" "%s" --source "%s"%s', ...
    python,fullfile(script_root,"bdam_sweeps.py"),request_path,campaign_root,script_root,flags);
[status,report] = system(command); fprintf("%s",report);
assert(status == 0,"BDam sweep planning failed; see report above.");
manifest = jsondecode(fileread(fullfile(campaign_root,"campaign.json")));
if string(getenv("BDAM_PREVIEW")) ~= "1"
    if isempty(fieldnames(manifest.axes)) && string(getenv("BDAM_CAMPAIGN_ROOT")) == "" && numel(manifest.members) == 1
        resolved = jsondecode(fileread(fullfile(string(manifest.members(1).path),"resolved_config.json")));
        prepareBDamMember(resolved,script_root,true);
        fprintf('Single-member inputs ready: python3 build_bdam_simulation.py ModelInput\n');
    else
        command = sprintf('"%s" "%s" prepare "%s"',python,fullfile(script_root,"bdam_sweeps.py"),fullfile(campaign_root,"campaign.json"));
        [status,report] = system(command); fprintf("%s",report);
        assert(status == 0,"Campaign preparation failed; inspect preparation.log.");
    end
end
fprintf('Campaign launch: %s bdam_sweeps.py run "%s"\n',python,fullfile(campaign_root,"campaign.json"));
