"""Explicit case evaluation for ensembles and external optimization drivers.

No sampling, reference insertion, or objective function is implicit in Study.
All active sources, studies and scratch directories must be local.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET

import numpy as np
import bdam_runtime as rt

HERE = Path(__file__).resolve().parent
VERSION = "bdam-study-v1"


def matlab_runtime(executable="matlab"):
    """Identify the installation without launching a MATLAB session."""
    executable = shutil.which(str(executable))
    if not executable:
        return None
    path = Path(executable).resolve()
    candidates = [p/"VersionInfo.xml" for p in path.parents]
    info = next((p for p in candidates if p.is_file()), None)
    if info is None:
        raise ValueError("Cannot identify MATLAB VersionInfo.xml; specify its installation executable.")
    xml = ET.parse(info).getroot()
    return dict(executable=str(path), version=xml.findtext("version"),
                release=xml.findtext("release"), installation_hash=rt.file_hash(info))


def _native(value):
    """Normalize optimizer NumPy values to independent JSON-compatible inputs."""
    if isinstance(value,np.ndarray):
        return _native(value.tolist())
    if isinstance(value,np.generic):
        return value.item()
    if isinstance(value,dict):
        return {k:_native(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [_native(v) for v in value]
    return value


def flatten(values, prefix=""):
    if not isinstance(values, dict):
        raise ValueError("Parameters must be an object.")
    result = {}
    for name, value in values.items():
        key = prefix+name
        if isinstance(value, dict) and value:
            nested=flatten(value,key+".")
            if set(nested) & set(result):
                raise ValueError(f"Repeated parameter under: {key}")
            result.update(nested)
        else:
            if key in result:
                raise ValueError(f"Repeated parameter: {key}")
            result[key] = value
    return result


def defaults(schema):
    result = {}
    for name, spec in schema["parameters"].items():
        rt.put(result, name, rt.clone(spec["default"]))
    return result


def load_schema(source):
    schema=rt.read(Path(source)/"bdam_parameter_schema.json")
    if schema.get("version")!="bdam-parameters-v7" or schema.get("defaults")!=defaults(schema):
        raise ValueError("Unsupported or inconsistent parameter registry; regenerate its MATLAB defaults mirror.")
    return schema


def _apply(config, overrides, schema):
    values = flatten(overrides)
    indexed = {}
    for name, value in values.items():
        match = re.fullmatch(r"(.+)\[([1-9][0-9]*)\]", name)
        if match:
            base, index = match[1], int(match[2])-1
            if base in values:
                raise ValueError(f"Conflicting whole-array and indexed assignments: {base}")
            spec = schema["parameters"].get(base)
            if not spec or spec["type"] != "array":
                raise ValueError(f"Unknown indexed parameter: {name}")
            array = indexed.setdefault(base, rt.clone(rt.get(config, base)))
            if not isinstance(array, list) or index >= len(array):
                raise ValueError(f"Index outside configured array: {name}; provide a complete array first.")
            array[index] = value
        else:
            if name not in schema["parameters"]:
                raise ValueError(f"Unknown parameter: {name}")
            rt.put(config, name, value)
    for name, array in indexed.items():
        rt.put(config, name, array)
    return config


def resolve_case(overrides, shared, schema):
    config = _apply(defaults(schema), shared, schema)
    config = _apply(config, overrides, schema)
    for name, spec in schema["parameters"].items():
        value = rt.get(config, name)
        if value is None:
            if not spec["automatic"]:
                raise ValueError(f"{name} does not support an automatic value.")
            continue
        kind = spec["type"]
        if kind == "boolean":
            if type(value) is not bool:
                raise ValueError(f"{name} requires true or false.")
        elif kind == "string":
            if not isinstance(value, str) or (not value.strip() and name not in ("hydrofacies_points_file", "monitoring_points_file")):
                raise ValueError(f"{name} requires text; blank cells are invalid.")
            if "enum" in spec and value not in spec["enum"]:
                raise ValueError(f"{name} must be one of {spec['enum']}.")
        elif kind == "records":
            if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
                raise ValueError(f"{name} requires a list of records.")
            required = ({"hydrofacies_id","K_m_per_day","K33_m_per_day"} if name=="hydrofacies_class_properties"
                        else {"x_m","y_m","z_top_m","z_bottom_m","hydrofacies_id"})
            for record in value:
                if set(record)!=required:
                    raise ValueError(f"{name} record fields must be {sorted(required)}.")
                if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in record.values()):
                    raise ValueError(f"{name} record values must be finite numbers.")
                rt.integer(record["hydrofacies_id"],"hydrofacies_id")
                if name=="hydrofacies_class_properties" and min(record["K_m_per_day"],record["K33_m_per_day"])<=0:
                    raise ValueError("Hydrofacies conductivities must be positive.")
        else:
            if isinstance(value,list) and any(isinstance(v,bool) for v in value):
                raise ValueError(f"{name} requires numbers, excluding booleans.")
            array = np.asarray(value)
            if array.dtype.kind not in "iuf" or not np.all(np.isfinite(array)):
                raise ValueError(f"{name} requires finite numbers, excluding booleans.")
            if kind in ("number", "integer") and array.ndim != 0:
                raise ValueError(f"{name} requires one scalar; arrays are not sweep axes.")
            if kind == "integer":
                rt.put(config, name, rt.integer(value, name, spec["minimum"]))
            elif kind == "array":
                size = spec["length"]
                if size == "n_layers":
                    size = config["n_layers"]
                if array.ndim != 1 or len(array) != size:
                    raise ValueError(f"{name} requires {size} values.")
                rt.put(config, name, array.astype(float).tolist())
            if "minimum" in spec and np.any(array < spec["minimum"]):
                raise ValueError(f"{name} must be >= {spec['minimum']}.")
            if "exclusive_minimum" in spec and np.any(array <= spec["exclusive_minimum"]):
                raise ValueError(f"{name} must be > {spec['exclusive_minimum']}.")
            if "maximum" in spec and np.any(array > spec["maximum"]):
                raise ValueError(f"{name} must be <= {spec['maximum']}.")
            if kind == "number":
                rt.put(config, name, int(value) if float(value).is_integer() else float(value))
    config["monitoring_points_file"] = config["monitoring_points_file"].strip()
    # Internal execution capacity is supplied separately; never a parameter axis.
    config["n_parallel_runs"] = 1
    config = rt.resolve(config)
    config["reference_mean_streamflow_m3_per_day"] = config["synthetic_mean_streamflow_m3_per_day"]
    rt.validate(config)
    _validate_geometry(config["geometry"])
    return config


def _validate_geometry(p):
    for key in ("domain_length_x_m", "domain_length_y_m", "spacing_x_m", "spacing_y_m"):
        if p[key] <= 0:
            raise ValueError(f"geometry.{key} must be positive.")
    for axis in ("x", "y"):
        count = p[f"domain_length_{axis}_m"]/p[f"spacing_{axis}_m"]
        if count < 2 or not math.isclose(count, round(count), rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError(f"Geometry {axis} length must contain an integer number of at least two cells.")
    if not (0 < p["dam_relative_distance_upstream"] < 1) or p["dam_height_m"] <= 0:
        raise ValueError("Dam must be inside the reach and have positive height.")
    if p["regional_longitudinal_slope"] <= 0 or p["channel_longitudinal_slope"] <= 0:
        raise ValueError("Coarse river currently requires positive slopes toward minimum Y.")
    periods = p["sine_periods"]
    if periods < 0 or not math.isclose(periods*2, round(periods*2), abs_tol=1e-10):
        raise ValueError("Sine periods must be a nonnegative multiple of 0.5.")
    if min(p["depths_m"]) <= 0 or min(p["bottom_widths_m"]) <= 0:
        raise ValueError("Cross-section widths and depths must be positive.")


def read_cases(path):
    """Read explicit CSV rows or a JSON array, preserving CSV column names."""
    path = Path(path)
    if path.suffix.lower() != ".csv":
        cases = rt.read(path)
        if not isinstance(cases, list):
            raise ValueError("Case JSON must be an array of rows.")
        return cases
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV requires unique column names.")
        result = []
        for row in reader:
            item = {}
            for name, value in row.items():
                if name is None or value is None:
                    raise ValueError("CSV rows must have all declared cells populated.")
                if name == "monitoring_points_file" and not value.strip():
                    item[name] = ""
                    continue
                if not value.strip():
                    raise ValueError("CSV rows must have all declared cells populated.")
                if name == "case_id" or name.startswith("metadata."):
                    item[name] = value
                else:
                    try:
                        item[name] = json.loads(value)
                    except json.JSONDecodeError:
                        item[name] = value
            result.append(item)
        return result


def grid_cases(axes, fixed=None):
    """Return an explicit Cartesian design; add references explicitly if wanted."""
    return [dict(parameters={**(fixed or {}), **dict(zip(axes, values))})
            for values in itertools.product(*axes.values())]


def random_cases(bounds, count, seed, fixed=None):
    """Return seeded independent uniform samples; discrete sampling stays external."""
    count = rt.integer(count, "count", 0)
    rng = np.random.default_rng(seed)
    for name, pair in bounds.items():
        if len(pair) != 2 or not all(math.isfinite(v) for v in pair) or pair[0] > pair[1]:
            raise ValueError(f"Invalid uniform bounds: {name}")
    return [dict(parameters={**(fixed or {}), **{name: float(rng.uniform(*pair)) for name,pair in bounds.items()}},
                 metadata=dict(design="independent_uniform", seed=seed, sample=i+1, bounds=bounds))
            for i in range(count)]


def _safe_id(value, label):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",value):
        raise ValueError(f"{label} must be a nonempty identifier using letters, digits, _, - or .")
    return value


def _parameter_json(value):
    # Preserve nonfinite parameter requests as diagnostic text so one invalid
    # candidate does not prevent the remaining rows from being persisted.
    if isinstance(value,float) and not math.isfinite(value):
        return str(value)
    if isinstance(value,dict):
        return {k:_parameter_json(v) for k,v in value.items()}
    if isinstance(value,list):
        return [_parameter_json(v) for v in value]
    return value


def _row(row, index):
    if not isinstance(row,dict):
        raise ValueError("Each case must be an object.")
    row = rt.clone(_native(row))
    identity = _safe_id(row.pop("case_id",f"case-{index+1:06d}"),"case_id")
    metadata = row.pop("metadata",{})
    if not isinstance(metadata,dict):
        raise ValueError("Case metadata must be an object.")
    for key in list(row):
        if key.startswith("metadata."):
            metadata[key[9:]] = row.pop(key)
    if "parameters" in row:
        parameters = row.pop("parameters")
        if row:
            raise ValueError("Use either a parameters object or flat columns, not both.")
    else:
        parameters = row
    if not isinstance(parameters,dict):
        raise ValueError("Case parameters must be an object.")
    return dict(case_id=identity,parameters=_parameter_json(parameters),metadata=metadata)


class Study:
    """Persistent local evaluations with append-only batches and validated reuse."""

    def __init__(self, root, settings=None):
        self.root = rt.local_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with rt.lock(self.root/"locks"/"study.lock", blocking=True):
            target = self.root/"study.json"
            if target.exists():
                saved = rt.read(target)
                if saved.get("version") != VERSION:
                    raise ValueError("Unsupported study version; use the matching tools.")
                self.settings = saved["settings"]
                if settings is not None and self._settings(settings) != self.settings:
                    raise ValueError("Study settings are immutable; use case overrides or a new study.")
            else:
                self.settings = self._settings(settings or {})
                rt.write(target,dict(version=VERSION,settings=self.settings))
        self.source = rt.local_path(self.settings["source"])
        self.execution = self.settings["execution"]
        self.schema = load_schema(self.source)

    @staticmethod
    def _settings(settings):
        if set(settings)-{"source","shared","execution"}:
            raise ValueError("Study settings allow source, shared and execution only.")
        execution = dict(n_parallel_runs=1,retention="full",matlab="matlab")
        supplied = settings.get("execution",{})
        if set(supplied)-set(execution):
            raise ValueError("Unknown execution setting.")
        execution.update(supplied)
        execution["n_parallel_runs"] = rt.integer(execution["n_parallel_runs"],"n_parallel_runs")
        if execution["retention"] not in ("full","compact"):
            raise ValueError("Retention must be full or compact.")
        source = rt.local_path(settings.get("source",HERE))
        schema = load_schema(source)
        shared = _native(settings.get("shared",{}))
        # Reject malformed/unknown shared settings as a study-level error.
        _apply(defaults(schema),shared,schema)
        return dict(source=str(source),shared=shared,execution=execution)

    def _batch(self,batch_id):
        return self.root/"batches"/(_safe_id(batch_id,"batch_id")+".json")

    def _read_batch(self,path):
        batch=rt.read(path)
        checksum=batch.pop("content_hash",None)
        if checksum!=rt.digest(batch):
            raise ValueError(f"Immutable batch manifest changed: {path}")
        return {**batch,"content_hash":checksum}

    def submit(self,cases,batch_id):
        """Persist explicit rows; invalid scientific cases become failed records."""
        path = self._batch(batch_id)
        if isinstance(cases,(str,Path)):
            cases = read_cases(cases)
        rows = [_row(row,i) for i,row in enumerate(cases)]
        if len({row["case_id"] for row in rows}) != len(rows):
            raise ValueError("Case IDs must be unique within a batch.")
        request = dict(cases=rows,shared=self.settings["shared"])
        rt.digest(request)  # Reject non-JSON/nonfinite metadata before creating snapshots.
        with rt.lock(self.root/"locks"/"study.lock",blocking=True):
            if path.exists():
                batch = self._read_batch(path)
                if batch["request"] != request:
                    raise ValueError("Batch ID already has a different immutable request.")
                return batch
            files = rt.source_files(self.source)
            hashes = {p.name:rt.file_hash(p) for p in files}
            # Include every scientific implementation dependency; docs/labels are excluded.
            scientific = {k:v for k,v in hashes.items() if (k.endswith((".py",".m")) and not k.startswith("test")) or k=="bdam_parameter_schema.json"}
            numerical = rt.runtime_provenance(self.source)
            matlab = matlab_runtime(self.execution["matlab"])
            members, records = {}, []
            for row in rows:
                record = {**row,"execution_id":None,"status":"pending"}
                try:
                    config = resolve_case(row["parameters"],self.settings["shared"],self.schema)
                    inputs = {}
                    for name in ("usgs_hydrograph_file","hydrofacies_points_file","monitoring_points_file"):
                        if config[name]:
                            file = Path(config[name]).expanduser()
                            file = file if file.is_absolute() else self.source/file
                            inputs[name] = file.resolve()
                    checksums = {name:rt.file_hash(file) for name,file in inputs.items()}
                    physical = {k:v for k,v in config.items() if k not in ("n_parallel_runs",*inputs)}
                    fingerprint = rt.digest(dict(config=physical,inputs=checksums,source=scientific,
                        runtime=numerical,matlab={k:v for k,v in (matlab or {}).items() if k!="executable"},version=VERSION))
                    identity = fingerprint[:24]
                    destination = self.root/"executions"/identity/"BDam"
                    member = dict(id=identity,fingerprint=fingerprint,path=str(destination))
                    if destination.exists():
                        if rt.read(destination/"provenance.json")["fingerprint"] != fingerprint:
                            raise RuntimeError("Execution identity collision.")
                    else:
                        # Publish snapshots only after complete construction; retries never see half a snapshot.
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        temporary = Path(tempfile.mkdtemp(prefix=".snapshot-",dir=destination.parent))
                        try:
                            for file in files:
                                shutil.copy2(file,temporary/file.name)
                            resolved = rt.clone(config)
                            resolved["source_root"] = str(destination)
                            resolved["source_geometry_file"] = str(destination/"Geometry"/"BDamGeometry.mat")
                            for name,file in inputs.items():
                                relative = Path("inputs")/name/file.name
                                (temporary/relative).parent.mkdir(parents=True,exist_ok=True)
                                shutil.copy2(file,temporary/relative)
                                resolved[name] = str(destination/relative)
                            rt.write(temporary/"resolved_config.json",resolved)
                            rt.write(temporary/"provenance.json",dict(fingerprint=fingerprint,scientific_config=physical,
                                source_hashes=hashes,input_hashes=checksums,resolved_config_hash=rt.digest(resolved),
                                runtime=numerical,matlab_runtime=matlab,version=VERSION))
                            for name, checksum in hashes.items():
                                if rt.file_hash(temporary/name)!=checksum:
                                    raise RuntimeError("Source changed while creating snapshot.")
                            for name, checksum in checksums.items():
                                if rt.file_hash(temporary/"inputs"/name/inputs[name].name)!=checksum:
                                    raise RuntimeError("Input changed while creating snapshot.")
                            temporary.rename(destination)
                        finally:
                            if temporary.exists():
                                shutil.rmtree(temporary)
                    members[identity]=member
                    record.update(execution_id=identity,resolved_parameters={k:v for k,v in config.items()
                        if k not in ("n_parallel_runs","reference_mean_streamflow_m3_per_day")},output_path=str(destination))
                except (ValueError,TypeError,KeyError,OSError) as exc:
                    record.update(status="failed",error=dict(phase="resolution",type=type(exc).__name__,message=str(exc)))
                records.append(record)
            # The runner finds one stable study-wide manifest for membership and capacity.
            registry_path = self.root/"campaign.json"
            registry = rt.read(registry_path) if registry_path.exists() else dict(version=VERSION,root=str(self.root),
                study_root=str(self.root),n_parallel_runs=self.execution["n_parallel_runs"],members=[])
            registered = {m["id"]:m for m in registry["members"]}
            registered.update(members)
            registry["members"]=list(registered.values())
            self._copy_executable()
            rt.write(registry_path,registry)
            batch = dict(version="bdam-batch-v1",study_root=str(self.root),batch_id=batch_id,request=request,cases=records,
                         members=list(members.values()),root=str(self.root),n_parallel_runs=self.execution["n_parallel_runs"])
            batch["content_hash"]=rt.digest(batch)
            rt.write(path,batch)
            return batch

    def _copy_executable(self):
        executable = next((p/"bin"/"mf6" for p in (self.source,*self.source.parents) if (p/"bin"/"mf6").is_file()),None)
        if executable is None:
            return
        rt.local_path(executable)
        target = self.root/"bin"/"mf6"
        target.parent.mkdir(exist_ok=True)
        if target.exists() and rt.file_hash(target)!=rt.file_hash(executable):
            raise RuntimeError("Study MF6 executable changed; create a new study.")
        if not target.exists():
            shutil.copy2(executable,target)

    def prepare(self,batch_id):
        """Generate geometry and paired handoffs serially for pending cases."""
        batch = self._read_batch(self._batch(batch_id))
        if not batch["members"]:
            return
        if not matlab_runtime(self.execution["matlab"]):
            raise RuntimeError("MATLAB executable is unavailable.")
        if not (self.root/"bin"/"mf6").is_file():
            raise RuntimeError("A local bin/mf6 executable is required.")
        for member in batch["members"]:
            rt.verify_snapshot(member["path"])
        rt.prepare(self._batch(batch_id),self.execution["matlab"])

    def evaluate(self,batch_id,retention=None):
        """Evaluate a batch and return one result per case in submitted order."""
        retention = retention or self.execution["retention"]
        if retention not in ("full","compact"):
            raise ValueError("Retention must be full or compact.")
        batch = self._read_batch(self._batch(batch_id))
        reused = [m["id"] for m in batch["members"] if rt.complete(m["path"],m["fingerprint"])]
        self.prepare(batch_id)
        ready = [m for m in batch["members"] if (Path(m["path"])/"prepared.json").is_file()]
        with ThreadPoolExecutor(max_workers=self.execution["n_parallel_runs"]) as pool:
            list(pool.map(lambda m:rt.run_member(rt.read(self.root/"campaign.json"),m,retention),ready))
        rt.write(self.root/"results"/batch_id/"evaluation.json",dict(reused_execution_ids=reused))
        return self.collect(batch_id)

    def collect(self,batch_id=None):
        """Revalidate completed executions and publish case-indexed results."""
        selected = [self._batch(batch_id)] if batch_id is not None else sorted((self.root/"batches").glob("*.json"))
        with rt.lock(self.root/"locks"/"collect.lock",blocking=True):
            results, summaries, checked = [], [], {}
            for batch_path in selected:
                batch = self._read_batch(batch_path)
                receipt = self.root/"results"/batch["batch_id"]/"evaluation.json"
                reused_ids = rt.read(receipt)["reused_execution_ids"] if receipt.exists() else []
                columns=list(dict.fromkeys(name for case in batch["cases"]
                    if case["execution_id"] for name in flatten(case["parameters"])))
                for case in batch["cases"]:
                    row = dict(batch_id=batch["batch_id"],case_id=case["case_id"],execution_id=case["execution_id"],
                        metadata=case["metadata"],requested_parameters=case["parameters"],
                        status=case["status"],error=case.get("error"),qa_status="not_run",
                        reused=False,resolved_parameters=case.get("resolved_parameters"),output_path=case.get("output_path"),summaries=[])
                    identity = case["execution_id"]
                    if identity:
                        member = next(m for m in batch["members"] if m["id"]==identity)
                        path=Path(member["path"])
                        valid = checked.setdefault(identity,None)
                        if valid is None:
                            valid = rt.complete(path,member["fingerprint"])
                            checked[identity]=valid
                        status=rt.read(path/"status.json") if (path/"status.json").exists() else {}
                        row.update(status=status.get("status","pending"))
                        if valid:
                            row.update(status="pass",qa_status="pass",elapsed_seconds=rt.read(path/"completion.json").get("elapsed_seconds"))
                            row["reused"] = identity in reused_ids or identity in {r["execution_id"] for r in results}
                            for summary in sorted((path/"Runs").glob("*_summary.csv")):
                                row["summaries"].append(str(summary))
                                with summary.open(newline="") as stream:
                                    for value in csv.DictReader(stream):
                                        parameters={name:_reported_value(case["resolved_parameters"],name) for name in columns}
                                        summaries.append({**value,"batch_id":batch["batch_id"],"case_id":case["case_id"],
                                            "execution_id":identity,**{f"parameter.{k}":v for k,v in parameters.items()},
                                            **{f"metadata.{k}":v for k,v in case["metadata"].items()},"summary":summary.name})
                        elif row["status"]=="pass":
                            row.update(status="invalid",qa_status="fail",error=dict(phase="validation",type="IntegrityError",message="Completion validation failed."))
                        elif row["status"] in ("failed", "DNC"):
                            row["error"]=dict(phase=status.get("phase","simulation"),type="ExecutionError",message=status.get("error","Unknown failure"))
                    results.append(row)
            folder=self.root/"results"/(batch_id or "all")
            folder.mkdir(parents=True,exist_ok=True)
            rt.write(folder/"results.json",results)
            _csv(folder/"case_index.csv",[{**row,**{f"parameter.{k}":v for k,v in flatten(row["resolved_parameters"] or row["requested_parameters"]).items()}} for row in results])
            _csv(folder/"ensemble_summary.csv",summaries)
            return results


def _reported_value(config,name):
    match=re.fullmatch(r"(.+)\[([1-9][0-9]*)\]",name)
    try:
        return rt.get(config,match[1])[int(match[2])-1] if match else rt.get(config,name)
    except IndexError:
        return None  # A different case may have fewer layers than this column.


def _csv(path,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row)) or ["batch_id","case_id","status"]
    temporary=path.with_suffix(".tmp")
    with temporary.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("init"); p.add_argument("root"); p.add_argument("--settings")
    p=sub.add_parser("submit"); p.add_argument("root"); p.add_argument("cases"); p.add_argument("batch_id")
    for name in ("prepare","evaluate","collect"):
        p=sub.add_parser(name); p.add_argument("root"); p.add_argument("batch_id",**({"nargs":"?"} if name=="collect" else {}))
    p=sub.add_parser("template"); p.add_argument("output"); p.add_argument("--source",default=str(HERE))
    args=parser.parse_args()
    if args.command=="template":
        schema=load_schema(args.source)
        _csv(Path(args.output),[{"case_id":"example",**{k:json.dumps(s["default"]) for k,s in schema["parameters"].items()}}]); return
    if args.command=="init":
        Study(args.root,rt.read(args.settings) if args.settings else {}); return
    study=Study(args.root)
    if args.command=="submit":
        result=study.submit(args.cases,args.batch_id)
    else:
        result=getattr(study,args.command)(args.batch_id)
    print(json.dumps(result,indent=2,allow_nan=False))
    if args.command=="evaluate" and any(row["status"]!="pass" for row in result):
        raise SystemExit(1)


if __name__=="__main__":
    main()
