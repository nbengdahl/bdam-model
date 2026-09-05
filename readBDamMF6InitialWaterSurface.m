function surface = readBDamMF6InitialWaterSurface(filePath,ncol,nrow,nlay)
%READBDAMMF6INITIALWATERSURFACE Read the uppermost valid MF6 IC head.
%   SURFACE uses the BDam native horizontal order [x,y]. FILEPATH must be
%   the FloPy-generated bdam.ic file containing a layered STRT array.

arguments
    filePath {mustBeTextScalar}
    ncol (1,1) double {mustBeInteger,mustBePositive}
    nrow (1,1) double {mustBeInteger,mustBePositive}
    nlay (1,1) double {mustBeInteger,mustBePositive}
end

filePath = string(filePath);
if ~isfile(filePath)
    error("BDam:InitialHeadFileMissing", ...
        "MF6 initial-condition file does not exist: %s",filePath);
end
lines = string(readlines(filePath));
start = find(~cellfun(@isempty,regexp(cellstr(lines), ...
    "^\s*strt\s+LAYERED\s*$","once","ignorecase")),1);
if isempty(start)
    error("BDam:InitialHeadFormat", ...
        "Initial-condition file %s lacks a layered STRT array.",filePath);
end

surface = nan(ncol,nrow);
unresolved = true(size(surface));
cursor = start+1;
for layer = 1:nlay
    [cursor,factor,constant] = findLayerControl(lines,cursor,filePath,layer);
    if isfinite(constant)
        native = repmat(constant*factor,ncol,nrow);
    else
        [cursor,values] = readLayerValues(lines,cursor,ncol*nrow,filePath,layer);
        mf6Rows = reshape(values,ncol,nrow)';
        native = fliplr(mf6Rows')*factor;
    end
    valid = unresolved & isfinite(native) & abs(native) < 1.0e29;
    surface(valid) = native(valid);
    unresolved(valid) = false;
end
end

function [cursor,factor,constant] = findLayerControl(lines,cursor,filePath,layer)
factor = 1.0;
constant = NaN;
while cursor <= numel(lines)
    line = strtrim(lines(cursor));
    cursor = cursor+1;
    if strlength(line) == 0 || startsWith(line,"#")
        continue
    end
    tokens = split(line);
    keyword = upper(tokens(1));
    if keyword == "INTERNAL"
        factorIndex = find(upper(tokens) == "FACTOR",1);
        if ~isempty(factorIndex) && factorIndex < numel(tokens)
            factor = str2double(tokens(factorIndex+1));
        end
        if ~isfinite(factor)
            error("BDam:InitialHeadFormat", ...
                "Layer %d has an invalid INTERNAL factor in %s.",layer,filePath);
        end
        return
    elseif keyword == "CONSTANT" && numel(tokens) >= 2
        constant = str2double(tokens(2));
        if ~isfinite(constant)
            error("BDam:InitialHeadFormat", ...
                "Layer %d has an invalid CONSTANT value in %s.",layer,filePath);
        end
        return
    elseif keyword == "OPEN/CLOSE"
        error("BDam:InitialHeadFormat", ...
            "External OPEN/CLOSE STRT arrays are not supported in %s.",filePath);
    elseif startsWith(upper(line),"END GRIDDATA")
        break
    end
end
error("BDam:InitialHeadFormat", ...
    "Initial-condition file %s lacks STRT data for layer %d.",filePath,layer);
end

function [cursor,values] = readLayerValues(lines,cursor,count,filePath,layer)
values = zeros(count,1);
filled = 0;
while cursor <= numel(lines) && filled < count
    line = strtrim(lines(cursor));
    cursor = cursor+1;
    if strlength(line) == 0 || startsWith(line,"#")
        continue
    end
    tokens = split(line);
    numbers = str2double(tokens);
    validNaN = upper(tokens) == "NAN";
    if any(isnan(numbers) & ~validNaN)
        error("BDam:InitialHeadFormat", ...
            "Layer %d has incomplete or nonnumeric STRT data in %s.",layer,filePath);
    end
    if filled+numel(numbers) > count
        error("BDam:InitialHeadFormat", ...
            "Layer %d has too many STRT values in %s.",layer,filePath);
    end
    values(filled+(1:numel(numbers))) = numbers;
    filled = filled+numel(numbers);
end
if filled ~= count
    error("BDam:InitialHeadFormat", ...
        "Layer %d has %d STRT values in %s; expected %d.", ...
        layer,filled,filePath,count);
end
end
