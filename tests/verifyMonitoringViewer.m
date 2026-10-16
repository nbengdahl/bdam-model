function receipt = verifyMonitoringViewer(outputRoot)
% Verify actual short-run CSV labels, selection and map highlights in the viewer.
results=loadBDamResults(outputRoot);
csvPoints=results.Targets(results.Targets.source=="csv",:);
assert(height(csvPoints)>=2,"Expected at least two retained CSV points.");
for row=1:height(csvPoints)
    variable=csvPoints.name(row)+"_m";
    label=results.Variables.Label(results.Variables.Name==variable);
    assert(isscalar(label) && label==csvPoints.original_name(row),"CSV variable label was lost.");
end
app=BDamResultsViewerApp(outputRoot);
cleanup=onCleanup(@()delete(app)); %#ok<NASGU>
buttons=findall(app.UIFigure,"Type","uibutton");
loadButton=buttons(arrayfun(@(button)string(button.Text)=="Load",buttons));
assert(isscalar(loadButton));
feval(loadButton.ButtonPushedFcn,loadButton,[]);
list=findall(app.UIFigure,"Type","uilistbox");
assert(isscalar(list));
selected=csvPoints.name(1:2)+"_m";
assert(all(ismember(selected,string(list.ItemsData))));
list.Value=cellstr(selected);
feval(list.ValueChangedFcn,list,struct("Value",selected));
drawnow;
texts=findall(app.MapAxes,"Type","text");
labels=strings(numel(texts),1);
for row=1:numel(texts), labels(row)=string(texts(row).String); end
assert(all(ismember(csvPoints.original_name(1:2),labels)),"Selected CSV map labels were lost.");
slider=findall(app.UIFigure,"Type","uislider");
assert(isscalar(slider));
slider.Value=1;
feval(slider.ValueChangedFcn,slider,[]);
assert(~isempty(findall(app.MapAxes,"Type","image")),"Viewer map did not load.");
receipt=struct("status","pass","target_count",height(results.Targets), ...
    "csv_target_count",height(csvPoints),"display_labels",csvPoints.original_name, ...
    "selected_ids",selected,"map_labels_preserved",true, ...
    "frame_count",height(results.Scopes.Monitored.Frames));
end
