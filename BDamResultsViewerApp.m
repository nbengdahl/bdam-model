classdef BDamResultsViewerApp < matlab.apps.AppBase
    %BDAMRESULTSVIEWERAPP Explore and animate completed BDam results.

    properties (Access = public)
        UIFigure
        TimeSeriesAxes
        MapAxes
    end

    properties (Access = private)
        Controls = struct()
        Results = struct()
        CurrentScopeKey (1,1) string = "Monitored"
        CurrentFrame (1,1) double = 1
        AcceptedVariables string = strings(0,1)
        CurrentTimeLine = []
        AnimationTimer = []
        MapLimitCache = struct()
        SurfaceCache = {}
        SurfaceCacheEnabled (1,1) logical = false
        SurfaceCacheBytes (1,1) double = 0
        MapImage = []
        MapContour = []
        MapColorbar = []
        MapTitle = []
    end

    methods (Access = private)
        function createComponents(app)
            app.UIFigure = uifigure("Visible","off", ...
                "Name","BDam Results Viewer", ...
                "Position",[60 40 1500 930], ...
                "Color",[0.96 0.97 0.98], ...
                "CloseRequestFcn",@(~,~)delete(app));

            mainGrid = uigridlayout(app.UIFigure,[1 2]);
            mainGrid.ColumnWidth = {355,"1x"};
            mainGrid.RowHeight = {"1x"};
            mainGrid.Padding = [10 10 10 10];
            mainGrid.ColumnSpacing = 10;

            controlPanel = uipanel(mainGrid,"Title","Viewer Controls", ...
                "FontWeight","bold");
            controlPanel.Layout.Row = 1;
            controlPanel.Layout.Column = 1;
            controlGrid = uigridlayout(controlPanel,[5 1]);
            controlGrid.RowHeight = {135,240,"1x",175,105};
            controlGrid.Padding = [8 8 8 8];
            controlGrid.RowSpacing = 8;
            controlGrid.Scrollable = "on";

            sourcePanel = uipanel(controlGrid,"Title","Output Folder", ...
                "FontWeight","bold");
            sourcePanel.Layout.Row = 1;
            sourceGrid = uigridlayout(sourcePanel,[3 2]);
            sourceGrid.RowHeight = {28,32,22};
            sourceGrid.ColumnWidth = {"1x",86};
            sourceGrid.Padding = [7 7 7 7];
            app.Controls.Folder = uieditfield(sourceGrid,"text", ...
                "Tooltip","Complete output root containing Geometry and Runs.");
            app.Controls.Folder.Layout.Row = 1;
            app.Controls.Folder.Layout.Column = [1 2];
            app.Controls.Browse = uibutton(sourceGrid,"push", ...
                "Text","Browse...", ...
                "ButtonPushedFcn",@(~,~)app.browseFolder());
            app.Controls.Browse.Layout.Row = 2;
            app.Controls.Browse.Layout.Column = 1;
            app.Controls.Load = uibutton(sourceGrid,"push", ...
                "Text","Load", ...
                "FontWeight","bold", ...
                "ButtonPushedFcn",@(~,~)app.loadFolder(app.Controls.Folder.Value));
            app.Controls.Load.Layout.Row = 2;
            app.Controls.Load.Layout.Column = 2;
            sourceNote = uilabel(sourceGrid,"Text", ...
                "Outputs are opened read-only.","FontAngle","italic", ...
                "FontColor",[0.35 0.35 0.35]);
            sourceNote.Layout.Row = 3;
            sourceNote.Layout.Column = [1 2];

            viewPanel = uipanel(controlGrid,"Title","Timeline and Map", ...
                "FontWeight","bold");
            viewPanel.Layout.Row = 2;
            viewGrid = uigridlayout(viewPanel,[7 3]);
            viewGrid.RowHeight = {28,24,28,28,28,28,24};
            viewGrid.ColumnWidth = {"1x",68,68};
            viewGrid.Padding = [7 7 7 7];
            scopeLabel = uilabel(viewGrid,"Text","Timeline scope");
            scopeLabel.Layout.Row = 1;
            scopeLabel.Layout.Column = 1;
            app.Controls.Scope = uidropdown(viewGrid, ...
                "Items",["Spinup","Monitored pre/post","All"], ...
                "ItemsData",["Spinup","Monitored","All"], ...
                "Value","Monitored", ...
                "ValueChangedFcn",@(~,~)app.scopeChanged());
            app.Controls.Scope.Layout.Row = 1;
            app.Controls.Scope.Layout.Column = [2 3];
            rasterHeader = uilabel(viewGrid,"Text","Raster", ...
                "HorizontalAlignment","center","FontWeight","bold");
            rasterHeader.Layout.Row = 2;
            rasterHeader.Layout.Column = 2;
            contourHeader = uilabel(viewGrid,"Text","Contours", ...
                "HorizontalAlignment","center","FontWeight","bold");
            contourHeader.Layout.Row = 2;
            contourHeader.Layout.Column = 3;
            depthLabel = uilabel(viewGrid,"Text","Depth to water");
            depthLabel.Layout.Row = 3;
            depthLabel.Layout.Column = 1;
            app.Controls.DepthRaster = uicheckbox(viewGrid, ...
                "Text","","Value",true,"Tag","DepthRaster", ...
                "Tooltip","Use depth to water for the color raster.", ...
                "ValueChangedFcn",@(~,~)app.mapAssignmentChanged("DepthRaster"));
            app.Controls.DepthRaster.Layout.Row = 3;
            app.Controls.DepthRaster.Layout.Column = 2;
            app.Controls.DepthContours = uicheckbox(viewGrid, ...
                "Text","","Value",false,"Tag","DepthContours", ...
                "Tooltip","Draw depth-to-water contours.", ...
                "ValueChangedFcn",@(~,~)app.mapAssignmentChanged("DepthContours"));
            app.Controls.DepthContours.Layout.Row = 3;
            app.Controls.DepthContours.Layout.Column = 3;
            elevationLabel = uilabel(viewGrid,"Text","Water-surface elevation");
            elevationLabel.Layout.Row = 4;
            elevationLabel.Layout.Column = 1;
            app.Controls.ElevationRaster = uicheckbox(viewGrid, ...
                "Text","","Value",false,"Tag","ElevationRaster", ...
                "Tooltip","Use groundwater elevation for the color raster.", ...
                "ValueChangedFcn",@(~,~)app.mapAssignmentChanged("ElevationRaster"));
            app.Controls.ElevationRaster.Layout.Row = 4;
            app.Controls.ElevationRaster.Layout.Column = 2;
            app.Controls.ElevationContours = uicheckbox(viewGrid, ...
                "Text","","Value",true,"Tag","ElevationContours", ...
                "Tooltip","Draw groundwater-elevation contours.", ...
                "ValueChangedFcn",@(~,~)app.mapAssignmentChanged("ElevationContours"));
            app.Controls.ElevationContours.Layout.Row = 4;
            app.Controls.ElevationContours.Layout.Column = 3;
            app.Controls.ShowLabels = uicheckbox(viewGrid, ...
                "Text","Label selected head monitors","Value",true, ...
                "ValueChangedFcn",@(~,~)app.rebuildMap());
            app.Controls.ShowLabels.Layout.Row = 5;
            app.Controls.ShowLabels.Layout.Column = [1 3];
            app.Controls.TransposeMap = uicheckbox(viewGrid, ...
                "Text","Transpose map axes (Y horizontal)","Value",false, ...
                "Tooltip","Display Y on the horizontal axis and X on the vertical axis.", ...
                "ValueChangedFcn",@(~,~)app.rebuildMap());
            app.Controls.TransposeMap.Layout.Row = 6;
            app.Controls.TransposeMap.Layout.Column = [1 3];
            mapNote = uilabel(viewGrid,"Text", ...
                "Raster is required; contours are optional.", ...
                "FontAngle","italic","FontColor",[0.35 0.35 0.35]);
            mapNote.Layout.Row = 7;
            mapNote.Layout.Column = [1 3];

            variablePanel = uipanel(controlGrid,"Title","Monitoring Variables", ...
                "FontWeight","bold");
            variablePanel.Layout.Row = 3;
            variableGrid = uigridlayout(variablePanel,[2 1]);
            variableGrid.RowHeight = {"1x",42};
            variableGrid.Padding = [7 7 7 7];
            app.Controls.Variables = uilistbox(variableGrid, ...
                "Multiselect","on", ...
                "ValueChangedFcn",@(source,event)app.variablesChanged(source,event));
            app.Controls.Variables.Layout.Row = 1;
            variableNote = uilabel(variableGrid,"Text", ...
                "Select any number of series from at most two unit families.", ...
                "WordWrap","on","FontAngle","italic", ...
                "FontColor",[0.35 0.35 0.35]);
            variableNote.Layout.Row = 2;

            playbackPanel = uipanel(controlGrid,"Title","Animation", ...
                "FontWeight","bold");
            playbackPanel.Layout.Row = 4;
            playbackGrid = uigridlayout(playbackPanel,[4 4]);
            playbackGrid.RowHeight = {34,28,28,27};
            playbackGrid.ColumnWidth = {50,"1x","1x",74};
            playbackGrid.Padding = [7 7 7 7];
            app.Controls.Previous = uibutton(playbackGrid,"push", ...
                "Text","<", "ButtonPushedFcn",@(~,~)app.stepFrame(-1));
            app.Controls.Previous.Layout.Row = 1;
            app.Controls.Previous.Layout.Column = 1;
            app.Controls.Play = uibutton(playbackGrid,"push", ...
                "Text","Play","FontWeight","bold", ...
                "ButtonPushedFcn",@(~,~)app.toggleAnimation());
            app.Controls.Play.Layout.Row = 1;
            app.Controls.Play.Layout.Column = [2 3];
            app.Controls.Next = uibutton(playbackGrid,"push", ...
                "Text",">", "ButtonPushedFcn",@(~,~)app.stepFrame(1));
            app.Controls.Next.Layout.Row = 1;
            app.Controls.Next.Layout.Column = 4;
            speedLabel = uilabel(playbackGrid,"Text","Frames/s");
            speedLabel.Layout.Row = 2;
            speedLabel.Layout.Column = [1 2];
            app.Controls.Speed = uidropdown(playbackGrid, ...
                "Items",["1","2","5","10","20"],"ItemsData",[1 2 5 10 20], ...
                "Value",5,"ValueChangedFcn",@(~,~)app.speedChanged());
            app.Controls.Speed.Layout.Row = 2;
            app.Controls.Speed.Layout.Column = 3;
            app.Controls.Loop = uicheckbox(playbackGrid, ...
                "Text","Loop","Value",true);
            app.Controls.Loop.Layout.Row = 2;
            app.Controls.Loop.Layout.Column = 4;
            app.Controls.Time = uilabel(playbackGrid,"Text","No data loaded", ...
                "HorizontalAlignment","center","FontWeight","bold");
            app.Controls.Time.Layout.Row = 3;
            app.Controls.Time.Layout.Column = [1 4];
            app.Controls.Frame = uislider(playbackGrid, ...
                "Limits",[1 2],"Value",1,"MajorTicks",[],"MinorTicks",[], ...
                "ValueChangedFcn",@(source,~)app.sliderChanged(source.Value), ...
                "ValueChangingFcn",@(~,event)app.sliderChanged(event.Value));
            app.Controls.Frame.Layout.Row = 4;
            app.Controls.Frame.Layout.Column = [1 4];

            statusPanel = uipanel(controlGrid,"Title","Status", ...
                "FontWeight","bold");
            statusPanel.Layout.Row = 5;
            statusGrid = uigridlayout(statusPanel,[1 1]);
            statusGrid.Padding = [5 5 5 5];
            app.Controls.Status = uitextarea(statusGrid,"Editable","off", ...
                "Value","Select a completed BDam output folder.");

            plotGrid = uigridlayout(mainGrid,[2 1]);
            plotGrid.Layout.Row = 1;
            plotGrid.Layout.Column = 2;
            plotGrid.RowHeight = {"0.50x","0.50x"};
            plotGrid.Padding = [0 0 0 0];
            plotGrid.RowSpacing = 10;
            app.TimeSeriesAxes = uiaxes(plotGrid);
            app.TimeSeriesAxes.Layout.Row = 1;
            app.TimeSeriesAxes.Box = "on";
            app.TimeSeriesAxes.Toolbar.Visible = "on";
            app.MapAxes = uiaxes(plotGrid);
            app.MapAxes.Layout.Row = 2;
            app.MapAxes.Box = "on";
            app.MapAxes.Toolbar.Visible = "on";

            app.enableDataControls(false);
            app.UIFigure.Visible = "on";
        end

        function startup(app,outputRoot)
            app.showPlaceholder(app.TimeSeriesAxes, ...
                "Load a completed output folder to view monitoring time series");
            app.showPlaceholder(app.MapAxes, ...
                "Load a completed output folder to view groundwater maps");
            if strlength(outputRoot) == 0
                appFolder = fileparts(mfilename("fullpath"));
                outputRoot = fullfile(appFolder,"..","BDam_out");
            end
            app.Controls.Folder.Value = char(outputRoot);
            app.setStatus(["Output folder selected:";string(outputRoot); ...
                "Click Load to read the completed results."],false);
        end

        function showPlaceholder(~,axesHandle,message)
            cla(axesHandle,"reset");
            text(axesHandle,0.5,0.5,message,"Units","normalized", ...
                "HorizontalAlignment","center","VerticalAlignment","middle", ...
                "FontAngle","italic","Color",[0.4 0.4 0.4]);
            axesHandle.XTick = [];
            axesHandle.YTick = [];
            title(axesHandle,"");
        end

        function browseFolder(app)
            initial = app.Controls.Folder.Value;
            if ~isfolder(initial)
                initial = pwd;
            end
            selected = uigetdir(initial,"Select completed BDam output folder");
            if isequal(selected,0)
                return
            end
            app.Controls.Folder.Value = selected;
            app.setStatus(["Output folder selected:";string(selected); ...
                "Click Load to read the completed results."],false);
        end

        function loadFolder(app,outputRoot)
            app.stopAnimation(true);
            app.enableDataControls(false);
            app.Controls.Load.Enable = "off";
            app.Controls.Browse.Enable = "off";
            app.setStatus("Validating and indexing BDam results...",false);
            drawnow
            try
                loaded = loadBDamResults(outputRoot);
            catch exception
                app.Controls.Load.Enable = "on";
                app.Controls.Browse.Enable = "on";
                app.setStatus(["Could not load results:";string(exception.message)],true);
                uialert(app.UIFigure,exception.message,"Results Load Failed","Icon","error");
                return
            end

            app.Results = loaded;
            app.Controls.Folder.Value = char(loaded.OutputRoot);
            if loaded.HasSpinup
                app.Controls.Scope.Items = cellstr(["Spinup","Monitored pre/post","All"]);
                app.Controls.Scope.ItemsData = cellstr(["Spinup","Monitored","All"]);
            else
                app.Controls.Scope.Items = cellstr(["Monitored pre/post","All"]);
                app.Controls.Scope.ItemsData = cellstr(["Monitored","All"]);
            end
            app.MapLimitCache = struct();
            app.SurfaceCache = {};
            app.SurfaceCacheEnabled = false;
            app.SurfaceCacheBytes = 0;
            app.clearMapHandles();
            xSpan = max(loaded.X,[],"all")-min(loaded.X,[],"all");
            ySpan = max(loaded.Y,[],"all")-min(loaded.Y,[],"all");
            app.Controls.TransposeMap.Value = ySpan > xSpan;
            labels = loaded.Variables.Label+"  ["+loaded.Variables.Unit+"]";
            app.Controls.Variables.Items = cellstr(labels);
            app.Controls.Variables.ItemsData = cellstr(loaded.Variables.Name);
            defaults = ["head_upstream_half_m","head_dam_upstream_1cell_m", ...
                "head_dam_downstream_1cell_m","head_downstream_half_m"];
            defaults = defaults(ismember(defaults,loaded.Variables.Name));
            if isempty(defaults)
                defaults = loaded.Variables.Name(1);
            end
            app.AcceptedVariables = defaults(:);
            app.Controls.Variables.Value = cellstr(app.AcceptedVariables);
            app.CurrentScopeKey = "Monitored";
            app.Controls.Scope.Value = char(app.CurrentScopeKey);
            app.CurrentFrame = 1;
            try
                app.preprocessHeadFields();
                app.prepareScope();
            catch exception
                app.enableDataControls(false);
                app.Controls.Load.Enable = "on";
                app.Controls.Browse.Enable = "on";
                app.setStatus(["Results were indexed, but display preparation failed:"; ...
                    string(exception.message)],true);
                uialert(app.UIFigure,exception.message,"Display Preparation Failed","Icon","error");
                return
            end
            app.Controls.Load.Enable = "on";
            app.Controls.Browse.Enable = "on";
            app.enableDataControls(true);
            scope = app.currentScope();
            if app.SurfaceCacheEnabled
                cacheStatus = sprintf("Memory cache: %.1f MiB across %d unique frames.", ...
                    app.SurfaceCacheBytes/2^20,app.totalUniqueFrames());
            else
                cacheStatus = sprintf("Indexed on-demand mode: estimated cache %.1f MiB exceeds 512 MiB.", ...
                    app.SurfaceCacheBytes/2^20);
            end
            app.setStatus(["Loaded completed BDam results."; ...
                "Resolution: "+loaded.TimeResolution; ...
                sprintf("Current scope: %d map frames, day %.6g to %.6g.", ...
                height(scope.Frames),scope.StartDay,scope.EndDay);cacheStatus], ...
                ~app.SurfaceCacheEnabled);
        end

        function enableDataControls(app,enabled)
            state = app.logicalEnable(enabled);
            names = ["Scope","DepthRaster","DepthContours","ElevationRaster", ...
                "ElevationContours","ShowLabels","TransposeMap","Variables", ...
                "Previous","Play","Next","Speed","Loop","Frame"];
            for name = names
                if isfield(app.Controls,name)
                    app.Controls.(name).Enable = state;
                end
            end
        end

        function value = logicalEnable(~,condition)
            if condition
                value = "on";
            else
                value = "off";
            end
        end

        function count = totalUniqueFrames(app)
            count = 0;
            for index = 1:numel(app.Results.Readers)
                count = count+app.Results.Readers{index}.NumFrames;
            end
        end

        function preprocessHeadFields(app)
            nx = size(app.Results.ZTop,1);
            ny = size(app.Results.ZTop,2);
            frameCount = app.totalUniqueFrames();
            app.SurfaceCacheBytes = 8*nx*ny*frameCount;
            app.SurfaceCache = {};
            app.SurfaceCacheEnabled = false;
            if app.SurfaceCacheBytes > 512*2^20
                return
            end

            progress = uiprogressdlg(app.UIFigure, ...
                "Title","Preprocessing groundwater heads", ...
                "Message","Reading saved heads into memory...", ...
                "Indeterminate","off","Cancelable","off");
            cleanup = onCleanup(@()delete(progress));
            app.SurfaceCache = cell(size(app.Results.Readers));
            completed = 0;
            try
                for readerIndex = 1:numel(app.Results.Readers)
                    reader = app.Results.Readers{readerIndex};
                    cube = nan(nx,ny,reader.NumFrames);
                    for frameIndex = 1:reader.NumFrames
                        cube(:,:,frameIndex) = reader.readWaterSurface(frameIndex);
                        completed = completed+1;
                        progress.Value = completed/frameCount;
                        progress.Message = sprintf( ...
                            "Workspace %d/%d, frame %d/%d", ...
                            readerIndex,numel(app.Results.Readers), ...
                            frameIndex,reader.NumFrames);
                        if mod(completed,5) == 0
                            drawnow limitrate
                        end
                    end
                    app.SurfaceCache{readerIndex} = cube;
                end
            catch exception
                app.SurfaceCache = {};
                rethrow(exception)
            end
            app.SurfaceCacheEnabled = true;
            for key = string(fieldnames(app.Results.Scopes))'
                app.ensureMapLimits(key);
            end
        end

        function surface = getWaterSurface(app,frame)
            if app.SurfaceCacheEnabled
                surface = app.SurfaceCache{frame.ReaderIndex}(:,:,frame.LocalFrame);
            else
                surface = app.Results.Readers{frame.ReaderIndex}.readWaterSurface( ...
                    frame.LocalFrame);
            end
        end

        function scopeChanged(app)
            if isempty(fieldnames(app.Results))
                return
            end
            app.stopAnimation(false);
            app.CurrentScopeKey = string(app.Controls.Scope.Value);
            app.CurrentFrame = 1;
            try
                app.prepareScope();
            catch exception
                app.setStatus(["Could not display selected scope:";string(exception.message)],true);
                uialert(app.UIFigure,exception.message,"Scope Failed","Icon","error");
            end
        end

        function prepareScope(app)
            scope = app.currentScope();
            frameCount = height(scope.Frames);
            app.CurrentFrame = min(app.CurrentFrame,frameCount);
            app.Controls.Frame.Limits = [0 max(1,frameCount-1)];
            app.Controls.Frame.Value = app.CurrentFrame-1;
            app.Controls.Frame.MajorTicks = [];
            app.ensureMapLimits(app.CurrentScopeKey);
            app.plotTimeSeries();
            app.rebuildMap();
        end

        function scope = currentScope(app)
            scope = app.Results.Scopes.(char(app.CurrentScopeKey));
        end

        function variablesChanged(app,source,event)
            selected = string(event.Value(:));
            if isempty(selected)
                source.Value = cellstr(app.AcceptedVariables);
                app.setStatus("Select at least one monitoring variable.",true);
                return
            end
            rows = ismember(app.Results.Variables.Name,selected);
            units = unique(app.Results.Variables.Unit(rows),"stable");
            if numel(units) > 2
                source.Value = cellstr(app.AcceptedVariables);
                app.setStatus("Selection rejected: use at most two unit families.",true);
                return
            end
            app.AcceptedVariables = selected;
            app.plotTimeSeries();
            app.rebuildMap();
        end

        function plotTimeSeries(app)
            if isempty(fieldnames(app.Results))
                return
            end
            axesHandle = app.TimeSeriesAxes;
            cla(axesHandle,"reset");
            axesHandle.Box = "on";
            grid(axesHandle,"on");
            hold(axesHandle,"on");
            scope = app.currentScope();
            summary = scope.Summary;
            selected = app.AcceptedVariables;
            metadata = app.Results.Variables;
            rows = ismember(metadata.Name,selected);
            units = unique(metadata.Unit(rows),"stable");
            colors = lines(max(1,numel(selected)));
            plotted = gobjects(0);
            plotLabels = strings(0,1);
            for unitIndex = 1:numel(units)
                if numel(units) == 2
                    if unitIndex == 1
                        yyaxis(axesHandle,"left");
                    else
                        yyaxis(axesHandle,"right");
                    end
                end
                members = selected(ismember(selected,metadata.Name(metadata.Unit == units(unitIndex))));
                for member = members(:)'
                    if ~ismember(member,string(summary.Properties.VariableNames))
                        continue
                    end
                    colorIndex = find(selected == member,1);
                    handle = plot(axesHandle,summary.time_days,summary.(member), ...
                        "LineWidth",1.35,"Color",colors(colorIndex,:));
                    plotted(end+1,1) = handle; %#ok<AGROW>
                    plotLabels(end+1,1) = metadata.Label(metadata.Name == member); %#ok<AGROW>
                end
                ylabel(axesHandle,units(unitIndex));
            end
            xlim(axesHandle,[scope.StartDay scope.EndDay]+ ...
                [-1 1]*max(1.0e-9,0.01*(scope.EndDay-scope.StartDay)));
            xlabel(axesHandle,"Elapsed model time (days)");
            title(axesHandle,scope.Name+" monitoring time series");
            if ~isempty(plotted)
                legend(axesHandle,plotted,cellstr(plotLabels), ...
                    "Location","best","Interpreter","none");
            end
            app.addPhaseBoundaries();
            currentTime = scope.Frames.TimeDays(app.CurrentFrame);
            app.CurrentTimeLine = xline(axesHandle,currentTime,"k-", ...
                "Current time","LineWidth",1.6, ...
                "LabelVerticalAlignment","bottom","HandleVisibility","off");
            hold(axesHandle,"off");
        end

        function addPhaseBoundaries(app)
            scope = app.currentScope();
            frames = scope.Frames;
            changes = [false;frames.Phase(2:end) ~= frames.Phase(1:end-1) | ...
                frames.PhaseYear(2:end) ~= frames.PhaseYear(1:end-1)];
            for row = find(changes)'
                label = replace(frames.Phase(row),"_"," ")+ ...
                    sprintf(" y%d",frames.PhaseYear(row));
                xline(app.TimeSeriesAxes,frames.TimeDays(row),":",label, ...
                    "Color",[0.4 0.4 0.4],"HandleVisibility","off", ...
                    "LabelVerticalAlignment","top");
            end
        end

        function mapAssignmentChanged(app,changed)
            controls = app.Controls;
            switch changed
                case "DepthRaster"
                    if controls.DepthRaster.Value
                        controls.ElevationRaster.Value = false;
                        if controls.DepthContours.Value
                            controls.DepthContours.Value = false;
                            controls.ElevationContours.Value = true;
                        end
                    elseif ~controls.ElevationRaster.Value
                        controls.DepthRaster.Value = true;
                        app.setStatus("A color-raster quantity must remain selected.",true);
                    end
                case "ElevationRaster"
                    if controls.ElevationRaster.Value
                        controls.DepthRaster.Value = false;
                        if controls.ElevationContours.Value
                            controls.ElevationContours.Value = false;
                            controls.DepthContours.Value = true;
                        end
                    elseif ~controls.DepthRaster.Value
                        controls.ElevationRaster.Value = true;
                        app.setStatus("A color-raster quantity must remain selected.",true);
                    end
                case "DepthContours"
                    if controls.DepthContours.Value
                        controls.ElevationContours.Value = false;
                        if controls.DepthRaster.Value
                            controls.DepthRaster.Value = false;
                            controls.ElevationRaster.Value = true;
                        end
                    end
                case "ElevationContours"
                    if controls.ElevationContours.Value
                        controls.DepthContours.Value = false;
                        if controls.ElevationRaster.Value
                            controls.ElevationRaster.Value = false;
                            controls.DepthRaster.Value = true;
                        end
                    end
            end
            app.rebuildMap();
        end

        function ensureMapLimits(app,scopeKey)
            key = char(scopeKey);
            if isfield(app.MapLimitCache,key)
                return
            end
            scope = app.Results.Scopes.(key);
            progress = [];
            if ~app.SurfaceCacheEnabled
                progress = uiprogressdlg(app.UIFigure, ...
                    "Title","Preparing map scale", ...
                    "Message","Scanning saved groundwater heads...", ...
                    "Indeterminate","off","Cancelable","off");
            end
            cleanup = onCleanup(@()app.deleteIfValid(progress));
            wseMin = Inf; wseMax = -Inf; depthMin = Inf; depthMax = -Inf;
            frameIndices = 1:height(scope.Frames);
            if app.Results.HasSpinup && any(string(scopeKey) == ["Spinup","All"]) && ...
                    numel(frameIndices) > 1
                frameIndices = frameIndices(2:end);
            end
            for scanIndex = 1:numel(frameIndices)
                frameIndex = frameIndices(scanIndex);
                frame = scope.Frames(frameIndex,:);
                surface = app.getWaterSurface(frame);
                depth = app.Results.ZTop-surface;
                validSurface = surface(isfinite(surface));
                validDepth = depth(isfinite(depth));
                if ~isempty(validSurface)
                    wseMin = min(wseMin,min(validSurface));
                    wseMax = max(wseMax,max(validSurface));
                end
                if ~isempty(validDepth)
                    depthMin = min(depthMin,min(validDepth));
                    depthMax = max(depthMax,max(validDepth));
                end
                if ~isempty(progress)
                    progress.Value = scanIndex/numel(frameIndices);
                    if mod(scanIndex,5) == 0
                        drawnow limitrate
                    end
                end
            end
            if any(~isfinite([wseMin wseMax depthMin depthMax]))
                error("BDam:ResultsHeads", ...
                    "Selected scope contains no valid groundwater-head values.");
            end
            app.MapLimitCache.(key) = struct( ...
                "WSE",app.expandLimits([wseMin wseMax]), ...
                "Depth",app.expandLimits([depthMin depthMax]));
        end

        function limits = expandLimits(~,limits)
            if limits(1) == limits(2)
                padding = max(1.0e-6,0.01*abs(limits(1)));
                limits = limits+[-padding padding];
            end
        end

        function deleteIfValid(~,handle)
            if ~isempty(handle) && isvalid(handle)
                delete(handle);
            end
        end

        function sliderChanged(app,value)
            if isempty(fieldnames(app.Results))
                return
            end
            app.stopAnimation(false);
            app.setFrame(round(value)+1);
        end

        function stepFrame(app,increment)
            app.stopAnimation(false);
            scope = app.currentScope();
            app.setFrame(max(1,min(height(scope.Frames),app.CurrentFrame+increment)));
        end

        function setFrame(app,frameIndex)
            scope = app.currentScope();
            frameIndex = max(1,min(height(scope.Frames),round(frameIndex)));
            app.CurrentFrame = frameIndex;
            app.Controls.Frame.Value = frameIndex-1;
            app.updateMapFrame();
            if ~isempty(app.CurrentTimeLine) && isvalid(app.CurrentTimeLine)
                app.CurrentTimeLine.Value = scope.Frames.TimeDays(frameIndex);
            end
            drawnow limitrate
        end

        function clearMapHandles(app)
            app.MapImage = [];
            app.MapContour = [];
            app.MapColorbar = [];
            app.MapTitle = [];
        end

        function rebuildMap(app)
            if isempty(fieldnames(app.Results))
                return
            end
            scope = app.currentScope();
            frame = scope.Frames(app.CurrentFrame,:);
            surface = app.getWaterSurface(frame);
            depth = app.Results.ZTop-surface;
            axesHandle = app.MapAxes;
            app.clearMapHandles();
            cla(axesHandle,"reset");
            colorbar(axesHandle,"off");
            axesHandle.Box = "on";
            hold(axesHandle,"on");
            x = app.Results.X(:,1);
            y = app.Results.Y(1,:);
            transposeMap = app.Controls.TransposeMap.Value;
            limits = app.MapLimitCache.(char(app.CurrentScopeKey));
            if app.Controls.DepthRaster.Value
                rasterData = depth;
                rasterLimits = limits.Depth;
                colorLabel = "Depth to water (m)";
            else
                rasterData = surface;
                rasterLimits = limits.WSE;
                colorLabel = "Water-surface elevation (m)";
            end
            if transposeMap
                app.MapImage = imagesc(axesHandle,y,x,rasterData);
            else
                app.MapImage = imagesc(axesHandle,x,y,rasterData');
            end
            clim(axesHandle,rasterLimits);
            set(axesHandle,"YDir","normal");
            axis(axesHandle,"image");
            colormap(axesHandle,parula(256));
            app.MapColorbar = colorbar(axesHandle);
            app.MapColorbar.Label.String = colorLabel;
            drawContours = app.Controls.DepthContours.Value || ...
                app.Controls.ElevationContours.Value;
            if drawContours
                if app.Controls.DepthContours.Value
                    contourData = depth;
                    contourLimits = limits.Depth;
                else
                    contourData = surface;
                    contourLimits = limits.WSE;
                end
                contourLevels = linspace(contourLimits(1),contourLimits(2),10);
                if transposeMap
                    [~,app.MapContour] = contour(axesHandle, ...
                        app.Results.Y,app.Results.X,contourData, ...
                        contourLevels,"LineColor",[0.08 0.08 0.08],"LineWidth",0.8, ...
                        "HandleVisibility","off");
                else
                    [~,app.MapContour] = contour(axesHandle, ...
                        app.Results.X',app.Results.Y',contourData', ...
                        contourLevels,"LineColor",[0.08 0.08 0.08],"LineWidth",0.8, ...
                        "HandleVisibility","off");
                end
            end
            app.plotMonitoringPoints();
            if transposeMap
                xlabel(axesHandle,"Y (m)");
                ylabel(axesHandle,"X (m)");
            else
                xlabel(axesHandle,"X (m)");
                ylabel(axesHandle,"Y (m)");
            end
            phaseLabel = replace(frame.Phase,"_"," ");
            app.MapTitle = title(axesHandle,sprintf("%s, year %d | day %.6g", ...
                phaseLabel,frame.PhaseYear,frame.TimeDays),"Interpreter","none");
            app.Controls.Time.Text = sprintf("Frame %d/%d | day %.6g", ...
                app.CurrentFrame-1,height(scope.Frames)-1,frame.TimeDays);
            hold(axesHandle,"off");
            drawnow limitrate
        end

        function updateMapFrame(app)
            if isempty(fieldnames(app.Results)) || isempty(app.MapImage) || ...
                    ~isgraphics(app.MapImage)
                app.rebuildMap();
                return
            end
            scope = app.currentScope();
            frame = scope.Frames(app.CurrentFrame,:);
            surface = app.getWaterSurface(frame);
            depth = app.Results.ZTop-surface;
            if app.Controls.DepthRaster.Value
                rasterData = depth;
            else
                rasterData = surface;
            end
            if app.Controls.TransposeMap.Value
                app.MapImage.CData = rasterData;
            else
                app.MapImage.CData = rasterData';
            end
            if ~isempty(app.MapContour) && isgraphics(app.MapContour)
                if app.Controls.DepthContours.Value
                    contourData = depth;
                else
                    contourData = surface;
                end
                if app.Controls.TransposeMap.Value
                    app.MapContour.ZData = contourData;
                else
                    app.MapContour.ZData = contourData';
                end
            end
            phaseLabel = replace(frame.Phase,"_"," ");
            app.MapTitle.String = sprintf("%s, year %d | day %.6g", ...
                phaseLabel,frame.PhaseYear,frame.TimeDays);
            app.Controls.Time.Text = sprintf("Frame %d/%d | day %.6g", ...
                app.CurrentFrame-1,height(scope.Frames)-1,frame.TimeDays);
        end

        function plotMonitoringPoints(app)
            targets = app.Results.Targets;
            if app.Controls.TransposeMap.Value
                horizontal = targets.resolved_y_m;
                vertical = targets.resolved_x_m;
            else
                horizontal = targets.resolved_x_m;
                vertical = targets.resolved_y_m;
            end
            scatter(app.MapAxes,horizontal,vertical,34, ...
                "o","MarkerFaceColor","w","MarkerEdgeColor","k", ...
                "LineWidth",0.8,"HandleVisibility","off");
            selectedTargets = strings(0,1);
            for variable = app.AcceptedVariables(:)'
                if startsWith(variable,"head_") && endsWith(variable,"_m")
                    selectedTargets(end+1,1) = extractBefore(variable,strlength(variable)-1); %#ok<AGROW>
                end
            end
            highlighted = ismember(targets.name,selectedTargets);
            if any(highlighted)
                scatter(app.MapAxes,horizontal(highlighted), ...
                    vertical(highlighted),52,"o", ...
                    "MarkerFaceColor",[0.86 0.12 0.12],"MarkerEdgeColor","w", ...
                    "LineWidth",1.1,"HandleVisibility","off");
                if app.Controls.ShowLabels.Value
                    labels = erase(targets.name(highlighted),"head_");
                    labels = replace(replace(labels,"_"," "),"1cell","1 cell");
                    count = nnz(highlighted);
                    ySigns = repmat([1;-1],ceil(count/2),1);
                    ySigns = ySigns(1:count);
                    horizontalOffset = 0.012*(max(horizontal)-min(horizontal));
                    verticalRange = max(vertical)-min(vertical);
                    verticalOffset = 0.02*verticalRange*ySigns;
                    text(app.MapAxes,horizontal(highlighted)+horizontalOffset, ...
                        vertical(highlighted)+verticalOffset,labels, ...
                        "Color",[0.15 0.05 0.05],"FontSize",9, ...
                        "FontWeight","bold","Interpreter","none");
                end
            end
        end

        function toggleAnimation(app)
            if ~isempty(app.AnimationTimer) && isvalid(app.AnimationTimer) && ...
                    strcmp(app.AnimationTimer.Running,"on")
                app.stopAnimation(false);
                return
            end
            scope = app.currentScope();
            if app.CurrentFrame >= height(scope.Frames) && ~app.Controls.Loop.Value
                app.setFrame(1);
            end
            app.createAnimationTimer();
            app.Controls.Play.Text = "Pause";
            start(app.AnimationTimer);
        end

        function createAnimationTimer(app)
            app.stopAnimation(true);
            app.AnimationTimer = timer( ...
                "ExecutionMode","fixedRate", ...
                "BusyMode","drop", ...
                "Period",1/double(app.Controls.Speed.Value), ...
                "TimerFcn",@(~,~)app.animationTick(), ...
                "ErrorFcn",@(~,event)app.animationFailed(event));
        end

        function animationTick(app)
            if isempty(fieldnames(app.Results)) || ...
                    isempty(app.UIFigure) || ~isvalid(app.UIFigure)
                app.stopAnimation(true);
                return
            end
            scope = app.currentScope();
            next = app.CurrentFrame+1;
            if next > height(scope.Frames)
                if app.Controls.Loop.Value
                    next = 1;
                else
                    app.stopAnimation(false);
                    return
                end
            end
            app.setFrame(next);
        end

        function animationFailed(app,event)
            app.stopAnimation(true);
            message = "Animation stopped because MATLAB reported a timer error.";
            if isprop(event,"Data") && isa(event.Data,"MException")
                message = message+" "+string(event.Data.message);
            end
            app.setStatus(message,true);
        end

        function speedChanged(app)
            wasRunning = ~isempty(app.AnimationTimer) && isvalid(app.AnimationTimer) && ...
                strcmp(app.AnimationTimer.Running,"on");
            app.stopAnimation(true);
            if wasRunning
                app.toggleAnimation();
            end
        end

        function stopAnimation(app,removeTimer)
            if ~isempty(app.AnimationTimer) && isvalid(app.AnimationTimer)
                if strcmp(app.AnimationTimer.Running,"on")
                    stop(app.AnimationTimer);
                end
                if removeTimer
                    delete(app.AnimationTimer);
                    app.AnimationTimer = [];
                end
            end
            if isfield(app.Controls,"Play") && isvalid(app.Controls.Play)
                app.Controls.Play.Text = "Play";
            end
        end

        function setStatus(app,lines,isWarning)
            app.Controls.Status.Value = cellstr(string(lines(:)));
            if isWarning
                app.Controls.Status.FontColor = [0.72 0.32 0.02];
            else
                app.Controls.Status.FontColor = [0.12 0.22 0.32];
            end
        end
    end

    methods (Access = public)
        function app = BDamResultsViewerApp(outputRoot)
            arguments
                outputRoot {mustBeTextScalar} = ""
            end
            app.createComponents();
            registerApp(app,app.UIFigure);
            app.startup(string(outputRoot));
            if nargout == 0
                clear app
            end
        end

        function delete(app)
            app.stopAnimation(true);
            app.SurfaceCache = {};
            app.SurfaceCacheEnabled = false;
            app.clearMapHandles();
            if ~isempty(app.UIFigure) && isvalid(app.UIFigure)
                app.UIFigure.CloseRequestFcn = [];
                delete(app.UIFigure);
            end
        end
    end
end
