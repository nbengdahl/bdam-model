"""Deprecated grid-design adapter. New applications should import bdam."""
import json
from pathlib import Path
import sys

import numpy as np
from bdam_runtime import HERE, clone, digest, get, put, read, resolve, validate, mark_prepared
import itertools
import warnings

def scalar_identity(value):
    """JSON 1 and 1.0 identify the same physical scalar candidate."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def expand(config, scalar_defaults, skip_baseline=False):
    """Scalar registry defines axes; native arrays never become Cartesian axes."""
    config = clone(config)
    axes = {}
    for name, default in scalar_defaults.items():
        value = get(config, name)
        if isinstance(default, bool):
            if type(value) is not bool:
                raise ValueError(f"{name} requires a scalar true or false.")
            continue
        if value is None or value == []:
            if default is None or name == "groundwater_boundary_k_m_per_day":
                continue
            raise ValueError(f"{name} cannot be empty.")
        array = np.asarray(value)
        if sum(n > 1 for n in array.shape) > 1:
            raise ValueError(f"{name} accepts a scalar or vector, not a matrix.")
        flat = array.ravel()
        if np.any([isinstance(v, (bool, np.bool_)) for v in flat]) or not np.issubdtype(flat.dtype, np.number) or np.any(~np.isfinite(flat)):
            raise ValueError(f"{name} requires finite numeric candidates.")
        if flat.size > 1:
            axes[name] = list(dict.fromkeys(scalar_identity(v) for v in flat.tolist()))
        else:
            put(config, name, scalar_identity(flat[0].item()))
    baseline = clone(config)
    for name in axes:
        put(baseline, name, scalar_identity(scalar_defaults[name]))
    baseline = resolve(baseline)
    reference_mean = baseline["synthetic_mean_streamflow_m3_per_day"]
    baseline["reference_mean_streamflow_m3_per_day"] = reference_mean
    configs = []
    for values in itertools.product(*axes.values()):
        member = clone(config)
        for name, value in zip(axes, values):
            put(member, name, value)
        member = resolve(member)
        member["reference_mean_streamflow_m3_per_day"] = reference_mean
        configs.append(member)
    if not skip_baseline:
        configs.insert(0, baseline)
    unique = {}
    for member in configs:
        if skip_baseline and member == baseline:
            continue
        try:
            validate(member)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid combination: {json.dumps(member, sort_keys=True)}\n{exc}") from exc
        unique.setdefault(digest(member), member)
    return list(unique.values()), baseline, axes


def plan(request, root, source=HERE, skip_baseline=False):
    """Translate the old vector request into explicit rows in a new study."""
    from bdam import Study
    warnings.warn("Use bdam.Study and explicit cases; sweep commands are deprecated.", FutureWarning)
    config = read(request)
    configs, baseline, _ = expand(config, read(Path(source)/"bdam_parameter_schema.json")["scalar_defaults"], skip_baseline)
    cases = []
    for i, item in enumerate(configs):
        item = clone(item)
        # Old requests selected a shared generated file; new cases rebuild it.
        item.pop("source_geometry_file", None)
        item.pop("reference_mean_streamflow_m3_per_day", None)
        item.pop("n_parallel_runs", None)
        cases.append(dict(case_id=f"grid-{i+1}", parameters=item, metadata=dict(reference=configs[i] == baseline)))
    study = Study(root, dict(source=str(source), execution=dict(n_parallel_runs=config.get("n_parallel_runs", 1))))
    return study.submit(cases, "grid")


def main():
    import argparse
    from bdam import Study
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("request"); p.add_argument("root"); p.add_argument("--source", default=str(HERE))
    p.add_argument("--skip-baseline", action="store_true")
    for name in ("prepare", "run", "collect"):
        p = sub.add_parser(name); p.add_argument("manifest")
        p.add_argument("--retention", choices=("full", "compact"), default="full")
    p = sub.add_parser("mark-prepared"); p.add_argument("path")
    args = parser.parse_args()
    if args.command == "mark-prepared":
        mark_prepared(args.path); return
    if args.command == "plan":
        plan(args.request,args.root,args.source,args.skip_baseline); return
    manifest = read(args.manifest)
    if manifest.get("version") != "bdam-batch-v1":
        parser.error("Frozen sweep campaigns require their original tools; create a fresh study.")
    study = Study(manifest["study_root"])
    if args.command == "collect":
        study.collect(manifest["batch_id"])
    elif args.command == "prepare":
        study.prepare(manifest["batch_id"])
    else:
        results = study.evaluate(manifest["batch_id"], retention=args.retention)
        sys.exit(int(any(row["status"] != "pass" for row in results)))


if __name__ == "__main__":
    main()
