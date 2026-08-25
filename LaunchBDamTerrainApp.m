function app = LaunchBDamTerrainApp
%LAUNCHBDAMTERRAINAPP Open the interactive BDam terrain generator.
%   LaunchBDamTerrainApp can be run from the MATLAB editor or command window.

appFolder = fileparts(mfilename("fullpath"));
if ~contains(path,appFolder)
    addpath(appFolder);
end
app = BDamTerrainApp;
if nargout == 0
    clear app
end
end
