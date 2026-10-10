function forcing = makeBDamPeriodicForcing(config,edges,root,forcing)
% Python supplies exact conservative integrals; MATLAB remains the H5 exporter.
request = fullfile(root,"forcing_request.json");
output = fullfile(root,"forcing_diagnostics.json");
writeBDamJson(request,struct("config",config,"edges",edges));
python = string(getenv("BDAM_PYTHON")); if python == "", python = "python3"; end
tool = fullfile(fileparts(mfilename("fullpath")),"bdam_forcing.py");
command = sprintf('"%s" "%s" "%s" "%s"',python,tool,request,output);
[status,report] = system(command);
assert(status == 0,"Periodic forcing failed: %s",report);
result = jsondecode(fileread(output));
forcing.upstream_inflow_m3_per_day = result.rates.upstream_inflow_m3_per_day(:);
forcing.land_infiltration_m_per_day = result.rates.land_recharge_m_per_day(:);
forcing.land_et_m_per_day = result.rates.land_et_m_per_day(:);
forcing.lake_precipitation_m_per_day = result.rates.lake_precipitation_m_per_day(:);
forcing.lake_evaporation_m_per_day = result.rates.lake_evaporation_m_per_day(:);
forcing.reference_inflow = result.reference_inflow(:);
forcing.monthly_rates = result.monthly_rates;
forcing.weekly_rates = result.weekly_rates;
forcing.transformation_version = string(result.version);
forcing.transformation_diagnostics = result.diagnostics;
forcing.transformation_controls = config.forcing_controls;
forcing.synthetic_source = "Periodic transformed USGS/Pullman climatologies; synthetic assumptions";
duration = diff(edges);
forcing.mean_streamflow_m3_per_day = dot(forcing.upstream_inflow_m3_per_day(1:end-1),duration)/365;
forcing.mean_land_et_m_per_day = dot(forcing.land_et_m_per_day(1:end-1),duration)/365;
forcing.mean_recharge_m_per_day = dot(forcing.land_infiltration_m_per_day(1:end-1),duration)/365;
forcing.annual_precipitation_mm = dot(forcing.lake_precipitation_m_per_day(1:end-1),duration)*1000;
forcing.timeseries = table(edges,forcing.upstream_inflow_m3_per_day, ...
    forcing.land_infiltration_m_per_day,forcing.land_et_m_per_day, ...
    forcing.lake_precipitation_m_per_day,forcing.lake_evaporation_m_per_day, ...
    VariableNames=["time_days","upstream_inflow_m3_per_day","land_recharge_m_per_day", ...
    "land_et_m_per_day","lake_precipitation_m_per_day","lake_evaporation_m_per_day"]);
end
