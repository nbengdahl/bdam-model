function [parameters,manifest] = loadBDamTerrainParameters(input_path)
%LOADBDAMTERRAINPARAMETERS Load a complete terrain parameter set from JSON/ZIP.

arguments
    input_path {mustBeTextScalar}
end

input_path = string(input_path);
if ~isfile(input_path)
    error("BDam:ParameterImportFile","Parameter file does not exist: %s",input_path);
end

[~,~,extension] = fileparts(input_path);
if strcmpi(extension,".zip")
    temporary_directory = string(tempname);
    mkdir(temporary_directory);
    cleanup_directory = onCleanup(@()removeTemporaryDirectory(temporary_directory));
    try
        unzip(input_path,temporary_directory);
    catch exception
        error("BDam:ParameterImportZip", ...
            "Could not read the portable ZIP: %s",exception.message);
    end
    json_path = fullfile(temporary_directory,"bdam_geometry.json");
    if ~isfile(json_path)
        error("BDam:ParameterImportManifest", ...
            "The ZIP does not contain bdam_geometry.json at its root.");
    end
elseif strcmpi(extension,".json")
    json_path = input_path;
else
    error("BDam:ParameterImportExtension", ...
        "Select a .json manifest or a portable .zip package.");
end

try
    manifest = jsondecode(fileread(json_path));
catch exception
    error("BDam:ParameterImportJson", ...
        "Could not parse the JSON manifest: %s",exception.message);
end
if ~isstruct(manifest) || ~isscalar(manifest) || ...
        ~isfield(manifest,"schema_version") || ...
        string(manifest.schema_version) ~= "bdam-portable-geometry-v1"
    error("BDam:ParameterImportSchema", ...
        "The selected file is not a bdam-portable-geometry-v1 manifest.");
end
if isfield(manifest,"parameter_schema_version") && ...
        string(manifest.parameter_schema_version) ~= "bdam-terrain-parameters-v1"
    error("BDam:ParameterImportParameterSchema", ...
        "The terrain parameter schema is not supported by this app.");
end
if ~isfield(manifest,"parameters") || ~isstruct(manifest.parameters) || ...
        ~isscalar(manifest.parameters)
    error("BDam:ParameterImportMissing", ...
        "The JSON manifest does not contain a terrain parameters object.");
end

source = manifest.parameters;
vector_fields = ["bottom_widths_m", "depths_m", "left_side_slopes", ...
    "right_side_slopes", "transverse_slopes"];
scalar_fields = ["vertical_offset_m", "dam_max_m", ...
    "domain_length_x_m", "domain_length_y_m", "spacing_x_m", ...
    "spacing_y_m", "origin_x_m", "origin_y_m", "sine_periods", ...
    "sine_amplitude_m", "regional_longitudinal_slope", ...
    "channel_longitudinal_slope", "dam_relative_distance_upstream", ...
    "vertical_exaggeration"];
required = [vector_fields scalar_fields "plot_lake"];
missing = required(~isfield(source,required));
if ~isempty(missing)
    error("BDam:ParameterImportIncomplete", ...
        "The terrain parameter set is incomplete. Missing: %s", ...
        strjoin(missing,", "));
end

parameters = struct();
for field = vector_fields
    value = source.(field);
    if ~isnumeric(value) || ~isreal(value) || numel(value) ~= 2 || ...
            any(~isfinite(value),"all")
        error("BDam:ParameterImportVector", ...
            "%s must contain exactly two finite real numbers.",field);
    end
    parameters.(field) = double(value(:)');
end
for field = scalar_fields
    value = source.(field);
    if ~isnumeric(value) || ~isreal(value) || ~isscalar(value) || ~isfinite(value)
        error("BDam:ParameterImportScalar", ...
            "%s must be one finite real number.",field);
    end
    parameters.(field) = double(value);
end
plot_lake = source.plot_lake;
if ~(islogical(plot_lake) && isscalar(plot_lake)) && ...
        ~(isnumeric(plot_lake) && isscalar(plot_lake) && ...
        isfinite(plot_lake) && ismember(plot_lake,[0 1]))
    error("BDam:ParameterImportLogical", ...
        "plot_lake must be true or false.");
end
parameters.plot_lake = logical(plot_lake);

% Cross-section validation is inexpensive and catches nested geometry,
% domain-fit, grid-spacing, and sign/positivity problems before UI assignment.
buildBDamCrossSection(parameters);
validateTerrainOnlyParameters(parameters);
clear cleanup_directory
end

function validateTerrainOnlyParameters(parameters)
Ly = parameters.domain_length_y_m;
dy = parameters.spacing_y_m;
periods = parameters.sine_periods;
regional_slope = parameters.regional_longitudinal_slope;
channel_slope = parameters.channel_longitudinal_slope;
if Ly <= 0 || dy <= 0
    error("BDam:ParameterImportYGrid", ...
        "Domain Y length and Y grid spacing must be positive.");
end
ny_exact = Ly/dy;
if abs(ny_exact-round(ny_exact)) > 1e-10*max(1,ny_exact) || round(ny_exact) < 2
    error("BDam:ParameterImportYDivisibility", ...
        "Domain Y length must contain an integer number of at least two cells.");
end
if periods < 0
    error("BDam:ParameterImportPeriods", ...
        "Sine-wave periods cannot be negative.");
end
half_period_count = periods/0.5;
if abs(half_period_count-round(half_period_count)) > ...
        10*eps(max(1,abs(half_period_count)))
    error("BDam:ParameterImportPeriods", ...
        "Sine-wave periods must be a multiple of one-half.");
end
if sign(regional_slope) ~= sign(channel_slope)
    error("BDam:ParameterImportSlopeDirection", ...
        "Regional and channel longitudinal slopes must have the same sign.");
end
if parameters.dam_relative_distance_upstream < 0 || ...
        parameters.dam_relative_distance_upstream > 1
    error("BDam:ParameterImportDamFraction", ...
        "The dam fraction must be between zero and one.");
end
if parameters.vertical_exaggeration <= 0
    error("BDam:ParameterImportVerticalExaggeration", ...
        "Vertical exaggeration must be positive.");
end
end

function removeTemporaryDirectory(path_name)
if isfolder(path_name)
    rmdir(path_name,"s");
end
end
