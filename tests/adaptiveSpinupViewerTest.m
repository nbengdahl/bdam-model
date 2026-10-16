classdef adaptiveSpinupViewerTest < matlab.unittest.TestCase
    properties (TestParameter)
        HasWarmup = struct("weeklyOnly",false,"withWarmup",true)
    end
    methods (TestClassSetup)
        function sourcePath(testCase)
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fileparts(fileparts(mfilename("fullpath")))));
        end
    end
    methods (Test)
        function weeklyWorkspacesFollowWarmup(testCase,HasWarmup)
            folder=testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
            root=createFixture(string(folder.Folder),HasWarmup);
            result=loadBDamResults(root);
            expected=(0:(3+double(HasWarmup)))'*365;
            testCase.verifyTrue(result.HasSpinup);
            testCase.verifyEqual(result.Scopes.Spinup.Frames.TimeDays,expected,AbsTol=1e-9);
            testCase.verifyEqual(result.SpinupDurationDays,expected(end),AbsTol=1e-9);
            testCase.verifyEqual(result.Scopes.Monitored.StartDay,0,AbsTol=1e-9);
            testCase.verifyEqual(result.Scopes.All.EndDay,expected(end)+365,AbsTol=1e-9);
        end
    end
end

function root=createFixture(root,hasWarmup)
mkdir(fullfile(root,"Geometry"));
X=[0 0;1 1]; Y=[0 1;0 1]; ZTop=ones(2); geometry_handoff=struct();
save(fullfile(root,"Geometry","BDamGeometry.mat"),"X","Y","ZTop","geometry_handoff");
paths=fullfile(root,"Runs","spinup","weekly","year_"+compose("%02d",(1:3)'));
if hasWarmup
    paths=[fullfile(root,"Runs","spinup","first_annual");paths];
end
paths=[paths;fullfile(root,"Runs","pre_dam","year_01")];
targets=table("head_test",1,1,VariableNames=["name","resolved_x_m","resolved_y_m"]);
for index=1:numel(paths)
    mkdir(paths(index));
    writetable(targets,fullfile(paths(index),"monitoring_targets.csv"));
    fid=fopen(fullfile(paths(index),"bdam.hds"),"w","ieee-le");
    fwrite(fid,[1 1],"int32"); fwrite(fid,[365 365],"double");
    fwrite(fid,uint8('HEAD            '),"uint8");
    fwrite(fid,[2 2 1],"int32"); fwrite(fid,index*ones(4,1),"double"); fclose(fid);
    fid=fopen(fullfile(paths(index),"bdam.ic"),"w");
    fprintf(fid,"BEGIN griddata\n strt LAYERED\n CONSTANT %.17g\nEND griddata\n",index-1); fclose(fid);
end
count=numel(paths)-1;
spinup=table(repmat("spinup_weekly",count+1,1),[1;(1:count)'], ...
    ["initial";repmat("completed_step",count,1)],(0:count)'*365, ...
    [0;repmat(365,count,1)],repmat("weekly",count+1,1), ...
    VariableNames=["phase","phase_year","event","time_days","phase_time_days","spinup_stage"]);
writetable(spinup,fullfile(root,"Runs","spinup_summary.csv"));
monitored=table(["pre_dam";"pre_dam"],[1;1],["initial";"completed_step"], ...
    [0;365],[0;365],[count;count+1], ...
    VariableNames=["phase","phase_year","event","time_days","phase_time_days","head_test_m"]);
writetable(monitored,fullfile(root,"Runs","weekly_summary.csv"));
end
