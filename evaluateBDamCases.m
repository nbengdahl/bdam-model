function result = evaluateBDamCases(cases,studyRoot,batchId,options)
%evaluateBDamCases - Submit, prepare, evaluate, or collect explicit cases
%   RESULT = evaluateBDamCases(CASES,studyRoot,batchId) evaluates a table.
%   RESULT = evaluateBDamCases(...,Action="submit") saves cases only.
%   RESULT = evaluateBDamCases(...,Settings=SETTINGS) initializes a study.
%   CASES may also be a CSV/JSON path. Column names are preserved.
%   CASES may also
%   be a struct array with case_id, parameters, and metadata fields.
%   See also defaultBDamConfig, buildBDamGeometry
arguments
    cases
    studyRoot (1,1) string
    batchId (1,1) string
    options.Action (1,1) string {mustBeMember(options.Action,["submit","prepare","evaluate","collect"])} = "evaluate"
    options.Settings (1,1) struct = struct()
end
root = string(fileparts(mfilename("fullpath")));
python = string(getenv("BDAM_PYTHON"));
if python=="", python="python3"; end
temporary = string(tempname);
mkdir(temporary);
cleanup = onCleanup(@() rmdir(temporary,"s"));
request = fullfile(temporary,"request.json");
response = fullfile(temporary,"response.json");
if istable(cases)
    rows = cell(height(cases),1);
    names = string(cases.Properties.VariableNames);
    for i=1:height(cases)
        % Build JSON explicitly: table names can contain dots/brackets.
        pairs = strings(1,numel(names));
        for j=1:numel(names)
            value = cases.(names(j))(i,:);
            if iscell(value) && isscalar(value), value=value{1}; end
            if isnumeric(value) || isstring(value) || ischar(value)
                assert(~any(ismissing(value),"all"),"BDam:MissingCell","Table cells cannot be missing.");
            end
            automaticNames=["K_by_layer_top_to_bottom","K33_by_layer_top_to_bottom", ...
                "groundwater_boundary_k_m_per_day","dam_settings.dam_line_sample_spacing_m", ...
                "forcing_controls.precipitation.center_day","forcing_controls.et.center_day", ...
                "forcing_controls.inflow.center_day"];
            encoded=string(jsonencode(value));
            if isempty(value) && any(names(j)==automaticNames), encoded="null"; end
            pairs(j)=string(jsonencode(names(j)))+":"+encoded;
        end
        rows{i}="{"+join(pairs,",")+"}";
    end
    casesJson="["+join(string(rows),",")+"]";
else
    casesJson=string(jsonencode(cases));
    if isscalar(cases) && isstruct(cases), casesJson="["+casesJson+"]"; end
end
settingsJson=string(jsonencode(options.Settings));
if isempty(fieldnames(options.Settings)), settingsJson="null"; end
payload='{"root":'+string(jsonencode(studyRoot))+',"batch_id":'+ ...
    string(jsonencode(batchId))+',"action":'+string(jsonencode(options.Action))+ ...
    ',"settings":'+settingsJson+',"cases":'+casesJson+'}';
fid=fopen(request,"w"); assert(fid>=0,"Cannot write request.");
fwrite(fid,unicode2native(char(payload),"UTF-8"),"uint8"); fclose(fid);
% Arguments are passed through a JSON request, never interpolated as code.
command=sprintf('"%s" "%s" "%s" "%s"',python, ...
    fullfile(root,"bdam_matlab_bridge.py"),request,response);
[status,report]=system(command);
assert(status==0,"BDam:BridgeFailure","%s",report);
result=jsondecode(fileread(response));
end
