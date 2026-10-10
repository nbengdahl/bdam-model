function base = mergeBDamConfig(base,override)
% Reject unknown keys rather than silently accepting misspelled parameters.
names = fieldnames(override);
for i = 1:numel(names)
    name = names{i};
    assert(isfield(base,name),"Unknown BDam configuration field: %s",name);
    if isstruct(base.(name)) && isscalar(base.(name)) && isstruct(override.(name))
        base.(name) = mergeBDamConfig(base.(name),override.(name));
    else
        base.(name) = override.(name);
    end
end
end
