%% MakeGrid -- non-interactive companion to BDamTerrainApp
% Shared defaults use the same non-display schema as BDamTerrainApp.
% For case-specific geometry use evaluateBDamCases or MakeInputs.m.

clearvars
close all
clc

%% Geometry inputs (same names, units, meanings, and defaults as the App)
config = defaultBDamConfig();
parameters = config.geometry;

% vertical_exaggeration and plot_lake are display-only App controls and are
% intentionally not geometry-script inputs.

script_root = fileparts(mfilename("fullpath"));
output_directory = fullfile(script_root,"Geometry");
if ~isfolder(output_directory), mkdir(output_directory); end
output_path = fullfile(output_directory,"BDamGeometry.mat");

buildBDamGeometry(parameters,string(output_path));
profile = buildBDamCrossSection(parameters);
terrain = buildBDamTerrain(parameters,profile);

%% Review plots (not inputs)
figure("Name","BDam cross section");
plot(profile.offset_m,profile.elevation_m,"LineWidth",2); grid on; hold on
yline(parameters.dam_height_m,"--k","Dam height","LineWidth",1.5);
xlabel("Distance normal to centerline (m)"); ylabel("Elevation (m)");
title("Generated channel cross section");

figure("Name","BDam terrain");
surf(terrain.X_m,terrain.Y_m,terrain.ZTop_m,"EdgeColor","none"); hold on
fill3(terrain.dam_wall_x_m,terrain.dam_wall_y_m,terrain.dam_wall_z_m,[0 0.35 1], ...
    "FaceAlpha",0.75,"EdgeColor",[0 0.15 0.8]);
axis equal; view(35,28); colorbar
xlabel("X (m)"); ylabel("Y (m)"); zlabel("Elevation (m)");
title("Generated BDam terrain");

fprintf("Geometry database written: %s\n",output_path);
