function manifest = exportBDamPortableGeometry(output_zip,terrain,profile,parameters,display_settings)
%EXPORTBDAMPORTABLEGEOMETRY Write a versioned HDF5/JSON geometry ZIP.

arguments
    output_zip {mustBeTextScalar}
    terrain (1,1) struct
    profile (1,1) struct
    parameters (1,1) struct
    display_settings (1,1) struct
end

schema = "bdam-portable-geometry-v1";
output_zip = string(output_zip);
if strlength(output_zip) == 0
    error("BDam:PortableExportPath","The portable export path cannot be empty.");
end

temporary_directory = string(tempname);
mkdir(temporary_directory);
cleanup_directory = onCleanup(@()removeTemporaryDirectory(temporary_directory));
h5_name = "bdam_geometry.h5";
json_name = "bdam_geometry.json";
h5_path = fullfile(temporary_directory,h5_name);
json_path = fullfile(temporary_directory,json_name);

shoreline_segments = terrain.lake_outline_segments_m;
shoreline_counts = cellfun(@(points)size(points,1),shoreline_segments);
shoreline_offsets = int64([0; cumsum(shoreline_counts(:))]);
if isempty(shoreline_segments)
    shoreline_vertices = zeros(0,2);
else
    shoreline_vertices = vertcat(shoreline_segments{:});
end
dam_wall_vertices = [terrain.dam_wall_x_m(:), ...
    terrain.dam_wall_y_m(:),terrain.dam_wall_z_m(:)];

datasets = struct("path",{},"shape",{},"units",{},"description",{});
datasets(end+1) = writeArray(h5_path,"/grid/X_m",terrain.X_m,"m", ...
    "Native MATLAB cell-center X coordinates [x,y].");
datasets(end+1) = writeArray(h5_path,"/grid/Y_m",terrain.Y_m,"m", ...
    "Native MATLAB cell-center Y coordinates [x,y].");
datasets(end+1) = writeArray(h5_path,"/grid/ZTop_m",terrain.ZTop_m,"m", ...
    "Terrain elevation at cell centers in native MATLAB [x,y] orientation.");
datasets(end+1) = writeArray(h5_path,"/grid/x_centers_m",terrain.x_m,"m", ...
    "Ascending X cell-center coordinate vector.");
datasets(end+1) = writeArray(h5_path,"/grid/y_centers_m",terrain.y_m,"m", ...
    "Ascending Y cell-center coordinate vector.");
datasets(end+1) = writeArray(h5_path,"/grid/lake_footprint_at_crest", ...
    uint8(terrain.lake_footprint_mask),"1", ...
    "Connected crest-stage lake mask in native MATLAB [x,y] orientation.");

datasets(end+1) = writeArray(h5_path,"/cross_section/normal_distance_m", ...
    profile.offset_m,"m","Signed normal distance from the centerline.");
datasets(end+1) = writeArray(h5_path,"/cross_section/elevation_m", ...
    profile.elevation_m,"m","Full channel and floodplain profile elevation.");
datasets(end+1) = writeArray(h5_path,"/cross_section/channel_profile_m", ...
    profile.channel_profile_m,"m","Channel-only profile used for grade blending.");
datasets(end+1) = writeArray(h5_path,"/cross_section/bank_offsets_m", ...
    profile.bank_offsets_m,"m","Negative- and positive-normal dam bank offsets.");

datasets(end+1) = writeArray(h5_path,"/centerline/x_m", ...
    terrain.centerline_x_m,"m","Centerline X coordinates within the domain.");
datasets(end+1) = writeArray(h5_path,"/centerline/y_m", ...
    terrain.centerline_y_m,"m","Centerline Y coordinates within the domain.");
datasets(end+1) = writeArray(h5_path,"/centerline/elevation_m", ...
    terrain.centerline_elevation_m,"m","Channel-bottom elevation along the centerline.");

datasets(end+1) = writeArray(h5_path,"/dam/endpoints_xy_m", ...
    terrain.dam_points_m,"m","Dam endpoints ordered negative to positive normal offset.");
datasets(end+1) = writeArray(h5_path,"/dam/wall_vertices_xyz_m", ...
    dam_wall_vertices,"m","Four dam-wall polygon vertices.");

datasets(end+1) = writeArray(h5_path,"/lake/display_X_m", ...
    terrain.lake_display_X_m,"m","Refined lake-display X coordinates.");
datasets(end+1) = writeArray(h5_path,"/lake/display_Y_m", ...
    terrain.lake_display_Y_m,"m","Refined lake-display Y coordinates.");
datasets(end+1) = writeArray(h5_path,"/lake/display_Z_m", ...
    terrain.lake_display_Z_m,"m","Refined horizontal lake surface; NaN outside footprint.");
datasets(end+1) = writeArray(h5_path,"/lake/shoreline_vertices_xy_m", ...
    shoreline_vertices,"m","Concatenated refined shoreline vertices.");
datasets(end+1) = writeArray(h5_path,"/lake/shoreline_segment_offsets_0based", ...
    shoreline_offsets,"1","Zero-based shoreline segment offsets, including final length.");
datasets(end+1) = writeArray(h5_path,"/display/parula_rgb", ...
    parula(256),"1","Exact MATLAB parula color table used by the terrain plot.");

h5writeatt(h5_path,"/","schema_version",char(schema));
h5writeatt(h5_path,"/","array_storage_order","F");
h5writeatt(h5_path,"/","producer","BDamTerrainApp");
validateHdf5(h5_path,datasets,schema);
h5_checksum = sha256File(h5_path);

manifest = struct();
manifest.schema_version = schema;
manifest.package_type = "bdam-portable-geometry";
manifest.producer = "BDamTerrainApp";
manifest.created_at = string(datetime("now","Format","yyyy-MM-dd'T'HH:mm:ss"));
manifest.hdf5_file = h5_name;
manifest.hdf5_sha256 = h5_checksum;
manifest.parameter_schema_version = "bdam-terrain-parameters-v1";
manifest.units = struct("horizontal","m","elevation","m","slope","dimensionless");
manifest.coordinate_system = struct( ...
    "type","local_cartesian", ...
    "crs",[], ...
    "vertical_datum","local synthetic datum; unspecified", ...
    "x_positive","right", ...
    "y_positive","toward increasing local Y", ...
    "z_positive","up", ...
    "rotation_degrees",0);
manifest.grid = struct( ...
    "type","structured_rectilinear_cell_centered", ...
    "native_shape_x_y",int64(size(terrain.ZTop_m)), ...
    "nx",int64(size(terrain.ZTop_m,1)), ...
    "ny",int64(size(terrain.ZTop_m,2)), ...
    "origin_x_domain_edge_m",parameters.origin_x_m, ...
    "origin_y_domain_edge_m",parameters.origin_y_m, ...
    "dx_m",parameters.spacing_x_m, ...
    "dy_m",parameters.spacing_y_m, ...
    "native_array_order","MATLAB [x,y], flattened column-major and reconstructed with order F", ...
    "mf6_conversion","transpose native [x,y] to [row,column], then reverse row axis so row 0 is maximum Y");
manifest.parameters = parameters;
manifest.regeneration = struct( ...
    "parameter_set_complete",true, ...
    "parameter_object","parameters", ...
    "matlab_cross_section_function","buildBDamCrossSection", ...
    "matlab_terrain_function","buildBDamTerrain", ...
    "description","The parameters object contains every user-controlled input required to regenerate the cross section, terrain, dam, and lake display geometry.");
manifest.centerline = struct( ...
    "tortuosity",terrain.tortuosity, ...
    "total_distance_m",terrain.total_centerline_distance_m);
manifest.dam = struct( ...
    "maximum_height_above_toe_m",parameters.dam_max_m, ...
    "toe_elevation_m",terrain.dam_toe_elevation_m, ...
    "crest_elevation_m",terrain.dam_crest_elevation_m, ...
    "fraction_upstream",parameters.dam_relative_distance_upstream, ...
    "distance_upstream_m",terrain.dam_distance_upstream_m, ...
    "centerline_station_y_m",terrain.dam_centerline_station_m, ...
    "upstream_side",terrain.dam_upstream_side, ...
    "endpoints_dataset","/dam/endpoints_xy_m");
manifest.lake = struct( ...
    "stage_m",terrain.lake_stage_m, ...
    "cell_count",int64(nnz(terrain.lake_footprint_mask)), ...
    "area_m2",nnz(terrain.lake_footprint_mask)*parameters.spacing_x_m*parameters.spacing_y_m, ...
    "touches_upstream_edge",terrain.lake_touches_upstream_edge, ...
    "shoreline_segment_count",int64(numel(shoreline_segments)));
manifest.display = display_settings;
manifest.datasets = datasets;

json_text = jsonencode(manifest,PrettyPrint=true);
file_id = fopen(json_path,"w");
if file_id < 0
    error("BDam:PortableManifest","Could not create the portable JSON manifest.");
end
cleanup_file = onCleanup(@()fcloseIfOpen(file_id));
fprintf(file_id,"%s\n",json_text);
clear cleanup_file

decoded = jsondecode(fileread(json_path));
if string(decoded.schema_version) ~= schema || ...
        string(decoded.hdf5_sha256) ~= h5_checksum
    error("BDam:PortableManifestValidation", ...
        "Portable manifest failed its write/read validation.");
end

temporary_zip = temporary_directory + ".zip";
cleanup_zip = onCleanup(@()deleteIfPresent(temporary_zip));
zip(temporary_zip,[h5_name json_name],temporary_directory);
[moved,message] = movefile(temporary_zip,output_zip,"f");
if ~moved
    error("BDam:PortableZipMove","Could not finalize portable ZIP: %s",message);
end
clear cleanup_zip cleanup_directory
end

function metadata = writeArray(h5_path,base_path,value,units,description)
shape = int64(size(value));
if islogical(value)
    value = uint8(value);
end
flat = value(:);
logical_count = numel(flat);
if isempty(flat)
    flat = zeros(1,1,"double");
end
h5create(h5_path,base_path+"/data",size(flat),"Datatype",class(flat));
h5write(h5_path,base_path+"/data",flat);
h5create(h5_path,base_path+"/shape",size(shape),"Datatype","int64");
h5write(h5_path,base_path+"/shape",shape);
h5writeatt(h5_path,base_path,"order","F");
h5writeatt(h5_path,base_path,"logical_element_count",int64(logical_count));
h5writeatt(h5_path,base_path,"units",char(units));
h5writeatt(h5_path,base_path,"description",char(description));
metadata = struct("path",string(base_path),"shape",shape, ...
    "units",string(units),"description",string(description));
end

function validateHdf5(h5_path,datasets,schema)
if string(h5readatt(h5_path,"/","schema_version")) ~= schema
    error("BDam:PortableHdf5Schema","HDF5 schema attribute does not match.");
end
for index = 1:numel(datasets)
    base = datasets(index).path;
    shape = int64(h5read(h5_path,base+"/shape"));
    data = h5read(h5_path,base+"/data");
    expected = prod(double(shape));
    count = double(h5readatt(h5_path,base,"logical_element_count"));
    if count ~= expected || numel(data) < max(1,expected)
        error("BDam:PortableHdf5Shape", ...
            "Dataset %s failed shape validation.",base);
    end
end
end

function checksum = sha256File(path_name)
digest = java.security.MessageDigest.getInstance("SHA-256");
file_id = fopen(path_name,"r");
if file_id < 0
    error("BDam:PortableChecksum","Could not open HDF5 file for checksum.");
end
cleanup_file = onCleanup(@()fcloseIfOpen(file_id));
while true
    bytes = fread(file_id,1024*1024,"*uint8");
    if isempty(bytes)
        break
    end
    digest.update(bytes);
end
raw = typecast(digest.digest(),"uint8");
checksum = lower(string(reshape(dec2hex(raw,2).',1,[])));
end

function fcloseIfOpen(file_id)
if file_id >= 0
    fclose(file_id);
end
end

function deleteIfPresent(path_name)
if isfile(path_name)
    delete(path_name);
end
end

function removeTemporaryDirectory(path_name)
if isfolder(path_name)
    rmdir(path_name,"s");
end
end
