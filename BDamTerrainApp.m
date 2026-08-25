classdef BDamTerrainApp < matlab.apps.AppBase
    %BDAMTERRAINAPP Interactive cross-section and terrain generator.

    properties (Access = public)
        UIFigure
        CrossSectionAxes
        TerrainAxes
    end

    properties (Access = private)
        Controls = struct()
        ProfileData = struct()
        TerrainData = struct()
        TerrainParameters = struct()
        ProfileCurrent = false
        TerrainCurrent = false
        TerrainView = [35 28]
    end

    methods (Access = private)
        function createComponents(app)
            app.UIFigure = uifigure("Visible","off", ...
                "Name","BDam Terrain Generator", ...
                "Position",[80 60 1400 850], ...
                "Color",[0.96 0.97 0.98]);

            mainGrid = uigridlayout(app.UIFigure,[1 2]);
            mainGrid.ColumnWidth = {365,"1x"};
            mainGrid.RowHeight = {"1x"};
            mainGrid.Padding = [10 10 10 10];
            mainGrid.ColumnSpacing = 10;

            controlPanel = uipanel(mainGrid,"Title","Terrain Parameters", ...
                "FontWeight","bold");
            controlPanel.Layout.Row = 1;
            controlPanel.Layout.Column = 1;

            controlGrid = uigridlayout(controlPanel,[5 1]);
            controlGrid.RowHeight = {270,420,145,172,165};
            controlGrid.ColumnWidth = {"1x"};
            controlGrid.Padding = [8 8 8 8];
            controlGrid.RowSpacing = 8;
            controlGrid.Scrollable = "on";

            channelPanel = uipanel(controlGrid,"Title","Channel Geometry", ...
                "FontWeight","bold");
            channelPanel.Layout.Row = 1;
            channelLayout = uigridlayout(channelPanel,[5 2]);
            channelLayout.RowHeight = {115,28,28,28,22};
            channelLayout.ColumnWidth = {"1x",105};
            channelLayout.Padding = [7 7 7 7];

            app.Controls.ChannelTable = uitable(channelLayout, ...
                "Data",[2 1 0.25 0.5; 10 1 1.5 2.5], ...
                "ColumnName",{"Bottom (m)","Depth (m)", ...
                    "Left slope","Right slope"}, ...
                "RowName",{"Lower","Upper"}, ...
                "ColumnEditable",true(1,4), ...
                "ColumnWidth",{65,55,67,70}, ...
                "CellEditCallback",@(~,~)app.profileInputChanged());
            app.Controls.ChannelTable.Layout.Row = 1;
            app.Controls.ChannelTable.Layout.Column = [1 2];

            app.Controls.TransverseLeft = app.addNumericField(channelLayout,2, ...
                "Left floodplain slope",0.01,@(~,~)app.profileInputChanged(), ...
                "Rise per meter toward negative X.");
            app.Controls.TransverseRight = app.addNumericField(channelLayout,3, ...
                "Right floodplain slope",0.02,@(~,~)app.profileInputChanged(), ...
                "Rise per meter toward positive X.");
            app.Controls.VerticalOffset = app.addNumericField(channelLayout,4, ...
                "Floodplain step (m)",0.25,@(~,~)app.profileInputChanged(), ...
                "Vertical step applied above the outer channel banks.");
            note = uilabel(channelLayout,"Text", ...
                "Side slopes are horizontal run per unit rise.", ...
                "FontAngle","italic","FontColor",[0.35 0.35 0.35]);
            note.Layout.Row = 5;
            note.Layout.Column = [1 2];

            reachPanel = uipanel(controlGrid,"Title","Reach, Grid, and Slopes", ...
                "FontWeight","bold");
            reachPanel.Layout.Row = 2;
            reachLayout = uigridlayout(reachPanel,[13 2]);
            reachLayout.RowHeight = repmat({27},1,13);
            reachLayout.ColumnWidth = {"1x",105};
            reachLayout.Padding = [7 7 7 7];

            app.Controls.OriginX = app.addNumericField(reachLayout,1, ...
                "X origin (m)",0,@(~,~)app.profileInputChanged(), ...
                "Coordinate at the minimum-X domain edge.");
            app.Controls.OriginY = app.addNumericField(reachLayout,2, ...
                "Y origin (m)",0,@(~,~)app.terrainInputChanged(), ...
                "Coordinate at the downstream, minimum-Y domain edge.");
            app.Controls.LengthX = app.addNumericField(reachLayout,3, ...
                "Domain X length (m)",50,@(~,~)app.profileInputChanged(), ...
                "Total transverse domain width.");
            app.Controls.LengthY = app.addNumericField(reachLayout,4, ...
                "Domain Y length (m)",100,@(~,~)app.terrainInputChanged(), ...
                "Projected downstream-to-upstream reach length.");
            app.Controls.SpacingX = app.addNumericField(reachLayout,5, ...
                "Grid spacing dx (m)",1,@(~,~)app.profileInputChanged(), ...
                "X length must be an integer multiple of dx.");
            app.Controls.SpacingY = app.addNumericField(reachLayout,6, ...
                "Grid spacing dy (m)",1,@(~,~)app.terrainInputChanged(), ...
                "Y length must be an integer multiple of dy.");
            app.Controls.SinePeriods = app.addNumericField(reachLayout,7, ...
                "Sine-wave periods",1,@(~,~)app.terrainInputChanged(), ...
                "Must be zero or a multiple of one-half period.");
            app.Controls.SineAmplitude = app.addNumericField(reachLayout,8, ...
                "Meander amplitude (m)",5,@(~,~)app.terrainInputChanged(), ...
                "Signed lateral centerline displacement; negative values " + ...
                "mirror the meander about the long axis.");
            app.Controls.RegionalSlope = app.addNumericField(reachLayout,9, ...
                "Regional Y slope",0.005,@(~,~)app.terrainInputChanged(), ...
                "Regional elevation change per meter of projected Y.");
            app.Controls.ChannelSlope = app.addNumericField(reachLayout,10, ...
                "Channel slope",0.0025,@(~,~)app.terrainInputChanged(), ...
                "Channel elevation change per meter of centerline distance.");
            app.Controls.VerticalExaggeration = app.addNumericField(reachLayout,11, ...
                "Vertical exaggeration",4,@(~,~)app.verticalExaggerationChanged(), ...
                "Display-only vertical exaggeration for the terrain plot.");
            app.Controls.VerticalExaggeration.Limits = [0 Inf];
            app.Controls.VerticalExaggeration.LowerLimitInclusive = "off";
            directionNote = uilabel(reachLayout,"Text", ...
                "Longitudinal slopes must share a sign; negative values fall toward +Y.", ...
                "FontAngle","italic","FontColor",[0.35 0.35 0.35]);
            directionNote.Layout.Row = 12;
            directionNote.Layout.Column = [1 2];
            gridNote = uilabel(reachLayout,"Text", ...
                "Projection runs only when Generate Terrain is pressed.", ...
                "FontAngle","italic","FontColor",[0.35 0.35 0.35]);
            gridNote.Layout.Row = 13;
            gridNote.Layout.Column = [1 2];

            damPanel = uipanel(controlGrid,"Title","Dam Geometry", ...
                "FontWeight","bold");
            damPanel.Layout.Row = 3;
            damLayout = uigridlayout(damPanel,[4 2]);
            damLayout.RowHeight = {28,28,28,22};
            damLayout.ColumnWidth = {"1x",105};
            damLayout.Padding = [7 7 7 7];
            app.Controls.DamMaximum = app.addNumericField(damLayout,1, ...
                "Maximum height (m)",1.5,@(~,~)app.profileInputChanged(), ...
                "Maximum dam crest height above the channel bottom.");
            app.Controls.DamFraction = app.addNumericField(damLayout,2, ...
                "Fraction upstream",0.25,@(~,~)app.terrainInputChanged(), ...
                "Fraction of centerline distance measured from the downstream end.");
            app.Controls.PlotLake = uicheckbox(damLayout, ...
                "Text","Plot Lake","Value",false, ...
                "Tooltip","Show the connected lake at maximum dam elevation.", ...
                "ValueChangedFcn",@(~,~)app.plotLakeChanged());
            app.Controls.PlotLake.Layout.Row = 3;
            app.Controls.PlotLake.Layout.Column = [1 2];
            damNote = uilabel(damLayout,"Text", ...
                "The dam is normal to the centerline at this arc distance.", ...
                "FontAngle","italic","FontColor",[0.35 0.35 0.35]);
            damNote.Layout.Row = 4;
            damNote.Layout.Column = [1 2];

            buttonPanel = uipanel(controlGrid,"BorderType","none");
            buttonPanel.Layout.Row = 4;
            buttonLayout = uigridlayout(buttonPanel,[4 2]);
            buttonLayout.RowHeight = {34,34,34,34};
            buttonLayout.ColumnWidth = {"1x","1x"};
            buttonLayout.Padding = [0 0 0 0];
            app.Controls.ImportParameters = uibutton(buttonLayout,"push", ...
                "Text","Import Parameters...", ...
                "ButtonPushedFcn",@(~,~)app.importParameters());
            app.Controls.ImportParameters.Layout.Row = 1;
            app.Controls.ImportParameters.Layout.Column = [1 2];
            app.Controls.GenerateProfile = uibutton(buttonLayout,"push", ...
                "Text","Generate Cross Section", ...
                "FontWeight","bold", ...
                "ButtonPushedFcn",@(~,~)app.generateCrossSection());
            app.Controls.GenerateProfile.Layout.Row = 2;
            app.Controls.GenerateProfile.Layout.Column = [1 2];
            app.Controls.GenerateTerrain = uibutton(buttonLayout,"push", ...
                "Text","Generate Terrain", ...
                "Enable","off", ...
                "ButtonPushedFcn",@(~,~)app.generateTerrain());
            app.Controls.GenerateTerrain.Layout.Row = 3;
            app.Controls.GenerateTerrain.Layout.Column = 1;
            app.Controls.Export = uibutton(buttonLayout,"push", ...
                "Text","Export MAT...", ...
                "Enable","off", ...
                "ButtonPushedFcn",@(~,~)app.exportGeometry());
            app.Controls.Export.Layout.Row = 3;
            app.Controls.Export.Layout.Column = 2;
            app.Controls.ExportPortable = uibutton(buttonLayout,"push", ...
                "Text","Export Portable ZIP...", ...
                "Enable","off", ...
                "ButtonPushedFcn",@(~,~)app.exportPortableGeometry());
            app.Controls.ExportPortable.Layout.Row = 4;
            app.Controls.ExportPortable.Layout.Column = [1 2];

            statusPanel = uipanel(controlGrid,"Title","Status", ...
                "FontWeight","bold");
            statusPanel.Layout.Row = 5;
            statusLayout = uigridlayout(statusPanel,[1 1]);
            statusLayout.Padding = [5 5 5 5];
            app.Controls.Status = uitextarea(statusLayout, ...
                "Editable","off", ...
                "Value","Enter parameters, then generate the cross section.", ...
                "FontName","Helvetica");

            plotGrid = uigridlayout(mainGrid,[2 1]);
            plotGrid.Layout.Row = 1;
            plotGrid.Layout.Column = 2;
            plotGrid.RowHeight = {"0.42x","0.58x"};
            plotGrid.ColumnWidth = {"1x"};
            plotGrid.Padding = [0 0 0 0];
            plotGrid.RowSpacing = 10;

            app.CrossSectionAxes = uiaxes(plotGrid);
            app.CrossSectionAxes.Layout.Row = 1;
            app.CrossSectionAxes.Box = "on";
            app.CrossSectionAxes.Toolbar.Visible = "on";

            app.TerrainAxes = uiaxes(plotGrid);
            app.TerrainAxes.Layout.Row = 2;
            app.TerrainAxes.Box = "on";
            app.TerrainAxes.Toolbar.Visible = "on";

            app.UIFigure.Visible = "on";
        end

        function field = addNumericField(~,parent,row,labelText,value,callback,tooltip)
            label = uilabel(parent,"Text",labelText);
            label.Layout.Row = row;
            label.Layout.Column = 1;
            field = uieditfield(parent,"numeric","Value",value, ...
                "ValueChangedFcn",callback,"Tooltip",tooltip);
            field.Layout.Row = row;
            field.Layout.Column = 2;
        end

        function startup(app)
            app.showPlaceholder(app.CrossSectionAxes, ...
                "Generate a cross section to preview channel geometry");
            app.showPlaceholder(app.TerrainAxes, ...
                "Confirm the cross section, then generate terrain");
        end

        function showPlaceholder(~,axesHandle,message)
            cla(axesHandle);
            text(axesHandle,0.5,0.5,message,"Units","normalized", ...
                "HorizontalAlignment","center", ...
                "VerticalAlignment","middle", ...
                "FontAngle","italic","Color",[0.4 0.4 0.4]);
            axesHandle.XTick = [];
            axesHandle.YTick = [];
            axesHandle.ZTick = [];
            title(axesHandle,"");
        end

        function parameters = collectParameters(app)
            channelData = app.Controls.ChannelTable.Data;
            if iscell(channelData)
                try
                    channelData = cell2mat(channelData);
                catch
                    error("BDam:ChannelTable", ...
                        "Every channel-table entry must be numeric.");
                end
            end
            if ~isnumeric(channelData) || ~isequal(size(channelData),[2 4])
                error("BDam:ChannelTable", ...
                    "The channel table must contain two rows and four numeric columns.");
            end

            parameters = struct();
            parameters.bottom_widths_m = channelData(:,1)';
            parameters.depths_m = channelData(:,2)';
            parameters.left_side_slopes = channelData(:,3)';
            parameters.right_side_slopes = channelData(:,4)';
            parameters.transverse_slopes = ...
                [app.Controls.TransverseLeft.Value app.Controls.TransverseRight.Value];
            parameters.vertical_offset_m = app.Controls.VerticalOffset.Value;
            parameters.dam_max_m = app.Controls.DamMaximum.Value;
            parameters.domain_length_x_m = app.Controls.LengthX.Value;
            parameters.domain_length_y_m = app.Controls.LengthY.Value;
            parameters.spacing_x_m = app.Controls.SpacingX.Value;
            parameters.spacing_y_m = app.Controls.SpacingY.Value;
            parameters.origin_x_m = app.Controls.OriginX.Value;
            parameters.origin_y_m = app.Controls.OriginY.Value;
            parameters.sine_periods = app.Controls.SinePeriods.Value;
            parameters.sine_amplitude_m = app.Controls.SineAmplitude.Value;
            parameters.regional_longitudinal_slope = app.Controls.RegionalSlope.Value;
            parameters.channel_longitudinal_slope = app.Controls.ChannelSlope.Value;
            parameters.dam_relative_distance_upstream = app.Controls.DamFraction.Value;
            parameters.vertical_exaggeration = app.Controls.VerticalExaggeration.Value;
            parameters.plot_lake = app.Controls.PlotLake.Value;
        end

        function profileInputChanged(app)
            hadProfile = ~isempty(fieldnames(app.ProfileData));
            hadTerrain = ~isempty(fieldnames(app.TerrainData));
            app.ProfileCurrent = false;
            app.TerrainCurrent = false;
            app.Controls.GenerateTerrain.Enable = "off";
            app.Controls.Export.Enable = "off";
            app.Controls.ExportPortable.Enable = "off";
            if hadProfile
                title(app.CrossSectionAxes,"Channel Cross Section (out of date)");
            end
            if hadTerrain
                title(app.TerrainAxes,"Terrain and Dam (out of date)");
            end
            app.setStatus("Profile inputs changed. Regenerate the cross section.",false);
        end

        function terrainInputChanged(app)
            hadTerrain = ~isempty(fieldnames(app.TerrainData));
            app.TerrainCurrent = false;
            app.Controls.Export.Enable = "off";
            app.Controls.ExportPortable.Enable = "off";
            if app.ProfileCurrent
                app.Controls.GenerateTerrain.Enable = "on";
            end
            if hadTerrain
                title(app.TerrainAxes,"Terrain and Dam (out of date)");
            end
            app.setStatus("Terrain inputs changed. Generate terrain to update the result.",false);
        end

        function verticalExaggerationChanged(app)
            factor = app.Controls.VerticalExaggeration.Value;
            if ~isfinite(factor) || factor <= 0
                uialert(app.UIFigure, ...
                    "Vertical exaggeration must be a positive finite value.", ...
                    "Invalid Display Parameter","Icon","error");
                return
            end
            if ~isempty(fieldnames(app.TerrainData))
                daspect(app.TerrainAxes,[1 1 1/factor]);
                title(app.TerrainAxes,sprintf( ...
                    "Terrain and Maximum Dam Wall (%gx vertical exaggeration)",factor));
            end
            if app.TerrainCurrent
                app.TerrainParameters.vertical_exaggeration = factor;
            end
        end

        function plotLakeChanged(app)
            if app.TerrainCurrent
                [azimuth,elevation] = view(app.TerrainAxes);
                app.TerrainView = [azimuth elevation];
                app.TerrainParameters.plot_lake = app.Controls.PlotLake.Value;
                app.plotTerrain(app.TerrainData);
            end
        end

        function importParameters(app)
            [fileName,folder] = uigetfile( ...
                {"*.json;*.zip","BDam portable JSON or ZIP (*.json, *.zip)"; ...
                "*.json","JSON manifest (*.json)"; ...
                "*.zip","Portable geometry ZIP (*.zip)"}, ...
                "Import BDam Terrain Parameters");
            if isequal(fileName,0)
                return
            end

            inputPath = fullfile(folder,fileName);
            try
                [parameters,manifest] = loadBDamTerrainParameters(inputPath);
                app.applyParameters(parameters);
                if isfield(manifest,"display") && ...
                        isfield(manifest.display,"matlab_azimuth_degrees") && ...
                        isfield(manifest.display,"matlab_elevation_degrees")
                    importedView = [manifest.display.matlab_azimuth_degrees, ...
                        manifest.display.matlab_elevation_degrees];
                    if isnumeric(importedView) && all(isfinite(importedView))
                        app.TerrainView = double(importedView);
                    end
                end
            catch exception
                uialert(app.UIFigure,exception.message, ...
                    "Parameter Import Failed","Icon","error");
                return
            end

            app.profileInputChanged();
            app.setStatus(["Parameters imported from:"; string(inputPath); ...
                "Generate the cross section to begin regeneration."],false);
        end

        function applyParameters(app,parameters)
            app.Controls.ChannelTable.Data = [ ...
                parameters.bottom_widths_m(:), ...
                parameters.depths_m(:), ...
                parameters.left_side_slopes(:), ...
                parameters.right_side_slopes(:)];
            app.Controls.TransverseLeft.Value = parameters.transverse_slopes(1);
            app.Controls.TransverseRight.Value = parameters.transverse_slopes(2);
            app.Controls.VerticalOffset.Value = parameters.vertical_offset_m;
            app.Controls.DamMaximum.Value = parameters.dam_max_m;
            app.Controls.LengthX.Value = parameters.domain_length_x_m;
            app.Controls.LengthY.Value = parameters.domain_length_y_m;
            app.Controls.SpacingX.Value = parameters.spacing_x_m;
            app.Controls.SpacingY.Value = parameters.spacing_y_m;
            app.Controls.OriginX.Value = parameters.origin_x_m;
            app.Controls.OriginY.Value = parameters.origin_y_m;
            app.Controls.SinePeriods.Value = parameters.sine_periods;
            app.Controls.SineAmplitude.Value = parameters.sine_amplitude_m;
            app.Controls.RegionalSlope.Value = ...
                parameters.regional_longitudinal_slope;
            app.Controls.ChannelSlope.Value = ...
                parameters.channel_longitudinal_slope;
            app.Controls.DamFraction.Value = ...
                parameters.dam_relative_distance_upstream;
            app.Controls.VerticalExaggeration.Value = ...
                parameters.vertical_exaggeration;
            app.Controls.PlotLake.Value = logical(parameters.plot_lake);
        end

        function generateCrossSection(app)
            try
                parameters = app.collectParameters();
                profile = buildBDamCrossSection(parameters);
            catch exception
                uialert(app.UIFigure,exception.message, ...
                    "Invalid Cross-Section Parameters","Icon","error");
                return
            end

            app.ProfileData = profile;
            app.ProfileCurrent = true;
            app.TerrainCurrent = false;
            app.Controls.GenerateTerrain.Enable = "on";
            app.Controls.Export.Enable = "off";
            app.Controls.ExportPortable.Enable = "off";

            cla(app.CrossSectionAxes);
            plot(app.CrossSectionAxes,profile.offset_m,profile.elevation_m, ...
                "LineWidth",2,"Color",[0.10 0.30 0.55], ...
                "DisplayName","Land surface");
            hold(app.CrossSectionAxes,"on");
            yline(app.CrossSectionAxes,parameters.dam_max_m,"--", ...
                "Maximum dam level","LineWidth",2,"Color",[0 0.35 1], ...
                "LabelHorizontalAlignment","center", ...
                "DisplayName","Maximum dam level");
            hold(app.CrossSectionAxes,"off");
            grid(app.CrossSectionAxes,"on");
            app.CrossSectionAxes.XTickMode = "auto";
            app.CrossSectionAxes.YTickMode = "auto";
            xlabel(app.CrossSectionAxes,"Normal distance from centerline (m)");
            ylabel(app.CrossSectionAxes,"Relative elevation (m)");
            title(app.CrossSectionAxes,"Channel Cross Section");
            xlim(app.CrossSectionAxes,[min(profile.offset_m) max(profile.offset_m)]);

            if isempty(profile.warnings)
                app.setStatus(["Cross section generated."; ...
                    "Review it, then select Generate Terrain."],false);
            else
                app.setStatus(["Cross section generated with warning:"; ...
                    profile.warnings],true);
            end
        end

        function generateTerrain(app)
            if ~app.ProfileCurrent
                uialert(app.UIFigure, ...
                    "Generate and confirm the current cross section first.", ...
                    "Cross Section Required","Icon","warning");
                return
            end

            try
                parameters = app.collectParameters();
            catch exception
                uialert(app.UIFigure,exception.message, ...
                    "Invalid Terrain Parameters","Icon","error");
                return
            end

            if ~isempty(fieldnames(app.TerrainData))
                [azimuth,elevation] = view(app.TerrainAxes);
                app.TerrainView = [azimuth elevation];
            end

            progress = uiprogressdlg(app.UIFigure, ...
                "Title","Generating terrain", ...
                "Message","Projecting grid cells onto the channel centerline...", ...
                "Indeterminate","on");
            app.Controls.GenerateProfile.Enable = "off";
            app.Controls.GenerateTerrain.Enable = "off";
            app.Controls.Export.Enable = "off";
            app.Controls.ExportPortable.Enable = "off";
            drawnow;
            cleanup = onCleanup(@()app.restoreAfterCalculation(progress));

            try
                terrain = buildBDamTerrain(parameters,app.ProfileData);
            catch exception
                uialert(app.UIFigure,exception.message, ...
                    "Terrain Generation Failed","Icon","error");
                return
            end

            app.TerrainData = terrain;
            app.TerrainParameters = parameters;
            app.TerrainCurrent = true;
            app.plotTerrain(terrain);

            summary = [sprintf("Terrain generated: %d x %d cells.", ...
                size(terrain.ZTop_m,1),size(terrain.ZTop_m,2)); ...
                sprintf("Tortuosity: %.6f",terrain.tortuosity); ...
                sprintf("Dam toe / crest: %.3f / %.3f m", ...
                    terrain.dam_toe_elevation_m,terrain.dam_crest_elevation_m)];
            if isempty(terrain.warnings)
                app.setStatus(summary,false);
            else
                app.setStatus([summary; "Warnings:"; terrain.warnings],true);
            end
            clear cleanup
        end

        function restoreAfterCalculation(app,progress)
            if isvalid(progress)
                close(progress);
            end
            if isvalid(app.UIFigure)
                app.Controls.GenerateProfile.Enable = "on";
                app.Controls.GenerateTerrain.Enable = ...
                    app.logicalEnable(app.ProfileCurrent);
                app.Controls.Export.Enable = ...
                    app.logicalEnable(app.TerrainCurrent);
                app.Controls.ExportPortable.Enable = ...
                    app.logicalEnable(app.TerrainCurrent);
            end
        end

        function value = logicalEnable(~,condition)
            if condition
                value = "on";
            else
                value = "off";
            end
        end

        function plotTerrain(app,terrain)
            cla(app.TerrainAxes);
            surf(app.TerrainAxes,terrain.X_m,terrain.Y_m,terrain.ZTop_m, ...
                "EdgeColor",[0.18 0.18 0.18],"EdgeAlpha",0.28);
            hold(app.TerrainAxes,"on");
            if app.TerrainParameters.plot_lake && ...
                    any(isfinite(terrain.lake_display_Z_m),"all")
                surf(app.TerrainAxes,terrain.lake_display_X_m, ...
                    terrain.lake_display_Y_m,terrain.lake_display_Z_m, ...
                    "FaceColor",[0.20 0.58 0.92], ...
                    "FaceAlpha",0.48,"EdgeColor","none");
                shoreline_z = terrain.lake_stage_m + ...
                    1e-5*max(1,range(terrain.ZTop_m,"all"));
                for segment = 1:numel(terrain.lake_outline_segments_m)
                    points = terrain.lake_outline_segments_m{segment};
                    plot3(app.TerrainAxes,points(:,1),points(:,2), ...
                        shoreline_z*ones(size(points,1),1), ...
                        "Color",[0.02 0.18 0.48],"LineWidth",2);
                end
            end
            plot3(app.TerrainAxes,terrain.centerline_x_m,terrain.centerline_y_m, ...
                terrain.centerline_elevation_m+0.01, ...
                "Color",[0.65 0.05 0.05],"LineWidth",1.5);
            fill3(app.TerrainAxes,terrain.dam_wall_x_m,terrain.dam_wall_y_m, ...
                terrain.dam_wall_z_m,[0 0.35 1], ...
                "FaceAlpha",0.80,"EdgeColor",[0 0.15 0.8],"LineWidth",1.5);
            hold(app.TerrainAxes,"off");
            xlabel(app.TerrainAxes,"X (m)");
            ylabel(app.TerrainAxes,"Y (m)");
            zlabel(app.TerrainAxes,"Elevation (m)");
            factor = app.TerrainParameters.vertical_exaggeration;
            title(app.TerrainAxes,sprintf( ...
                "Terrain and Maximum Dam Wall (%gx vertical exaggeration)",factor));
            grid(app.TerrainAxes,"on");
            app.TerrainAxes.XTickMode = "auto";
            app.TerrainAxes.YTickMode = "auto";
            app.TerrainAxes.ZTickMode = "auto";
            axis(app.TerrainAxes,"tight");
            daspect(app.TerrainAxes,[1 1 1/factor]);
            view(app.TerrainAxes,app.TerrainView);
            colormap(app.TerrainAxes,"parula");
        end

        function exportGeometry(app)
            if ~app.TerrainCurrent
                uialert(app.UIFigure, ...
                    "Generate current terrain before exporting.", ...
                    "Current Terrain Required","Icon","warning");
                return
            end

            [fileName,folder] = uiputfile("*.mat", ...
                "Export BDam Geometry","BDamGeometry.mat");
            if isequal(fileName,0)
                return
            end

            outputPath = fullfile(folder,fileName);
            try
                saveBDamGeometry(outputPath,app.TerrainData, ...
                    app.ProfileData,app.TerrainParameters);
            catch exception
                uialert(app.UIFigure,exception.message, ...
                    "Export Failed","Icon","error");
                return
            end
            app.setStatus(["Geometry exported successfully:"; string(outputPath)],false);
        end

        function exportPortableGeometry(app)
            if ~app.TerrainCurrent
                uialert(app.UIFigure, ...
                    "Generate current terrain before exporting.", ...
                    "Current Terrain Required","Icon","warning");
                return
            end

            [fileName,folder] = uiputfile("*.zip", ...
                "Export Portable BDam Geometry","BDamGeometryPortable.zip");
            if isequal(fileName,0)
                return
            end

            outputPath = fullfile(folder,fileName);
            try
                displaySettings = app.captureDisplaySettings();
                exportBDamPortableGeometry(outputPath,app.TerrainData, ...
                    app.ProfileData,app.TerrainParameters,displaySettings);
            catch exception
                uialert(app.UIFigure,exception.message, ...
                    "Portable Export Failed","Icon","error");
                return
            end
            app.setStatus(["Portable geometry exported successfully:"; ...
                string(outputPath); ...
                "Schema: bdam-portable-geometry-v1"],false);
        end

        function settings = captureDisplaySettings(app)
            [azimuth,elevation] = view(app.TerrainAxes);
            cameraPosition = app.TerrainAxes.CameraPosition;
            cameraTarget = app.TerrainAxes.CameraTarget;
            cameraVector = cameraTarget-cameraPosition;
            vectorLength = norm(cameraVector);
            if vectorLength > 0
                cameraVector = cameraVector/vectorLength;
            end
            app.TerrainView = [azimuth elevation];
            settings = struct( ...
                "matlab_azimuth_degrees",azimuth, ...
                "matlab_elevation_degrees",elevation, ...
                "camera_position_xyz",cameraPosition, ...
                "camera_target_xyz",cameraTarget, ...
                "camera_up_vector_xyz",app.TerrainAxes.CameraUpVector, ...
                "camera_view_angle_degrees",app.TerrainAxes.CameraViewAngle, ...
                "projection",string(app.TerrainAxes.Projection), ...
                "world_view_vector_camera_to_target",cameraVector, ...
                "vertical_exaggeration",app.TerrainParameters.vertical_exaggeration, ...
                "plot_lake",logical(app.Controls.PlotLake.Value), ...
                "terrain_colormap_dataset","/display/parula_rgb", ...
                "terrain_edge_rgb",[0.18 0.18 0.18], ...
                "terrain_edge_alpha",0.28, ...
                "centerline_rgb",[0.65 0.05 0.05], ...
                "centerline_line_width",1.5, ...
                "dam_face_rgb",[0 0.35 1], ...
                "dam_face_alpha",0.80, ...
                "dam_edge_rgb",[0 0.15 0.8], ...
                "dam_edge_line_width",1.5, ...
                "lake_face_rgb",[0.20 0.58 0.92], ...
                "lake_face_alpha",0.48, ...
                "shoreline_rgb",[0.02 0.18 0.48], ...
                "shoreline_line_width",2);
        end

        function setStatus(app,lines,isWarning)
            lines = string(lines(:));
            app.Controls.Status.Value = cellstr(lines);
            if isWarning
                app.Controls.Status.FontColor = [0.72 0.32 0.02];
            else
                app.Controls.Status.FontColor = [0.12 0.22 0.32];
            end
        end
    end

    methods (Access = public)
        function app = BDamTerrainApp
            app.createComponents();
            registerApp(app,app.UIFigure);
            runStartupFcn(app,@startup);
            if nargout == 0
                clear app
            end
        end

        function delete(app)
            if ~isempty(app.UIFigure) && isvalid(app.UIFigure)
                delete(app.UIFigure);
            end
        end
    end
end
