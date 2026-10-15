classdef makeCoarseRiverScenarioTest < matlab.unittest.TestCase
    properties (TestParameter)
        Scenario = struct('preDam',"pre_dam",'postDam',"post_dam")
    end

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            sourceFolder = fileparts(fileparts(mfilename("fullpath")));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture(sourceFolder));
        end
    end

    methods (Test)
        function interiorDepressionDoesNotLowerOutlet(testCase,Scenario)
            f = makeCoarseRiverScenarioTest.fixture(Scenario,false);
            [~,outlets] = makeCoarseRiverScenario(Scenario,f.lake,f.outlets, ...
                f.top,f.layers,f.X,f.Y,1,1,f.geometry,f.dam,f.upstream, ...
                f.channel,f.settings);
            riverOutlets = outlets(outlets.role=="channel_manning",:);
            testCase.verifyEqual(riverOutlets.invert_elevation_m(1), ...
                f.expectedOutlet,AbsTol=1e-12);
            testCase.verifyGreaterThan(riverOutlets.invert_elevation_m(1), ...
                f.interiorMinimum);
            testCase.verifyEqual(riverOutlets.invert_elevation_m(end), ...
                f.externalInvert,AbsTol=1e-12);
        end

        function offChannelDepressionDoesNotSetOutlet(testCase,Scenario)
            f = makeCoarseRiverScenarioTest.fixture(Scenario,true);
            [~,outlets] = makeCoarseRiverScenario(Scenario,f.lake,f.outlets, ...
                f.top,f.layers,f.X,f.Y,1,1,f.geometry,f.dam,f.upstream, ...
                f.channel,f.settings);
            riverOutlets = outlets(outlets.role=="channel_manning",:);
            testCase.verifyEqual(riverOutlets.invert_elevation_m(1), ...
                f.expectedOutlet,AbsTol=1e-12);
            testCase.verifyGreaterThan(riverOutlets.invert_elevation_m(1), ...
                f.offChannelMinimum);
        end

        function damWeirStillUsesCrest(testCase)
            f = makeCoarseRiverScenarioTest.fixture("post_dam",false);
            [~,outlets] = makeCoarseRiverScenario("post_dam",f.lake,f.outlets, ...
                f.top,f.layers,f.X,f.Y,1,1,f.geometry,f.dam,f.upstream, ...
                f.channel,f.settings);
            testCase.verifyEqual(outlets.role(1),"dam_crest_weir");
            testCase.verifyEqual(outlets.invert_elevation_m(1), ...
                f.dam.crest_elevation_m,AbsTol=1e-12);
        end
    end

    methods (Static, Access = private)
        function f = fixture(scenario,offChannelPit)
            [f.Y,f.X] = meshgrid(0.5:19.5,0.5:4.5);
            f.top = 0.01*f.Y + [1;0.3;0;0.3;1];
            % Every pool has a deeper interior cell upstream of its exit.
            f.top(3,2:2:end) = f.top(3,2:2:end)-0.05;
            f.channel = false(size(f.top));
            f.channel(3,:) = true;
            firstRow = 19;
            if scenario=="post_dam", firstRow=3; end
            f.expectedOutlet = f.top(3,firstRow);
            f.interiorMinimum = f.top(3,firstRow+1);
            if offChannelPit
                f.top(2,firstRow) = f.expectedOutlet-0.025;
            end
            f.offChannelMinimum = f.top(2,firstRow);
            f.layers = cat(3,f.top-2,f.top);
            f.upstream = f.Y>=4;
            p = struct('sine_periods',0,'domain_length_y_m',20, ...
                'sine_amplitude_m',0,'origin_y_m',0, ...
                'channel_longitudinal_slope',0.01);
            f.geometry = struct('parameters',p,'dam_centerline_station_m',4);
            f.dam = struct('crest_elevation_m',0.9, ...
                'grid_mask',false(size(f.top)));
            f.settings = struct('downstream_segments',2, ...
                'manning_roughness',0.04,'manning_width_m',2, ...
                'pond_exchange_height_above_thalweg_m',1.25, ...
                'river_storage_height_above_highest_bed_m',0.5);
            f.lake = struct('name',"pond",'lake_id',1, ...
                'initial_stage_m',0.1,'footprint_mask',f.channel & f.upstream, ...
                'storage_footprint_mask',f.channel & f.upstream, ...
                'lakebed_vertical_k_m_per_day',0.05, ...
                'lakebed_thickness_m',0.25,'stage_area_volume',table());
            f.externalInvert = 0.007; % Explicit control differs from local bed.
            f.outlets = table(2,f.externalInvert, ...
                VariableNames={'width_m','invert_elevation_m'});
        end
    end
end
