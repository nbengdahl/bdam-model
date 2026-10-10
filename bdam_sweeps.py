"""Plan, prepare, run, resume, and collect isolated BDam Cartesian campaigns."""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import itertools
import json
import math
import platform
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    import fcntl
except ImportError:  # Windows single-run compatibility; campaign locks use msvcrt.
    fcntl = None
    import msvcrt
import numpy as np

HERE = Path(__file__).resolve().parent
VERSION = "bdam-campaign-v1"
_LOCK_STATE = threading.local()


def lock_fds():
    inherited = [int(fd) for fd in os.environ.get("BDAM_INHERITED_LOCK_FDS", "").split(",") if fd]
    return tuple(inherited + getattr(_LOCK_STATE, "fds", []))



def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def geometry_fingerprint(path):
    """Hash numerical geometry consumed by preparation, ignoring export timestamps."""
    import h5py
    checksum = hashlib.sha256()
    with h5py.File(path,"r") as stream:
        def visit(name,obj):
            if isinstance(obj,h5py.Dataset):
                data=np.asarray(obj)
                checksum.update(name.encode()); checksum.update(str(data.shape).encode())
                checksum.update(data.dtype.str.encode()); checksum.update(data.tobytes())
        for name in ("X","Y","ZTop","dx","dy","parameters","post_dam","dam_settings"):
            obj=stream[name]
            if isinstance(obj,h5py.Group):
                obj.visititems(lambda child,item: visit(name+"/"+child,item))
            else:
                visit(name,obj)
    return checksum.hexdigest()


def runtime_provenance(source):
    import h5py, flopy
    executable = next((p/"bin"/"mf6" for p in (Path(source),*Path(source).parents)
                       if (p/"bin"/"mf6").is_file()),None)
    return dict(python=platform.python_version(),numpy=np.__version__,h5py=h5py.__version__,
                flopy=flopy.__version__,mf6_sha256=file_hash(executable) if executable else None)


def get(config, dotted):
    value = config
    for key in dotted.split("."):
        value = value[key]
    return value


def put(config, dotted, value):
    keys = dotted.split(".")
    target = config
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value


def clone(value):
    return json.loads(json.dumps(value))


def local_path(path):
    path = Path(path).expanduser().resolve()
    if any(name in str(path).lower() for name in
           ("my drive", "google drive", "googledrive", "onedrive", "dropbox", "icloud", "/volumes/")):
        raise ValueError(f"Active campaign must use local nonsynchronized storage: {path}")
    return path


def integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum or int(value) != value:
        raise ValueError(f"{name} must be an integer >= {minimum}.")
    return int(value)


def resolve(config):
    config = clone(config)
    layers = integer(config["n_layers"], "n_layers")
    for key, default in (("K_by_layer_top_to_bottom", .03), ("K33_by_layer_top_to_bottom", .003)):
        if config.get(key) is None or config[key] == []:
            config[key] = [default]*layers
    if config.get("ghb_k_mean_m_per_day") is None or config["ghb_k_mean_m_per_day"] == []:
        config["ghb_k_mean_m_per_day"] = config["K_constant"]
    for driver in config["forcing_controls"].values():
        if driver["center_day"] == []:
            driver["center_day"] = None
    for name in ("pullman_monthly_precipitation_mm", "synthetic_land_et_monthly_factor",
                 "synthetic_recharge_monthly_factor", "K_by_layer_top_to_bottom", "K33_by_layer_top_to_bottom"):
        config[name] = np.asarray(config[name],dtype=float).ravel().tolist()
    for name in ("hydrofacies_points","hydrofacies_class_properties"):
        if isinstance(config.get(name),dict):
            config[name] = [config[name]]
    return config


def validate(config):
    integer(config["n_parallel_runs"], "n_parallel_runs")
    mf, dam = config["mf6_parameters"], config["dam_settings"]
    for name in ("fall_average_spinup_years", "monthly_spinup_years", "weekly_spinup_years", "pre_dam_years", "post_dam_years"):
        integer(mf[name], f"mf6_parameters.{name}", 0)
    if mf["pre_dam_years"]+mf["post_dam_years"] == 0:
        raise ValueError("At least one monitored year is required.")
    for name in ("uzf_ntrailwaves", "uzf_nwavesets"):
        integer(mf[name], f"mf6_parameters.{name}")
    integer(config["channel_half_width_cells"], "channel_half_width_cells", 0)
    integer(dam["leakage_half_width_cells"], "dam_settings.leakage_half_width_cells", 0)
    integer(dam["leakage_n_top_layers"], "dam_settings.leakage_n_top_layers")
    integer(dam["stage_table_rows"], "dam_settings.stage_table_rows", 3)
    if dam["leakage_n_top_layers"] > config["n_layers"]:
        raise ValueError("Dam leakage layer count exceeds n_layers.")
    positive = ("model_bottom_offset", "K_constant", "K33_constant", "specific_storage", "lakebed_thickness_m",
                "lakebed_vertical_k_m_per_day", "ghb_k_mean_m_per_day", "downstream_control_distance_in_domain_lengths",
                "rating_curve_stage_range_m", "rating_curve_exponent", "pre_dam_outlet_width_m", "post_dam_weir_width_m")
    for name in positive:
        if config[name] <= 0:
            raise ValueError(f"{name} must be positive.")
    for name in ("k_multiplier","k33_multiplier","max_lake_extent_height_above_weir_m"):
        if dam[name] <= 0:
            raise ValueError(f"dam_settings.{name} must be positive.")
    if dam["dam_line_sample_spacing_m"] not in (None,[]) and dam["dam_line_sample_spacing_m"] <= 0:
        raise ValueError("Dam sample spacing must be positive or automatic.")
    if config["post_dam"]["initial_depth_above_dam_toe_m"] < 0:
        raise ValueError("Post-dam initial depth must be nonnegative.")
    if config["longitudinal_direction"] not in ("x","y"):
        raise ValueError("longitudinal_direction must be x or y.")
    if config["hydraulic_conductivity_mode"] not in ("constant","by_layer","hydrofacies_points"):
        raise ValueError("Unknown hydraulic conductivity mode.")
    if mf["uzf_eps"] <= 0 or not mf["uzf_thtr"] <= mf["uzf_extwc"] <= mf["uzf_thts"]:
        raise ValueError("Invalid UZF exponent or ET water content.")
    if config.get("reference_mean_streamflow_m3_per_day",1) <= 0:
        raise ValueError("The reference rating curve requires positive mean inflow.")
    if config["layer_growth_factor"] < 1:
        raise ValueError("layer_growth_factor must be >= 1.")
    if not 0 <= config["specific_yield"] <= 1 or not 0 < config["effective_porosity"] <= 1:
        raise ValueError("Invalid yield or effective porosity.")
    if not (0 <= mf["uzf_thtr"] < mf["uzf_thts"] <= 1 and mf["uzf_thtr"] <= mf["uzf_thti"] <= mf["uzf_thts"]):
        raise ValueError("Require thtr < thts and thti between the residual and saturated water contents.")
    for name in ("initial_head_channel_offset_m", "uzf_surfdep_m", "uzf_extdp_m", "external_weir_invert_depth_m"):
        if mf[name] < 0:
            raise ValueError(f"mf6_parameters.{name} must be nonnegative.")
    for name in ("synthetic_mean_streamflow_m3_per_day", "synthetic_mean_land_et_m_per_day",
                 "synthetic_recharge_fraction_of_precipitation", "synthetic_lake_evaporation_fraction_of_land_et", "downstream_control_base_depth_m"):
        if config[name] < 0:
            raise ValueError(f"{name} must be nonnegative.")
    for name in ("pullman_monthly_precipitation_mm", "synthetic_land_et_monthly_factor", "synthetic_recharge_monthly_factor"):
        array = np.asarray(config[name], dtype=float).ravel()
        if array.size != 12 or np.any(~np.isfinite(array)) or np.any(array < 0):
            raise ValueError(f"{name} requires 12 finite nonnegative values.")
        if name == "synthetic_land_et_monthly_factor" and not array.sum():
            raise ValueError("ET factors cannot all be zero.")
    if config["hydraulic_conductivity_mode"] == "by_layer":
        for name in ("K_by_layer_top_to_bottom", "K33_by_layer_top_to_bottom"):
            a = np.asarray(config[name], dtype=float).ravel()
            if a.size != config["n_layers"] or np.any(~np.isfinite(a)) or np.any(a <= 0):
                raise ValueError(f"{name} must match the member layer count and be positive.")
    if config["time_resolution"] not in ("daily", "weekly") or config["forcing_interpolation"] != "STEPWISE":
        raise ValueError("Use daily/weekly resolution and STEPWISE period averages.")
    if config["forcing_mode"] not in ("periodic", "legacy"):
        raise ValueError("forcing_mode must be periodic or legacy.")
    for name, controls in config["forcing_controls"].items():
        from bdam_forcing import PeriodicCurve, TransformedCurve
        TransformedCurve(PeriodicCurve(np.ones(365)), **controls)
        if config["forcing_mode"] == "legacy" and controls != dict(magnitude_scale=1, shift_days=0, width_factor=1, center_day=None):
            raise ValueError(f"Legacy mode requires identity {name} controls.")


def scalar_identity(value):
    """JSON 1 and 1.0 identify the same physical scalar candidate."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def expand(config, scalar_defaults, skip_baseline=False):
    """Scalar registry defines axes; native arrays never become Cartesian axes."""
    config = clone(config)
    axes = {}
    for name, default in scalar_defaults.items():
        value = get(config, name)
        if value is None or value == []:
            if default is None or name == "ghb_k_mean_m_per_day":
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


def source_files(source):
    # Ordinary preparation writes these into the source working directory.
    # They are generated member artifacts, never immutable source inputs.
    generated = {"forcing_request.json", "forcing_diagnostics.json", "campaign.json",
                 "provenance.json", "resolved_config.json", "prepared.json",
                 "status.json", "completion.json", "member_index.csv"}
    return sorted(p for p in source.iterdir() if p.is_file() and
                  p.name not in generated and not p.name.endswith("_summary.csv") and
                  (p.suffix in (".m", ".py", ".md", ".json", ".csv", ".cff")
                   or p.name in ("requirements.txt", "LICENSE")))


def _plan(request, root, source, skip_baseline=False):
    root, source = local_path(root), Path(source).resolve()
    config = read(request)
    schema = read(source/"bdam_parameter_schema.json")
    config.setdefault("n_parallel_runs", 1)
    integer(config["n_parallel_runs"], "n_parallel_runs")
    configs, baseline, axes = expand(config, schema["scalar_defaults"], skip_baseline)
    files = source_files(source)
    hashes = {p.name: file_hash(p) for p in files}
    inputs = {}
    for name in ("source_geometry_file", "usgs_hydrograph_file", "hydrofacies_points_file"):
        if config.get(name):
            path = Path(config[name])
            if not path.is_absolute():
                path = source/path
            inputs[name] = path.resolve()
    input_hashes = {k: file_hash(v) for k, v in inputs.items()}
    scientific_input_hashes = dict(input_hashes)
    scientific_input_hashes["source_geometry_file"] = geometry_fingerprint(inputs["source_geometry_file"])
    model_names = {"bdam_forcing.py","build_bdam_simulation.py","prepareBDamMember.m",
                   "makeBDamPeriodicForcing.m","ExportPreparationForFloPy.m"}
    model_hashes = {k:v for k,v in hashes.items() if k in model_names}
    runtime = runtime_provenance(source)
    root.mkdir(parents=True, exist_ok=True)
    for ancestor in (source, *source.parents):
        executable = ancestor/"bin"/"mf6"
        if executable.is_file():
            local_path(executable)
            (root/"bin").mkdir(exist_ok=True)
            target = root/"bin"/"mf6"
            if target.exists() and file_hash(target) != file_hash(executable):
                raise ValueError("Campaign MF6 executable differs from the selected local executable.")
            if not target.exists():
                shutil.copy2(executable,target)
            break
    members = []
    for member in configs:
        # Runtime paths and scheduling capacity do not change the scientific identity.
        scientific = {k: v for k, v in member.items() if k not in ("n_parallel_runs", *inputs)}
        fingerprint = digest(dict(config=scientific, source=model_hashes, inputs=scientific_input_hashes, runtime=runtime, version=VERSION))
        identity = fingerprint[:16]
        path = root/"members"/identity/"BDam"
        is_baseline = member == baseline
        if path.exists():
            existing = read(path/"provenance.json")
            if existing["fingerprint"] != fingerprint:
                raise ValueError(f"Conflicting member directory: {path}")
        else:
            path.mkdir(parents=True)
            for file in files:
                shutil.copy2(file, path/file.name)
            resolved = clone(member)
            resolved["source_root"] = str(path)
            for name, file in inputs.items():
                destination = path/"inputs"/name/file.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, destination)
                resolved[name] = str(destination)
            # Viewer and normal build layout retain the geometry database.
            (path/"Geometry").mkdir()
            shutil.copy2(inputs["source_geometry_file"], path/"Geometry"/"BDamGeometry.mat")
            resolved["source_geometry_file"] = str(path/"Geometry"/"BDamGeometry.mat")
            write(path/"resolved_config.json", resolved)
            write(path/"provenance.json", dict(fingerprint=fingerprint, scientific_config=scientific,
                  source_hashes=hashes, input_hashes=input_hashes,
                  resolved_config_hash=digest(resolved), model_source_hashes=model_hashes,
                  scientific_input_hashes=scientific_input_hashes, runtime=runtime, version=VERSION))
        members.append(dict(id=identity, fingerprint=fingerprint, path=str(path), baseline=is_baseline))
    manifest = dict(version=VERSION, root=str(root), n_parallel_runs=config["n_parallel_runs"],
                    axes=axes, members=members, member_count=len(members), skip_baseline=skip_baseline)
    if (root/"campaign.json").exists() and read(root/"campaign.json") != manifest:
        raise ValueError("Campaign already exists with a different manifest; choose a new campaign root.")
    write(root/"campaign.json", manifest)
    print(f"Planned {len(members)} members; n_parallel_runs={manifest['n_parallel_runs']}; axes={axes}", flush=True)
    return manifest


def plan(request,root,source,skip_baseline=False):
    root = local_path(root)
    with lock(root/"locks"/"plan.lock",blocking=True):
        return _plan(request,root,source,skip_baseline)


@contextlib.contextmanager
def lock(path, blocking=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            if fcntl is not None:
                fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            else:
                stream.seek(0)
                if not path.stat().st_size:
                    stream.write(" "); stream.flush(); stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, PermissionError):
            yield False
            return
        try:
            _LOCK_STATE.fds = getattr(_LOCK_STATE, "fds", []) + [stream.fileno()]
            # Never truncate a byte-range-locked Windows file.
            if fcntl is not None:
                stream.seek(0); stream.truncate()
                stream.write(json.dumps(dict(pid=os.getpid(), claimed_at=time.time())))
                stream.flush()
            yield True
        finally:
            _LOCK_STATE.fds.remove(stream.fileno())
            if fcntl is not None:
                pass  # Closing the last inherited descriptor releases the claim.
            else:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def slot(root, capacity):
    with contextlib.ExitStack() as stack:
        while True:
            for i in range(capacity):
                candidate = contextlib.ExitStack()
                acquired = candidate.enter_context(lock(Path(root)/"locks"/f"slot-{i}.lock"))
                if acquired:
                    stack.enter_context(candidate)
                    yield i
                    return
                candidate.close()
            time.sleep(.2)


def verify_snapshot(path):
    path = Path(path)
    provenance = read(path/"provenance.json")
    if provenance.get("runtime") and runtime_provenance(path) != provenance["runtime"]:
        raise ValueError(f"Numerical runtime changed: {path}")
    if digest(read(path/"resolved_config.json")) != provenance["resolved_config_hash"]:
        raise ValueError(f"Resolved configuration changed: {path}")
    for name, checksum in provenance["source_hashes"].items():
        if file_hash(path/name) != checksum:
            raise ValueError(f"Source snapshot changed: {path/name}")
    config = read(path/"resolved_config.json")
    for name, checksum in provenance["input_hashes"].items():
        if file_hash(config[name]) != checksum:
            raise ValueError(f"Source input changed: {config[name]}")
    return provenance


def prepare(manifest_path, matlab="matlab"):
    manifest = read(manifest_path)
    # One serial MATLAB session, even when several schedulers/agents are active.
    with lock(Path(manifest["root"])/"locks"/"prepare.lock", blocking=True):
        if all((Path(m["path"])/"prepared.json").exists() for m in manifest["members"]):
            return
        for member in manifest["members"]:
            verify_snapshot(member["path"])
        literal = str(Path(manifest_path).resolve()).replace("'", "''")
        env = {**os.environ, "BDAM_PYTHON": sys.executable}
        with (Path(manifest["root"])/"preparation.log").open("a") as log:
            result = subprocess.run([matlab, "-batch", f"prepareBDamCampaign('{literal}')"],
                                    cwd=Path(manifest["members"][0]["path"]) if manifest["members"] else HERE,
                                    env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"MATLAB preparation failed; inspect {manifest['root']}/preparation.log")


def mark_prepared(path):
    path = Path(path)
    provenance = verify_snapshot(path)
    files = [p for p in (path/"ModelInput").rglob("*") if p.is_file()]
    if not all((path/"ModelInput"/phase/"preparation_handoff.h5").is_file() for phase in ("pre_dam","post_dam")):
        raise ValueError("Both scenario handoffs must be prepared.")
    write(path/"prepared.json", dict(fingerprint=provenance["fingerprint"],
          handoff_hashes={str(p.relative_to(path)):file_hash(p) for p in files}))


def expected_workspaces(path):
    config = read(Path(path)/"resolved_config.json")
    mf = config["mf6_parameters"]
    fall, monthly, weekly = (mf[n] for n in ("fall_average_spinup_years", "monthly_spinup_years", "weekly_spinup_years"))
    result = []
    if fall:
        result += [("spinup/initial_relaxation", "pre_dam", 7., 1), ("spinup/first_annual", "pre_dam", 365., 1)]
    elif monthly or weekly:
        first_steps = 12 if monthly else 52
        result.append(("spinup/first_annual", "pre_dam", 365., first_steps))
    years = fall+monthly+weekly
    if years > 1:
        steps = fall+monthly*12+weekly*52-(1 if fall else 12 if monthly else 52)
        result.append(("spinup/staged", "pre_dam", (years-1)*365., steps))
    count = 365 if config["time_resolution"] == "daily" else 52
    for phase in ("pre_dam", "post_dam"):
        result.extend((f"{phase}/year_{year:02d}", phase, 365., count)
                      for year in range(1, mf[f"{phase}_years"]+1))
    return result


def validate_results(path, save_restart=True):
    from build_bdam_simulation import load_handoff, _validate_completed_workspace
    from build_bdam_simulation import _read_final_state
    import flopy
    path = Path(path)
    states, records = {}, []
    for relative, phase, final_time, steps in expected_workspaces(path):
        workspace = path/"Runs"/relative
        handoff = load_handoff(path/"ModelInput"/phase/"preparation_handoff.h5")
        _validate_completed_workspace(handoff, workspace, final_time, True)
        head = flopy.utils.HeadFile(workspace/"bdam.hds")
        try:
            if len(head.get_times()) != steps:
                raise RuntimeError(f"Wrong saved-step count in {workspace}")
        finally:
            head.close()
        prefix = relative.replace("/", "_")
        for name, value in zip(("heads", "stages", "water_content"), _read_final_state(handoff, workspace)):
            states[f"{prefix}_{name}"] = value
        records.append(dict(workspace=relative, final_time=final_time, steps=steps))
    config = read(path/"resolved_config.json")
    summaries = [f"{config['time_resolution']}_summary.csv"]
    if any(relative.startswith("spinup/") for relative,_,_,_ in expected_workspaces(path)):
        summaries.append("spinup_summary.csv")
    for name in summaries:
        if not (path/"Runs"/name).is_file():
            raise RuntimeError(f"Missing {name}")
    if save_restart:
        np.savez_compressed(path/"Runs"/"restart_states.npz", **states)
    return records


def result_hashes(path):
    path = Path(path)
    keep = [p for p in (path/"Runs").rglob("*") if p.is_file()]
    return {str(p.relative_to(path)): file_hash(p) for p in keep}


def _complete(path, fingerprint):
    path = Path(path)
    marker = path/"completion.json"
    if not marker.exists():
        return False
    info = read(marker)
    if info.get("fingerprint") != fingerprint or info.get("status") != "pass":
        return False
    verify_snapshot(path)
    for relative, checksum in info["result_hashes"].items():
        if not (path/relative).is_file() or file_hash(path/relative) != checksum:
            return False
    if info["retention"] == "full":
        validate_results(path, save_restart=False)
    else:
        with np.load(path/"Runs"/"restart_states.npz") as states:
            if not states.files or any(not np.all(np.isfinite(states[name])) for name in states.files):
                return False
    return True


def complete(path,fingerprint):
    try:
        return _complete(path,fingerprint)
    except (OSError,ValueError,RuntimeError,KeyError,EOFError):
        return False


def compact(path):
    # Keep all scientific CSVs, JSON QA, listings/logs, and extracted restart arrays.
    for item in (Path(path)/"Runs").rglob("*"):
        if item.is_file() and item.suffix not in (".csv", ".json", ".npz", ".lst", ".log", ".md"):
            item.unlink()


def run_member(manifest, member, retention="full", reuse_baseline=None):
    path = Path(member["path"])
    with contextlib.ExitStack() as claims:
        acquired = claims.enter_context(lock(path.parent/"member.lock"))
        waited = not acquired
        if waited:
            claims.close()
            claims.enter_context(lock(path.parent/"member.lock",blocking=True))
        try:
            provenance = verify_snapshot(path)
            if complete(path, member["fingerprint"]):
                return dict(id=member["id"], status="pass", resumed=True)
            if waited and (path/"status.json").exists() and read(path/"status.json").get("status") == "failed":
                return read(path/"status.json")
            if reuse_baseline and member["baseline"]:
                reuse = Path(reuse_baseline).resolve()
                if not complete(reuse, member["fingerprint"]):
                    raise ValueError("Baseline reuse requires matching provenance and validated completion.")
                if (path/"Runs").exists():
                    raise ValueError("Baseline destination already has outputs; choose a fresh campaign.")
                shutil.copytree(reuse/"Runs", path/"Runs")
                write(path/"completion.json", read(reuse/"completion.json"))
                write(path/"status.json", dict(id=member["id"], status="pass", reused_from=str(reuse)))
                return dict(id=member["id"], status="pass", reused=True)
            prepared = read(path/"prepared.json")
            if prepared["fingerprint"] != member["fingerprint"]:
                raise ValueError("Prepared handoffs do not match member provenance.")
            for relative,checksum in prepared["handoff_hashes"].items():
                if file_hash(path/relative) != checksum:
                    raise ValueError(f"Prepared handoff changed: {relative}")
            start = time.monotonic()
            attempt = len(list(path.glob("attempt-*")))+1
            attempt_path = path/f"attempt-{attempt:03d}"
            attempt_path.mkdir()
            # Preserve every failed prior attempt without reusing its workspace.
            if (path/"Runs").exists():
                shutil.move(path/"Runs", attempt_path/"prior_Runs")
            cache = path/"matplotlib-cache"; cache.mkdir(exist_ok=True)
            env = {**os.environ, "MPLCONFIGDIR": str(cache), "PYTHONUNBUFFERED": "1"}
            env["BDAM_CAMPAIGN_MANIFEST"] = str(Path(manifest["root"])/"campaign.json")
            env["BDAM_INHERITED_LOCK_FDS"] = ",".join(map(str,lock_fds())) if os.name == "posix" else ""
            write(path/"status.json", dict(id=member["id"], status="running", attempt=attempt))
            with (attempt_path/"model_runner.log").open("w") as log:
                process = subprocess.run([sys.executable, "build_bdam_simulation.py", "ModelInput",
                                          "--staging-root", str(attempt_path/"staging")],
                                         cwd=path, env=env, stdout=log, stderr=subprocess.STDOUT,
                                         **({"pass_fds": lock_fds()} if os.name == "posix" else {}))
            if process.returncode:
                raise RuntimeError(f"Model exited {process.returncode}; inspect {attempt_path}")
            records = validate_results(path)
            if retention == "compact":
                compact(path)
            completion = dict(fingerprint=provenance["fingerprint"], status="pass", retention=retention,
                              elapsed_seconds=time.monotonic()-start, workspaces=records,
                              result_hashes=result_hashes(path))
            write(path/"completion.json", completion)
            write(path/"status.json", dict(id=member["id"], status="pass", elapsed_seconds=completion["elapsed_seconds"]))
            return dict(id=member["id"], status="pass")
        except Exception as exc:
            status = dict(id=member["id"], status="failed", error=str(exc))
            write(path/"status.json", status)
            return status


def collect(manifest):
    root = Path(manifest["root"])
    with lock(root/"locks"/"collect.lock", blocking=True):
        index, summaries = [], []
        for member in manifest["members"]:
            path = Path(member["path"])
            config = read(path/"resolved_config.json")
            row = dict(member_id=member["id"], baseline=member["baseline"], output_path=str(path), status="pending")
            if (path/"status.json").exists():
                row.update({k: v for k, v in read(path/"status.json").items() if k != "id"})
            if (path/"completion.json").exists() and complete(path, member["fingerprint"]):
                row.update(status="pass", elapsed_seconds=read(path/"completion.json")["elapsed_seconds"])
                for summary in sorted((path/"Runs").glob("*_summary.csv")):
                    with summary.open(newline="") as stream:
                        for result in csv.DictReader(stream):
                            summaries.append(dict(member_id=member["id"], summary=summary.name,
                                                  **{f"parameter.{key}": get(config, key) for key in manifest["axes"]}, **result))
            elif row["status"] == "pass":
                row.update(status="invalid", error="Completion validation failed.")
            row.update({f"parameter.{key}": get(config, key) for key in manifest["axes"]})
            row["resolved_config"] = json.dumps(config, sort_keys=True)
            index.append(row)
        for name, rows in (("member_index.csv", index), ("ensemble_summary.csv", summaries)):
            fields = list(dict.fromkeys(key for row in rows for key in row)) or ["member_id", "status"]
            temporary = root/(name+".tmp")
            with temporary.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            temporary.replace(root/name)
        return index


def run(manifest_path, retention="full", reuse_baseline=None):
    manifest = read(manifest_path)
    local_path(manifest["root"])
    integer(manifest["n_parallel_runs"], "n_parallel_runs")
    if not manifest["members"]:
        collect(manifest)
        return 0
    prepare(manifest_path)
    with ThreadPoolExecutor(max_workers=manifest["n_parallel_runs"]) as workers:
        results = list(workers.map(lambda member: run_member(manifest, member, retention, reuse_baseline), manifest["members"]))
    index = collect(manifest)
    print(json.dumps(results, indent=2), flush=True)
    return 1 if any(row["status"] in ("failed", "invalid") for row in index) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan")
    planner.add_argument("request", type=Path); planner.add_argument("root", type=Path)
    planner.add_argument("--source", type=Path, default=HERE)
    planner.add_argument("--skip-baseline", action="store_true")
    runner = commands.add_parser("run")
    runner.add_argument("manifest", type=Path)
    runner.add_argument("--retention", choices=("full", "compact"), default="full")
    runner.add_argument("--reuse-baseline", type=Path)
    stamper = commands.add_parser("mark-prepared"); stamper.add_argument("path", type=Path)
    preparer = commands.add_parser("prepare"); preparer.add_argument("manifest", type=Path)
    collector = commands.add_parser("collect"); collector.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        plan(args.request, args.root, args.source, args.skip_baseline)
    elif args.command == "mark-prepared":
        mark_prepared(args.path)
    elif args.command == "prepare":
        prepare(args.manifest)
    elif args.command == "collect":
        collect(read(args.manifest))
    else:
        sys.exit(run(args.manifest, args.retention, args.reuse_baseline))


if __name__ == "__main__":
    main()
