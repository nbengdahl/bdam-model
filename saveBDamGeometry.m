function geometry_handoff = saveBDamGeometry(output_path, terrain, profile, parameters)
%SAVEBDAMGEOMETRY Save a versioned MAT handoff for MakeInputs.m.

arguments
    output_path {mustBeTextScalar}
    terrain (1,1) struct
    profile (1,1) struct
    parameters (1,1) struct
end

output_path = string(output_path);
if strlength(output_path) == 0
    error("BDam:ExportPath", "The geometry export path cannot be empty.");
end

X = terrain.X_m;
Y = terrain.Y_m;
ZTop = terrain.ZTop_m;
Z = terrain.Z_m;
x = terrain.x_m;
y = terrain.y_m;
dx = parameters.spacing_x_m;
dy = parameters.spacing_y_m;
dam_points = terrain.dam_points_m;
dam_max = parameters.dam_max_m;
tortuosity = terrain.tortuosity;
dam_centerline_station_m = terrain.dam_centerline_station_m;
dam_toe_elevation_m = terrain.dam_toe_elevation_m;
dam_crest_elevation_m = terrain.dam_crest_elevation_m;
dam_wall_x_m = terrain.dam_wall_x_m;
dam_wall_y_m = terrain.dam_wall_y_m;
dam_wall_z_m = terrain.dam_wall_z_m;
lake_maximum_stage_m = terrain.lake_stage_m;
lake_footprint_mask = terrain.lake_footprint_mask;
lake_touches_upstream_edge = terrain.lake_touches_upstream_edge;

post_dam = struct("dam_endpoints_xy",dam_points);
dam_settings = struct( ...
    "crest_height_above_dam_toe_m",dam_max, ...
    "upstream_side",terrain.dam_upstream_side);
cross_section = struct( ...
    "normal_distance_m",profile.offset_m, ...
    "elevation_m",profile.elevation_m, ...
    "channel_profile_m",profile.channel_profile_m, ...
    "bank_offsets_m",profile.bank_offsets_m);
centerline = struct( ...
    "x_m",terrain.centerline_x_m, ...
    "y_m",terrain.centerline_y_m, ...
    "elevation_m",terrain.centerline_elevation_m, ...
    "total_distance_m",terrain.total_centerline_distance_m);
lake = struct( ...
    "maximum_stage_m",lake_maximum_stage_m, ...
    "footprint_mask",lake_footprint_mask, ...
    "touches_upstream_edge",lake_touches_upstream_edge, ...
    "outline_segments_m",{terrain.lake_outline_segments_m});

geometry_handoff = struct();
geometry_handoff.schema_version = "bdam-geometry-mat-v1";
geometry_handoff.units = "meters";
geometry_handoff.array_orientation = ...
    "MATLAB [x,y]; first dimension is X and second dimension is Y";
geometry_handoff.exported_at = string(datetime("now", ...
    "Format","yyyy-MM-dd'T'HH:mm:ss"));
geometry_handoff.parameters = parameters;
geometry_handoff.post_dam = post_dam;
geometry_handoff.dam_settings = dam_settings;
geometry_handoff.tortuosity = tortuosity;
geometry_handoff.dam_toe_elevation_m = dam_toe_elevation_m;
geometry_handoff.dam_crest_elevation_m = dam_crest_elevation_m;
geometry_handoff.lake = lake;

save(output_path,"X","Y","ZTop","Z","x","y","dx","dy", ...
    "dam_points","dam_max","post_dam","dam_settings", ...
    "parameters","cross_section","centerline","tortuosity", ...
    "dam_centerline_station_m","dam_toe_elevation_m", ...
    "dam_crest_elevation_m","dam_wall_x_m","dam_wall_y_m", ...
    "dam_wall_z_m","lake_maximum_stage_m","lake_footprint_mask", ...
    "lake_touches_upstream_edge","lake","geometry_handoff","-v7.3");
end
