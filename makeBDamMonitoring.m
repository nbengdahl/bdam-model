function monitoring = makeBDamMonitoring(X,Y,ZTop,channel,upstream,downstream,dam,direction,nz,Z,dx,dy,point_file)
% Retain stream diagnostics; optionally replace the six grid points from CSV.
% CSV z is depth below the ground elevation of the containing model column.

    dam_xy=0.5*(dam.endpoint_1_xy+dam.endpoint_2_xy);
    if direction=="y"
        coordinates=Y(1,:); dam_coordinate=dam_xy(2);
        upstream_indices=find(any(upstream,1)); downstream_indices=find(any(downstream,1));
    else
        coordinates=X(:,1)'; dam_coordinate=dam_xy(1);
        upstream_indices=find(any(upstream,2))'; downstream_indices=find(any(downstream,2))';
    end
    assert(~isempty(upstream_indices) && ~isempty(downstream_indices), "Dam reference must split the model into two nonempty zones.");
    [~,q]=min(abs(coordinates(upstream_indices)-dam_coordinate)); up_near=upstream_indices(q);
    [~,q]=max(abs(coordinates(upstream_indices)-dam_coordinate)); up_end=upstream_indices(q);
    [~,q]=min(abs(coordinates(upstream_indices)-0.5*(dam_coordinate+coordinates(up_end)))); up_half=upstream_indices(q);
    [~,q]=min(abs(coordinates(downstream_indices)-dam_coordinate)); down_near=downstream_indices(q);
    [~,q]=max(abs(coordinates(downstream_indices)-dam_coordinate)); down_end=downstream_indices(q);
    [~,q]=min(abs(coordinates(downstream_indices)-0.5*(dam_coordinate+coordinates(down_end)))); down_half=downstream_indices(q);
    stations=[up_half;up_near;down_near;down_half]; points=zeros(4,3);
    for q=1:4
        if direction=="y"
            j=stations(q); candidates=find(channel(:,j)); [~,local]=min(ZTop(candidates,j)); i=candidates(local);
        else
            i=stations(q); candidates=find(channel(i,:)); [~,local]=min(ZTop(i,candidates)); j=candidates(local);
        end
        points(q,:)=[X(i,j),Y(i,j),0];
    end
    % Meandering reaches can project the two dam-adjacent station requests
    % onto one channel cell. Keep both named channel diagnostics; the six
    % generated domain-grid monitors are required to be unique; CSV monitors may share cells.
    % The named channel stations are geometric diagnostics. On a strongly
    % curved reach their cell-center projection need not lie strictly on the
    % analytic dam-side mask; model validity does not depend on that label.
    names=["head_upstream_half";"head_dam_upstream_1cell"; ...
        "head_dam_downstream_1cell";"head_downstream_half"];
    x_targets=min(X(:)) + [0.25 0.75].*(max(X(:))-min(X(:)));
    y_targets=min(Y(:)) + [0.25 0.50 0.75].*(max(Y(:))-min(Y(:)));
    domain_points=zeros(6,3); domain_names=strings(6,1);
    index=1;
    for x_fraction=[25 75]
        for y_fraction=[25 50 75]
            domain_points(index,:)=[x_targets((x_fraction==[25 75])), ...
                y_targets((y_fraction==[25 50 75])), 0];
            domain_names(index)=sprintf("head_domain_x%02d_y%02d_bottom",x_fraction,y_fraction);
            index=index+1;
        end
    end
    point_file=strtrim(string(point_file));
    omitted=repmat(omissionRecord(),0,1);
    metadata=repmat(targetRecord(),4,1);
    for q=1:4
        metadata(q).source="stream";
        metadata(q).original_name=names(q);
    end
    labels=names;
    custom_ix=[]; custom_iy=[];
    if point_file==""
        extra=repmat(targetRecord(),6,1);
        for q=1:6
            extra(q).source="grid";
            extra(q).original_name=domain_names(q);
        end
        labels=[labels;domain_names];
    else
        [domain_points,domain_names,extra,omitted,custom_ix,custom_iy]= ...
            readMonitoringCSV(point_file,X,Y,Z,dx,dy);
        labels=[labels;string({extra.original_name})'];
    end
    metadata=[metadata;extra];
    monitoring=makeHeadMonitoring([points;domain_points],[names;domain_names],X,Y,nz,dx,dy);
    if point_file~="" && ~isempty(custom_ix)
        monitoring.head_points_resolved_i_x(5:end)=custom_ix;
        monitoring.head_points_resolved_i_y(5:end)=custom_iy;
    end
    ix=monitoring.head_points_resolved_i_x;
    iy=monitoring.head_points_resolved_i_y;
    resolved=sub2ind(size(ZTop),ix,iy);
    monitoring.head_points_resolved_xy=[X(resolved),Y(resolved)];
    if point_file==""
        assert(numel(unique(resolved(5:end)))==6, "The six domain monitor points must resolve to unique cells.");
    end
    for q=1:numel(ix)
        native=nz+1-monitoring.head_points_resolved_layer_top_down(q);
        metadata(q).resolved_z_m=0.5*(Z(ix(q),iy(q),native)+Z(ix(q),iy(q),native+1));
    end
    monitoring.head_point_labels=labels;
    monitoring.target_metadata=metadata;
    monitoring.omitted_points=omitted;
    monitoring.input_file=point_file;
    monitoring.depth_convention="CSV z is meters below terrain in the containing model column; direct cell head";
end

function monitoring = makeHeadMonitoring(points, names, X, Y, nz, dx, dy)
    bounds=[min(X(:))-dx/2,max(X(:))+dx/2,min(Y(:))-dy/2,max(Y(:))+dy/2];
    tolerance=64*eps(max(1,max(abs(bounds))));
    assert(all(isfinite(points),"all") && all(points(:,1)>=bounds(1)-tolerance & points(:,1)<=bounds(2)+tolerance & ...
        points(:,2)>=bounds(3)-tolerance & points(:,2)<=bounds(4)+tolerance), "Head-monitor coordinates must be inside the model domain.");
    requested_layer=points(:,3);
    assert(all(mod(requested_layer,1)==0 & requested_layer>=0 & requested_layer<=nz), ...
        "Head-monitor layers must be integers: 0 for bottom or 1 through n_layers top-down.");
    resolved_layer=requested_layer; resolved_layer(resolved_layer==0)=nz;
    n=size(points,1); ix=zeros(n,1); iy=zeros(n,1);
    for q=1:n
        [~,idx]=min((X-points(q,1)).^2+(Y-points(q,2)).^2,[],"all","linear");
        [ix(q),iy(q)]=ind2sub(size(X),idx);
    end
    monitoring=struct(); monitoring.head_points_requested_xy_layer=points;
    monitoring.head_point_names=string(names(:)); monitoring.head_points_resolved_i_x=ix;
    monitoring.head_points_resolved_i_y=iy; monitoring.head_points_resolved_layer_top_down=resolved_layer;
    monitoring.head_points_resolved_xy=[X(sub2ind(size(X),ix,iy)),Y(sub2ind(size(Y),ix,iy))];
    monitoring.layer_convention="positive layers are top-down; layer 0 selects the bottom layer";
end

function record = targetRecord()
record=struct("source","","csv_row",0,"original_name","", ...
    "requested_depth_m",[],"requested_elevation_m",[],"resolved_z_m",0);
end

function record = omissionRecord()
record=struct("csv_row",0,"x",0,"y",0,"z",0,"name","","reason","");
end

function [points,names,metadata,omitted,ix,iy] = readMonitoringCSV(path,X,Y,Z,dx,dy)
assert(isfile(path),"BDam:MonitoringFile","Monitoring CSV does not exist: %s",path);
[fid,message]=fopen(path,"r");
assert(fid>=0,"BDam:MonitoringFile","Cannot read monitoring CSV: %s",message);
cleanup=onCleanup(@()fclose(fid));
contents=fread(fid,Inf,"*char")';
clear cleanup
points=zeros(0,3); names=strings(0,1); ix=zeros(0,1); iy=zeros(0,1);
metadata=repmat(targetRecord(),0,1); omitted=repmat(omissionRecord(),0,1);
if strlength(strtrim(string(contents)))==0, return; end
try
    rows=readtable(path,"VariableNamingRule","preserve","TextType","string");
catch failure
    error("BDam:MonitoringCSV","Cannot parse monitoring CSV: %s",failure.message);
end
headers=lower(strtrim(string(rows.Properties.VariableNames)));
required=["x","y","z","name"];
assert(all(arrayfun(@(name)nnz(headers==name)==1,required)), ...
    "BDam:MonitoringCSV","Monitoring CSV requires unique x,y,z,name columns (case insensitive).");
if height(rows)==0, return; end
values=zeros(height(rows),3);
for q=1:3
    values(:,q)=str2double(string(rows{:,find(headers==required(q),1)}));
end
assert(all(isfinite(values),"all"),"BDam:MonitoringCSV", ...
    "Monitoring CSV x,y,z must be finite numeric values.");
labels=string(rows{:,find(headers=="name",1)});
labels(ismissing(labels))=""; labels=strtrim(labels);
[nx,ny,ninterfaces]=size(Z); nz=ninterfaces-1;
xmin=min(X(:))-dx/2; xmax=max(X(:))+dx/2;
ymin=min(Y(:))-dy/2; ymax=max(Y(:))+dy/2;
for row=1:height(rows)
    x=values(row,1); y=values(row,2); depth=values(row,3);
    reason="";
    xy_tolerance=64*eps(max(1,max(abs([xmin,xmax,ymin,ymax]))));
    if x<xmin-xy_tolerance || x>xmax+xy_tolerance || y<ymin-xy_tolerance || y>ymax+xy_tolerance
        reason="outside horizontal model bounds";
    else
        fraction=[(x-xmin)/dx,(y-ymin)/dy];
        near_face=abs(fraction-round(fraction))<=64*eps(max(1,max(abs(fraction))));
        fraction(near_face)=round(fraction(near_face));
        i=min(nx,max(1,floor(fraction(1))+1));
        j=min(ny,max(1,floor(fraction(2))+1));
        interfaces=reshape(Z(i,j,:),[],1);
        elevation=interfaces(end)-depth;
        tolerance=64*eps(max(1,max(abs(interfaces))));
        if depth<0
            reason="above terrain (negative depth)";
        elseif elevation<interfaces(1)-tolerance
            reason="below model bottom";
        end
    end
    if reason~=""
        entry=omissionRecord();
        entry.csv_row=row; entry.x=x; entry.y=y; entry.z=depth;
        entry.name=labels(row); entry.reason=reason;
        omitted(end+1,1)=entry; %#ok<AGROW>
        continue
    end
    assert(strlength(labels(row))>0,"BDam:MonitoringCSV", ...
        "Retained monitoring CSV row %d requires a nonblank name.",row);
    previous=string({metadata.original_name});
    assert(~any(strcmpi(previous,labels(row))),"BDam:MonitoringCSV", ...
        "Retained monitoring names must be unique without regard to case: %s",labels(row));
    % Snap numerical roundoff at an interface; first native match is deeper.
    [distance,interface]=min(abs(interfaces-elevation));
    if distance<=tolerance, elevation=interfaces(interface); end
    native=find(elevation>=interfaces(1:end-1) & elevation<=interfaces(2:end),1,"first");
    assert(~isempty(native),"BDam:MonitoringCSV","Cannot resolve layer for CSV row %d.",row);
    points(end+1,:)=[x,y,nz+1-native]; %#ok<AGROW>
    names(end+1,1)=sprintf("head_csv_%04d",row); %#ok<AGROW>
    ix(end+1,1)=i; iy(end+1,1)=j; %#ok<AGROW>
    entry=targetRecord(); entry.source="csv"; entry.csv_row=row;
    entry.original_name=labels(row); entry.requested_depth_m=depth;
    entry.requested_elevation_m=elevation;
    metadata(end+1,1)=entry; %#ok<AGROW>
end
if ~isempty(omitted)
    warning("BDam:MonitoringOmitted","Omitted %d monitoring point(s) outside the modeled volume; see monitoring_omitted.csv.",numel(omitted));
end
end
