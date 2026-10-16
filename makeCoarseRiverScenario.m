function [lakes,outlets,atmosphere_mask,experiment] = makeCoarseRiverScenario(scenario,lake_templates,outlet_controls,ZTop,Z,Y,dx,dy,geometry,dam,upstream,channel,settings)
% Coarse pools: full DEM storage, independently selected exchange.
assert(mean(ZTop(:,1))<mean(ZTop(:,end)), 'Coarse river supports downstream minimum-Y only.');
mode="pond_narrow"; ndown=settings.downstream_segments;
assert(isscalar(ndown) && isfinite(ndown) && ndown>=1 && fix(ndown)==ndown, ...
    'BDam:SegmentCount','Downstream segments must be a positive integer.');
available_rows=nnz(any(channel & ~upstream & ~dam.grid_mask,1));
assert(ndown<=available_rows,"BDam:SegmentResolution", ...
    "Requested %d downstream segments but only %d longitudinal channel cells are available.", ...
    ndown,available_rows);
nrough=settings.manning_roughness; width=settings.manning_width_m;
pond_cut=settings.pond_exchange_height_above_thalweg_m;
river_cap=settings.river_storage_height_above_highest_bed_m;
assert(all(isfinite([nrough width pond_cut river_cap])) && all([nrough width pond_cut river_cap]>0));
p=geometry.parameters; wave=2*pi*p.sine_periods/p.domain_length_y_m;
speed=@(yy)sqrt(1+(p.sine_amplitude_m*wave*cos(wave*(yy-p.origin_y_m))).^2);
yedge=p.origin_y_m; ydam=geometry.dam_centerline_station_m;
sdam=integral(speed,yedge,ydam,'RelTol',1e-10); interval=sdam/ndown;
send=integral(speed,yedge,yedge+p.domain_length_y_m,'RelTol',1e-10);
[edges,nup]=bdamRiverPoolEdges(sdam,send,ndown);
yrow=Y(1,:); srow=arrayfun(@(yy)integral(speed,yedge,yy,'RelTol',1e-10),yrow);
thalweg=min(ZTop,[],1); relative=ZTop-thalweg;
atmosphere_mask=false(size(ZTop)); lakes=lake_templates([]);
provider=strings(0,1); receiver=provider; invert=[]; widths=[]; role=provider;
cout=[]; rough=[]; slopes=[];
if scenario=="post_dam"
    lake=lake_templates(1); storage=lake.footprint_mask;
    exchange=storage & relative<=pond_cut;
    lake=replaceConnections(lake,exchange,ZTop,Z,dx,dy); lake.storage_footprint_mask=storage;
    lakes=lake; atmosphere_mask=storage;
    provider(end+1,1)=lake.name; receiver(end+1,1)="river_1";
    invert(end+1,1)=dam.crest_elevation_m; widths(end+1,1)=outlet_controls.width_m(1);
    role(end+1,1)="dam_crest_weir"; cout(end+1,1)=2; rough(end+1,1)=0; slopes(end+1,1)=0;
    domains=cell(ndown,1);
    % Order pools upstream to downstream. Domain follows existing dam-side mask.
    for k=1:ndown
        bucket=ndown-k; rows=(srow>=edges(bucket+1))&(srow<edges(bucket+2));
        domains{k}=repmat(rows,size(ZTop,1),1)&~upstream&~dam.grid_mask;
    end
else
    npool=ndown+nup; domains=cell(npool,1);
    for k=1:npool
        bucket=npool-k; rows=(srow>=edges(bucket+1))&(srow<edges(bucket+2));
        domains{k}=repmat(rows,size(ZTop,1),1);
    end
end
actual_extents=zeros(numel(domains),2);
for k=1:numel(domains)
    domain=domains{k}; domain=domain & repmat(any(domain & channel,1),size(ZTop,1),1);
    rows=any(domain,1); assert(any(rows),'BDam:EmptyPool','Requested segmentation creates an empty pool; use fewer segments or a finer grid.');
    actual_extents(k,:)=[min(srow(rows)) max(srow(rows))];
    rowmin=min(ZTop+1e6*~domain,[],1); low=min(rowmin(rows)); cap=max(rowmin(rows))+river_cap;
    storage=floodConnected(domain & ZTop<=cap,channel&domain&ZTop<=cap);
    assert(any(storage,'all'));
    exchange=storage;
    lake=lake_templates(end); lake.name="river_"+k; lake.lake_id=numel(lakes)+1;
    lake.initial_stage_m=low+0.10;
    lake=replaceConnections(lake,exchange,ZTop,Z,dx,dy); lake.storage_footprint_mask=storage;
    st=unique([linspace(low-0.01,cap,81)';ZTop(storage)]); a=zeros(size(st));v=a;
    for j=1:numel(st)
        wet=floodConnected(storage & ZTop<=st(j),channel&domain&ZTop<=st(j));
        a(j)=nnz(wet)*dx*dy;v(j)=sum(max(st(j)-ZTop(wet),0))*dx*dy;
    end
    % LAK requires strictly increasing volumes: one zero-volume bed row.
    keep=[find(v==0,1,'last');find(diff(v)>0)+1];
    st=st(keep);a=a(keep);v=v(keep);assert(all(diff(v)>0));
    lake.stage_area_volume=table(st,st-low,a,v,'VariableNames',{'stage_elevation_m','stage_above_toe_m','area_m2','volume_m3'});
    if isempty(lakes), lakes=lake; else, lakes(end+1)=lake; end
    atmosphere_mask=atmosphere_mask|storage;
    provider(end+1,1)=lake.name;
    if k<numel(domains), receiver(end+1,1)="river_"+(k+1); else, receiver(end+1,1)="external"; end
    % Minimum-Y is downstream. Interior depressions do not set the outlet.
    pool_channel=domain & channel;
    downstream_y=min(Y(pool_channel));
    outlet_channel=pool_channel & Y==downstream_y;
    outlet_bed=min(ZTop(outlet_channel));
    invert(end+1,1)=outlet_bed; widths(end+1,1)=width;role(end+1,1)="channel_manning";
    cout(end+1,1)=1;rough(end+1,1)=nrough;slopes(end+1,1)=abs(p.channel_longitudinal_slope);
end
% Preserve the independent external invert from the boundary contract.
invert(end)=outlet_controls.invert_elevation_m(end);
outlets=table(provider,receiver,invert,widths,role,cout,rough,slopes,'VariableNames', ...
    {'provider_lake','receiver','invert_elevation_m','width_m','role','type_code','roughness','slope'});
if scenario=="post_dam"
    pond_rows=any(lakes(1).storage_footprint_mask,1);
    actual_extents=[min(srow(pond_rows)) max(srow(pond_rows)); actual_extents];
    lake_roles=["upstream_impoundment"; repmat("downstream_pool",ndown,1)];
else
    lake_roles=[repmat("upstream_pool",nup,1); repmat("downstream_pool",ndown,1)];
end
experiment=struct('enabled',1,'downstream_segments',ndown,'exchange_narrow',1,'pond_only_narrow',1, ...
    'river_storage_height_above_highest_bed_m',river_cap,'pond_exchange_height_above_thalweg_m',pond_cut, ...
    'segment_interval_m',interval,'dam_distance_from_outlet_m',sdam, ...
    'pool_interval_edges_m',edges,'pool_cell_center_extents_m',actual_extents, ...
    'upstream_pool_count',nup,'lake_roles',lake_roles);
fprintf('COARSE RIVER: %s, downstream segments %d, interval %.5g m; atmosphere cells %d; exchange cells %d\n', ...
    mode,ndown,interval,nnz(atmosphere_mask),sum(arrayfun(@(l)nnz(l.footprint_mask),lakes)));
end

function lake=replaceConnections(lake,mask,ZTop,Z,dx,dy)
assert(any(mask,'all'),'No groundwater exchange cells');
[ii,jj]=find(mask);n=numel(ii);lake.footprint_mask=mask;
lake.connection_i_x=ii;lake.connection_i_y=jj;lake.connection_layer_native=(size(Z,3)-1)*ones(n,1);
lake.vertical_connection_area_m2=dx*dy*ones(n,1);
lake.vertical_connection_conductance_m2_per_day=lake.lakebed_vertical_k_m_per_day/lake.lakebed_thickness_m*lake.vertical_connection_area_m2;
% All lake geometry/diagnostic elevations still come from unmodified terrain.
lake.land_elevation_m=ZTop(mask);
end

function mask=floodConnected(candidate,seed)
mask=false(size(candidate));q=find(seed&candidate);mask(q)=true;pos=1;
[nx,ny]=size(mask);
while pos<=numel(q)
    [i,j]=ind2sub([nx,ny],q(pos));pos=pos+1;ii=[i-1 i+1 i i];jj=[j j j-1 j+1];
    ok=ii>=1&ii<=nx&jj>=1&jj<=ny;new=sub2ind([nx,ny],ii(ok),jj(ok));new=new(candidate(new)&~mask(new));
    mask(new)=true;q=[q;new(:)];
end
end
