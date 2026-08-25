function profile = buildBDamCrossSection(parameters)
%BUILD-BDAMCROSSSECTION Build the two-level channel/floodplain profile.
%   PROFILE = buildBDamCrossSection(PARAMETERS) is the calculation-only
%   counterpart of the cross-section portion of MakeGrid.m.  It has no
%   graphics or file-system side effects, which makes it suitable for apps
%   and automated validation.

arguments
    parameters (1,1) struct
end

required = ["bottom_widths_m", "depths_m", "left_side_slopes", ...
    "right_side_slopes", "transverse_slopes", "vertical_offset_m", ...
    "dam_max_m", "domain_length_x_m", "spacing_x_m", "origin_x_m"];
missing = required(~isfield(parameters, required));
if ~isempty(missing)
    error("BDam:MissingParameter", "Missing cross-section parameter(s): %s", ...
        strjoin(missing, ", "));
end

bottom_widths = rowVector(parameters.bottom_widths_m, "bottom widths");
depths = rowVector(parameters.depths_m, "section depths");
left_slopes = rowVector(parameters.left_side_slopes, "left side slopes");
right_slopes = rowVector(parameters.right_side_slopes, "right side slopes");
transverse_slopes = rowVector(parameters.transverse_slopes, "transverse slopes");

if any([numel(bottom_widths), numel(depths), numel(left_slopes), ...
        numel(right_slopes)] ~= 2)
    error("BDam:SectionCount", "Exactly two nested channel sections are required.");
end
if numel(transverse_slopes) ~= 2
    error("BDam:TransverseSlopeCount", ...
        "Two transverse slopes are required: negative-x and positive-x.");
end

mustBeFiniteReal(bottom_widths, "bottom widths");
mustBeFiniteReal(depths, "section depths");
mustBeFiniteReal(left_slopes, "left side slopes");
mustBeFiniteReal(right_slopes, "right side slopes");
mustBeFiniteReal(transverse_slopes, "transverse slopes");
if any(bottom_widths <= 0) || any(depths <= 0) || ...
        any(left_slopes <= 0) || any(right_slopes <= 0)
    error("BDam:PositiveChannelGeometry", ...
        "Bottom widths, depths, and side slopes must all be positive.");
end
if any(transverse_slopes < 0)
    error("BDam:TransverseSlope", "Transverse surface slopes cannot be negative.");
end

lower_top_width = bottom_widths(1) + ...
    depths(1) * (left_slopes(1) + right_slopes(1));
if bottom_widths(2) < lower_top_width
    error("BDam:NestedGeometry", ...
        "The upper-section bottom width (%.4g m) must be at least the " + ...
        "lower-section top width (%.4g m).", ...
        bottom_widths(2), lower_top_width);
end

Lx = finiteScalar(parameters.domain_length_x_m, "domain X length");
dx = finiteScalar(parameters.spacing_x_m, "X grid spacing");
x0 = finiteScalar(parameters.origin_x_m, "X origin");
vertical_offset = finiteScalar(parameters.vertical_offset_m, "vertical offset");
dam_max = finiteScalar(parameters.dam_max_m, "maximum dam height");
if Lx <= 0 || dx <= 0
    error("BDam:GridDimensions", "Domain length and grid spacing must be positive.");
end
if vertical_offset < 0 || dam_max < 0
    error("BDam:NonnegativeElevation", ...
        "Vertical offset and maximum dam height cannot be negative.");
end

nx_exact = Lx / dx;
nx = round(nx_exact);
if abs(nx_exact - nx) > 1e-10 * max(1, nx_exact) || nx < 2
    error("BDam:GridDivisibility", ...
        "Domain X length must contain an integer number of at least two cells.");
end

x = x0 + dx .* (1:nx)' - dx/2;
xt = x - mean(x);

left_bank_exact = -max(bottom_widths/2 + left_slopes .* depths);
right_bank_exact = max(bottom_widths/2 + right_slopes .* depths);
if min(xt) > left_bank_exact || max(xt) < right_bank_exact
    error("BDam:ChannelOutsideDomain", ...
        "The X domain is too narrow to contain both outer channel banks.");
end

section_elevation = zeros(nx, 2);
for section = 1:2
    left_base = -(bottom_widths(section)/2) / left_slopes(section);
    section_elevation(:,section) = ...
        ((1/left_slopes(section)) .* abs(xt) + left_base) .* (xt < 0);

    right_base = -(bottom_widths(section)/2) / right_slopes(section);
    section_elevation(:,section) = section_elevation(:,section) + ...
        ((1/right_slopes(section)) .* abs(xt) + right_base) .* (xt > 0);

    section_elevation(:,section) = min(max( ...
        section_elevation(:,section), 0), depths(section));
end

channel_base = sum(section_elevation, 2);
plateau = channel_base == max(channel_base);
channel_profile = channel_base + vertical_offset .* plateau;

raised_plateau = channel_profile == max(channel_profile);
left_bank_index = find(raised_plateau & xt < 0, 1, "last");
right_bank_index = find(raised_plateau & xt > 0, 1, "first");
if isempty(left_bank_index) || isempty(right_bank_index)
    error("BDam:UnresolvedBanks", ...
        "The grid spacing is too coarse to resolve both outer channel banks.");
end

floodplain_elevation = zeros(nx, 2);
floodplain_elevation(:,1) = ...
    -(xt - xt(left_bank_index)) .* transverse_slopes(1);
floodplain_elevation(:,2) = ...
    (xt - xt(right_bank_index)) .* transverse_slopes(2);
floodplain_elevation = max(floodplain_elevation, 0);
elevation = channel_profile + sum(floodplain_elevation, 2);

warnings = strings(0,1);
edge_clearance = min(abs([min(xt)-xt(left_bank_index), ...
    max(xt)-xt(right_bank_index)]));
if edge_clearance < 2*dx
    warnings(end+1,1) = ...
        "The channel banks are within two cells of an X-domain boundary.";
end

profile = struct();
profile.x_m = x;
profile.offset_m = xt;
profile.elevation_m = elevation;
profile.channel_profile_m = channel_profile;
profile.channel_base_m = channel_base;
profile.section_elevation_m = section_elevation;
profile.left_bank_index = left_bank_index;
profile.right_bank_index = right_bank_index;
profile.bank_offsets_m = [xt(left_bank_index); xt(right_bank_index)];
profile.exact_bank_offsets_m = [left_bank_exact; right_bank_exact];
profile.maximum_dam_height_m = dam_max;
profile.warnings = warnings;
end

function value = rowVector(value, description)
if ~isnumeric(value) || ~isreal(value)
    error("BDam:NumericParameter", "%s must be a real numeric vector.", description);
end
value = value(:)';
end

function mustBeFiniteReal(value, description)
if any(~isfinite(value))
    error("BDam:FiniteParameter", "%s must contain only finite values.", description);
end
end

function value = finiteScalar(value, description)
if ~isnumeric(value) || ~isreal(value) || ~isscalar(value) || ~isfinite(value)
    error("BDam:ScalarParameter", "%s must be one finite real scalar.", description);
end
value = double(value);
end
