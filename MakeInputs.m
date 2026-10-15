%% MakeInputs - Prepare explicit cases with generated geometry
% Set BDAM_STUDY_ROOT to a local study directory and BDAM_CASES to CSV/JSON.
% With neither set, prepare one default case in this standalone source tree.
% BDAM_CONFIG is a JSON object of shared scientific parameter overrides.
% BDAM_PREVIEW=1 submits without generating geometry or preparing handoffs.
script_root = string(fileparts(mfilename("fullpath")));
cases_path = string(getenv("BDAM_CASES"));
if cases_path==""
    cases = table("default",VariableNames="case_id");
else
    cases = cases_path; % Python reads CSV/JSON without changing column names.
end
settings = struct("source",script_root);
if string(getenv("BDAM_CONFIG"))~=""
    settings.shared_file = string(getenv("BDAM_CONFIG"));
end
study_root = string(getenv("BDAM_STUDY_ROOT"));
standalone = study_root=="";
if standalone, study_root=fullfile(script_root,"Study"); end
batch_id = string(getenv("BDAM_BATCH_ID"));
if batch_id=="", batch_id="inputs"; end
preview = string(getenv("BDAM_PREVIEW"))=="1";
results = evaluateBDamCases(cases,study_root,batch_id, ...
    Settings=settings,Action="submit");
if ~preview
    evaluateBDamCases(cases,study_root,batch_id,Action="prepare");
    if standalone
        assert(isscalar(results.members),"Standalone mode requires exactly one valid case; set BDAM_STUDY_ROOT.");
        member_root = string(results.members(1).path);
        config = jsondecode(fileread(fullfile(member_root,"resolved_config.json")));
        config.source_geometry_file = fullfile(script_root,"Geometry","BDamGeometry.mat");
        if ~isfolder(fullfile(script_root,"Geometry")), mkdir(fullfile(script_root,"Geometry")); end
        copyfile(fullfile(member_root,"Geometry","BDamGeometry.mat"),config.source_geometry_file);
        prepareBDamMember(config,script_root,true);
        fprintf("Standalone inputs ready: python3 build_bdam_simulation.py ModelInput\n");
    end
end
fprintf('Study: %s; batch: %s\n',study_root,batch_id);
