"""Validated model execution, provenance, and cross-process capacity locks."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
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
import uuid

try:
    import fcntl
except ImportError:  # Windows single-run compatibility; campaign locks use msvcrt.
    fcntl = None
    import msvcrt
import numpy as np
import bdam_spinup as spinup

HERE = Path(__file__).resolve().parent
_LOCK_STATE = threading.local()


def lock_fds():
    inherited = [int(fd) for fd in os.environ.get("BDAM_INHERITED_LOCK_FDS", "").split(",") if fd]
    return tuple(inherited + getattr(_LOCK_STATE, "fds", []))


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
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
    if config.get("groundwater_boundary_k_m_per_day") is None or config["groundwater_boundary_k_m_per_day"] == []:
        config["groundwater_boundary_k_m_per_day"] = config["K_constant"]
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
    spinup.settings(mf)
    for name in ("fall_average_spinup_years", "monthly_spinup_years", "weekly_spinup_years", "pre_dam_years", "post_dam_years"):
        integer(mf[name], f"mf6_parameters.{name}", 0)
    if mf["pre_dam_years"]+mf["post_dam_years"] == 0:
        raise ValueError("At least one monitored year is required.")
    for name in ("uzf_ntrailwaves", "uzf_nwavesets"):
        integer(mf[name], f"mf6_parameters.{name}")
    integer(config["channel_half_width_cells"], "channel_half_width_cells", 0)
    integer(dam["leakage_half_width_cells"], "dam_settings.leakage_half_width_cells", 0)
    integer(dam["leakage_n_top_layers"], "dam_settings.leakage_n_top_layers")
    integer(dam["leakage_halo_cells"], "dam_settings.leakage_halo_cells", 0)
    if dam["leakage_halo_cells"] not in (0,1):
        raise ValueError("dam_settings.leakage_halo_cells must be 0 or 1.")
    integer(dam["stage_table_rows"], "dam_settings.stage_table_rows", 3)
    if dam["leakage_n_top_layers"] > config["n_layers"]:
        raise ValueError("Dam leakage layer count exceeds n_layers.")
    positive = ("model_bottom_offset", "K_constant", "K33_constant", "specific_storage", "lakebed_thickness_m",
                "lakebed_vertical_k_m_per_day", "groundwater_boundary_k_m_per_day", "groundwater_boundary_resistance_in_domain_lengths",
                 "post_dam_weir_width_m")
    for name in positive:
        if config[name] <= 0:
            raise ValueError(f"{name} must be positive.")
    if "k_multiplier" in dam or "k33_multiplier" in dam:
        raise ValueError("Obsolete conductivity multiplier; use dam_settings.under_dam_k_m_per_day.")
    for name in ("under_dam_k_m_per_day","max_lake_extent_height_above_weir_m"):
        value=dam[name]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError(f"dam_settings.{name} must be a finite positive scalar.")
    if dam["dam_line_sample_spacing_m"] not in (None,[]) and dam["dam_line_sample_spacing_m"] <= 0:
        raise ValueError("Dam sample spacing must be positive or automatic.")
    if config["longitudinal_direction"] not in ("x","y"):
        raise ValueError("longitudinal_direction must be x or y.")
    if config["hydraulic_conductivity_mode"] not in ("constant","by_layer","hydrofacies_points"):
        raise ValueError("Unknown hydraulic conductivity mode.")
    if mf["uzf_eps"] <= 0 or not mf["uzf_thtr"] <= mf["uzf_extwc"] <= mf["uzf_thts"]:
        raise ValueError("Invalid UZF exponent or ET water content.")
    if config.get("groundwater_boundary_mode", "drain") not in ("drain", "constant_ghb"):
        raise ValueError("Unknown groundwater boundary mode.")
    for name in ("drain_elevation_above_outlet_bed_m", "constant_ghb_head_above_outlet_bed_m", "external_outlet_height_above_bed_m"):
        if not math.isfinite(config[name]) or (name == "external_outlet_height_above_bed_m" and config[name] < 0):
            raise ValueError(f"{name} must be finite; surface outlet height must be nonnegative.")
    for edge in ("x_min", "x_max", "y_max"):
        value = config["groundwater_edge_flux"][f"{edge}_m3_per_day"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"groundwater_edge_flux.{edge}_m3_per_day must be a finite scalar.")
    river = config["river_settings"]
    integer(river["downstream_segments"], "river_settings.downstream_segments")
    for name, value in river.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"river_settings.{name} must be finite and positive.")
    if config["layer_growth_factor"] < 1:
        raise ValueError("layer_growth_factor must be >= 1.")
    if not 0 <= config["specific_yield"] <= 1 or not 0 < config["effective_porosity"] <= 1:
        raise ValueError("Invalid yield or effective porosity.")
    if not (0 <= mf["uzf_thtr"] < mf["uzf_thts"] <= 1 and mf["uzf_thtr"] <= mf["uzf_thti"] <= mf["uzf_thts"]):
        raise ValueError("Require thtr < thts and thti between the residual and saturated water contents.")
    for name in ("initial_head_channel_offset_m", "uzf_surfdep_m", "uzf_extdp_m", "uzf_extwc"):
        if mf[name] < 0:
            raise ValueError(f"mf6_parameters.{name} must be nonnegative.")
    for name in ("synthetic_mean_streamflow_m3_per_day", "synthetic_mean_land_et_m_per_day",
                 "synthetic_recharge_fraction_of_precipitation", "synthetic_lake_evaporation_fraction_of_land_et"):
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
    if "matlab_runtime" in provenance:
        from bdam import matlab_runtime
        expected = provenance["matlab_runtime"]
        if matlab_runtime(expected["executable"] if expected else "matlab") != expected:
            raise ValueError("MATLAB runtime changed.")
    return provenance


def prepare(manifest_path, matlab="matlab"):
    manifest = read(manifest_path)
    # One serial MATLAB session, even when several schedulers/agents are active.
    with lock(Path(manifest["root"])/"locks"/"prepare.lock", blocking=True):
        if all((Path(m["path"])/"prepared.json").exists() for m in manifest["members"]):
            return
        for member in manifest["members"]:
            verify_snapshot(member["path"])
        for member in manifest["members"]:
            path = Path(member["path"])
            if (path/"prepared.json").exists():
                continue
            artifacts = [p for p in (path/"Geometry",path/"ModelInput",path/"status.json",path/"forcing_request.json",path/"forcing_diagnostics.json") if p.exists()]
            if artifacts:
                attempts = path/"preparation-attempts"
                attempts.mkdir(exist_ok=True)
                archive = attempts/f"attempt-{len(list(attempts.iterdir()))+1:03d}"
                archive.mkdir()
                for artifact in artifacts:
                    if artifact.is_dir():
                        shutil.copytree(artifact,archive/artifact.name)
                    else:
                        shutil.copy2(artifact,archive/artifact.name)
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
    files = [p for folder in ("ModelInput", "Geometry") for p in (path/folder).rglob("*") if p.is_file()]
    if not all((path/"ModelInput"/phase/"preparation_handoff.h5").is_file() for phase in ("pre_dam","post_dam")):
        raise ValueError("Both scenario handoffs must be prepared.")
    write(path/"prepared.json", dict(fingerprint=provenance["fingerprint"],
          handoff_hashes={str(p.relative_to(path)):file_hash(p) for p in files}))


def expected_workspaces(path):
    config = read(Path(path)/"resolved_config.json")
    mf = config["mf6_parameters"]
    fall, monthly, weekly = (mf[n] for n in ("fall_average_spinup_years", "monthly_spinup_years", "weekly_spinup_years"))
    convergence = spinup.settings(mf)
    adaptive = convergence['spinup_until_converged']
    if adaptive:
        weekly = 0
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
    if adaptive:
        report = spinup.validate_report(Path(path)/'Runs', convergence)
        result.extend((relative, 'pre_dam', 365., 52) for relative in report['weekly_workspaces'])
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
    convergence = spinup.settings(config['mf6_parameters'])
    if convergence['spinup_until_converged']:
        report = spinup.validate_report(path/'Runs', convergence)
        spinup.validate_states(report, load_handoff(path/'ModelInput/pre_dam/preparation_handoff.h5'), states)
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
    prepared = read(path/"prepared.json")
    for relative, checksum in prepared["handoff_hashes"].items():
        if file_hash(path/relative) != checksum:
            return False
    if info["retention"] == "full":
        validate_results(path, save_restart=False)
    else:
        with np.load(path/"Runs"/"restart_states.npz") as states:
            if not states.files or any(not np.all(np.isfinite(states[name])) for name in states.files):
                return False
            convergence = spinup.settings(read(path/'resolved_config.json')['mf6_parameters'])
            if convergence['spinup_until_converged']:
                from build_bdam_simulation import load_handoff
                report = spinup.validate_report(path/'Runs', convergence)
                spinup.validate_states(report, load_handoff(path/'ModelInput/pre_dam/preparation_handoff.h5'), states)
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


def run_member(manifest, member, retention="full"):
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
            if waited and (path/"status.json").exists() and read(path/"status.json").get("status") in ("failed", "DNC"):
                return read(path/"status.json")
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
            if (path/'completion.json').exists():
                shutil.move(path/'completion.json', attempt_path/'prior_completion.json')
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
            if process.returncode == spinup.DNC_EXIT_CODE:
                convergence = spinup.settings(read(path/'resolved_config.json')['mf6_parameters'])
                if not convergence['spinup_until_converged']:
                    raise RuntimeError('Unexpected DNC exit from fixed spinup.')
                report = spinup.validate_report(path/'Runs', convergence, require_converged=False)
                if report['outcome'] != 'DNC':
                    raise RuntimeError('DNC exit without a matching convergence report.')
                status = dict(id=member['id'], status='DNC', phase='spinup',
                              error=f"DNC (did not converge) after {report['years_completed']} weekly years; inspect {attempt_path}",
                              elapsed_seconds=time.monotonic()-start)
                write(path/'status.json', status)
                return status
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Internal preparation receipt writer.")
    parser.add_argument("command", choices=("mark-prepared",))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    mark_prepared(args.path)
