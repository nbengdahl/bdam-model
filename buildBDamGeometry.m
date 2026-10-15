function buildBDamGeometry(parameters,outputPath)
%buildBDamGeometry - Generate a geometry handoff without figures
%   buildBDamGeometry(PARAMETERS,outputPath) builds terrain and saves it.
%   See also defaultBDamConfig, buildBDamTerrain, saveBDamGeometry
arguments
    parameters (1,1) struct
    outputPath (1,1) string
end
folder = fileparts(outputPath);
if ~isfolder(folder), mkdir(folder); end
profile = buildBDamCrossSection(parameters);
terrain = buildBDamTerrain(parameters,profile);
saveBDamGeometry(outputPath,terrain,profile,parameters);
end
