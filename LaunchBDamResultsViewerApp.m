function app = LaunchBDamResultsViewerApp(outputRoot)
%LAUNCHBDAMRESULTSVIEWERAPP Open the interactive BDam results viewer.
%   LaunchBDamResultsViewerApp opens ../BDam_out relative to this file.
%   LaunchBDamResultsViewerApp(OUTPUTROOT) opens another complete output
%   root containing Geometry/BDamGeometry.mat and Runs/.

arguments
    outputRoot {mustBeTextScalar} = ""
end

appFolder = fileparts(mfilename("fullpath"));
if ~contains(path,appFolder)
    addpath(appFolder);
end
app = BDamResultsViewerApp(outputRoot);
if nargout == 0
    clear app
end
end
