classdef makeBDamMonitoringTest < matlab.unittest.TestCase
    methods (TestClassSetup)
        function path(testCase)
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fileparts(fileparts(mfilename("fullpath")))));
        end
    end
    methods (Test)
        function blankKeepsOriginalTenPoints(testCase)
            mon=fixture("");
            testCase.verifyNumElements(mon.head_point_names,10);
            testCase.verifyEqual(mon.head_points_resolved_layer_top_down,3*ones(10,1));
            testCase.verifyEqual(mon.head_point_names(5),"head_domain_x25_y25_bottom");
            testCase.verifyEqual(mon.head_points_requested_xy_layer(5:end,1:2), ...
                [1.75,2.25;1.75,4;1.75,5.75;4.25,2.25;4.25,4;4.25,5.75]);
            testCase.verifyEmpty(mon.omitted_points);
            testCase.verifyEqual(fixture("   "),mon);
        end
        function depthsFacesAndOmittedRows(testCase)
            folder=testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
            file=fullfile(folder.Folder,"points.csv");
            text="X,Y,Z,Name"+newline+ ...
                "0,0,0,Surface label"+newline+ ...
                "7,1,1,Outside"+newline+ ...
                "3,4,3,Interface α"+newline+ ...
                "3,4,6,Deeper interface"+newline+ ...
                "6,8,10,Bottom corner"+newline+ ...
                "2,2,-1,Above ground"+newline+ ...
                "2,2,11,Below bottom"+newline+ ...
                "3,4,1,Same cell different depth"+newline;
            writeText(file,text);
            mon=fixture(file);
            testCase.verifyNumElements(mon.head_point_names,9);
            testCase.verifyEqual(mon.head_point_names(5:end), ...
                ["head_csv_0001";"head_csv_0003";"head_csv_0004";"head_csv_0005";"head_csv_0008"]);
            testCase.verifyEqual(mon.head_points_resolved_layer_top_down(5:end),[1;2;3;3;1]);
            testCase.verifyEqual(mon.head_points_resolved_i_x(5:end),[1;4;4;6;4]);
            testCase.verifyEqual(mon.head_points_resolved_i_y(5:end),[1;5;5;8;5]);
            testCase.verifyEqual(mon.head_point_labels(6),"Interface α");
            testCase.verifyEqual([mon.target_metadata(5:end).resolved_z_m]',[8.5;5.5;2;2;8.5]);
            testCase.verifyEqual([mon.omitted_points.csv_row]',[2;6;7]);
            testCase.verifyTrue(all(strlength(string({mon.omitted_points.reason}))>0));
            original=fixture("");
            testCase.verifyEqual(mon.head_points_resolved_i_x(1:4),original.head_points_resolved_i_x(1:4));
            testCase.verifyEqual(mon.head_points_resolved_i_y(1:4),original.head_points_resolved_i_y(1:4));
        end
        function decimalSpacingInternalFaceSelectsIncreasingCell(testCase)
            folder=testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
            file=fullfile(folder.Folder,"decimal.csv");
            writeText(file,"x,y,z,name"+newline+"0.3,0.4,1,Decimal face"+newline);
            mon=fixture(file,0.1);
            testCase.verifyEqual(mon.head_points_resolved_i_x(5),4);
            testCase.verifyEqual(mon.head_points_resolved_i_y(5),5);
            writeText(file,"x,y,z,name"+newline+"0.2,0.2,0,Origin face"+newline+"1.4,1.8,0,Maximum face"+newline);
            mon=fixture(file,0.2,0.2);
            testCase.verifyEqual(mon.head_points_resolved_i_x(5:end),[1;6]);
            testCase.verifyEqual(mon.head_points_resolved_i_y(5:end),[1;8]);
        end
        function emptyHeaderOnlyAndAllOutsideKeepStreamPoints(testCase)
            folder=testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
            file=fullfile(folder.Folder,"empty.csv");
            for text=["", "x,y,z,name"+newline, "x,y,z,name"+newline+"-1,1,1,Outside"+newline]
                writeText(file,text);
                mon=fixture(file);
                testCase.verifyNumElements(mon.head_point_names,4);
            end
        end
        function malformedAndDuplicateRetainedNamesFail(testCase)
            folder=testCase.applyFixture(matlab.unittest.fixtures.TemporaryFolderFixture);
            file=fullfile(folder.Folder,"bad.csv");
            for text=["x,y,name"+newline+"1,1,A", ...
                    "x,y,z,name"+newline+"1,1,NaN,A", ...
                    "x,y,z,name"+newline+"1,1,abc,A", ...
                    "x,y,z,name"+newline+"1,1,1,"+newline, ...
                    "x,y,z,name"+newline+"1,1,1,A"+newline+"2,2,2,a"+newline]
                writeText(file,text);
                testCase.verifyError(@()fixture(file),"BDam:MonitoringCSV");
            end
            testCase.verifyError(@()fixture(fullfile(folder.Folder,"missing.csv")),"BDam:MonitoringFile");
        end
    end
end

function mon=fixture(path,spacing,origin)
if nargin<2, spacing=1; end
if nargin<3, origin=0; end
[X,Y]=ndgrid((0.5:1:5.5)*spacing+origin,(0.5:1:7.5)*spacing+origin);
ZTop=10*ones(size(X));
Z=cat(3,zeros(size(X)),4*ones(size(X)),7*ones(size(X)),ZTop);
channel=false(size(X)); channel(3,:)=true;
upstream=Y>=4*spacing+origin; downstream=~upstream;
dam=struct("endpoint_1_xy",[0,4]*spacing+origin,"endpoint_2_xy",[6,4]*spacing+origin);
mon=makeBDamMonitoring(X,Y,ZTop,channel,upstream,downstream,dam,"y",3,Z,spacing,spacing,string(path));
end

function writeText(path,text)
fid=fopen(path,"w","n","UTF-8"); assert(fid>=0);
cleanup=onCleanup(@()fclose(fid));
fprintf(fid,"%s",text);
end
