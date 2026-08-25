%% MakeGrid -- non-interactive companion to BDamTerrainApp
% All geometry inputs below use exactly the non-display parameter schema of
% BDamTerrainApp. Edit this section, then run the script to create the
% versioned geometry database consumed by MakeInputs.m.

clearvars
close all
clc

%% Geometry inputs (same names, units, meanings, and defaults as the App)
parameters = struct();
parameters.bottom_widths_m = [2 10];
parameters.depths_m = [1 1];
parameters.left_side_slopes = [0.25 1.5];
parameters.right_side_slopes = [0.5 2.5];
parameters.transverse_slopes = [0.01 0.02];
parameters.vertical_offset_m = 0.25;
parameters.dam_max_m = 1.5;
parameters.domain_length_x_m = 50;
parameters.domain_length_y_m = 100;
parameters.spacing_x_m = 1;
parameters.spacing_y_m = 1;
parameters.origin_x_m = 0;
parameters.origin_y_m = 0;
parameters.sine_periods = 1;
parameters.sine_amplitude_m = 5;
parameters.regional_longitudinal_slope = 0.005;
parameters.channel_longitudinal_slope = 0.0025;
parameters.dam_relative_distance_upstream = 0.25;

% vertical_exaggeration and plot_lake are display-only App controls and are
% intentionally not geometry-script inputs.

script_root = fileparts(mfilename("fullpath"));
output_directory = fullfile(script_root,"Geometry");
if ~isfolder(output_directory), mkdir(output_directory); end
output_path = fullfile(output_directory,"BDamGeometry.mat");

profile = buildBDamCrossSection(parameters);
terrain = buildBDamTerrain(parameters,profile);
geometry_handoff = saveBDamGeometry(output_path,terrain,profile,parameters); %#ok<NASGU>

%% Review plots (not inputs)
figure("Name","BDam cross section");
plot(profile.offset_m,profile.elevation_m,"LineWidth",2); grid on; hold on
yline(parameters.dam_max_m,"--k","Maximum dam height","LineWidth",1.5);
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
