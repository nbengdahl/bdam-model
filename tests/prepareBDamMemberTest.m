classdef prepareBDamMemberTest < matlab.unittest.TestCase
    methods (Test)
        function lowDamWithBackgroundConductivityPrepares(testCase)
            source=string(fileparts(fileparts(mfilename("fullpath"))));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture(source));
            folder=testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
            root=string(folder.Folder);
            config=defaultBDamConfig();
            config.groundwater_edge_flux=struct("x_min_m3_per_day",3, ...
                "x_max_m3_per_day",-5,"y_max_m3_per_day",7);
            config.geometry.dam_height_m=0.5;
            config.dam_settings.k_multiplier=1;
            config.dam_settings.k33_multiplier=1;
            config.groundwater_boundary_k_m_per_day=config.K_constant;
            config.K_by_layer_top_to_bottom=repmat(0.03,1,config.n_layers);
            config.K33_by_layer_top_to_bottom=repmat(0.003,1,config.n_layers);
            config.source_root=root;
            config.source_geometry_file=fullfile(root,"Geometry","BDamGeometry.mat");
            config.usgs_hydrograph_file=fullfile(source,"usgs_13348000_hydrograph.csv");
            config.reference_mean_streamflow_m3_per_day=config.synthetic_mean_streamflow_m3_per_day;
            buildBDamGeometry(config.geometry,config.source_geometry_file);
            prepareBDamMember(config,root,false);
            pre=fullfile(root,"ModelInput","pre_dam","preparation_handoff.h5");
            post=fullfile(root,"ModelInput","post_dam","preparation_handoff.h5");
            testCase.verifyTrue(isfile(pre));
            testCase.verifyTrue(isfile(post));
            testCase.verifyEqual(string(h5readatt(post,"/","schema_version")),"bdam-preparation-hdf5-v8");
            for file = [pre,post]
                testCase.verifyEqual(h5read(file,"/boundaries/edge_flux/x_min_m3_per_day/data"),3);
                testCase.verifyEqual(h5read(file,"/boundaries/edge_flux/x_max_m3_per_day/data"),-5);
                testCase.verifyEqual(h5read(file,"/boundaries/edge_flux/y_max_m3_per_day/data"),7);
            end
            testCase.verifyEqual(h5read(post,"/properties/K/data"),h5read(post,"/properties/K_background/data"));
            testCase.verifyEqual(h5read(post,"/properties/K33/data"),h5read(post,"/properties/K33_background/data"));
            testCase.verifyEqual(h5read(post,"/surface_water/n_lakes/data"),3);
            top=h5read(post,"/grid/ZTop/data");
            mask=logical(h5read(post,"/surface_water/lakes/lake_1/storage_footprint_mask/data"));
            exchange=logical(h5read(post,"/surface_water/lakes/lake_1/footprint_mask/data"));
            stage=h5read(post,"/surface_water/lakes/lake_1/stage_area_volume/stage_m/data");
            volume=h5read(post,"/surface_water/lakes/lake_1/stage_area_volume/volume_m3/data");
            area=h5read(post,"/surface_water/lakes/lake_1/stage_area_volume/area_m2/data");
            terrain=top(mask);
            testCase.verifyEqual(stage(1),min(top(exchange)));
            testCase.verifyEqual(volume(1),0);
            testCase.verifyGreaterThan(area(1),0);
            testCase.verifyTrue(all(diff(volume)>0));
            testCase.verifyTrue(all(ismember(unique(terrain),stage)));
            % The default cell area is 1 m2. Disconnected pockets need not
            % contribute at intermediate stages, but the first bed interval
            % has exactly the storage of its lowest terrain cells.
            for q=1:numel(stage)
                expected=sum(max(stage(q)-terrain,0));
                testCase.verifyLessThanOrEqual(volume(q),expected+1e-9);
            end
            mid=(stage(1)+stage(2))/2;
            testCase.verifyEqual(interp1(stage,volume,mid), ...
                sum(max(mid-terrain,0)),AbsTol=1e-12);
            cap=h5read(post,"/surface_water/dam/maximum_lake_extent_stage_m/data");
            testCase.verifyEqual(area(stage>=cap),repmat(nnz(mask),nnz(stage>=cap),1));
        end
    end
end
