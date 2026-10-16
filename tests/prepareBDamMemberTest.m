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
            config.geometry.dam_max_m=0.5;
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
            testCase.verifyEqual(string(h5readatt(post,"/","schema_version")),"bdam-preparation-hdf5-v7");
            for file = [pre,post]
                testCase.verifyEqual(h5read(file,"/boundaries/edge_flux/x_min_m3_per_day/data"),3);
                testCase.verifyEqual(h5read(file,"/boundaries/edge_flux/x_max_m3_per_day/data"),-5);
                testCase.verifyEqual(h5read(file,"/boundaries/edge_flux/y_max_m3_per_day/data"),7);
            end
            testCase.verifyEqual(h5read(post,"/properties/K/data"),h5read(post,"/properties/K_background/data"));
            testCase.verifyEqual(h5read(post,"/properties/K33/data"),h5read(post,"/properties/K33_background/data"));
            testCase.verifyEqual(h5read(post,"/surface_water/n_lakes/data"),3);
        end
    end
end
