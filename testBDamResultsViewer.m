function tests = testBDamResultsViewer
%TESTBDAMRESULTSVIEWER Tests for the MF6 reader and completed-run loader.
tests = functiontests(localfunctions);
end

function testReaderIndexesTimesLayersAndOrientation(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
path = fullfile(folder.Folder,"synthetic.hds");
top1 = [11 12;21 22;31 32];
bottom1 = [101 102;201 202;301 302];
top2 = top1+0.5;
bottom2 = bottom1+0.5;
writeHeadFile(path,[7 14],cat(4,cat(3,top1,bottom1),cat(3,top2,bottom2)));

reader = BDamMF6HeadReader(path);
testCase.verifyEqual(reader.Times,[7;14],"AbsTol",1.0e-12);
testCase.verifyEqual(reader.NumFrames,2);
testCase.verifyEqual(reader.NumLayers,2);
testCase.verifyEqual(reader.NumColumns,3);
testCase.verifyEqual(reader.NumRows,2);
testCase.verifyEqual(reader.readLayer(1,1),top1);
testCase.verifyEqual(reader.readLayer(2,2),bottom2);
testCase.verifyEqual(reader.readSnapshot(1),cat(3,top1,bottom1));
end

function testReaderUsesUppermostValidHead(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
path = fullfile(folder.Folder,"dry_top.hds");
top = [1 -1.0e30;3 NaN];
bottom = [10 20;30 40];
writeHeadFile(path,1,cat(3,top,bottom));

reader = BDamMF6HeadReader(path);
testCase.verifyEqual(reader.readWaterSurface(1),[1 20;3 40]);
end

function testReaderRejectsTruncatedValues(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
path = fullfile(folder.Folder,"truncated.hds");
fileID = fopen(path,"w","ieee-le");
cleanup = onCleanup(@()fclose(fileID));
writeHeader(fileID,1,1,1,1,"HEAD",2,2,1);
fwrite(fileID,[1 2],"double");
clear cleanup

testCase.verifyError(@()BDamMF6HeadReader(path),"BDam:HeadFileTruncated");
end

function testReaderRejectsWrongRecordLabel(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
path = fullfile(folder.Folder,"wrong_label.hds");
fileID = fopen(path,"w","ieee-le");
cleanup = onCleanup(@()fclose(fileID));
writeHeader(fileID,1,1,1,1,"DRAWDOWN",1,1,1);
fwrite(fileID,1,"double");
clear cleanup

testCase.verifyError(@()BDamMF6HeadReader(path),"BDam:HeadFileLabel");
end

function testReaderRejectsIncompleteLayerSet(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
path = fullfile(folder.Folder,"missing_layer.hds");
fileID = fopen(path,"w","ieee-le");
cleanup = onCleanup(@()fclose(fileID));
writeHeader(fileID,1,1,1,1,"HEAD",1,1,1); fwrite(fileID,1,"double");
writeHeader(fileID,1,1,1,1,"HEAD",1,1,3); fwrite(fileID,3,"double");
clear cleanup

testCase.verifyError(@()BDamMF6HeadReader(path),"BDam:HeadFileLayers");
end

function testLoaderRejectsIncompleteOutputRoot(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
testCase.verifyError(@()loadBDamResults(folder.Folder),"BDam:ResultsGeometry");
end

function testLoaderAcceptsZeroSpinupOutput(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
root = createZeroSpinupFixture(folder.Folder);

results = loadBDamResults(root);
testCase.verifyFalse(results.HasSpinup);
testCase.verifyEqual(results.SpinupDurationDays,0);
testCase.verifyFalse(isfield(results.Scopes,"Spinup"));
testCase.verifyEqual(results.Scopes.All.Frames,results.Scopes.Monitored.Frames);
testCase.verifyEqual(results.Scopes.All.Summary,results.Scopes.Monitored.Summary);
testCase.verifyEqual(results.Scopes.All.StartDay,0,"AbsTol",1.0e-12);
testCase.verifyEqual(results.Scopes.All.EndDay,14,"AbsTol",1.0e-12);
end

function testLoaderRejectsHalfPresentSpinupOutput(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
root = createZeroSpinupFixture(folder.Folder);
fileID = fopen(fullfile(root,"Runs","spinup_summary.csv"),"w");
fclose(fileID);

testCase.verifyError(@()loadBDamResults(root),"BDam:ResultsSummary");
end

function testViewerOffersTwentyFramesPerSecond(testCase)
app = BDamResultsViewerApp();
cleanup = onCleanup(@()delete(app));
dropdowns = findall(app.UIFigure,"Type","uidropdown");
hasTwentyFps = false;
for index = 1:numel(dropdowns)
    values = dropdowns(index).ItemsData;
    if isnumeric(values) && isequal(values,[1 2 5 10 20])
        hasTwentyFps = true;
    end
end
testCase.verifyTrue(hasTwentyFps);
clear cleanup
end

function testViewerLoadsZeroSpinupWithoutSpinupScope(testCase)
folder = testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
root = createZeroSpinupFixture(folder.Folder);
app = LaunchBDamResultsViewerApp(root);
cleanup = onCleanup(@()delete(app));
buttons = findall(app.UIFigure,"Type","uibutton");
loadButton = buttons(arrayfun(@(button)string(button.Text) == "Load",buttons));
testCase.assertNumElements(loadButton,1);
feval(loadButton.ButtonPushedFcn,loadButton,[]);

dropdowns = findall(app.UIFigure,"Type","uidropdown");
scopeDropdown = [];
for index = 1:numel(dropdowns)
    if isequal(string(dropdowns(index).ItemsData),["Monitored" "All"])
        scopeDropdown = dropdowns(index);
    end
end
testCase.assertNotEmpty(scopeDropdown);
testCase.verifyEqual(string(scopeDropdown.Value),"Monitored");
testCase.verifyFalse(any(string(scopeDropdown.ItemsData) == "Spinup"));
slider = findall(app.UIFigure,"Type","uislider");
testCase.verifyEqual(slider.Limits,[0 1]);
testCase.verifyEqual(slider.Value,0);
slider.Value = 1;
feval(slider.ValueChangedFcn,slider,[]);
slider.Value = 0;
feval(slider.ValueChangedFcn,slider,[]);
labels = findall(app.UIFigure,"Type","uilabel");
testCase.verifyTrue(any(arrayfun(@(label)contains(string(label.Text), ...
    "Frame 0/1"),labels)));
clear cleanup
end

function testCompletedRunWhenAvailable(testCase)
package = fileparts(mfilename("fullpath"));
root = fullfile(package,"..","BDam_out");
testCase.assumeTrue(isfile(fullfile(root,"Runs","weekly_summary.csv")), ...
    "The optional completed BDam_out integration fixture is unavailable.");

results = loadBDamResults(root);
testCase.verifyEqual(height(results.Scopes.Monitored.Frames),104);
testCase.verifyEqual(height(results.Scopes.All.Frames),180);
testCase.verifyEqual(results.Scopes.Monitored.EndDay,730,"AbsTol",1.0e-8);
testCase.verifyEqual(results.Scopes.All.EndDay,1825,"AbsTol",1.0e-8);

firstFrame = results.Scopes.Monitored.Frames(1,:);
target = results.Targets(1,:);
layer = target.resolved_layer_top_down;
heads = results.Readers{firstFrame.ReaderIndex}.readLayer(firstFrame.LocalFrame,layer);
observed = heads(target.resolved_i_x,target.resolved_i_y);
summary = results.Scopes.Monitored.Summary;
row = find(summary.event == "completed_step",1);
variable = target.name+"_m";
testCase.verifyEqual(observed,summary.(variable)(row),"AbsTol",1.0e-10);
end

function testViewerCachesSurfacesAndRetainsMapHandles(testCase)
package = fileparts(mfilename("fullpath"));
root = fullfile(package,"..","BDam_out");
testCase.assumeTrue(isfile(fullfile(root,"Runs","weekly_summary.csv")), ...
    "The optional completed BDam_out integration fixture is unavailable.");

app = LaunchBDamResultsViewerApp(root);
cleanup = onCleanup(@()delete(app));
buttons = findall(app.UIFigure,"Type","uibutton");
loadButton = [];
for index = 1:numel(buttons)
    if string(buttons(index).Text) == "Load"
        loadButton = buttons(index);
    end
end
testCase.assertNotEmpty(loadButton);
feval(loadButton.ButtonPushedFcn,loadButton,[]);

statusAreas = findall(app.UIFigure,"Type","uitextarea");
statusText = strjoin(string(statusAreas(1).Value)," ");
testCase.verifyTrue(contains(statusText,"Memory cache:"));
imageHandle = findall(app.MapAxes,"Type","image");
contourHandle = findall(app.MapAxes,"Type","contour");
testCase.assertNumElements(imageHandle,1);
testCase.assertNumElements(contourHandle,1);

results = loadBDamResults(root);
frame = results.Scopes.Monitored.Frames(2,:);
surface = results.Readers{frame.ReaderIndex}.readWaterSurface(frame.LocalFrame);
expectedDepth = results.ZTop-surface;
slider = findall(app.UIFigure,"Type","uislider");
slider.Value = 1;
feval(slider.ValueChangedFcn,slider,[]);
testCase.verifyEqual(imageHandle.CData,expectedDepth,"AbsTol",1.0e-12);
testCase.verifyEqual(contourHandle.ZData,surface,"AbsTol",1.0e-12);

slider.Value = 2;
feval(slider.ValueChangedFcn,slider,[]);
testCase.verifyEqual(findall(app.MapAxes,"Type","image"),imageHandle);
testCase.verifyEqual(findall(app.MapAxes,"Type","contour"),contourHandle);
clear cleanup
end

function writeHeadFile(path,times,values)
% VALUES is [ncol,nrow,nlay,nframe], with singleton dimensions permitted.
dimensions = size(values);
dimensions(end+1:4) = 1;
ncol = dimensions(1); nrow = dimensions(2);
nlay = dimensions(3); nframe = dimensions(4);
assert(nframe == numel(times));
fileID = fopen(path,"w","ieee-le");
cleanup = onCleanup(@()fclose(fileID));
for frame = 1:nframe
    for layer = 1:nlay
        writeHeader(fileID,frame,frame,times(frame),times(frame), ...
            "HEAD",ncol,nrow,layer);
        native = values(:,:,layer,frame);
        fwrite(fileID,fliplr(native),"double");
    end
end
end

function root = createZeroSpinupFixture(root)
geometryPath = fullfile(root,"Geometry");
workspace = fullfile(root,"Runs","pre_dam","year_01");
mkdir(geometryPath);
mkdir(workspace);
X = [0 0;1 1];
Y = [0 1;0 1];
ZTop = ones(2);
geometry_handoff = struct();
save(fullfile(geometryPath,"BDamGeometry.mat"),"X","Y","ZTop","geometry_handoff");

first = ones(2);
second = 2*ones(2);
writeHeadFile(fullfile(workspace,"bdam.hds"),[7 14],cat(4,first,second));
targets = table("head_test",1,1, ...
    VariableNames=["name","resolved_x_m","resolved_y_m"]);
writetable(targets,fullfile(workspace,"monitoring_targets.csv"));
summary = table(["pre_dam";"pre_dam";"pre_dam"],[1;1;1], ...
    ["initial";"completed_step";"completed_step"],[0;7;14],[0;7;14], ...
    [1;1;2],VariableNames=["phase","phase_year","event","time_days", ...
    "phase_time_days","head_test_m"]);
writetable(summary,fullfile(root,"Runs","weekly_summary.csv"));
end

function writeHeader(fileID,kstp,kper,pertim,totim,label,ncol,nrow,layer)
fwrite(fileID,kstp,"int32");
fwrite(fileID,kper,"int32");
fwrite(fileID,pertim,"double");
fwrite(fileID,totim,"double");
label = char(label);
label = [label repmat(' ',1,16-numel(label))];
fwrite(fileID,uint8(label(1:16)),"uint8");
fwrite(fileID,ncol,"int32");
fwrite(fileID,nrow,"int32");
fwrite(fileID,layer,"int32");
end
