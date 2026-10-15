function app = LaunchBDamResultsViewerApp(outputRoot)
%LAUNCHBDAMRESULTSVIEWERAPP Open the interactive BDam results viewer.
%   LaunchBDamResultsViewerApp selects the verified v0.2.0 local run.
%   LaunchBDamResultsViewerApp(OUTPUTROOT) opens another complete output
%   root containing Geometry/BDamGeometry.mat and Runs/.

arguments
    outputRoot {mustBeTextScalar} = ""
end

if strlength(string(outputRoot)) == 0
    outputRoot = fullfile(getenv("HOME"),"BDamRuns", ...
        "bdam-q0p1-20261015","BDam");
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
