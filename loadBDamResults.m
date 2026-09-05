function results = loadBDamResults(outputRoot)
%LOADBDAMRESULTS Validate and index a complete BDam output root.
%   RESULTS = LOADBDAMRESULTS(OUTPUTROOT) reads geometry and monitoring
%   summaries, indexes every MF6 head file, and constructs Spinup,
%   Monitored pre/post, and All timeline scopes. Model outputs are read only.

arguments
    outputRoot {mustBeTextScalar}
end

outputRoot = string(outputRoot);
if strlength(outputRoot) == 0 || ~isfolder(outputRoot)
    error("BDam:ResultsRoot", ...
        "The selected BDam output root is not a folder: %s",outputRoot);
end
outputRoot = string(char(java.io.File(char(outputRoot)).getCanonicalPath()));
geometryPath = fullfile(outputRoot,"Geometry","BDamGeometry.mat");
runsPath = fullfile(outputRoot,"Runs");
if ~isfile(geometryPath)
    error("BDam:ResultsGeometry", ...
        "Missing Geometry/BDamGeometry.mat under %s.",outputRoot);
end
if ~isfolder(runsPath)
    error("BDam:ResultsRuns", ...
        "Missing Runs folder under %s.",outputRoot);
end

geometry = load(geometryPath,"X","Y","ZTop","geometry_handoff");
requiredGeometry = ["X","Y","ZTop"];
if ~all(isfield(geometry,requiredGeometry))
    error("BDam:ResultsGeometry", ...
        "Geometry must contain X, Y, and ZTop arrays.");
end
if ~isequal(size(geometry.X),size(geometry.Y),size(geometry.ZTop)) || ...
        ~ismatrix(geometry.ZTop) || any(~isfinite(geometry.ZTop),"all")
    error("BDam:ResultsGeometry", ...
        "Geometry X, Y, and ZTop must be equal-sized finite 2-D arrays.");
end

spinupSummaryPath = fullfile(runsPath,"spinup_summary.csv");
weeklyPath = fullfile(runsPath,"weekly_summary.csv");
dailyPath = fullfile(runsPath,"daily_summary.csv");
hasSpinupSummary = isfile(spinupSummaryPath);
spinupDefinitions = spinupWorkspaces(runsPath);
hasSpinupHeads = ~isempty(spinupDefinitions);
if hasSpinupSummary ~= hasSpinupHeads
    error("BDam:ResultsSummary", ...
        "Spinup output is incomplete under %s. Runs/spinup_summary.csv "+ ...
        "and completed spinup head workspaces must either both exist or both be absent.", ...
        outputRoot);
end
if isfile(weeklyPath) == isfile(dailyPath)
    error("BDam:ResultsSummary", ...
        "Runs must contain exactly one of weekly_summary.csv or daily_summary.csv.");
end
if isfile(weeklyPath)
    monitoredSummaryPath = weeklyPath;
    timeResolution = "weekly";
else
    monitoredSummaryPath = dailyPath;
    timeResolution = "daily";
end

monitoredSummary = normalizeSummary(readtable(monitoredSummaryPath, ...
    "VariableNamingRule","preserve"));
validateSummary(monitoredSummary,monitoredSummaryPath,false);
if hasSpinupSummary
    spinupSummary = normalizeSummary(readtable(spinupSummaryPath, ...
        "VariableNamingRule","preserve"));
    validateSummary(spinupSummary,spinupSummaryPath,true);
end

workspaceDefinitions = struct("Path",{},"Phase",{},"PhaseYear",{});
if hasSpinupHeads
    workspaceDefinitions = spinupDefinitions;
end
workspaceDefinitions = [workspaceDefinitions; annualWorkspaces(runsPath,"pre_dam"); ...
    annualWorkspaces(runsPath,"post_dam")];
if ~any(string({workspaceDefinitions.Phase}) ~= "spinup")
    error("BDam:ResultsHeads", ...
        "No pre_dam or post_dam annual head workspaces were found.");
end

readers = cell(numel(workspaceDefinitions),1);
initialSurfaces = cell(numel(workspaceDefinitions),1);
targetReference = table();
for index = 1:numel(workspaceDefinitions)
    workspace = workspaceDefinitions(index);
    headPath = fullfile(workspace.Path,"bdam.hds");
    targetPath = fullfile(workspace.Path,"monitoring_targets.csv");
    if ~isfile(headPath) || ~isfile(targetPath)
        error("BDam:ResultsWorkspace", ...
            "Workspace %s must contain bdam.hds and monitoring_targets.csv.", ...
            workspace.Path);
    end
    readers{index} = BDamMF6HeadReader(headPath);
    if readers{index}.NumColumns ~= size(geometry.ZTop,1) || ...
            readers{index}.NumRows ~= size(geometry.ZTop,2)
        error("BDam:ResultsGrid", ...
            "Head grid in %s does not match Geometry/BDamGeometry.mat.", ...
            workspace.Path);
    end
    initialSurfaces{index} = readBDamMF6InitialWaterSurface( ...
        fullfile(workspace.Path,"bdam.ic"),readers{index}.NumColumns, ...
        readers{index}.NumRows,readers{index}.NumLayers);
    targets = normalizeTargets(readtable(targetPath,"VariableNamingRule","preserve"));
    if isempty(targetReference)
        targetReference = targets;
    elseif ~sameTargets(targetReference,targets)
        error("BDam:ResultsTargets", ...
            "Monitoring targets differ between completed workspaces.");
    end
end

[monitoredFrames,monitoredDuration] = buildMonitoredFrames( ...
    readers,workspaceDefinitions,monitoredSummary);

scopes = struct();
if hasSpinupHeads
    [spinupFrames,spinupDuration] = buildSpinupFrames( ...
        readers,workspaceDefinitions,spinupSummary);
    allMonitoredSummary = monitoredSummary;
    allMonitoredSummary.time_days = allMonitoredSummary.time_days+spinupDuration;
    allSummary = verticallyConcatenateSummaries(spinupSummary,allMonitoredSummary);
    % The monitored initial state is the same continuous state as the final
    % spinup frame, so keep it in the Monitored scope but do not duplicate it
    % at the Spinup/Monitored boundary of the All scope.
    allMonitoredFrames = monitoredFrames(2:end,:);
    allMonitoredFrames.TimeDays = allMonitoredFrames.TimeDays+spinupDuration;
    allFrames = [spinupFrames;allMonitoredFrames];
    scopes.Spinup = makeScope("Spinup",spinupSummary,spinupFrames);
else
    spinupDuration = 0.0;
    allSummary = monitoredSummary;
    allFrames = monitoredFrames;
end
scopes.Monitored = makeScope("Monitored pre/post",monitoredSummary,monitoredFrames);
scopes.All = makeScope("All",allSummary,allFrames);

results = struct();
results.OutputRoot = outputRoot;
results.GeometryPath = string(geometryPath);
results.X = geometry.X;
results.Y = geometry.Y;
results.ZTop = geometry.ZTop;
results.Readers = readers;
results.InitialSurfaces = initialSurfaces;
results.Workspaces = workspaceDefinitions;
results.Targets = targetReference;
results.Scopes = scopes;
results.TimeResolution = timeResolution;
results.HasSpinup = hasSpinupHeads;
results.SpinupDurationDays = spinupDuration;
results.MonitoredDurationDays = monitoredDuration;
results.Variables = monitoringVariables(allSummary);
end

function summary = normalizeSummary(summary)
names = string(summary.Properties.VariableNames);
textNames = ["phase","event","spinup_stage"];
for name = textNames
    if ismember(name,names)
        summary.(name) = string(summary.(name));
    end
end
end

function validateSummary(summary,path,isSpinup)
required = ["phase","phase_year","event","time_days","phase_time_days"];
if ~all(ismember(required,string(summary.Properties.VariableNames)))
    error("BDam:ResultsSummary", ...
        "Summary %s lacks required phase/time columns.",path);
end
if isempty(summary) || any(~isfinite(summary.time_days)) || ...
        any(diff(summary.time_days) < -1.0e-8)
    error("BDam:ResultsSummary", ...
        "Summary times must be finite and nondecreasing in %s.",path);
end
if isSpinup && ~ismember("spinup_stage",string(summary.Properties.VariableNames))
    error("BDam:ResultsSummary", ...
        "Spinup summary %s lacks spinup_stage.",path);
end
end

function definitions = annualWorkspaces(runsPath,phase)
phasePath = fullfile(runsPath,phase);
definitions = struct("Path",{},"Phase",{},"PhaseYear",{});
if ~isfolder(phasePath)
    return
end
entries = dir(fullfile(phasePath,"year_*"));
years = [];
paths = strings(0,1);
for index = 1:numel(entries)
    token = regexp(entries(index).name,"^year_(\d+)$","tokens","once");
    if entries(index).isdir && ~isempty(token)
        years(end+1,1) = str2double(token{1}); %#ok<AGROW>
        paths(end+1,1) = string(fullfile(entries(index).folder,entries(index).name)); %#ok<AGROW>
    end
end
if isempty(years)
    return
end
[years,order] = sort(years);
paths = paths(order);
if any(diff(years) == 0)
    error("BDam:ResultsWorkspace", ...
        "Duplicate %s annual workspace numbers were found.",phase);
end
for index = 1:numel(years)
    definitions(index,1) = struct( ...
        "Path",paths(index),"Phase",string(phase),"PhaseYear",years(index));
end
end

function definitions = spinupWorkspaces(runsPath)
definitions = struct("Path",{},"Phase",{},"PhaseYear",{});
names = ["first_annual" "staged"];
for index = 1:numel(names)
    path = fullfile(runsPath,"spinup",names(index));
    if isfile(fullfile(path,"bdam.hds"))
        definitions(end+1,1) = struct( ... %#ok<AGROW>
            "Path",string(path),"Phase","spinup","PhaseYear",index);
    end
end
end

function targets = normalizeTargets(targets)
required = ["name","resolved_x_m","resolved_y_m"];
if ~all(ismember(required,string(targets.Properties.VariableNames))) || isempty(targets)
    error("BDam:ResultsTargets", ...
        "monitoring_targets.csv lacks required name and resolved-coordinate columns.");
end
targets.name = lower(string(targets.name));
if any(~isfinite(targets.resolved_x_m)) || any(~isfinite(targets.resolved_y_m))
    error("BDam:ResultsTargets", ...
        "Monitoring target coordinates must be finite.");
end
end

function equal = sameTargets(left,right)
equal = height(left) == height(right) && ...
    isequal(left.name,right.name) && ...
    max(abs(left.resolved_x_m-right.resolved_x_m),[],"all") < 1.0e-9 && ...
    max(abs(left.resolved_y_m-right.resolved_y_m),[],"all") < 1.0e-9;
end

function [frames,duration] = buildSpinupFrames(readers,definitions,summary)
completed = summary.event == "completed_step";
rows = find(completed);
frames = table([],[],[],strings(0,1),[],[], ...
    VariableNames=["ReaderIndex","LocalFrame","TimeDays","Phase", ...
    "PhaseYear","PhaseTimeDays"]);
duration = 0;
cursor = 1;
firstReader = find(string({definitions.Phase}) == "spinup",1);
initialRow = find(summary.event == "initial",1);
if isempty(firstReader) || isempty(initialRow)
    error("BDam:ResultsAlignment", ...
        "Spinup results lack an initial state for the frame-zero map.");
end
frames = [frames;table(firstReader,0,0,string(summary.phase(initialRow)), ...
    summary.phase_year(initialRow),summary.phase_time_days(initialRow), ...
    VariableNames=frames.Properties.VariableNames)];
for readerIndex = 1:numel(readers)
    if definitions(readerIndex).Phase ~= "spinup"
        continue
    end
    reader = readers{readerIndex};
    stop = cursor+reader.NumFrames-1;
    if stop > numel(rows)
        error("BDam:ResultsAlignment", ...
            "Spinup summary contains fewer completed steps than the head workspaces.");
    end
    blockRows = rows(cursor:stop);
    globalTimes = duration+reader.Times;
    if ~timesMatch(summary.time_days(blockRows),globalTimes)
        error("BDam:ResultsAlignment", ...
            "Spinup summary completed steps do not align with the spinup head workspaces.");
    end
    block = table(repmat(readerIndex,reader.NumFrames,1), ...
        transpose(1:reader.NumFrames),globalTimes,string(summary.phase(blockRows)), ...
        summary.phase_year(blockRows),summary.phase_time_days(blockRows), ...
        VariableNames=frames.Properties.VariableNames);
    frames = [frames;block]; %#ok<AGROW>
    duration = duration+reader.Times(end);
    cursor = stop+1;
end
if cursor-1 ~= numel(rows)
    error("BDam:ResultsAlignment", ...
        "Spinup summary contains more completed steps than the head workspaces.");
end
end

function [frames,duration] = buildMonitoredFrames(readers,definitions,summary)
frames = table([],[],[],strings(0,1),[],[], ...
    VariableNames=["ReaderIndex","LocalFrame","TimeDays","Phase", ...
    "PhaseYear","PhaseTimeDays"]);
duration = 0;
firstReader = find(string({definitions.Phase}) ~= "spinup",1);
initialRows = find(summary.event == "initial");
if isempty(firstReader) || isempty(initialRows)
    error("BDam:ResultsAlignment", ...
        "Monitored results lack an initial state for the frame-zero map.");
end
[~,firstInitial] = min(summary.time_days(initialRows));
initialRow = initialRows(firstInitial);
frames = [frames;table(firstReader,0,0,string(summary.phase(initialRow)), ...
    summary.phase_year(initialRow),summary.phase_time_days(initialRow), ...
    VariableNames=frames.Properties.VariableNames)];
for readerIndex = 1:numel(readers)
    reader = readers{readerIndex};
    definition = definitions(readerIndex);
    if definition.Phase == "spinup"
        continue
    end
    mask = summary.event == "completed_step" & ...
        summary.phase == definition.Phase & ...
        summary.phase_year == definition.PhaseYear;
    rows = find(mask);
    if numel(rows) ~= reader.NumFrames || ...
            ~timesMatch(summary.phase_time_days(rows),reader.Times)
        error("BDam:ResultsAlignment", ...
            "Summary rows do not align with %s year %d head times.", ...
            definition.Phase,definition.PhaseYear);
    end
    block = table(repmat(readerIndex,reader.NumFrames,1), ...
        transpose(1:reader.NumFrames),duration+reader.Times, ...
        repmat(definition.Phase,reader.NumFrames,1), ...
        repmat(definition.PhaseYear,reader.NumFrames,1),reader.Times, ...
        VariableNames=frames.Properties.VariableNames);
    frames = [frames;block]; %#ok<AGROW>
    duration = duration+reader.Times(end);
end
if isempty(frames)
    error("BDam:ResultsAlignment","No monitored head frames were found.");
end
if ~timesMatch(frames.TimeDays(frames.LocalFrame > 0), ...
        summary.time_days(summary.event == "completed_step"))
    error("BDam:ResultsAlignment", ...
        "The continuous monitored summary timeline does not align with head workspaces.");
end
end

function match = timesMatch(left,right)
left = double(left(:));
right = double(right(:));
if numel(left) ~= numel(right)
    match = false;
    return
end
tolerance = max(1.0e-8,1.0e-9*max(abs([left;right]),[],"all"));
match = all(abs(left-right) <= tolerance);
end

function scope = makeScope(name,summary,frames)
scope = struct("Name",string(name),"Summary",summary,"Frames",frames, ...
    "StartDay",min([summary.time_days;frames.TimeDays]), ...
    "EndDay",max([summary.time_days;frames.TimeDays]));
end

function combined = verticallyConcatenateSummaries(first,second)
allNames = union(string(first.Properties.VariableNames), ...
    string(second.Properties.VariableNames),"stable");
first = addMissingVariables(first,second,allNames);
second = addMissingVariables(second,first,allNames);
first = first(:,cellstr(allNames));
second = second(:,cellstr(allNames));
combined = [first;second];
end

function target = addMissingVariables(target,reference,allNames)
targetNames = string(target.Properties.VariableNames);
for name = allNames
    if ismember(name,targetNames)
        continue
    end
    sample = reference.(name);
    if isnumeric(sample)
        target.(name) = nan(height(target),1);
    elseif islogical(sample)
        target.(name) = false(height(target),1);
    else
        target.(name) = strings(height(target),1);
    end
end
end

function variables = monitoringVariables(summary)
excluded = ["phase","phase_year","event","time_days","phase_time_days", ...
    "duration_days","spinup_stage","stage_year","stage_time_days"];
names = string(summary.Properties.VariableNames);
keep = false(size(names));
for index = 1:numel(names)
    keep(index) = ~ismember(names(index),excluded) && isnumeric(summary.(names(index)));
end
names = names(keep)';
labels = strings(size(names));
units = strings(size(names));
for index = 1:numel(names)
    labels(index) = strjoin(split(names(index),"_")," ");
    units(index) = variableUnit(names(index));
end
variables = table(names,labels,units, ...
    VariableNames=["Name","Label","Unit"]);
end

function unit = variableUnit(name)
if endsWith(name,"_m3_per_day")
    unit = "m^3/day";
elseif endsWith(name,"_m3")
    unit = "m^3";
elseif endsWith(name,"_m")
    unit = "m";
elseif contains(name,"percent")
    unit = "%";
else
    unit = "dimensionless";
end
end
