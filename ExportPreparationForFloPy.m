function [h5_path, manifest_path] = ExportPreparationForFloPy(preparation, output_directory)
% Export verified MATLAB preparation data as a plain, versioned FloPy handoff.
% Run MakeInputs.m first, then call:
%   ExportPreparationForFloPy(preparation, "flopy_handoff")
% No MATLAB tables, objects, or orientation inference are exported.

arguments
    preparation (1,1) struct
    output_directory (1,1) string = "flopy_handoff"
end

assert(isfield(preparation, "metadata") && isfield(preparation, "grid"), ...
    "preparation must be produced by MakeInputs.m.");
if ~isfolder(output_directory), mkdir(output_directory); end
h5_path = fullfile(output_directory, "preparation_handoff.h5");
manifest_path = fullfile(output_directory, "preparation_manifest.json");
if isfile(h5_path), delete(h5_path); end

% Every array is flattened in MATLAB column-major order and accompanied by its
% native shape. Python reconstructs it with order='F', avoiding HDF5 dimension
% reversal ambiguities between MATLAB and h5py.
g = preparation.grid;
writeArray(h5_path, "/grid/X", g.X); writeArray(h5_path, "/grid/Y", g.Y);
writeArray(h5_path, "/grid/dx_m", g.dx_m); writeArray(h5_path, "/grid/dy_m", g.dy_m);
writeArray(h5_path, "/grid/ZTop", g.ZTop); writeArray(h5_path, "/grid/ZBot", g.ZBot);
writeArray(h5_path, "/grid/Z", g.Z); writeArray(h5_path, "/grid/ZCell", g.ZCell);

p = preparation.properties;
writeArray(h5_path, "/properties/K", p.K); writeArray(h5_path, "/properties/K33", p.K33);
writeArray(h5_path, "/properties/K_background", p.K_background);
writeArray(h5_path, "/properties/K33_background", p.K33_background);
writeArray(h5_path, "/properties/Sy", p.Sy); writeArray(h5_path, "/properties/Ss", p.Ss);
writeArray(h5_path, "/properties/Porosity", p.Porosity);
writeArray(h5_path, "/properties/BDA_LEAKAGE_MASK", uint8(p.BDA_LEAKAGE_MASK));
writeArray(h5_path, "/properties/BDA_LEAKAGE_FOOTPRINT", uint8(p.BDA_LEAKAGE_FOOTPRINT));

c = preparation.parameters.calendar;
writeArray(h5_path, "/calendar/perlen_days", c.perlen_days); writeArray(h5_path, "/calendar/nstp", c.nstp);
writeArray(h5_path, "/calendar/water_year_start_month", c.water_year_start_month);
writeArray(h5_path, "/calendar/water_year_start_day", c.water_year_start_day);
f = preparation.parameters.forcing;
writeArray(h5_path, "/forcing/time_days", f.time_days);
writeArray(h5_path, "/forcing/upstream_inflow_m3_per_day", f.upstream_inflow_m3_per_day);
writeArray(h5_path, "/forcing/land_recharge_m_per_day", f.land_infiltration_m_per_day);
writeArray(h5_path, "/forcing/land_et_m_per_day", f.land_et_m_per_day);
writeArray(h5_path, "/forcing/lake_precipitation_m_per_day", f.lake_precipitation_m_per_day);
writeArray(h5_path, "/forcing/lake_evaporation_m_per_day", f.lake_evaporation_m_per_day);

b = preparation.boundaries;
writeArray(h5_path, "/boundaries/downstream_ghb_mask", uint8(b.downstream_ghb_mask));
writeArray(h5_path, "/boundaries/domain_length_m", b.domain_length_m);
writeArray(h5_path, "/boundaries/downstream_control_distance_m", b.downstream_control_distance_m);
writeArray(h5_path, "/boundaries/rating_curve/flow_m3_per_day", b.rating_curve.flow_m3_per_day);
writeArray(h5_path, "/boundaries/rating_curve/stage_m", b.rating_curve.stage_m_at_downstream_control);
writeArray(h5_path, "/boundaries/downstream_control_stage_m", b.downstream_control_stage_timeseries.stage_m_at_downstream_control);
ghb = b.ghb_cells;
writeArray(h5_path, "/boundaries/ghb/i_x", ghb.i_x); writeArray(h5_path, "/boundaries/ghb/i_y", ghb.i_y);
writeArray(h5_path, "/boundaries/ghb/native_layer", ghb.native_layer);
writeArray(h5_path, "/boundaries/ghb/conductance_m2_per_day", ghb.conductance_m2_per_day);
writeArray(h5_path, "/boundaries/ghb/external_flow_path_length_m", ghb.external_flow_path_length_m);
writeArray(h5_path, "/boundaries/ghb/reference_head_m", vertcat(ghb.reference_head_timeseries{:}));

sw = preparation.surface_water;
writeArray(h5_path, "/surface_water/channel_mask", uint8(sw.channel_mask));
writeArray(h5_path, "/surface_water/n_lakes", numel(sw.lakes));
for lake_number = 1:numel(sw.lakes)
    lake = sw.lakes(lake_number); base = string(sprintf("/surface_water/lakes/lake_%d", lake_number));
    writeArray(h5_path, base + "/footprint_mask", uint8(lake.footprint_mask));
    writeArray(h5_path, base + "/initial_stage_m", lake.initial_stage_m);
    writeArray(h5_path, base + "/connection_i_x", lake.connection_i_x);
    writeArray(h5_path, base + "/connection_i_y", lake.connection_i_y);
    writeArray(h5_path, base + "/connection_layer_native", lake.connection_layer_native);
    writeArray(h5_path, base + "/lakebed_thickness_m", lake.lakebed_thickness_m);
    writeArray(h5_path, base + "/lakebed_vertical_k_m_per_day", lake.lakebed_vertical_k_m_per_day);
    has_table = ~isempty(lake.stage_area_volume);
    writeArray(h5_path, base + "/has_stage_area_volume", uint8(has_table));
    if has_table
        curve = lake.stage_area_volume;
        writeArray(h5_path, base + "/stage_area_volume/stage_m", curve.stage_elevation_m);
        writeArray(h5_path, base + "/stage_area_volume/volume_m3", curve.volume_m3);
        writeArray(h5_path, base + "/stage_area_volume/area_m2", curve.area_m2);
    end
end
writeArray(h5_path, "/surface_water/outlets/width_m", sw.outlets.width_m);
if preparation.metadata.scenario == "post_dam"
    writeArray(h5_path, "/surface_water/dam/crest_elevation_m", sw.dam.crest_elevation_m);
    writeArray(h5_path, "/surface_water/dam/maximum_lake_extent_stage_m", sw.dam.maximum_lake_extent_stage_m);
    writeArray(h5_path, "/surface_water/dam/stage_table_maximum_m", sw.dam.stage_table_maximum_m);
end

zones = preparation.validation_zones;
writeArray(h5_path, "/validation_zones/upstream_mask", uint8(zones.upstream_mask));
writeArray(h5_path, "/validation_zones/downstream_mask", uint8(zones.downstream_mask));
writeArray(h5_path, "/validation_zones/dam_endpoint_1_xy", zones.reference_dam.endpoint_1_xy);
writeArray(h5_path, "/validation_zones/dam_endpoint_2_xy", zones.reference_dam.endpoint_2_xy);

u = preparation.uzf;
writeArray(h5_path, "/uzf/eligible_mask", uint8(u.eligible_mask));
writeArray(h5_path, "/uzf/start_layer_number_top_down", u.start_layer_number_top_down);
% Atmospheric-flux masks make the intentional UZF/LAK split auditable:
% UZF receives recharge/ET only where land_atmosphere_mask is true; LAK
% receives precipitation/evaporation only where lake_atmosphere_mask is true.
writeArray(h5_path, "/atmosphere/land_uzf_mask", uint8(u.land_atmosphere_mask));
writeArray(h5_path, "/atmosphere/lake_lak_mask", uint8(u.lake_atmosphere_mask));
mon = preparation.monitoring;
writeArray(h5_path, "/monitoring/head_points_requested_xy_layer", mon.head_points_requested_xy_layer);
writeArray(h5_path, "/monitoring/head_points_resolved_i_x", mon.head_points_resolved_i_x);
writeArray(h5_path, "/monitoring/head_points_resolved_i_y", mon.head_points_resolved_i_y);
writeArray(h5_path, "/monitoring/head_points_resolved_layer_top_down", mon.head_points_resolved_layer_top_down);
writeArray(h5_path, "/monitoring/head_points_resolved_xy", mon.head_points_resolved_xy);
mf6 = preparation.parameters.mf6_parameters;
fields = fieldnames(mf6);
for i = 1:numel(fields), writeArray(h5_path, "/mf6_parameters/" + fields{i}, mf6.(fields{i})); end

manifest = struct();
manifest.schema_version = "bdam-preparation-hdf5-v3";
manifest.scenario = char(preparation.metadata.scenario);
manifest.units = char(preparation.metadata.units);
manifest.time_resolution = char(preparation.parameters.calendar.resolution);
manifest.calendar_basis = char(preparation.parameters.forcing.calendar_basis);
manifest.native_array_order = "MATLAB [x,y,layer], flattened column-major; see companion shape datasets";
manifest.grid_shape = size(g.ZTop);
manifest.n_lakes = numel(sw.lakes);
manifest.n_outlets = height(sw.outlets);
manifest.atmospheric_flux_formulation = "UZF land recharge/ET; LAK precipitation/evaporation; RCH and EVT prohibited";
manifest.streamflow_forcing_source = char(preparation.parameters.forcing.synthetic_source);
manifest.streamflow_hydrograph_file = char(preparation.parameters.forcing.hydrograph_file);
manifest.lake_footprint_atmosphere_assumption = "Fixed maximum LAK connection footprints are excluded from layer-1 UZF even when locally above simulated stage";
manifest.treatment_only_input_names = cellstr(preparation.parameters.scenario.treatment_only_input_names);
manifest.hdf5_file = "preparation_handoff.h5";
manifest.source_script = "MakeInputs.m";
manifest.monitoring_head_point_names = cellstr(preparation.monitoring.head_point_names);
manifest.monitoring_layer_convention = char(preparation.monitoring.layer_convention);
manifest.longitudinal_direction = char(preparation.validation_zones.longitudinal_direction);
manifest.dam_upstream_side = char(preparation.validation_zones.reference_dam.upstream_side);
manifest.exported_at = char(datetime("now", "Format", "yyyy-MM-dd'T'HH:mm:ss"));
% The runner reads these root attributes directly, so the HDF5 file alone is
% sufficient at runtime. The adjacent JSON remains a convenient audit report.
h5writeatt(h5_path,"/","schema_version",manifest.schema_version);
h5writeatt(h5_path,"/","scenario",manifest.scenario);
h5writeatt(h5_path,"/","units",manifest.units);
h5writeatt(h5_path,"/","time_resolution",manifest.time_resolution);
h5writeatt(h5_path,"/","monitoring_head_point_names_json",jsonencode(manifest.monitoring_head_point_names));
fid = fopen(manifest_path, "w"); assert(fid > 0, "Cannot create manifest file.");
fprintf(fid, "%s\n", jsonencode(manifest, PrettyPrint=true)); fclose(fid);
fprintf("FloPy handoff written:\n  %s\n  %s\n", h5_path, manifest_path);
end

function writeArray(h5_path, base_path, value)
% Write numeric/logical data and a shape vector; HDF5 contains no MATLAB types.
value = double(value);
flat = value(:);
data_path = base_path + "/data";
shape_path = base_path + "/shape";
h5create(h5_path, data_path, size(flat), Datatype="double"); h5write(h5_path, data_path, flat);
shape = int64(size(value));
h5create(h5_path, shape_path, size(shape), Datatype="int64"); h5write(h5_path, shape_path, shape);
end
