function [edges,nup] = bdamRiverPoolEdges(downstreamLength,totalLength,ndown)
%bdamRiverPoolEdges - Partition a reach with a larger upstream end pool
%   EDGES = bdamRiverPoolEdges(downstreamLength,totalLength,NDOWN) gives
%   increasing distances from the outlet, measured along the centerline.
%   [EDGES,NUP] = bdamRiverPoolEdges(...) also returns upstream pool count.
%   See also makeCoarseRiverScenario
arguments
    downstreamLength (1,1) double {mustBeFinite,mustBePositive}
    totalLength (1,1) double {mustBeFinite,mustBePositive}
    ndown (1,1) double {mustBeFinite,mustBeInteger,mustBePositive}
end
assert(totalLength>downstreamLength,"BDam:DamPosition", ...
    "Dam must lie inside the reach.");
interval=downstreamLength/ndown;
tol=1e-10*max(1,totalLength);
nup=max(1,floor((totalLength-downstreamLength+tol)/interval));
edges=[(0:ndown)*interval downstreamLength+(1:nup-1)*interval totalLength];
end
