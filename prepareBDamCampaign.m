function prepareBDamCampaign(manifest_path)
% All members are prepared serially; no MODFLOW simulation is launched here.
manifest = jsondecode(fileread(manifest_path));
for i = 1:numel(manifest.members)
    member = manifest.members(i);
    root = string(member.path);
    config = jsondecode(fileread(fullfile(root,"resolved_config.json")));
    if isfile(fullfile(root,"prepared.json")), continue; end
    try
        if isfield(config,"geometry")
            buildBDamGeometry(config.geometry,string(config.source_geometry_file));
        end
        prepareBDamMember(config,root,false);
        python = string(getenv("BDAM_PYTHON")); if python == "", python = "python3"; end
        command = sprintf('"%s" "%s" mark-prepared "%s"',python,fullfile(root,"bdam_sweeps.py"),root);
        [status,report] = system(command);
        assert(status == 0,"Could not record prepared handoffs: %s",report);
    catch failure
        if ~isfield(manifest,"study_root"), rethrow(failure); end
        writeBDamJson(fullfile(root,"status.json"),struct( ...
            "id",member.id,"status","failed","phase","preparation", ...
            "error",failure.getReport()));
    end
end
end
