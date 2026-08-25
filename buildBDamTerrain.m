function terrain = buildBDamTerrain(parameters, profile)
%BUILD-BDAMTERRAIN Extrude a channel profile normal to a sine centerline.
%   TERRAIN = buildBDamTerrain(PARAMETERS, PROFILE) performs the numerical
%   terrain construction used by the BDam terrain app without creating UI
%   objects or writing files.

arguments
    parameters (1,1) struct
    profile (1,1) struct = buildBDamCrossSection(parameters)
end

required = ["domain_length_y_m", "spacing_y_m", "origin_y_m", ...
    "sine_periods", "sine_amplitude_m", "regional_longitudinal_slope", ...
    "channel_longitudinal_slope", "dam_relative_distance_upstream", ...
    "dam_max_m", "domain_length_x_m", "spacing_x_m", "origin_x_m", ...
    "depths_m"];
missing = required(~isfield(parameters, required));
if ~isempty(missing)
    error("BDam:MissingParameter", "Missing terrain parameter(s): %s", ...
        strjoin(missing, ", "));
end

Ly = finiteScalar(parameters.domain_length_y_m, "domain Y length");
dy = finiteScalar(parameters.spacing_y_m, "Y grid spacing");
y0 = finiteScalar(parameters.origin_y_m, "Y origin");
Lx = finiteScalar(parameters.domain_length_x_m, "domain X length");
dx = finiteScalar(parameters.spacing_x_m, "X grid spacing");
x0 = finiteScalar(parameters.origin_x_m, "X origin");
periods = finiteScalar(parameters.sine_periods, "number of sine periods");
amplitude = finiteScalar(parameters.sine_amplitude_m, "sine amplitude");
regional_slope = finiteScalar(parameters.regional_longitudinal_slope, ...
    "regional longitudinal slope");
channel_slope = finiteScalar(parameters.channel_longitudinal_slope, ...
    "channel longitudinal slope");
dam_fraction = finiteScalar(parameters.dam_relative_distance_upstream, ...
    "relative dam distance");
dam_max = finiteScalar(parameters.dam_max_m, "maximum dam height");
depths = parameters.depths_m(:)';

if Ly <= 0 || dy <= 0 || Lx <= 0 || dx <= 0
    error("BDam:GridDimensions", "Domain dimensions and grid spacings must be positive.");
end
if periods < 0
    error("BDam:MeanderParameters", ...
        "The number of sine periods cannot be negative.");
end
if sign(regional_slope) ~= sign(channel_slope)
    error("BDam:LongitudinalSlopeDirection", ...
        "Regional and channel longitudinal slopes must have the same sign " + ...
        "(or both be zero) so they slope in the same direction.");
end
half_period_count = periods / 0.5;
if abs(half_period_count - round(half_period_count)) > ...
        10*eps(max(1, abs(half_period_count)))
    error("BDam:SinePeriods", "Sine periods must be a multiple of 0.5.");
end
if dam_fraction < 0 || dam_fraction > 1 || dam_max < 0
    error("BDam:DamParameters", ...
        "Dam distance must be in [0,1] and dam height cannot be negative.");
end
if numel(depths) ~= 2 || any(~isfinite(depths)) || any(depths <= 0)
    error("BDam:Depths", "Exactly two positive, finite section depths are required.");
end

ny_exact = Ly / dy;
ny = round(ny_exact);
if abs(ny_exact - ny) > 1e-10 * max(1, ny_exact) || ny < 2
    error("BDam:GridDivisibility", ...
        "Domain Y length must contain an integer number of at least two cells.");
end

x = profile.x_m;
nx = numel(x);
if nx ~= round(Lx/dx) || abs(x(1) - (x0+dx/2)) > 1e-10*max(1,Lx)
    error("BDam:ProfileMismatch", ...
        "The confirmed cross section does not match the current X-domain inputs.");
end
y = y0 + dy .* (1:ny)' - dy/2;
[X,Y] = ndgrid(x,y);

xt = profile.offset_m;
z = profile.elevation_m;
z_channel = profile.channel_profile_m;
x_center = mean(x);
wave_number = 2*pi*periods/Ly;
centerline_x = @(yc) x_center + amplitude.*sin(wave_number.*(yc-y0));
centerline_dx = @(yc) amplitude.*wave_number.*cos(wave_number.*(yc-y0));
centerline_d2x = @(yc) -amplitude.*wave_number.^2.*sin(wave_number.*(yc-y0));
centerline_speed = @(yc) sqrt(1 + centerline_dx(yc).^2);

if periods == 0 || amplitude == 0
    tortuosity = 1;
    minimum_radius = Inf;
else
    tortuosity = integral(centerline_speed, y0, y0+Ly, ...
        "RelTol", 1e-11, "AbsTol", 1e-12) / Ly;
    minimum_radius = 1/(abs(amplitude)*wave_number^2);
end

warnings = profile.warnings;
modeled_lateral_reach = max(abs(xt)) + abs(amplitude);
if modeled_lateral_reach >= minimum_radius
    warnings(end+1,1) = sprintf( ...
        "The modeled lateral reach (%.3g m) equals or " + ...
        "exceeds the minimum centerline radius of curvature (%.3g m). " + ...
        "Perpendicular sections may intersect on far banks; the nearest " + ...
        "branch was used.", modeled_lateral_reach, minimum_radius);
end
if abs(amplitude) + max(abs(profile.bank_offsets_m)) > Lx/2
    warnings(end+1,1) = ...
        "The meander plus channel-bank width extends beyond the X domain.";
end

projection_margin = modeled_lateral_reach + max(dx,dy);
projection_min = y0 - projection_margin;
projection_max = y0 + Ly + projection_margin;
seed_step = min(dx,dy)/4;
centerline_y_seed = projection_min:seed_step:projection_max;
if centerline_y_seed(end) < projection_max
    centerline_y_seed(end+1) = projection_max;
end
centerline_x_seed = centerline_x(centerline_y_seed);

centerline_station = zeros(size(X));
signed_normal_distance = zeros(size(X));
projection_residual = zeros(size(X));
projection_tol = 1e-10*max([1 Lx Ly]);
newton_step_tol = 1e-12*max([1 Lx Ly]);

for point = 1:numel(X)
    grid_x = X(point);
    grid_y = Y(point);
    seed_distance_sq = (centerline_x_seed-grid_x).^2 + ...
        (centerline_y_seed-grid_y).^2;
    [best_seed_distance_sq, seed_index] = min(seed_distance_sq);
    station = centerline_y_seed(seed_index);
    converged = false;

    for iteration = 1:20
        curve_x = centerline_x(station);
        curve_dx = centerline_dx(station);
        curve_d2x = centerline_d2x(station);
        derivative = (curve_x-grid_x)*curve_dx + (station-grid_y);
        second_derivative = 1 + curve_dx^2 + (curve_x-grid_x)*curve_d2x;
        if ~isfinite(second_derivative) || abs(second_derivative) < eps
            break
        end
        next_station = station - derivative/second_derivative;
        next_station = min(max(next_station,projection_min),projection_max);
        if abs(next_station-station) <= newton_step_tol
            station = next_station;
            converged = true;
            break
        end
        station = next_station;
    end

    curve_x = centerline_x(station);
    curve_dx = centerline_dx(station);
    curve_d2x = centerline_d2x(station);
    derivative = (curve_x-grid_x)*curve_dx + (station-grid_y);
    second_derivative = 1 + curve_dx^2 + (curve_x-grid_x)*curve_d2x;
    newton_distance_sq = (curve_x-grid_x)^2 + (station-grid_y)^2;

    if ~converged || second_derivative <= 0 || ...
            abs(derivative) > projection_tol || ...
            newton_distance_sq > best_seed_distance_sq + projection_tol^2
        first_index = max(1,seed_index-2);
        last_index = min(numel(centerline_y_seed),seed_index+2);
        objective = @(u) (centerline_x(u)-grid_x).^2 + (u-grid_y).^2;
        station = fminbnd(objective, centerline_y_seed(first_index), ...
            centerline_y_seed(last_index));
        curve_x = centerline_x(station);
        curve_dx = centerline_dx(station);
        derivative = (curve_x-grid_x)*curve_dx + (station-grid_y);
    end

    normal_scale = sqrt(1+curve_dx^2);
    centerline_station(point) = station;
    signed_normal_distance(point) = ...
        ((grid_x-curve_x)-curve_dx*(grid_y-station))/normal_scale;
    projection_residual(point) = derivative;
end

arc_y = unique([centerline_y_seed y0 y0+Ly]);
arc_distance = cumtrapz(arc_y,centerline_speed(arc_y));
arc_distance = arc_distance - interp1(arc_y,arc_distance,y0,"pchip");
station_arc_distance = interp1(arc_y,arc_distance,centerline_station,"pchip");

profile_elevation = interp1(xt,z,signed_normal_distance,"linear","extrap");
channel_profile_elevation = interp1(xt,z_channel, ...
    signed_normal_distance,"linear","extrap");
channel_weight = 1-channel_profile_elevation/sum(depths);
channel_weight = min(max(channel_weight,0),1);
channel_weight = channel_weight.^2 .* (3-2.*channel_weight);
channel_grade = channel_slope .* station_arc_distance;
regional_grade = regional_slope .* (Y-y0);
ZTop = profile_elevation + channel_weight.*channel_grade + ...
    (1-channel_weight).*regional_grade;
Z = reshape(ZTop,nx,ny,1);

total_centerline_distance = tortuosity*Ly;
dam_distance_upstream = dam_fraction*total_centerline_distance;
if regional_slope < 0
    % Negative slopes fall toward +Y, so the downstream boundary is y0+Ly
    % and upstream distance is measured back toward -Y.
    dam_arc_distance = total_centerline_distance-dam_distance_upstream;
    dam_upstream_side = "right";
else
    % Positive (or flat) slopes retain the minimum-Y downstream convention.
    dam_arc_distance = dam_distance_upstream;
    dam_upstream_side = "left";
end
dam_station = interp1(arc_distance,arc_y,dam_arc_distance,"pchip");
dam_center_x = centerline_x(dam_station);
dam_centerline_slope = centerline_dx(dam_station);
dam_normal = [1 -dam_centerline_slope];
dam_normal = dam_normal/norm(dam_normal);
dam_offsets = profile.bank_offsets_m;
dam_points = [dam_center_x + dam_offsets.*dam_normal(1), ...
    dam_station + dam_offsets.*dam_normal(2)];

dam_profile_bottom = interp1(xt,z,0,"linear","extrap");
dam_channel_profile_bottom = interp1(xt,z_channel,0,"linear","extrap");
dam_weight = 1-dam_channel_profile_bottom/sum(depths);
dam_weight = min(max(dam_weight,0),1);
dam_weight = dam_weight^2*(3-2*dam_weight);
dam_toe_elevation = dam_profile_bottom + ...
    dam_weight*channel_slope*dam_arc_distance + ...
    (1-dam_weight)*regional_slope*(dam_station-y0);
dam_crest_elevation = dam_toe_elevation + dam_max;
dam_wall_x = [dam_points(1,1) dam_points(2,1) dam_points(2,1) dam_points(1,1)];
dam_wall_y = [dam_points(1,2) dam_points(2,2) dam_points(2,2) dam_points(1,2)];
dam_wall_z = [dam_toe_elevation dam_toe_elevation ...
    dam_crest_elevation dam_crest_elevation];

% Build the connected crest-stage pond on the upstream side of the dam.
% The model-grid mask is retained for handoff, while a four-times-refined
% interpolated mask provides a smoother display plane and bathtub-ring line.
dam_vector = dam_points(2,:)-dam_points(1,:);
dam_cross = dam_vector(1).*(Y-dam_points(1,2)) - ...
    dam_vector(2).*(X-dam_points(1,1));
if dam_upstream_side == "left"
    upstream_mask = dam_cross > 0;
else
    upstream_mask = dam_cross < 0;
end
dam_distance = pointToSegmentDistance(X,Y,dam_points(1,:),dam_points(2,:));
lake_candidate = upstream_mask & ZTop <= dam_crest_elevation;
lake_seed = lake_candidate & dam_distance <= max(dx,dy);
if ~any(lake_seed,"all") && any(lake_candidate,"all")
    candidate_index = find(lake_candidate);
    [~,nearest] = min(dam_distance(candidate_index));
    lake_seed(candidate_index(nearest)) = true;
end
lake_footprint_mask = floodFill4(lake_candidate,lake_seed);

lake_refinement = 4;
lake_x = linspace(x0,x0+Lx,lake_refinement*nx+1);
lake_y = linspace(y0,y0+Ly,lake_refinement*ny+1);
[lake_X,lake_Y] = ndgrid(lake_x,lake_y);
terrain_interpolant = griddedInterpolant({x,y},ZTop,"linear","nearest");
lake_land = terrain_interpolant(lake_X,lake_Y);
lake_cross = dam_vector(1).*(lake_Y-dam_points(1,2)) - ...
    dam_vector(2).*(lake_X-dam_points(1,1));
if dam_upstream_side == "left"
    lake_upstream = lake_cross > 0;
else
    lake_upstream = lake_cross < 0;
end
lake_distance = pointToSegmentDistance( ...
    lake_X,lake_Y,dam_points(1,:),dam_points(2,:));
lake_candidate_display = lake_upstream & lake_land <= dam_crest_elevation;
lake_display_spacing = max(lake_x(2)-lake_x(1),lake_y(2)-lake_y(1));
lake_seed_display = lake_candidate_display & ...
    lake_distance <= 1.5*lake_display_spacing;
if ~any(lake_seed_display,"all") && any(lake_candidate_display,"all")
    candidate_index = find(lake_candidate_display);
    [~,nearest] = min(lake_distance(candidate_index));
    lake_seed_display(candidate_index(nearest)) = true;
end
lake_display_mask = floodFill4(lake_candidate_display,lake_seed_display);
lake_surface_z = dam_crest_elevation*ones(size(lake_X));
lake_surface_z(~lake_display_mask) = NaN;
lake_outline_segments = maskContourSegments(lake_x,lake_y,lake_display_mask);

if ~any(lake_footprint_mask,"all")
    warnings(end+1,1) = ...
        "The maximum dam elevation does not create a connected upstream lake.";
end
if regional_slope < 0
    lake_touches_upstream_edge = any(lake_footprint_mask(:,1),"all");
else
    lake_touches_upstream_edge = any(lake_footprint_mask(:,end),"all");
end

centerline_plot_y = linspace(y0,y0+Ly,501);
centerline_plot_x = centerline_x(centerline_plot_y);
centerline_plot_arc = interp1(arc_y,arc_distance,centerline_plot_y,"pchip");
centerline_plot_z = dam_profile_bottom + channel_slope.*centerline_plot_arc;

if any(dam_points(:,1) < min(X(:)) | dam_points(:,1) > max(X(:)) | ...
        dam_points(:,2) < min(Y(:)) | dam_points(:,2) > max(Y(:)))
    warnings(end+1,1) = ...
        "One or both dam endpoints lie outside the cell-center coordinate bounds.";
end

terrain = struct();
terrain.x_m = x;
terrain.y_m = y;
terrain.X_m = X;
terrain.Y_m = Y;
terrain.ZTop_m = ZTop;
terrain.Z_m = Z;
terrain.tortuosity = tortuosity;
terrain.minimum_radius_curvature_m = minimum_radius;
terrain.centerline_station_m = centerline_station;
terrain.signed_normal_distance_m = signed_normal_distance;
terrain.projection_residual_m = projection_residual;
terrain.centerline_y_m = centerline_plot_y;
terrain.centerline_x_m = centerline_plot_x;
terrain.centerline_elevation_m = centerline_plot_z;
terrain.total_centerline_distance_m = total_centerline_distance;
terrain.dam_arc_distance_m = dam_arc_distance;
terrain.dam_distance_upstream_m = dam_distance_upstream;
terrain.dam_centerline_station_m = dam_station;
terrain.dam_points_m = dam_points;
terrain.dam_upstream_side = dam_upstream_side;
terrain.dam_toe_elevation_m = dam_toe_elevation;
terrain.dam_crest_elevation_m = dam_crest_elevation;
terrain.dam_wall_x_m = dam_wall_x;
terrain.dam_wall_y_m = dam_wall_y;
terrain.dam_wall_z_m = dam_wall_z;
terrain.lake_stage_m = dam_crest_elevation;
terrain.lake_footprint_mask = lake_footprint_mask;
terrain.lake_touches_upstream_edge = lake_touches_upstream_edge;
terrain.lake_display_X_m = lake_X;
terrain.lake_display_Y_m = lake_Y;
terrain.lake_display_Z_m = lake_surface_z;
terrain.lake_outline_segments_m = lake_outline_segments;
terrain.warnings = unique(warnings,"stable");
end

function value = finiteScalar(value, description)
if ~isnumeric(value) || ~isreal(value) || ~isscalar(value) || ~isfinite(value)
    error("BDam:ScalarParameter", "%s must be one finite real scalar.", description);
end
value = double(value);
end

function distance = pointToSegmentDistance(x,y,p1,p2)
vector = p2-p1;
fraction = ((x-p1(1)).*vector(1) + (y-p1(2)).*vector(2)) ./ sum(vector.^2);
fraction = min(max(fraction,0),1);
distance = hypot(x-(p1(1)+fraction.*vector(1)), ...
    y-(p1(2)+fraction.*vector(2)));
end

function mask = floodFill4(candidate,seed)
[nx,ny] = size(candidate);
mask = false(nx,ny);
queue = find(seed);
mask(queue) = true;
position = 1;
while position <= numel(queue)
    [i,j] = ind2sub([nx,ny],queue(position));
    position = position+1;
    neighbor_i = [i-1 i+1 i i];
    neighbor_j = [j j j-1 j+1];
    valid = neighbor_i>=1 & neighbor_i<=nx & neighbor_j>=1 & neighbor_j<=ny;
    neighbor = sub2ind([nx,ny],neighbor_i(valid),neighbor_j(valid));
    add = neighbor(candidate(neighbor) & ~mask(neighbor));
    mask(add) = true;
    queue = [queue; add(:)]; %#ok<AGROW>
end
end

function segments = maskContourSegments(x,y,mask)
segments = cell(0,1);
if ~any(mask,"all") || all(mask,"all")
    return
end
contour_matrix = contourc(x,y,double(mask'),[0.5 0.5]);
column = 1;
while column < size(contour_matrix,2)
    point_count = contour_matrix(2,column);
    if point_count < 2 || column+point_count > size(contour_matrix,2)
        break
    end
    points = contour_matrix(:,column+(1:point_count))';
    segments{end+1,1} = points; %#ok<AGROW>
    column = column+point_count+1;
end
end
