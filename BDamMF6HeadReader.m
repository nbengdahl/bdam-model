classdef BDamMF6HeadReader
    %BDAMMF6HEADREADER Indexed reader for double-precision MF6 head files.
    %   Arrays returned by this class use the BDam native horizontal order
    %   [x,y]. Layer numbers are MODFLOW top-down layer numbers.

    properties (SetAccess = private)
        FilePath (1,1) string
        Times (:,1) double
        NumFrames (1,1) double
        NumLayers (1,1) double
        NumRows (1,1) double
        NumColumns (1,1) double
    end

    properties (Access = private)
        ValueOffsets (:,:) double
    end

    methods
        function reader = BDamMF6HeadReader(filePath)
            arguments
                filePath {mustBeTextScalar}
            end

            reader.FilePath = string(filePath);
            if ~isfile(reader.FilePath)
                error("BDam:HeadFileMissing", ...
                    "MF6 head file does not exist: %s",reader.FilePath);
            end

            [reader.Times,reader.ValueOffsets,reader.NumRows, ...
                reader.NumColumns,reader.NumLayers] = ...
                reader.indexFile(reader.FilePath);
            reader.NumFrames = numel(reader.Times);
        end

        function values = readLayer(reader,frameIndex,layerTopDown)
            arguments
                reader (1,1) BDamMF6HeadReader
                frameIndex (1,1) double {mustBeInteger,mustBePositive}
                layerTopDown (1,1) double {mustBeInteger,mustBePositive}
            end
            if frameIndex > reader.NumFrames
                error("BDam:HeadFrameRange", ...
                    "Head frame %d exceeds the available %d frames.", ...
                    frameIndex,reader.NumFrames);
            end
            if layerTopDown > reader.NumLayers
                error("BDam:HeadLayerRange", ...
                    "Head layer %d exceeds the available %d layers.", ...
                    layerTopDown,reader.NumLayers);
            end

            fileID = fopen(reader.FilePath,"r","ieee-le");
            if fileID < 0
                error("BDam:HeadFileOpen", ...
                    "Could not open MF6 head file: %s",reader.FilePath);
            end
            cleanup = onCleanup(@()fclose(fileID));
            status = fseek(fileID,reader.ValueOffsets(frameIndex,layerTopDown),"bof");
            if status ~= 0
                error("BDam:HeadFileSeek", ...
                    "Could not seek to frame %d, layer %d in %s.", ...
                    frameIndex,layerTopDown,reader.FilePath);
            end
            raw = fread(fileID,[reader.NumColumns reader.NumRows], ...
                "double=>double");
            if numel(raw) ~= reader.NumRows*reader.NumColumns
                error("BDam:HeadFileTruncated", ...
                    "Truncated head values in %s.",reader.FilePath);
            end

            % fread produces [column, MF6 row]. MF6 rows run from high Y to
            % low Y, so reverse the second dimension for native [x,y].
            values = fliplr(raw);
        end

        function values = readSnapshot(reader,frameIndex)
            arguments
                reader (1,1) BDamMF6HeadReader
                frameIndex (1,1) double {mustBeInteger,mustBePositive}
            end
            values = nan(reader.NumColumns,reader.NumRows,reader.NumLayers);
            for layer = 1:reader.NumLayers
                values(:,:,layer) = reader.readLayer(frameIndex,layer);
            end
        end

        function surface = readWaterSurface(reader,frameIndex)
            %READWATERSURFACE Return the uppermost valid head in each column.
            if frameIndex < 1 || frameIndex > reader.NumFrames || mod(frameIndex,1) ~= 0
                error("BDam:HeadFrameRange", ...
                    "Head frame must be an integer from 1 through %d.",reader.NumFrames);
            end
            fileID = fopen(reader.FilePath,"r","ieee-le");
            if fileID < 0
                error("BDam:HeadFileOpen", ...
                    "Could not open MF6 head file: %s",reader.FilePath);
            end
            cleanup = onCleanup(@()fclose(fileID));
            surface = nan(reader.NumColumns,reader.NumRows);
            unresolved = true(size(surface));
            for layer = 1:reader.NumLayers
                status = fseek(fileID,reader.ValueOffsets(frameIndex,layer),"bof");
                if status ~= 0
                    error("BDam:HeadFileSeek", ...
                        "Could not seek to frame %d, layer %d in %s.", ...
                        frameIndex,layer,reader.FilePath);
                end
                heads = fread(fileID,[reader.NumColumns reader.NumRows], ...
                    "double=>double");
                if numel(heads) ~= reader.NumRows*reader.NumColumns
                    error("BDam:HeadFileTruncated", ...
                        "Truncated head values in %s.",reader.FilePath);
                end
                heads = fliplr(heads);
                valid = unresolved & isfinite(heads) & abs(heads) < 1.0e29;
                surface(valid) = heads(valid);
                unresolved(valid) = false;
                if ~any(unresolved,"all")
                    break
                end
            end
        end
    end

    methods (Access = private, Static)
        function [times,offsets,nrow,ncol,nlay] = indexFile(filePath)
            fileID = fopen(filePath,"r","ieee-le");
            if fileID < 0
                error("BDam:HeadFileOpen", ...
                    "Could not open MF6 head file: %s",filePath);
            end
            cleanup = onCleanup(@()fclose(fileID));

            records = struct("time",{},"layer",{},"offset",{});
            nrow = NaN;
            ncol = NaN;
            recordNumber = 0;
            while true
                [kstp,count] = fread(fileID,1,"int32=>double");
                if count == 0
                    break
                end
                recordNumber = recordNumber+1;
                kper = BDamMF6HeadReader.readScalar(fileID,"int32=>double",filePath);
                pertim = BDamMF6HeadReader.readScalar(fileID,"double=>double",filePath);
                totim = BDamMF6HeadReader.readScalar(fileID,"double=>double",filePath);
                textBytes = fread(fileID,16,"uint8=>uint8");
                if numel(textBytes) ~= 16
                    error("BDam:HeadFileTruncated", ...
                        "Truncated head header in %s at record %d.", ...
                        filePath,recordNumber);
                end
                label = strtrim(string(char(textBytes(:)')));
                thisNcol = BDamMF6HeadReader.readScalar(fileID,"int32=>double",filePath);
                thisNrow = BDamMF6HeadReader.readScalar(fileID,"int32=>double",filePath);
                layer = BDamMF6HeadReader.readScalar(fileID,"int32=>double",filePath);

                if label ~= "HEAD"
                    error("BDam:HeadFileLabel", ...
                        "Expected a HEAD record in %s; found '%s'.",filePath,label);
                end
                if any(~isfinite([kstp kper pertim totim thisNcol thisNrow layer])) || ...
                        kstp < 1 || kper < 1 || pertim < 0 || totim < 0 || ...
                        thisNcol < 1 || thisNrow < 1 || layer < 1 || ...
                        any(mod([kstp kper thisNcol thisNrow layer],1) ~= 0)
                    error("BDam:HeadFileHeader", ...
                        "Invalid MF6 head header in %s at record %d.", ...
                        filePath,recordNumber);
                end
                if isnan(nrow)
                    nrow = thisNrow;
                    ncol = thisNcol;
                elseif thisNrow ~= nrow || thisNcol ~= ncol
                    error("BDam:HeadFileDimensions", ...
                        "Head-grid dimensions change within %s.",filePath);
                end

                valueOffset = ftell(fileID);
                valueCount = thisNrow*thisNcol;
                status = fseek(fileID,8*valueCount,"cof");
                if status ~= 0 || ftell(fileID) > BDamMF6HeadReader.fileSize(filePath)
                    error("BDam:HeadFileTruncated", ...
                        "Truncated head values in %s at record %d.", ...
                        filePath,recordNumber);
                end
                records(recordNumber) = struct( ...
                    "time",totim,"layer",layer,"offset",valueOffset);
            end

            if isempty(records)
                error("BDam:HeadFileEmpty", ...
                    "No HEAD records were found in %s.",filePath);
            end
            nlay = max([records.layer]);
            rawTimes = [records.time];
            times = rawTimes(1);
            frameForRecord = ones(size(rawTimes));
            for index = 2:numel(rawTimes)
                tolerance = max(1.0e-10,1.0e-10*abs(rawTimes(index)));
                if abs(rawTimes(index)-times(end)) > tolerance
                    if rawTimes(index) <= times(end)
                        error("BDam:HeadFileTimes", ...
                            "Head times are not strictly increasing in %s.",filePath);
                    end
                    times(end+1) = rawTimes(index); %#ok<AGROW>
                end
                frameForRecord(index) = numel(times);
            end
            times = times(:);
            offsets = nan(numel(times),nlay);
            for index = 1:numel(records)
                frame = frameForRecord(index);
                layer = records(index).layer;
                if layer > nlay || ~isnan(offsets(frame,layer))
                    error("BDam:HeadFileLayers", ...
                        "Duplicate or invalid layer record in %s at time %.12g.", ...
                        filePath,records(index).time);
                end
                offsets(frame,layer) = records(index).offset;
            end
            if any(isnan(offsets),"all")
                error("BDam:HeadFileLayers", ...
                    "At least one time in %s lacks a complete set of layers 1:%d.", ...
                    filePath,nlay);
            end
        end

        function value = readScalar(fileID,precision,filePath)
            [value,count] = fread(fileID,1,precision);
            if count ~= 1
                error("BDam:HeadFileTruncated", ...
                    "Truncated MF6 head header in %s.",filePath);
            end
        end

        function bytes = fileSize(filePath)
            info = dir(filePath);
            bytes = info.bytes;
        end
    end
end
