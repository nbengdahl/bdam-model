function config = defaultBDamConfig()
%defaultBDamConfig - Load authoritative scientific parameter defaults
%   CONFIG = defaultBDamConfig() reads the packaged parameter registry.
%   See also buildBDamGeometry, prepareBDamMember
arguments
end
registry = jsondecode(fileread(fullfile(fileparts(mfilename("fullpath")), ...
    "bdam_parameter_schema.json")));
config = registry.defaults;
end
