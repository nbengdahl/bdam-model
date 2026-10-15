classdef bdamRiverPoolEdgesTest < matlab.unittest.TestCase
    properties (TestParameter)
        Segments = struct('one',1,'two',2,'three',3)
    end
    methods (TestClassSetup)
        function addSource(testCase)
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fileparts(fileparts(mfilename("fullpath")))));
        end
    end
    methods (Test)
        function exactFit(testCase,Segments)
            [edges,nup]=bdamRiverPoolEdges(6,24,Segments);
            testCase.verifyEqual(nup,3*Segments);
            testCase.verifyEqual(diff(edges),repmat(6/Segments,1,4*Segments),AbsTol=1e-10);
        end
        function upstreamRemainderEnlargesLastPool(testCase)
            [edges,nup]=bdamRiverPoolEdges(6,23,2);
            testCase.verifyEqual(nup,5);
            testCase.verifyEqual(diff(edges),[3 3 3 3 3 3 5],AbsTol=1e-10);
        end
        function shortUpstreamReachHasOnePool(testCase)
            [edges,nup]=bdamRiverPoolEdges(6,8,1);
            testCase.verifyEqual(nup,1);
            testCase.verifyEqual(edges,[0 6 8],AbsTol=1e-10);
        end
        function exactFitToleratesRoundoff(testCase)
            [~,nup]=bdamRiverPoolEdges(6,24-1e-12,2);
            testCase.verifyEqual(nup,6);
        end
        function invalidCountRejected(testCase)
            testCase.verifyError(@()bdamRiverPoolEdges(6,24,1.5), ...
                "MATLAB:validators:mustBeInteger");
        end
    end
end
