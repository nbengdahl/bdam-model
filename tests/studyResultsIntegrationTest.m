classdef studyResultsIntegrationTest < matlab.unittest.TestCase
    properties
        Root
    end
    methods (TestClassSetup)
        function completedCase(testCase)
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fileparts(fileparts(mfilename("fullpath")))));
            testCase.Root=string(getenv("BDAM_TEST_OUTPUT_ROOT"));
            testCase.assumeTrue(isfile(fullfile(testCase.Root,"completion.json")), ...
                "Set BDAM_TEST_OUTPUT_ROOT to a fully validated study execution.");
        end
    end
    methods (Test)
        function loaderUsesActualTopology(testCase)
            config=jsondecode(fileread(fullfile(testCase.Root,"resolved_config.json")));
            pre=jsondecode(fileread(fullfile(testCase.Root,"ModelInput", ...
                "pre_dam","preparation_manifest.json")));
            post=jsondecode(fileread(fullfile(testCase.Root,"ModelInput", ...
                "post_dam","preparation_manifest.json")));
            testCase.verifyEqual(post.n_lakes,config.river_settings.downstream_segments+1);
            result=loadBDamResults(testCase.Root);
            testCase.verifyTrue(ismember("lake"+pre.n_lakes+"_stage_m",result.Variables.Name));
            testCase.verifyEqual(result.Scopes.Monitored.EndDay, ...
                365*(config.mf6_parameters.pre_dam_years+config.mf6_parameters.post_dam_years),AbsTol=1e-8);
        end
        function viewerLoadsAndSelectsDynamicSeries(testCase)
            app=LaunchBDamResultsViewerApp(testCase.Root);
            testCase.addTeardown(@()delete(app));
            buttons=findall(app.UIFigure,"Type","uibutton");
            button=buttons(string({buttons.Text})=="Load");
            testCase.assertNumElements(button,1);
            feval(button.ButtonPushedFcn,button,[]);
            testCase.verifyNumElements(findall(app.MapAxes,"Type","image"),1);
            variables=findall(app.UIFigure,"Type","uilistbox");
            entries=string(variables(1).ItemsData);
            pre=jsondecode(fileread(fullfile(testCase.Root,"ModelInput", ...
                "pre_dam","preparation_manifest.json")));
            testCase.verifyTrue(ismember("lake"+pre.n_lakes+"_stage_m",entries));
        end
    end
end
