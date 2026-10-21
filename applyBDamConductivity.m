function [K,K33,zones] = applyBDamConductivity(Kbackground,K33background,channel,distance,dx,dy,settings)
% Isotropic under-dam core with an optional one-cell plan-view transition.
arguments
    Kbackground double
    K33background double
    channel logical
    distance double
    dx (1,1) double {mustBePositive,mustBeFinite}
    dy (1,1) double {mustBePositive,mustBeFinite}
    settings struct
end
assert(isequal(size(Kbackground),size(K33background)) && ...
    isequal(size(channel),size(distance),[size(Kbackground,1),size(Kbackground,2)]));
assert(all(isfinite(Kbackground) & Kbackground>0,'all') && ...
    all(isfinite(K33background) & K33background>0,'all'));
nz=size(Kbackground,3);
assert(ismember(settings.leakage_halo_cells,[0 1]),'Halo width must be 0 or 1 cell.');
assert(settings.leakage_n_top_layers>=1 && settings.leakage_n_top_layers<=nz && ...
    settings.leakage_n_top_layers==fix(settings.leakage_n_top_layers));
validateattributes(settings.under_dam_k_m_per_day,{'double'},{'scalar','real','finite','positive'});
assert(~isfield(settings,'k_multiplier') && ~isfield(settings,'k33_multiplier'), ...
    'Use under_dam_k_m_per_day in m/day; conductivity multipliers are obsolete.');
assert( ...
    isfinite(settings.leakage_half_width_cells) && settings.leakage_half_width_cells>=0);
core=channel & distance<=settings.leakage_half_width_cells*max(dx,dy);
halo=false(size(core));
if settings.leakage_halo_cells==1
    % No toolbox, wraparound, channel clipping, or fixed cell-count assumption.
    halo=conv2(double(core),ones(3),'same')>0 & ~core;
end
layers=nz:-1:(nz-settings.leakage_n_top_layers+1);
zones.core_footprint=core; zones.halo_footprint=halo;
zones.footprint=core|halo;
zones.core_mask=false(size(Kbackground)); zones.halo_mask=false(size(Kbackground));
zones.core_mask(:,:,layers)=repmat(core,1,1,numel(layers));
zones.halo_mask(:,:,layers)=repmat(halo,1,1,numel(layers));
zones.mask=zones.core_mask|zones.halo_mask;
target=settings.under_dam_k_m_per_day*ones(size(Kbackground));
K=Kbackground; K33=K33background;
K(zones.core_mask)=target(zones.core_mask);
K33(zones.core_mask)=target(zones.core_mask);
K(zones.halo_mask)=(Kbackground(zones.halo_mask)+target(zones.halo_mask))/2;
K33(zones.halo_mask)=(K33background(zones.halo_mask)+target(zones.halo_mask))/2;
assert(~any(zones.core_mask & zones.halo_mask,'all'));
assert(isequal(K(~zones.mask),Kbackground(~zones.mask)) && ...
    isequal(K33(~zones.mask),K33background(~zones.mask)));
end
