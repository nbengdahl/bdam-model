function verifyPreparedLakeStorage(inputRoot)
% Verify the actual single-run MakeInputs handoffs without editing them.
arguments
    inputRoot (1,1) string
end
for phase=["pre_dam","post_dam"]
    file=fullfile(inputRoot,phase,"preparation_handoff.h5");
    top=readArray(file,"/grid/ZTop");
    n=readArray(file,"/surface_water/n_lakes");
    for i=1:n
        base="/surface_water/lakes/lake_"+i;
        storage=logical(readArray(file,base+"/storage_footprint_mask"));
        exchange=logical(readArray(file,base+"/footprint_mask"));
        stage=readArray(file,base+"/stage_area_volume/stage_m");
        volume=readArray(file,base+"/stage_area_volume/volume_m3");
        area=readArray(file,base+"/stage_area_volume/area_m2");
        bed=min(top(exchange));
        assert(min(top(storage))==bed && stage(1)==bed && volume(1)==0 && area(1)>0, ...
            "Lake %d in %s cannot reach an empty state.",i,phase);
        assert(all(diff(stage)>0) && all(diff(volume)>0));
        if phase=="post_dam" && i==1
            terrain=top(storage);
            cellArea=readArray(file,"/grid/dx_m")*readArray(file,"/grid/dy_m");
            assert(all(ismember(unique(terrain),stage)));
            mid=(stage(1)+stage(2))/2;
            assert(abs(interp1(stage,volume,mid)-sum(max(mid-terrain,0))*cellArea)<1e-12);
            cap=readArray(file,"/surface_water/dam/maximum_lake_extent_stage_m");
            assert(all(area(stage>=cap)==nnz(storage)*cellArea));
            above=find(stage>=cap);
            assert(all(abs(diff(volume(above))./diff(stage(above))-area(end))<1e-8));
        end
    end
end
fprintf('Prepared LAK dry-bottom, terrain-breakpoint and capped-storage checks passed.\n');
end

function values=readArray(file,path)
    shape=double(h5read(file,path+"/shape"));
    values=reshape(h5read(file,path+"/data"),shape(:)');
end
