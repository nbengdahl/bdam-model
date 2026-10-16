classdef evaluateBDamCasesTest < matlab.unittest.TestCase
    methods (TestClassSetup)
        function sourcePath(testCase)
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fileparts(fileparts(mfilename("fullpath")))));
        end
    end
    methods (Test)
        function tableNamesAndAutomaticValuesRoundtrip(testCase)
            folder=string(tempname); mkdir(folder);
            testCase.addTeardown(@()rmdir(folder,"s"));
            cases=table(["a";"b"],[0.01;0.02],[3;4],{[];[]},["α";"β"], ...
                VariableNames=["case_id","K_constant", ...
                "geometry.bottom_widths_m[1]","groundwater_boundary_k_m_per_day","metadata.label"]);
            result=evaluateBDamCases(cases,folder,"matlab",Action="submit");
            testCase.verifyNumElements(result.members,2);
            testCase.verifyEqual(string(result.cases(1).metadata.label),"α");
            testCase.verifyEqual(result.cases(1).resolved_parameters.K_constant,0.01,AbsTol=1e-12);
            testCase.verifyEqual(result.cases(1).resolved_parameters.geometry.bottom_widths_m,[3;10],AbsTol=1e-12);
            testCase.verifyEqual(result.cases(1).resolved_parameters.groundwater_boundary_k_m_per_day,0.01,AbsTol=1e-12);
        end
        function blankMonitoringFilenameAccepted(testCase)
            folder=string(tempname); mkdir(folder);
            testCase.addTeardown(@()rmdir(folder,"s"));
            cases=table(["a";"b";"c"],["";"   ";string(missing)], ...
                VariableNames=["case_id","monitoring_points_file"]);
            result=evaluateBDamCases(cases,folder,"monitoring",Action="submit");
            testCase.verifyNumElements(result.members,1);
            for row=1:3
                testCase.verifyEqual(string(result.cases(row).resolved_parameters.monitoring_points_file),"");
            end
        end
        function missingCellRejected(testCase)
            cases=table(string(missing),VariableNames="case_id");
            testCase.verifyError(@()evaluateBDamCases(cases,"unused","bad",Action="submit"),"BDam:MissingCell");
        end
    end
end
