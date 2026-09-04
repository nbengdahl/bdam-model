#!/usr/bin/env python3
"""Build and run MODFLOW 6 BDA simulations from the MATLAB HDF5 handoff.

The only accepted physical-input interface is ExportPreparationForFloPy.m.
All MATLAB [x, y, layer] arrays are converted here, once, to MF6
[layer, row (north-to-south), column].
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import h5py
import numpy as np
import flopy

SCHEMA = "bdam-preparation-hdf5-v4"
REQUIRED_BINARY_OUTPUTS = (
    "bdam.hds", "bdam.cbc", "bdam.lak.stage", "bdam.lak.bud",
    "bdam.uzf.wc", "bdam.uzf.bud",
)
MONITORING_OUTPUTS = (
    "bdam.heads.csv", "bdam.lake_fluxes.csv", "bdam.ghb_flux.csv",
)
FLUX_OUTPUT = "bdam.fluxes.csv"
SOLVER_OUTER_OUTPUT = "bdam.solver.outer.csv"
SOLVER_INNER_OUTPUT = "bdam.solver.inner.csv"
SOLVER_STATS_OUTPUT = "bdam.solver_stats.json"
SOLVER_PROFILES = {
    "balanced": "MODERATE",
    "conservative": "COMPLEX",
}


@dataclass
class Handoff:
    path: Path
    manifest: dict

    def array(self, path: str, dtype=float) -> np.ndarray:
        with h5py.File(self.path, "r") as h5:
            if f"{path}/data" not in h5 or f"{path}/shape" not in h5:
                raise ValueError(f"Missing required handoff dataset: {path}")
            flat = np.asarray(h5[f"{path}/data"]).ravel()
            shape = tuple(np.asarray(h5[f"{path}/shape"]).astype(int).ravel())
        return np.asarray(flat, dtype=dtype).reshape(shape, order="F")

    def scalar(self, path: str) -> float:
        return float(self.array(path).ravel()[0])


@dataclass
class RuntimeSchedule:
    """Calendar and forcing override used by multi-year validation runs."""

    perlen_days: np.ndarray
    nstp: np.ndarray
    time_days: np.ndarray
    forcing: dict[str, np.ndarray]
    downstream_control_stage_m: np.ndarray
    ghb_reference_head_m: np.ndarray


@dataclass
class SpinupStep:
    """Summary labels for one completed step in the staged spinup schedule."""

    phase: str
    stage: str
    stage_year: int
    stage_time_days: float


def _solver_settings(profile: str, save_inner_iterations: bool = False,
                     robust_initialization: bool = False) -> dict:
    """Return the explicit, reproducible IMS settings for a solver profile."""
    try:
        complexity = SOLVER_PROFILES[profile]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported solver profile {profile!r}; choose from {sorted(SOLVER_PROFILES)}."
        ) from exc
    settings = {
        "complexity": complexity,
        "outer_dvclose": 1.0e-5,
        "inner_dvclose": 1.0e-6,
        "rcloserecord": "1e-6 strict",
        "linear_acceleration": "BICGSTAB",
        "csv_outer_output_filerecord": SOLVER_OUTER_OUTPUT,
    }
    if profile == "balanced" and robust_initialization:
        # The first solve starts from an analytical state and may include a
        # long fall-average spinup step. The packaged default requires the
        # robust COMPLEX preset there. Restarted annual solves use the faster
        # MODERATE preset; no physical input or closure tolerance changes.
        settings["complexity"] = "COMPLEX"
    if save_inner_iterations:
        settings["csv_inner_output_filerecord"] = SOLVER_INNER_OUTPUT
    return settings


def _positive_integer(value: float, name: str) -> int:
    """Validate numerical-capacity inputs read from the numeric HDF5 schema."""
    if not np.isfinite(value) or value <= 0 or value != int(value):
        raise ValueError(f"{name} must be a positive integer; received {value!r}.")
    return int(value)


def _validate_calendar(perlen: np.ndarray, nstp: np.ndarray, resolution: str) -> None:
    """Enforce the BDam release's annual daily/weekly calendar."""
    perlen = np.asarray(perlen, dtype=float).ravel()
    nstp = np.asarray(nstp, dtype=int).ravel()
    expected_periods = 365 if resolution == "daily" else 52 if resolution == "weekly" else None
    if expected_periods is None:
        raise ValueError(f"Unsupported time resolution: {resolution!r}")
    if len(perlen) != expected_periods or len(nstp) != expected_periods:
        raise ValueError(f"{resolution.capitalize()} mode requires exactly {expected_periods} stress periods.")
    if np.any(~np.isfinite(perlen)) or np.any(perlen <= 0.0) or np.any(nstp != 1):
        raise ValueError("Every forcing period must be positive and contain exactly one MF6 time step.")
    expected_lengths = np.ones(365) if resolution == "daily" else np.full(52, 365.0 / 52.0)
    if not np.allclose(perlen, expected_lengths, atol=1.0e-12, rtol=0.0):
        raise ValueError(f"{resolution.capitalize()} stress-period lengths do not match one model year.")


def _duration_weighted_period_means(
    source_edges: np.ndarray, source_rates: np.ndarray, target_edges: np.ndarray,
) -> np.ndarray:
    """Aggregate piecewise-constant rates without changing integrated volume."""
    source_edges = np.asarray(source_edges, dtype=float).ravel()
    source_rates = np.asarray(source_rates, dtype=float).ravel()
    target_edges = np.asarray(target_edges, dtype=float).ravel()
    if len(source_edges) != len(source_rates) + 1 or np.any(np.diff(source_edges) <= 0.0):
        raise ValueError("Source edges and rates are inconsistent.")
    if len(target_edges) < 2 or np.any(np.diff(target_edges) <= 0.0):
        raise ValueError("Target edges must be strictly increasing.")
    totals = np.zeros(len(target_edges) - 1, dtype=float)
    for target, (left, right) in enumerate(zip(target_edges[:-1], target_edges[1:])):
        first = max(0, int(np.searchsorted(source_edges, left, side="right") - 1))
        last = min(len(source_rates), int(np.searchsorted(source_edges, right, side="left") + 1))
        for source in range(first, last):
            overlap = max(0.0, min(right, source_edges[source + 1]) - max(left, source_edges[source]))
            totals[target] += source_rates[source] * overlap
    return totals / np.diff(target_edges)


def _resample_period_values(source_edges: np.ndarray, endpoint_values: np.ndarray,
                            target_edges: np.ndarray) -> np.ndarray:
    """Resample stepwise endpoint data and retain only target-period rates."""
    values = np.asarray(endpoint_values, dtype=float).ravel()
    if len(values) != len(source_edges):
        raise ValueError("Endpoint values do not match their source time edges.")
    return _duration_weighted_period_means(source_edges, values[:-1], target_edges)


def _fall_average_period_values(source_edges: np.ndarray,
                                endpoint_values: np.ndarray) -> float:
    """Return the simple mean of September, October, and November values."""
    month_lengths = np.asarray(
        [31, 30, 31, 31, 28, 31, 30, 31, 30, 31, 31, 30], dtype=float)
    month_edges = np.concatenate(([0.0], np.cumsum(month_lengths)))
    monthly = _resample_period_values(source_edges, endpoint_values, month_edges)
    # Monthly arrays are October--September; select Sep, Oct, Nov in that order.
    return float(np.mean(monthly[[11, 0, 1]]))


def _fall_average_forcing_schedule(handoff: Handoff, duration_days: float) -> RuntimeSchedule:
    """Build one transient period driven by September--November means."""
    if not np.isfinite(duration_days) or duration_days <= 0.0:
        raise ValueError("Fall-average relaxation duration must be positive and finite.")
    source_perlen = handoff.array("/calendar/perlen_days").ravel()
    source_edges = np.concatenate(([0.0], np.cumsum(source_perlen)))
    forcing_names = (
        "upstream_inflow_m3_per_day", "land_recharge_m_per_day", "land_et_m_per_day",
        "lake_precipitation_m_per_day", "lake_evaporation_m_per_day",
    )
    forcing = {
        name: _fall_average_period_values(
            source_edges, handoff.array(f"/forcing/{name}").ravel())
        for name in forcing_names
    }
    downstream = _fall_average_period_values(
        source_edges, handoff.array("/boundaries/downstream_control_stage_m").ravel())
    source_ghb = handoff.array("/boundaries/ghb/reference_head_m")
    if source_ghb.ndim != 2 or source_ghb.shape[1] != len(source_perlen) + 1:
        raise ValueError("GHB endpoint series does not match the source calendar.")
    ghb = np.asarray([
        _fall_average_period_values(source_edges, row) for row in source_ghb
    ], dtype=float)
    return RuntimeSchedule(
        perlen_days=np.asarray([duration_days], dtype=float),
        nstp=np.ones(1, dtype=int),
        time_days=np.asarray([0.0, duration_days], dtype=float),
        forcing={name: np.repeat(value, 2) for name, value in forcing.items()},
        downstream_control_stage_m=np.repeat(downstream, 2),
        ghb_reference_head_m=np.repeat(ghb[:, np.newaxis], 2, axis=1),
    )


def _staged_spinup_schedule(handoff: Handoff, counts: dict[str, int]) -> tuple[RuntimeSchedule, list[SpinupStep]]:
    """Build one continuous fall-average -> monthly -> weekly transient schedule."""
    source_perlen = handoff.array("/calendar/perlen_days").ravel()
    source_edges = np.concatenate(([0.0], np.cumsum(source_perlen)))
    source_time = handoff.array("/forcing/time_days").ravel()
    if len(source_time) != len(source_edges) or not np.allclose(source_time, source_edges, atol=1.0e-10, rtol=0.0):
        raise ValueError("Exported forcing times do not match the source calendar.")
    forcing_names = (
        "upstream_inflow_m3_per_day", "land_recharge_m_per_day", "land_et_m_per_day",
        "lake_precipitation_m_per_day", "lake_evaporation_m_per_day",
    )
    source_forcing = {name: handoff.array(f"/forcing/{name}").ravel() for name in forcing_names}
    source_downstream = handoff.array("/boundaries/downstream_control_stage_m").ravel()
    source_ghb = handoff.array("/boundaries/ghb/reference_head_m")
    if source_ghb.ndim != 2 or source_ghb.shape[1] != len(source_edges):
        raise ValueError("GHB endpoint series does not match the source calendar.")

    # Model time begins on October 1. These are October--September month
    # lengths; source series have already been circularly shifted by MATLAB.
    month_lengths = np.asarray([31, 30, 31, 31, 28, 31, 30, 31, 30, 31, 31, 30], dtype=float)
    month_edges = np.concatenate(([0.0], np.cumsum(month_lengths)))
    week_edges = np.linspace(0.0, 365.0, 53)
    monthly_forcing = {
        name: _resample_period_values(source_edges, values, month_edges)
        for name, values in source_forcing.items()
    }
    weekly_forcing = {
        name: _resample_period_values(source_edges, values, week_edges)
        for name, values in source_forcing.items()
    }
    monthly_downstream = _resample_period_values(source_edges, source_downstream, month_edges)
    weekly_downstream = _resample_period_values(source_edges, source_downstream, week_edges)
    monthly_ghb = np.vstack([
        _resample_period_values(source_edges, row, month_edges) for row in source_ghb
    ])
    weekly_ghb = np.vstack([
        _resample_period_values(source_edges, row, week_edges) for row in source_ghb
    ])

    perlen_parts: list[np.ndarray] = []
    forcing_parts = {name: [] for name in forcing_names}
    downstream_parts: list[np.ndarray] = []
    ghb_parts: list[np.ndarray] = []
    metadata: list[SpinupStep] = []

    def append_year(stage: str, phase: str, year: int, perlen: np.ndarray,
                    forcing_rates: dict[str, np.ndarray], downstream: np.ndarray,
                    ghb: np.ndarray) -> None:
        perlen = np.asarray(perlen, dtype=float)
        perlen_parts.append(perlen)
        for name in forcing_names:
            forcing_parts[name].append(np.asarray(forcing_rates[name], dtype=float))
        downstream_parts.append(np.asarray(downstream, dtype=float))
        ghb_parts.append(np.asarray(ghb, dtype=float))
        for endpoint in np.cumsum(perlen):
            metadata.append(SpinupStep(phase, stage, year, float((year - 1) * 365.0 + endpoint)))

    fall_months = [11, 0, 1]  # September, October, November in Oct--Sep order.
    fall_forcing = {
        name: np.asarray([float(np.mean(values[fall_months]))])
        for name, values in monthly_forcing.items()
    }
    fall_downstream = np.asarray([float(np.mean(monthly_downstream[fall_months]))])
    fall_ghb = np.mean(monthly_ghb[:, fall_months], axis=1, keepdims=True)
    for year in range(1, counts["fall_average_spinup_years"] + 1):
        append_year("fall_average", "spinup_fall_average", year, np.asarray([365.0]),
                    fall_forcing, fall_downstream, fall_ghb)
    for year in range(1, counts["monthly_spinup_years"] + 1):
        append_year("monthly", "spinup_monthly", year, month_lengths,
                    monthly_forcing, monthly_downstream, monthly_ghb)
    weekly_lengths = np.diff(week_edges)
    for year in range(1, counts["weekly_spinup_years"] + 1):
        append_year("weekly", "spinup_weekly", year, weekly_lengths,
                    weekly_forcing, weekly_downstream, weekly_ghb)
    if not metadata:
        raise ValueError("A staged spinup schedule requires at least one configured spinup year.")

    perlen = np.concatenate(perlen_parts)
    rates = {name: np.concatenate(parts) for name, parts in forcing_parts.items()}
    downstream = np.concatenate(downstream_parts)
    ghb = np.concatenate(ghb_parts, axis=1)
    time = np.concatenate(([0.0], np.cumsum(perlen)))
    schedule = RuntimeSchedule(
        perlen_days=perlen,
        nstp=np.ones(len(perlen), dtype=int),
        time_days=time,
        forcing={name: np.concatenate((values, values[-1:])) for name, values in rates.items()},
        downstream_control_stage_m=np.concatenate((downstream, downstream[-1:])),
        ghb_reference_head_m=np.concatenate((ghb, ghb[:, -1:]), axis=1),
    )
    if len(metadata) != len(perlen) or not np.isclose(np.sum(perlen), 365.0 * sum(counts.values())):
        raise RuntimeError("Staged spinup schedule dimensions or total duration are inconsistent.")
    return schedule, metadata


def load_handoff(h5_path: Path) -> Handoff:
    manifest_path = h5_path.with_name("preparation_manifest.json")
    if not h5_path.is_file():
        raise FileNotFoundError(f"HDF5 handoff does not exist: {h5_path}")
    # The JSON is optional human-readable provenance. Runtime metadata lives
    # in HDF5 root attributes so this file is the sole converter input.
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
    else:
        with h5py.File(h5_path, "r") as h5:
            def attribute_text(value):
                if isinstance(value, np.ndarray):
                    value = value.ravel()[0]
                return value.decode() if hasattr(value, "decode") else str(value)
            manifest = {key: attribute_text(value) for key, value in h5.attrs.items()}
            if "monitoring_head_point_names_json" in manifest:
                manifest["monitoring_head_point_names"] = json.loads(manifest.pop("monitoring_head_point_names_json"))
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError(f"Unsupported handoff schema: {manifest.get('schema_version')!r}")
    if manifest.get("units") != "meters and days":
        raise ValueError("FloPy conversion requires the verified meters-and-days handoff.")
    return Handoff(h5_path, manifest)


def mf2(array: np.ndarray) -> np.ndarray:
    """Convert MATLAB [x,y] to MF6 [row north->south,column x]."""
    return np.flip(np.asarray(array).T, axis=0)


def mf3(array: np.ndarray) -> np.ndarray:
    """Convert MATLAB [x,y,layer bottom->top] to MF6 [layer top->bottom,row,col]."""
    return np.flip(np.transpose(np.asarray(array), (2, 1, 0)), axis=1)[::-1, :, :]


def mf_cell(native_layer: int, ix: int, iy: int, nlay: int, nrow: int) -> tuple[int, int, int]:
    return nlay - int(native_layer), nrow - int(iy), int(ix) - 1


def _mf6_executable() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "bin" / "mf6"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Could not locate the project bin/mf6 executable.")


def _required(h: Handoff) -> None:
    for path in (
        "/grid/X", "/grid/Y", "/grid/ZTop", "/grid/Z", "/properties/K", "/properties/K33",
        "/properties/K_background", "/properties/K33_background", "/properties/Porosity", "/calendar/perlen_days",
        "/forcing/time_days", "/boundaries/ghb/reference_head_m", "/uzf/eligible_mask",
        "/atmosphere/land_uzf_mask", "/atmosphere/lake_lak_mask",
        "/mf6_parameters/uzf_thtr", "/mf6_parameters/uzf_ntrailwaves",
        "/mf6_parameters/uzf_nwavesets", "/monitoring/head_points_requested_xy_layer",
        "/mf6_parameters/initial_head_channel_offset_m",
        "/mf6_parameters/initial_head_lateral_gradient_m_per_m",
        "/mf6_parameters/initial_head_upslope_reduction_m_per_m",
        "/monitoring/head_points_resolved_i_x", "/monitoring/head_points_resolved_i_y",
        "/monitoring/head_points_resolved_layer_top_down", "/monitoring/head_points_resolved_xy",
        "/validation_zones/upstream_mask", "/validation_zones/downstream_mask",
        "/validation_zones/dam_endpoint_1_xy", "/validation_zones/dam_endpoint_2_xy",
        "/surface_water/channel_mask",
    ):
        h.array(path)


def uzf_cells(handoff: Handoff) -> list[tuple[int, int, int]]:
    """Return UZF feature cells in the exact order used by packagedata."""
    top = mf2(handoff.array("/grid/ZTop"))
    nrow, ncol = top.shape
    eligible = mf3(handoff.array("/uzf/eligible_mask", bool))
    return [(lay, row, col) for row in range(nrow) for col in range(ncol)
            for lay in range(eligible.shape[0]) if eligible[lay, row, col]]


def _lake_data(h: Handoff, nlay: int, nrow: int) -> list[dict]:
    lakes: list[dict] = []
    for number in range(1, int(h.scalar("/surface_water/n_lakes")) + 1):
        base = f"/surface_water/lakes/lake_{number}"
        ix = h.array(f"{base}/connection_i_x", int).ravel()
        iy = h.array(f"{base}/connection_i_y", int).ravel()
        native = h.array(f"{base}/connection_layer_native", int).ravel()
        if not (len(ix) == len(iy) == len(native)):
            raise ValueError(f"Lake {number} connection arrays have inconsistent lengths.")
        stage = h.scalar(f"{base}/initial_stage_m")
        table = None
        if int(h.scalar(f"{base}/has_stage_area_volume")):
            table = np.column_stack((
                h.array(f"{base}/stage_area_volume/stage_m").ravel(),
                h.array(f"{base}/stage_area_volume/volume_m3").ravel(),
                h.array(f"{base}/stage_area_volume/area_m2").ravel(),
            ))
            if not (np.all(np.diff(table[:, 0]) > 0) and table[0, 0] <= stage <= table[-1, 0]):
                raise ValueError(f"Lake {number} stage-area-volume table does not bracket its initial stage.")
        lakes.append({
            "number": number, "stage": stage, "cells": [mf_cell(k, x, y, nlay, nrow) for x, y, k in zip(ix, iy, native)],
            "bed_leakance": h.scalar(f"{base}/lakebed_vertical_k_m_per_day") / h.scalar(f"{base}/lakebed_thickness_m"),
            "table": table,
        })
    return lakes


def _validate_lake_topology(h: Handoff, lakes: list[dict], top: np.ndarray) -> dict:
    """Reject ambiguous or physically misplaced LAK--GWF connections."""
    seen: dict[tuple[int, int, int], int] = {}
    dry_counts: list[int] = []
    for lake in lakes:
        cells = lake["cells"]
        if len(cells) != len(set(cells)):
            raise ValueError(f"Lake {lake['number']} contains duplicate groundwater connections.")
        for cell in cells:
            if cell in seen:
                raise ValueError(
                    f"Groundwater cell {cell} is connected vertically to lakes "
                    f"{seen[cell]} and {lake['number']}."
                )
            seen[cell] = lake["number"]
        elevations = np.array([top[row, col] for _, row, col in cells])
        if not np.any(elevations <= lake["stage"]):
            raise ValueError(f"Lake {lake['number']} has no cells wetted at its initial stage.")
        dry_counts.append(int(np.count_nonzero(elevations > lake["stage"])))
    if h.manifest["scenario"] == "post_dam":
        if len(lakes) != 2:
            raise ValueError("Post-dam handoff must contain exactly two lakes.")
        downstream_row = 0 if float(np.mean(top[0])) <= float(np.mean(top[-1])) else top.shape[0] - 1
        if not any(row == downstream_row for _, row, _ in lakes[1]["cells"]):
            raise ValueError("Downstream lake does not connect to the low-elevation downstream model edge.")
    return {"unique_lake_connections": len(seen), "dry_fixed_footprint_cells": dry_counts}


def _monitoring(h: Handoff, nlay: int, nrow: int, ncol: int, workspace: Path) -> list[tuple[str, tuple[int, int, int]]]:
    requested = h.array("/monitoring/head_points_requested_xy_layer")
    ix = h.array("/monitoring/head_points_resolved_i_x", int).ravel()
    iy = h.array("/monitoring/head_points_resolved_i_y", int).ravel()
    layer = h.array("/monitoring/head_points_resolved_layer_top_down", int).ravel()
    resolved_xy = h.array("/monitoring/head_points_resolved_xy")
    if requested.ndim != 2 or requested.shape[1] != 3 or resolved_xy.shape != (len(ix), 2) or \
            not (len(ix) == len(iy) == len(layer) == len(requested)):
        raise ValueError("Invalid exported head-monitor configuration.")
    names = h.manifest.get("monitoring_head_point_names", [])
    if len(names) != len(ix):
        names = [f"head_{i + 1:02d}" for i in range(len(ix))]
    records: list[tuple[str, tuple[int, int, int]]] = []
    rows = []
    for name, x, y, lay, xy, request in zip(names, ix, iy, layer, resolved_xy, requested):
        if not (1 <= x <= ncol and 1 <= y <= nrow and 1 <= lay <= nlay):
            raise ValueError(f"Head monitor {name!r} resolves outside the MF6 grid.")
        safe_name = str(name).strip().replace(" ", "_")
        cell = (int(lay) - 1, nrow - int(y), int(x) - 1)
        records.append((safe_name, cell))
        rows.append([safe_name, *request, int(x), int(y), int(lay), *xy, *cell])
    with (workspace / "monitoring_targets.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "requested_x_m", "requested_y_m", "requested_layer_top_down", "resolved_i_x", "resolved_i_y", "resolved_layer_top_down", "resolved_x_m", "resolved_y_m", "mf6_layer_zero_based", "mf6_row_zero_based", "mf6_column_zero_based"])
        writer.writerows(rows)
    (workspace / "monitoring_README.md").write_text(
        "# Monitoring outputs\n\n"
        "- `bdam.heads.csv` contains simulated groundwater heads in meters at the targets in `monitoring_targets.csv`.\n"
        "- `bdam.lake_fluxes.csv` contains MF6 LAK observations. Rates are m3/day except `stage` (m), `volume` (m3), rainfall/evaporation (m/day), and `surface-area` (m2, if added later).\n"
        "- Positive/negative signs are MF6's native conventions; `outlet1_flow` is the native LAK-to-LAK transfer in the post-dam model and the external outlet in the pre-dam model.\n"
        "- `bdam.ghb_flux.csv` reports total downstream GHB exchange.\n"
        "- `bdam.fluxes.csv` contains coupled external inflow/outflow, atmospheric components, combined storage change, coupled residual, the separately named GWF listing totals, signed lake-to-groundwater exchange, and signed groundwater flow across the reference dam line at every saved step. Rates are m3/day and interval volumes are m3.\n"
        "- Coupled inputs are land infiltration, lake precipitation, upstream surface inflow, and positive GHB inflow. Outputs are land ET, rejected infiltration, lake evaporation, external surface outflow/withdrawal, and GHB outflow. Internal LAK--GWF and LAK-to-LAK flow and storage terms are excluded from external totals.\n"
        "- `net_atmospheric_recharge` is infiltration plus lake precipitation minus land ET and lake evaporation. Positive `combined_storage_change` means increasing GWF+UZF+LAK storage; `coupled_mass_residual` is external net inflow minus storage change.\n"
        "- Positive lake exchange is lake-to-groundwater; negative is groundwater-to-lake. Positive cross-dam flow is upstream-to-downstream. Before dam installation, lake1/lake2 denote the upstream/downstream portions of the single river divided at the reference dam line.\n"
        "- `bdam.cbc` and `bdam.water_balance.json` provide machine-readable model-budget accounting.\n"
    )
    return records


def _validate_capped_lake_table(h: Handoff, lakes: list[dict]) -> None:
    if h.manifest["scenario"] != "post_dam":
        return
    cap = h.scalar("/surface_water/dam/maximum_lake_extent_stage_m")
    table = lakes[0]["table"]
    if table is None or not np.any(np.isclose(table[:, 0], cap)):
        raise ValueError("The upstream lake table must include the maximum-footprint stage exactly.")
    cap_row = int(np.where(np.isclose(table[:, 0], cap))[0][0])
    above = table[cap_row:, :]
    if not np.allclose(above[:, 2], above[0, 2]):
        raise ValueError("Lake area must remain constant above the maximum-footprint stage.")
    if len(above) > 1 and not np.allclose(np.diff(above[:, 1]), above[0, 2] * np.diff(above[:, 0])):
        raise ValueError("Lake volume must increase linearly above the maximum-footprint stage.")


def _lake_observations(lakes: list[dict]) -> list[tuple]:
    """Return a complete, compact lake water-balance observation set."""
    records: list[tuple] = []
    for lake in lakes:
        label = f"lake{lake['number']}"
        target = f"lake_{lake['number']}"
        for term in ("stage", "volume", "rainfall", "ext-inflow", "lak", "evaporation", "withdrawal", "storage", "constant"):
            records.append((f"{label}_{term.replace('-', '_')}", term, target))
    # Outlet flow reports the post-dam routed crest transfer or the external
    # discharge, without requesting MF6's DNODATA-only optional subterms.
    for outlet_number in range(1, len(lakes) + 1):
        records.append((f"outlet{outlet_number}_flow", "outlet", outlet_number))
    return records


def _write_tab6(path: Path, table: np.ndarray) -> None:
    with path.open("w") as f:
        f.write("BEGIN DIMENSIONS\n")
        f.write(f"  NROW {len(table)}\n  NCOL 3\nEND DIMENSIONS\nBEGIN TABLE\n")
        for stage, volume, area in table:
            f.write(f"  {stage:.12g} {volume:.12g} {area:.12g}\n")
        f.write("END TABLE\n")


def validate_lak_outlet_routes(lak_path: Path) -> None:
    """Verify the serialized LAK outlet topology before MF6 is started.

    FloPy accepts zero-based lake IDs, while MODFLOW 6 writes one-based IDs
    and uses zero as the external-boundary receiver.  Checking the written
    file prevents a self-routed outlet from becoming a difficult-to-diagnose
    transient convergence failure.
    """
    lines = lak_path.read_text().splitlines()
    try:
        begin = next(i for i, line in enumerate(lines) if line.strip().upper() == "BEGIN OUTLETS")
        end = next(i for i, line in enumerate(lines[begin + 1:], begin + 1)
                   if line.strip().upper() == "END OUTLETS")
    except StopIteration as exc:
        raise ValueError(f"{lak_path}: missing LAK OUTLETS block.") from exc
    actual = []
    for line in lines[begin + 1:end]:
        fields = line.split()
        if len(fields) < 3:
            raise ValueError(f"{lak_path}: malformed LAK outlet record: {line!r}")
        actual.append(tuple(map(int, fields[:3])))
    expected_by_count = {
        1: [(1, 1, 0)],             # pre-dam lake -> external boundary
        2: [(1, 1, 2), (2, 2, 0)], # upstream lake -> downstream lake -> external boundary
    }
    expected = expected_by_count.get(len(actual))
    if expected is None:
        raise ValueError(f"{lak_path}: expected one or two outlets, found {len(actual)}.")
    if actual != expected:
        raise ValueError(f"{lak_path}: invalid LAK outlet routing {actual}; expected {expected}.")


def _ts(package, filename: str, names: list[str], time: np.ndarray, columns: list[np.ndarray]) -> None:
    time = np.asarray(time, dtype=float).ravel()
    if len(time) < 2 or np.any(~np.isfinite(time)) or np.any(np.diff(time) <= 0):
        raise ValueError(f"{filename}: time-series times must be finite and strictly increasing.")
    if any(len(np.asarray(c).ravel()) != len(time) for c in columns):
        raise ValueError(f"{filename}: every time-series column must match the time vector.")
    records = [(float(t), *[float(np.asarray(c).ravel()[i]) for c in columns]) for i, t in enumerate(time)]
    # MF6 accumulates repeating decimal stress-period lengths independently from
    # the MATLAB calendar.  Keep the final STEPWISE value defined a tiny amount
    # beyond the nominal endpoint so roundoff cannot leave the last time step
    # outside the time-series range (notably 365 / 52 weekly periods).
    # FloPy writes TS6 times to eight decimal places, so this must be larger
    # than that printed precision as well as the floating-point accumulation.
    endpoint_pad = max(1.0e-6, abs(float(time[-1])) * 1.0e-12)
    records.append((float(time[-1] + endpoint_pad), *[float(np.asarray(c).ravel()[-1]) for c in columns]))
    flopy.mf6.ModflowUtlts(
        package, filename=filename, time_series_namerecord=names,
        interpolation_methodrecord=["STEPWISE"] * len(names), timeseries=records,
    )


def _print_flux_summary(qa: dict, forcing: dict[str, np.ndarray], perlen: np.ndarray,
                        cell_area: float, lake_count: int) -> None:
    """Report forcing-reference volumes; MF6 budgets remain the accounting source."""
    def volume(name: str, cells: int) -> float:
        return float(np.dot(forcing[name][:-1], perlen) * cell_area * cells)
    print(f"Atmospheric flux QA (transient): UZF land cells={qa['land_cells']}, "
          f"LAK cells={qa['lake_cells']}, UZF atmosphere features={qa['uzf_atmosphere_features']}, "
          f"zero-forcing lake chains={qa['zero_forcing_lake_chains']}, "
          f"LAK rain/evap assignments={lake_count}/{lake_count}")
    print("  Forcing-reference volumes (m3): "
          f"UZF infiltration={volume('land_recharge_m_per_day', qa['land_cells']):.6g}, "
          f"UZF ET={volume('land_et_m_per_day', qa['land_cells']):.6g}, "
          f"LAK precipitation={volume('lake_precipitation_m_per_day', qa['lake_cells']):.6g}, "
          f"LAK evaporation={volume('lake_evaporation_m_per_day', qa['lake_cells']):.6g}")


def _atmospheric_masks(h: Handoff, lakes: list[dict], nrow: int, ncol: int) -> tuple[np.ndarray, np.ndarray]:
    """Validate the exclusive UZF-land / LAK-water atmospheric split."""
    land = mf2(h.array("/atmosphere/land_uzf_mask", bool))
    lake = mf2(h.array("/atmosphere/lake_lak_mask", bool))
    if land.shape != (nrow, ncol) or lake.shape != (nrow, ncol):
        raise ValueError("Atmospheric masks do not match the MF6 grid.")
    if np.any(land & lake) or not np.all(land | lake):
        raise ValueError("Land and lake atmospheric masks must be mutually exclusive and complete.")
    lake_connections = np.zeros((nrow, ncol), dtype=bool)
    for item in lakes:
        for lay, row, col in item["cells"]:
            if lay == 0:
                lake_connections[row, col] = True
    if not np.array_equal(lake, lake_connections):
        raise ValueError("LAK footprints and lake atmospheric mask are inconsistent.")
    return land, lake


def _uzf_records(h: Handoff, nlay: int, nrow: int, ncol: int, k33: np.ndarray,
                 land_mask: np.ndarray, lake_mask: np.ndarray,
                 initial_wc: np.ndarray | None = None) -> tuple[list[tuple], list[tuple], dict]:
    eligible = mf3(h.array("/uzf/eligible_mask", bool))
    if np.any(eligible[0] & lake_mask) or not np.all(eligible[0][land_mask]):
        raise ValueError("Layer-1 UZF eligibility must include every land cell and exclude every lake cell.")
    p = {name: h.scalar(f"/mf6_parameters/{name}") for name in (
        "uzf_surfdep_m", "uzf_thtr", "uzf_thts", "uzf_thti", "uzf_eps", "uzf_extdp_m", "uzf_extwc")}
    if not p["uzf_thtr"] <= p["uzf_thti"] <= p["uzf_thts"] or p["uzf_extwc"] < p["uzf_thtr"]:
        raise ValueError("Invalid UZF water-content parameters in handoff.")
    cells = uzf_cells(h)
    index = {cell: i for i, cell in enumerate(cells)}
    packagedata, perioddata = [], []
    for ifno, (lay, row, col) in enumerate(cells):
        below = index.get((lay + 1, row, col), -1)
        exposed_land = lay == 0 and land_mask[row, col]
        if initial_wc is None:
            thti = p["uzf_thti"]
        else:
            if initial_wc.ndim != 1 or initial_wc.size != len(cells):
                raise ValueError("Spinup UZF water-content state does not match the UZF feature chain.")
            # MF6 reports zero for dry/deactivated UZF feature states.  A
            # restart THTI must remain within the package's physical bounds.
            thti = float(np.clip(initial_wc[ifno], p["uzf_thtr"], p["uzf_thts"]))
        packagedata.append((ifno, (lay, row, col), int(exposed_land), below, p["uzf_surfdep_m"],
                            k33[lay, row, col], p["uzf_thtr"], p["uzf_thts"], thti, p["uzf_eps"]))
        if exposed_land:
            perioddata.append((ifno, "uzf_finf", "uzf_pet", p["uzf_extdp_m"], p["uzf_extwc"], 0.0, 0.0, 0.0))
        else:
            perioddata.append((ifno, 0.0, 0.0, p["uzf_extdp_m"], p["uzf_extwc"], 0.0, 0.0, 0.0))
    first_layer = {}
    for lay, row, col in cells:
        first_layer.setdefault((row, col), lay)
    if any(first_layer[row, col] != 0 for row, col in zip(*np.where(land_mask))):
        raise ValueError("Every exposed land column must start its UZF chain in layer 1.")
    if any(first_layer[row, col] != 1 for row, col in zip(*np.where(lake_mask))):
        raise ValueError("Every lake-footprint UZF chain must start in layer 2.")
    land_atmosphere = sum(1 for item in perioddata if isinstance(item[1], str) and isinstance(item[2], str))
    zero_lake_chain = sum(1 for item in perioddata if item[0] in {
        index[(1, row, col)] for row, col in zip(*np.where(lake_mask))})
    if land_atmosphere != int(np.count_nonzero(land_mask)) or zero_lake_chain != int(np.count_nonzero(lake_mask)):
        raise ValueError("UZF atmospheric assignments do not match the exported land/lake masks.")
    return packagedata, perioddata, {
        "land_cells": int(np.count_nonzero(land_mask)), "lake_cells": int(np.count_nonzero(lake_mask)),
        "uzf_atmosphere_features": land_atmosphere, "zero_forcing_lake_chains": zero_lake_chain,
    }


def build_from_handoff(h5_path: str | Path, workspace: str | Path, scenario: str | None = None,
                       resolution: str | None = None,
                       initial_heads: np.ndarray | None = None, initial_lake_stages: np.ndarray | None = None,
                       initial_uzf_wc: np.ndarray | None = None,
                       runtime_schedule: RuntimeSchedule | None = None,
                       save_monitoring: bool = True, solver_profile: str = "balanced",
                       save_inner_iterations: bool = False,
                       robust_initialization: bool = False) -> flopy.mf6.MFSimulation:
    h = load_handoff(Path(h5_path)); _required(h)
    scenario = scenario or h.manifest["scenario"]
    if scenario != h.manifest["scenario"]:
        raise ValueError("The requested scenario must match the verified handoff scenario.")
    ws = Path(workspace); ws.mkdir(parents=True, exist_ok=True)
    top = mf2(h.array("/grid/ZTop")); z = h.array("/grid/Z")
    ncol, nrow = top.shape[1], top.shape[0]; nlay = z.shape[2] - 1
    botm = mf3(z[:, :, :-1])
    k, k33, sy, ss = (mf3(h.array(p)) for p in ("/properties/K", "/properties/K33", "/properties/Sy", "/properties/Ss"))
    perlen = h.array("/calendar/perlen_days").ravel(); nstp = h.array("/calendar/nstp", int).ravel()
    if resolution and runtime_schedule is None and ((resolution == "daily") != (len(perlen) == 365)):
        raise ValueError("Requested resolution does not match the verified handoff calendar.")
    time = h.array("/forcing/time_days").ravel()
    forcing = {name: h.array(f"/forcing/{name}").ravel() for name in (
        "upstream_inflow_m3_per_day", "land_recharge_m_per_day", "land_et_m_per_day",
        "lake_precipitation_m_per_day", "lake_evaporation_m_per_day")}
    downstream_stage = h.array("/boundaries/downstream_control_stage_m").ravel()
    ghb_heads_override = h.array("/boundaries/ghb/reference_head_m")
    if runtime_schedule is not None:
        perlen = np.asarray(runtime_schedule.perlen_days, dtype=float).ravel()
        nstp = np.asarray(runtime_schedule.nstp, dtype=int).ravel()
        time = np.asarray(runtime_schedule.time_days, dtype=float).ravel()
        forcing = {name: np.asarray(runtime_schedule.forcing[name], dtype=float).ravel() for name in forcing}
        downstream_stage = np.asarray(runtime_schedule.downstream_control_stage_m, dtype=float).ravel()
        ghb_heads_override = np.asarray(runtime_schedule.ghb_reference_head_m, dtype=float)
        if len(perlen) != len(nstp) or np.any(perlen <= 0.0) or np.any(nstp < 1):
            raise ValueError("Runtime schedule requires positive, matching PERLEN/NSTP arrays.")
    if np.any(nstp != 1):
        raise ValueError(
            "The BDam release permits exactly one MF6 time step per forcing period. "
            "Regenerate the handoff with the current MakeInputs.m."
        )
    if len(time) != len(perlen) + 1 or any(len(v) != len(time) for v in forcing.values()):
        raise ValueError("Forcing time-series dimensions do not match the TDIS calendar.")
    if any(np.any(~np.isfinite(values)) or np.any(values < 0.0) for values in forcing.values()):
        raise ValueError("Atmospheric and inflow forcing series must be finite and nonnegative.")
    if runtime_schedule is None:
        _validate_calendar(perlen, nstp, resolution or h.manifest.get("time_resolution", ""))
    sim = flopy.mf6.MFSimulation(sim_name=f"bdam_{scenario}", sim_ws=ws, exe_name=str(_mf6_executable()))
    # Eight decimal places accumulate measurable calendar drift for 365/52-day
    # periods. Eighteen round-trips binary64 restart states exactly while also
    # preserving annual endpoints and flux integration.
    sim.simulation_data.float_precision = 18
    flopy.mf6.ModflowTdis(sim, time_units="DAYS", nper=len(perlen), perioddata=list(zip(perlen, nstp, [1.0] * len(perlen))))
    flopy.mf6.ModflowIms(sim, **_solver_settings(
        solver_profile, save_inner_iterations, robust_initialization))
    gwf = flopy.mf6.ModflowGwf(sim, modelname="bdam", save_flows=True, newtonoptions="NEWTON UNDER_RELAXATION")
    flopy.mf6.ModflowGwfdis(gwf, length_units="METERS", nlay=nlay, nrow=nrow, ncol=ncol,
                             delr=float(h.scalar("/grid/dx_m")), delc=float(h.scalar("/grid/dy_m")), top=top, botm=botm)
    lakes = _lake_data(h, nlay, nrow)
    # New runs use the same analytical water table as the multi-year runner;
    # restarts preserve every simulated groundwater head unchanged.
    strt = initial_heads if initial_heads is not None else _analytical_initial_heads(h)
    if np.asarray(strt).shape != (nlay, nrow, ncol):
        raise ValueError("Initial-head array does not match the MF6 grid.")
    flopy.mf6.ModflowGwfic(gwf, strt=strt)
    flopy.mf6.ModflowGwfnpf(gwf, icelltype=np.ones_like(k, int), k=k, k33=k33, save_flows=True)
    flopy.mf6.ModflowGwfsto(gwf, iconvert=np.ones_like(k, int), ss=ss, sy=sy,
                             transient={0: True}, save_flows=True)

    _validate_capped_lake_table(h, lakes)
    lake_topology_qa = _validate_lake_topology(h, lakes, top)
    land_mask, lake_mask = _atmospheric_masks(h, lakes, nrow, ncol)
    head_monitors = _monitoring(h, nlay, nrow, ncol, ws) if save_monitoring else []
    packagedata, connectiondata, tables = [], [], []
    for lake in lakes:
        lake_id = lake["number"] - 1
        stage = lake["stage"] if initial_lake_stages is None else float(initial_lake_stages[lake_id])
        packagedata.append((lake_id, stage, len(lake["cells"]), f"lake_{lake['number']}"))
        for iconn, cell in enumerate(lake["cells"]):
            connectiondata.append((lake_id, iconn, cell, "VERTICAL", lake["bed_leakance"], 0.0, 0.0, 0.0, 0.0))
        if lake["table"] is not None:
            tabname = f"lake_{lake['number']}.tab"; _write_tab6(ws / tabname, lake["table"])
            tables.append((lake_id, tabname))
    widths = h.array("/surface_water/outlets/width_m").ravel()
    external_invert = float(h.array("/boundaries/ghb/reference_head_m")[0, 0] - h.scalar("/mf6_parameters/external_weir_invert_depth_m"))
    # FloPy uses zero-based lake IDs; -1 serializes as MF6's external
    # receiver (lakeout = 0).  Do not use 0 for an external receiver: that
    # serializes as lake 1 and creates a self-routed outlet.
    outlets = [(0, 0, -1, "WEIR", external_invert, widths[-1], 0.0, 0.0)]
    if len(lakes) == 2:
        crest = h.scalar("/surface_water/dam/crest_elevation_m")
        outlets = [(0, 0, 1, "WEIR", crest, widths[0], 0.0, 0.0),
                   (1, 1, -1, "WEIR", external_invert, widths[1], 0.0, 0.0)]
    lak = flopy.mf6.ModflowGwflak(gwf, pname="LAK_MAIN", nlakes=len(lakes), noutlets=len(outlets), ntables=len(tables),
                                  packagedata=packagedata, connectiondata=connectiondata, tables=tables or None, outlets=outlets,
                                  surfdep=h.scalar("/mf6_parameters/uzf_surfdep_m"),
                                  boundnames=True, save_flows=True, time_conversion=86400.0,
                                  stage_filerecord="bdam.lak.stage", budget_filerecord="bdam.lak.bud")
    lak_period = []
    for lake_id in range(len(lakes)):
        lak_period += [(lake_id, "RAINFALL", f"lak{lake_id + 1}_rain"), (lake_id, "EVAPORATION", f"lak{lake_id + 1}_evap")]
    lak_period.append((0, "INFLOW", "lak1_inflow"))
    if sum(item[1] == "RAINFALL" for item in lak_period) != len(lakes) or \
            sum(item[1] == "EVAPORATION" for item in lak_period) != len(lakes):
        raise ValueError("Every lake must receive exactly one LAK rainfall and evaporation assignment.")
    lak.perioddata.set_data({0: lak_period})
    lak_columns = [forcing["upstream_inflow_m3_per_day"]]
    lak_names = ["lak1_inflow"]
    for lake_id in range(len(lakes)):
        lak_names += [f"lak{lake_id + 1}_rain", f"lak{lake_id + 1}_evap"]
        lak_columns += [forcing["lake_precipitation_m_per_day"], forcing["lake_evaporation_m_per_day"]]
    _ts(lak, "bdam.lak.ts", lak_names, time, lak_columns)
    if save_monitoring:
        lak.obs.initialize(digits=12, filename="bdam.lak.obs", continuous={"bdam.lake_fluxes.csv": _lake_observations(lakes)})
        flopy.mf6.ModflowUtlobs(gwf, digits=12, filename="bdam.gwf.obs",
                                 continuous={"bdam.heads.csv": [(name, "HEAD", cell) for name, cell in head_monitors]})

    ghb_i = h.array("/boundaries/ghb/i_x", int).ravel(); ghb_j = h.array("/boundaries/ghb/i_y", int).ravel(); ghb_k = h.array("/boundaries/ghb/native_layer", int).ravel()
    ghb_c = h.array("/boundaries/ghb/conductance_m2_per_day").ravel(); ghb_heads = ghb_heads_override
    if ghb_heads.shape != (len(ghb_i), len(time)):
        raise ValueError("GHB head-series matrix must be [cell, time].")
    ghb_names = [f"ghb_{i:04d}" for i in range(len(ghb_i))]
    ghb_spd = [(mf_cell(k0, i0, j0, nlay, nrow), ghb_names[i], ghb_c[i], "downstream_ghb") for i, (i0, j0, k0) in enumerate(zip(ghb_i, ghb_j, ghb_k))]
    ghb = flopy.mf6.ModflowGwfghb(gwf, pname="GHB_DOWNSTREAM", maxbound=len(ghb_spd),
                                  stress_period_data={0: ghb_spd}, boundnames=True, save_flows=True)
    _ts(ghb, "bdam.ghb.ts", ghb_names, time, [ghb_heads[i, :] for i in range(len(ghb_i))])
    if save_monitoring:
        ghb.obs.initialize(digits=12, filename="bdam.ghb.obs",
                           continuous={"bdam.ghb_flux.csv": [("ghb_total", "ghb", "downstream_ghb")]})

    uzf_pd, uzf_period, atmosphere_qa = _uzf_records(h, nlay, nrow, ncol, k33, land_mask, lake_mask, initial_uzf_wc)
    ntrailwaves = _positive_integer(
        h.scalar("/mf6_parameters/uzf_ntrailwaves"), "uzf_ntrailwaves")
    nwavesets = _positive_integer(
        h.scalar("/mf6_parameters/uzf_nwavesets"), "uzf_nwavesets")
    uzf = flopy.mf6.ModflowGwfuzf(gwf, pname="UZF_LAND", nuzfcells=len(uzf_pd), packagedata=uzf_pd,
                                  perioddata={0: uzf_period}, simulate_et=True, unsat_etwc=True, save_flows=True,
                                  ntrailwaves=ntrailwaves, nwavesets=nwavesets,
                                  wc_filerecord="bdam.uzf.wc", budget_filerecord="bdam.uzf.bud")
    _ts(uzf, "bdam.uzf.ts", ["uzf_finf", "uzf_pet"], time,
        [forcing["land_recharge_m_per_day"], forcing["land_et_m_per_day"]])
    flopy.mf6.ModflowGwfoc(gwf, head_filerecord="bdam.hds", budget_filerecord="bdam.cbc",
                            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")])
    prohibited = [package.package_type for package in gwf.packagelist if package.package_type.lower() in {"rch", "evt"}]
    if prohibited:
        raise RuntimeError(f"RCH/EVT packages are prohibited by the UZF/LAK atmospheric formulation: {prohibited}")
    _print_flux_summary(atmosphere_qa, forcing, perlen, float(h.scalar("/grid/dx_m") * h.scalar("/grid/dy_m")), len(lakes))
    print(f"Lake topology QA: unique connections={lake_topology_qa['unique_lake_connections']}, "
          f"fixed-footprint cells above initial stage={lake_topology_qa['dry_fixed_footprint_cells']}")
    return sim


def _execute_mf6(workspace: Path, solver_profile: str = "balanced") -> float:
    """Run one blocking MF6 process and require its explicit success markers."""
    workspace = Path(workspace)
    started = time.perf_counter()
    completed = subprocess.run(
        [str(_mf6_executable())], cwd=workspace, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    elapsed_seconds = time.perf_counter() - started
    listing = workspace / "mfsim.lst"
    listing_text = listing.read_text(errors="replace") if listing.is_file() else ""
    if completed.returncode != 0 or "Normal termination of simulation." not in listing_text:
        stdout = completed.stdout or ""
        model_listing = workspace / "bdam.lst"
        model_listing_text = (model_listing.read_text(errors="replace")
                              if model_listing.is_file() else "")
        combined = f"{listing_text}\n{model_listing_text}\n{stdout}"
        guidance = ""
        if "NWAVESETS needs to be increased" in combined:
            guidance = (
                "\nMF6 exhausted the configured UZF wave capacity. Increase "
                "mf6_parameters.uzf_nwavesets from 20 to 40 in MakeInputs.m, regenerate "
                "the handoffs, and rerun. Increase it further only if MF6 repeats this error."
            )
        elif solver_profile == "balanced" and re.search(
                r"convergence failure|failed to converge|did not converge", combined, re.IGNORECASE):
            guidance = "\nRerun the unchanged model with --solver-profile conservative."
        report = stdout[-4000:]
        raise RuntimeError(
            f"MF6 did not terminate normally (exit code {completed.returncode}).\n{report}{guidance}"
        )
    return elapsed_seconds


def _solver_memory_bytes(listing_text: str) -> int | None:
    """Extract MF6's final reported allocation from the simulation listing."""
    matches = list(re.finditer(
        r"MEMORY MANAGER TOTAL STORAGE BY DATA TYPE, IN (MEGABYTES|GIGABYTES)"
        r".*?^\s*Total\s+([0-9.Ee+-]+)\s*$",
        listing_text, re.MULTILINE | re.DOTALL,
    ))
    if not matches:
        return None
    unit, value = matches[-1].groups()
    scale = 1024 ** 2 if unit == "MEGABYTES" else 1024 ** 3
    return int(float(value) * scale)


def _write_solver_stats(workspace: Path, solver_profile: str, ntrailwaves: int,
                        nwavesets: int, elapsed_seconds: float,
                        save_inner_iterations: bool,
                        robust_initialization: bool) -> None:
    """Write compact solver provenance and iteration statistics."""
    workspace = Path(workspace)
    listing_text = (workspace / "mfsim.lst").read_text(errors="replace")
    version_match = re.search(r"\bVERSION\s+([0-9]+(?:\.[0-9]+)+)", listing_text)
    rows: list[dict[str, str]] = []
    outer_path = workspace / SOLVER_OUTER_OUTPUT
    if outer_path.is_file():
        with outer_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError("MF6 did not produce required outer-iteration diagnostics.")
    ims_settings = _solver_settings(
        solver_profile, save_inner_iterations, robust_initialization)
    stats = {
        "status": "normal_termination",
        "solver_profile": solver_profile,
        "ims_complexity": ims_settings["complexity"],
        "solver_variant": "robust_initialization" if robust_initialization else "standard",
        "outer_dvclose": 1.0e-5,
        "inner_dvclose": 1.0e-6,
        "inner_rclose": 1.0e-6,
        "rclose_option": "STRICT",
        "linear_acceleration": "BICGSTAB",
        "uzf_ntrailwaves": ntrailwaves,
        "uzf_nwavesets": nwavesets,
        "mf6_version": version_match.group(1) if version_match else None,
        "solve_wall_time_seconds": elapsed_seconds,
        "time_step_count": len({(row["kper"], row["kstp"]) for row in rows}),
        "total_outer_iterations": len(rows),
        "total_inner_iterations": int(rows[-1]["total_inner_iterations"]),
        "maximum_outer_iterations_per_time_step": max(int(row["nouter"]) for row in rows),
        "reported_memory_allocation_bytes": _solver_memory_bytes(listing_text),
        "outer_iteration_file": SOLVER_OUTER_OUTPUT,
        "inner_iteration_file": SOLVER_INNER_OUTPUT if save_inner_iterations else None,
    }
    (workspace / SOLVER_STATS_OUTPUT).write_text(json.dumps(stats, indent=2) + "\n")


def _run(sim: flopy.mf6.MFSimulation, solver_profile: str, ntrailwaves: int,
         nwavesets: int, save_inner_iterations: bool,
         robust_initialization: bool) -> None:
    """Write, execute, and verify one complete MF6 simulation workspace.

    Run MF6 directly rather than through FloPy's stdout convenience wrapper.
    A restart is valid only after the MF6 process has exited normally and all
    binary state/output files have been closed and populated.
    """
    sim.write_simulation(silent=True)
    workspace = Path(sim.sim_path)
    validate_lak_outlet_routes(workspace / "bdam.lak")
    elapsed_seconds = _execute_mf6(workspace, solver_profile)
    empty = [name for name in REQUIRED_BINARY_OUTPUTS
             if not (workspace / name).is_file() or (workspace / name).stat().st_size == 0]
    if empty:
        raise RuntimeError(f"MF6 terminated normally but did not finalize required outputs: {empty}")
    perioddata = sim.get_package("tdis").perioddata.get_data()
    expected_final_time = float(np.sum(perioddata["perlen"]))
    output_times = flopy.utils.HeadFile(workspace / "bdam.hds").get_times()
    if not output_times or not np.isclose(output_times[-1], expected_final_time, atol=1.0e-8):
        raise RuntimeError(
            f"MF6 output ends at {output_times[-1] if output_times else 'no saved time'} days; "
            f"expected {expected_final_time} days."
        )
    _write_solver_stats(workspace, solver_profile, ntrailwaves, nwavesets,
                        elapsed_seconds, save_inner_iterations, robust_initialization)
    _write_budget_qa(workspace)


def _budget_record_sums(budget: flopy.utils.CellBudgetFile, text_name: str) -> list[float]:
    records = budget.get_data(text=text_name)
    sums: list[float] = []
    for record in records:
        if getattr(record.dtype, "names", None) and "q" in record.dtype.names:
            sums.append(float(np.sum(record["q"])))
        else:
            sums.append(float(np.sum(record)))
    return sums


def _budget_sum_at_time(budget: flopy.utils.CellBudgetFile, text_name: str, time: float) -> float:
    """Return one required budget-record sum at a saved time."""
    records = budget.get_data(text=text_name, totim=time)
    if len(records) != 1:
        raise RuntimeError(f"Required {text_name} budget record is missing or duplicated at time {time:.12g}.")
    record = records[0]
    if getattr(record.dtype, "names", None) and "q" in record.dtype.names:
        value = float(np.sum(record["q"]))
    else:
        value = float(np.sum(record))
    if not np.isfinite(value):
        raise RuntimeError(f"Budget record {text_name} is non-finite at time {time:.12g}.")
    return value


def _cross_dam_connections(shape: tuple[int, int, int], upstream: np.ndarray,
                           ia: np.ndarray, ja: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Locate horizontal FLOW-JA-FACE entries crossing the reference dam line."""
    node_count = int(np.prod(shape))
    if len(ia) != node_count + 1:
        raise RuntimeError("DIS grid connectivity does not match the model shape.")
    indices: list[int] = []
    signs: list[float] = []
    for a in range(node_count):
        ca = np.unravel_index(a, shape)
        for index in range(int(ia[a]), int(ia[a + 1])):
            b = int(ja[index])
            if a >= b:
                continue
            cb = np.unravel_index(b, shape)
            if ca[0] != cb[0] or abs(ca[1] - cb[1]) + abs(ca[2] - cb[2]) != 1:
                continue
            a_up = bool(upstream[ca[1], ca[2]])
            b_up = bool(upstream[cb[1], cb[2]])
            if a_up == b_up:
                continue
            indices.append(index)
            signs.append(-1.0 if a_up else 1.0)
    if not indices:
        raise RuntimeError("Reference dam line has no horizontal groundwater connections.")
    return np.asarray(indices, dtype=int), np.asarray(signs, dtype=float)


def _cross_dam_rate(record, connections: tuple[np.ndarray, np.ndarray],
                    connection_count: int) -> float:
    """Return positive upstream-to-downstream horizontal FLOW-JA-FACE rate."""
    if record is None:
        return 0.0
    values = np.asarray(record, dtype=float).ravel()
    if values.size != connection_count:
        raise RuntimeError("FLOW-JA-FACE and DIS grid connectivity are inconsistent.")
    indices, signs = connections
    return float(np.dot(values[indices], signs))


def _lake_exchange_rates(record, shape: tuple[int, int, int], upstream: np.ndarray,
                         scenario: str) -> tuple[float, float]:
    """Return signed Lake 1/Lake 2 exchange, positive from lake to groundwater."""
    names = getattr(record.dtype, "names", None)
    if not names or not {"node", "node2", "q"}.issubset(names):
        raise RuntimeError("GWF LAK budget record is not cell-resolved.")
    lake1 = lake2 = 0.0
    for item in record:
        node = int(item["node"]) - 1
        if not 0 <= node < int(np.prod(shape)):
            raise RuntimeError("GWF LAK budget contains an invalid groundwater node.")
        q = float(item["q"])
        if scenario == "pre_dam":
            cell = np.unravel_index(node, shape)
            if bool(upstream[cell[1], cell[2]]):
                lake1 += q
            else:
                lake2 += q
        else:
            lake_number = int(item["node2"])
            if lake_number == 1:
                lake1 += q
            elif lake_number == 2:
                lake2 += q
            else:
                raise RuntimeError(f"Post-dam LAK budget references unexpected lake {lake_number}.")
    total = float(np.sum(record["q"]))
    tolerance = max(1.0e-10, abs(total) * 1.0e-10)
    if not np.isclose(lake1 + lake2, total, atol=tolerance, rtol=0.0):
        raise RuntimeError("Lake 1 and Lake 2 exchanges do not reconstruct total GWF LAK exchange.")
    return lake1, lake2


def _write_flux_monitoring(handoff: Handoff, workspace: Path,
                           discrepancy_tolerance_percent: float = 0.1) -> None:
    """Derive coupled external fluxes and internal diagnostics from MF6 budgets."""
    workspace = Path(workspace)
    cbc = flopy.utils.CellBudgetFile(workspace / "bdam.cbc", precision="double")
    uzf_budget = flopy.utils.CellBudgetFile(workspace / "bdam.uzf.bud", precision="double")
    lak_budget = flopy.utils.CellBudgetFile(workspace / "bdam.lak.bud", precision="double")
    times = np.asarray(cbc.get_times(), dtype=float)
    for label, budget in (("UZF", uzf_budget), ("LAK", lak_budget)):
        budget_times = np.asarray(budget.get_times(), dtype=float)
        if len(budget_times) != len(times) or not np.allclose(budget_times, times, atol=1.0e-8, rtol=0.0):
            raise RuntimeError(f"GWF and {label} budgets have inconsistent saved times.")
    listing = flopy.utils.Mf6ListBudget(workspace / "bdam.lst").get_incremental()
    required = {"totim", "time_step", "stress_period", "TOTAL_IN", "TOTAL_OUT", "IN-OUT",
                "PERCENT_DISCREPANCY"}
    if listing.dtype.names is None or not required.issubset(listing.dtype.names):
        raise RuntimeError("MF6 listing budget is missing required total-flow fields.")
    if len(times) == 0 or len(times) != len(listing):
        raise RuntimeError("GWF and listing budgets have inconsistent saved-step counts.")

    z = handoff.array("/grid/Z")
    shape = (z.shape[2] - 1, z.shape[1], z.shape[0])
    upstream = mf2(handoff.array("/validation_zones/upstream_mask", bool))
    downstream = mf2(handoff.array("/validation_zones/downstream_mask", bool))
    if upstream.shape != shape[1:] or not np.all(np.logical_xor(upstream, downstream)):
        raise RuntimeError("Reference dam masks are not exhaustive and mutually exclusive.")
    grid = flopy.mf6.utils.MfGrdFile(workspace / "bdam.dis.grb")
    if tuple(int(value) for value in grid.shape) != shape:
        raise RuntimeError("DIS grid and handoff dimensions are inconsistent.")
    cross_dam_connections = _cross_dam_connections(shape, upstream, grid.ia, grid.ja)

    rate_names = [
        "in_total", "out_total", "in_minus_out", "combined_storage_change",
        "coupled_mass_residual", "gwf_budget_in_total", "gwf_budget_out_total",
        "gwf_budget_in_minus_out", "land_infiltration", "land_evapotranspiration",
        "lake_precipitation", "lake_evaporation", "net_atmospheric_recharge",
        "surface_inflow", "surface_outflow", "ghb_inflow", "ghb_outflow",
        "rejected_infiltration", "lake1_to_groundwater", "lake2_to_groundwater",
        "groundwater_cross_dam_upstream_to_downstream",
    ]
    fields = (["time", "duration_days"] + [f"{name}_m3_per_day" for name in rate_names] +
              ["percent_discrepancy", "gwf_percent_discrepancy"] +
              [f"{name}_m3" for name in rate_names])
    rows = []
    previous = 0.0
    for step_index, (time, item) in enumerate(zip(times, listing)):
        if int(item["time_step"]) != 0 or int(item["stress_period"]) != step_index or not np.isclose(
                float(item["totim"]), time, atol=5.0e-4, rtol=5.0e-5):
            raise RuntimeError("GWF and listing budget times are misaligned.")
        duration = float(time - previous)
        previous = float(time)
        if duration <= 0.0:
            raise RuntimeError("Flux monitoring times are not strictly increasing.")
        gwf_in = float(item["TOTAL_IN"])
        gwf_out = float(item["TOTAL_OUT"])
        gwf_residual = float(item["IN-OUT"])
        gwf_discrepancy = float(item["PERCENT_DISCREPANCY"])
        if not np.all(np.isfinite([gwf_in, gwf_out, gwf_residual, gwf_discrepancy])) or gwf_in < 0.0 or gwf_out < 0.0:
            raise RuntimeError("MF6 total-flow budget contains invalid values.")
        listing_roundoff = 1.0e-4 * max(1.0, abs(gwf_in), abs(gwf_out))
        if not np.isclose(gwf_in - gwf_out, gwf_residual, atol=listing_roundoff, rtol=0.0):
            raise RuntimeError("MF6 total inflow, outflow, and residual are inconsistent.")
        if abs(gwf_discrepancy) > discrepancy_tolerance_percent:
            raise RuntimeError(
                f"GWF water-balance discrepancy {abs(gwf_discrepancy):.6g}% exceeds "
                f"{discrepancy_tolerance_percent:.6g}%."
            )

        lake_records = cbc.get_data(text="LAK", totim=time)
        face_records = cbc.get_data(text="FLOW-JA-FACE", totim=time)
        if len(lake_records) != 1 or len(face_records) != 1:
            raise RuntimeError("Required LAK or FLOW-JA-FACE record is missing or duplicated.")
        lake1, lake2 = _lake_exchange_rates(
            lake_records[0], shape, upstream, handoff.manifest["scenario"])
        cross_dam = _cross_dam_rate(face_records[0], cross_dam_connections, len(grid.ja))

        infiltration = _budget_sum_at_time(uzf_budget, "INFILTRATION", time)
        land_et = -_budget_sum_at_time(uzf_budget, "UZET", time)
        rejected = -_budget_sum_at_time(uzf_budget, "REJ-INF", time)
        lake_rain = _budget_sum_at_time(lak_budget, "RAINFALL", time)
        lake_evap = -_budget_sum_at_time(lak_budget, "EVAPORATION", time)
        lake_external_in = _budget_sum_at_time(lak_budget, "EXT-INFLOW", time)
        lake_external_out = -_budget_sum_at_time(lak_budget, "EXT-OUTFLOW", time)
        withdrawal = -_budget_sum_at_time(lak_budget, "WITHDRAWAL", time)
        runoff = _budget_sum_at_time(lak_budget, "RUNOFF", time)
        constant = _budget_sum_at_time(lak_budget, "CONSTANT", time)
        ghb_net = _budget_sum_at_time(cbc, "GHB", time)
        ghb_in, ghb_out = max(ghb_net, 0.0), max(-ghb_net, 0.0)
        surface_in = lake_external_in + max(runoff, 0.0) + max(constant, 0.0)
        surface_out = lake_external_out + withdrawal + max(-runoff, 0.0) + max(-constant, 0.0)
        total_in = infiltration + lake_rain + surface_in + ghb_in
        total_out = land_et + rejected + lake_evap + surface_out + ghb_out
        external_net = total_in - total_out
        native_storage = (
            _budget_sum_at_time(cbc, "STO-SS", time) +
            _budget_sum_at_time(cbc, "STO-SY", time) +
            _budget_sum_at_time(uzf_budget, "STORAGE", time) +
            _budget_sum_at_time(lak_budget, "STORAGE", time)
        )
        storage_change = -native_storage
        coupled_residual = external_net - storage_change
        denominator = max(1.0e-30, 0.5 * (total_in + total_out))
        coupled_discrepancy = 100.0 * coupled_residual / denominator
        net_atmospheric = infiltration + lake_rain - land_et - lake_evap
        rates = {
            "in_total": total_in, "out_total": total_out, "in_minus_out": external_net,
            "combined_storage_change": storage_change, "coupled_mass_residual": coupled_residual,
            "gwf_budget_in_total": gwf_in, "gwf_budget_out_total": gwf_out,
            "gwf_budget_in_minus_out": gwf_residual,
            "land_infiltration": infiltration, "land_evapotranspiration": land_et,
            "lake_precipitation": lake_rain, "lake_evaporation": lake_evap,
            "net_atmospheric_recharge": net_atmospheric,
            "surface_inflow": surface_in, "surface_outflow": surface_out,
            "ghb_inflow": ghb_in, "ghb_outflow": ghb_out,
            "rejected_infiltration": rejected,
            "lake1_to_groundwater": lake1, "lake2_to_groundwater": lake2,
            "groundwater_cross_dam_upstream_to_downstream": cross_dam,
        }
        if not np.all(np.isfinite(list(rates.values()) + [coupled_discrepancy])):
            raise RuntimeError("Derived flux monitoring contains non-finite values.")
        if abs(coupled_discrepancy) > discrepancy_tolerance_percent:
            raise RuntimeError(
                f"Coupled-system mass discrepancy {abs(coupled_discrepancy):.6g}% exceeds "
                f"{discrepancy_tolerance_percent:.6g}% at time {time:.12g} days."
            )
        row = {"time": time, "duration_days": duration,
               "percent_discrepancy": coupled_discrepancy,
               "gwf_percent_discrepancy": gwf_discrepancy}
        row.update({f"{name}_m3_per_day": value for name, value in rates.items()})
        row.update({f"{name}_m3": value * duration for name, value in rates.items()})
        rows.append(row)
    with (workspace / FLUX_OUTPUT).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    qa_path = workspace / "bdam.water_balance.json"
    qa = json.loads(qa_path.read_text())
    qa.update({
        "coupled_external_budget_discrepancy_tolerance_percent": discrepancy_tolerance_percent,
        "maximum_absolute_coupled_external_budget_discrepancy_percent":
            max(abs(row["percent_discrepancy"]) for row in rows),
        "coupled_flux_output": FLUX_OUTPUT,
    })
    qa_path.write_text(json.dumps(qa, indent=2) + "\n")


def _write_budget_qa(workspace: Path, discrepancy_tolerance_percent: float = 0.1) -> None:
    """Write and enforce compact, machine-readable whole-model budget QA."""
    required = ["bdam.lst", "bdam.cbc", "bdam.lak.bud", "bdam.uzf.bud"]
    missing = [name for name in required if not (workspace / name).is_file()]
    if missing:
        raise RuntimeError(f"Successful MF6 run is missing required budget outputs: {missing}")
    incremental, _ = flopy.utils.Mf6ListBudget(workspace / "bdam.lst").get_dataframes()
    discrepancy = np.asarray(incremental["PERCENT_DISCREPANCY"], dtype=float)
    discrepancy = discrepancy[np.isfinite(discrepancy)]
    if discrepancy.size == 0:
        raise RuntimeError("No finite whole-model percent-discrepancy records were found.")
    max_discrepancy = float(np.max(np.abs(discrepancy)))
    if max_discrepancy > discrepancy_tolerance_percent:
        raise RuntimeError(
            f"Whole-model water-balance discrepancy {max_discrepancy:.6g}% exceeds "
            f"{discrepancy_tolerance_percent:.6g}%."
        )
    cbc = flopy.utils.CellBudgetFile(workspace / "bdam.cbc", precision="double")
    available = {name.decode().strip() if isinstance(name, bytes) else str(name).strip()
                 for name in cbc.get_unique_record_names()}
    expected_terms = {"GHB", "LAK", "UZF-GWRCH", "STO-SS", "STO-SY"}
    missing_terms = sorted(expected_terms - available)
    if missing_terms:
        raise RuntimeError(f"GWF budget is missing required terms: {missing_terms}; found {sorted(available)}")
    term_summary = {}
    for name in sorted(expected_terms):
        values = _budget_record_sums(cbc, name)
        term_summary[name] = {
            "record_count": len(values),
            "minimum_net_rate_m3_per_day": min(values),
            "maximum_net_rate_m3_per_day": max(values),
        }
    lak_budget = flopy.utils.CellBudgetFile(workspace / "bdam.lak.bud", precision="double")
    lak_record_names = {name.decode().strip() if isinstance(name, bytes) else str(name).strip()
                        for name in lak_budget.get_unique_record_names()}
    internal_records = lak_budget.get_data(text="FLOW-JA-FACE") if "FLOW-JA-FACE" in lak_record_names else []
    internal_errors = []
    internal_rates = []
    for record in internal_records:
        directed = {(int(row["node"]), int(row["node2"])): float(row["q"]) for row in record}
        for (node, node2), rate in directed.items():
            reverse = directed.get((node2, node))
            if reverse is not None and node < node2:
                internal_errors.append(abs(rate + reverse))
                internal_rates.append(abs(rate))
    max_internal_error = max(internal_errors, default=0.0)
    if max_internal_error > 1.0e-8:
        raise RuntimeError(f"LAK-to-LAK routed-flow conservation error is {max_internal_error:.6g} m3/day.")
    qa = {
        "status": "pass",
        "whole_model_discrepancy_tolerance_percent": discrepancy_tolerance_percent,
        "maximum_absolute_whole_model_discrepancy_percent": max_discrepancy,
        "gwf_budget_terms": term_summary,
        "maximum_lak_to_lak_conservation_error_m3_per_day": max_internal_error,
        "maximum_lak_to_lak_transfer_m3_per_day": max(internal_rates, default=0.0),
        "observation_csv_status": "MF6 observation files are optional; binary budgets are authoritative.",
        "required_outputs": required,
    }
    (workspace / "bdam.water_balance.json").write_text(json.dumps(qa, indent=2) + "\n")


def _read_mf6_array_final(path: Path, expected_shape: tuple[int, ...]) -> tuple[float, np.ndarray]:
    """Read the final time and state from an MF6 binary array file.

    LAK and UZF binary array outputs use the MF6 array header layout, which
    is not indexed correctly by FloPy's generic HeadFile reader here.  Keep
    the small reader here rather than
    changing the simulation outputs or silently using an earlier state.
    """
    header = np.dtype([
        ("kstp", "<i4"), ("kper", "<i4"), ("pertim", "<f8"),
        ("totim", "<f8"), ("text", "S16"), ("ncol", "<i4"),
        ("nrow", "<i4"), ("ilay", "<i4"),
    ])
    records: list[tuple[float, int, int, int, np.ndarray]] = []
    with path.open("rb") as binary:
        while True:
            raw = binary.read(header.itemsize)
            if not raw:
                break
            if len(raw) != header.itemsize:
                raise RuntimeError(f"Truncated MF6 array header in {path}.")
            item = np.frombuffer(raw, dtype=header, count=1)[0]
            ncol, nrow, ilay = int(item["ncol"]), int(item["nrow"]), int(item["ilay"])
            if ncol <= 0 or nrow <= 0 or ilay <= 0:
                raise RuntimeError(f"Invalid MF6 array dimensions in {path}.")
            count = ncol * nrow
            values = np.fromfile(binary, dtype="<f8", count=count)
            if values.size != count:
                raise RuntimeError(f"Truncated MF6 array values in {path}.")
            records.append((float(item["totim"]), ilay, nrow, ncol, values))
    if not records:
        raise RuntimeError(f"No MF6 array records found in {path}.")
    last_time = max(record[0] for record in records)
    final = [record for record in records if np.isclose(record[0], last_time)]
    result = np.full(expected_shape, np.nan, dtype=float)
    for _, ilay, nrow, ncol, values in final:
        if len(expected_shape) == 1:
            if ilay != 1 or nrow != 1 or ncol != expected_shape[0]:
                raise RuntimeError(f"Unexpected LAK state dimensions in {path}.")
            result[:] = values
        else:
            if (nrow, ncol) != expected_shape[1:] or not 1 <= ilay <= expected_shape[0]:
                raise RuntimeError(f"Unexpected MF6 array dimensions in {path}.")
            result[ilay - 1, :, :] = values.reshape((nrow, ncol))
    if not np.all(np.isfinite(result)):
        raise RuntimeError(f"Final MF6 state is incomplete in {path}.")
    return last_time, result


def _read_mf6_array_last(path: Path, expected_shape: tuple[int, ...]) -> np.ndarray:
    """Read only the final state from an MF6 binary array file."""
    return _read_mf6_array_final(path, expected_shape)[1]


def _load_initial_heads(path: str | Path, expected_shape: tuple[int, int, int]) -> np.ndarray:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Initial-head file does not exist: {path}")
    heads = flopy.utils.HeadFile(path).get_data()
    if heads.shape != expected_shape or not np.all(np.isfinite(heads)):
        raise ValueError(f"Initial-head file {path} does not match the active MF6 grid.")
    return heads


def _read_lake_stage_series(path: Path, count: int) -> list[tuple[float, np.ndarray]]:
    """Read each LAK stage record; MF6 does not index this array format as heads."""
    header = np.dtype([("kstp", "<i4"), ("kper", "<i4"), ("pertim", "<f8"),
                       ("totim", "<f8"), ("text", "S16"), ("ncol", "<i4"),
                       ("nrow", "<i4"), ("ilay", "<i4")])
    result: list[tuple[float, np.ndarray]] = []
    with path.open("rb") as binary:
        while raw := binary.read(header.itemsize):
            if len(raw) != header.itemsize:
                raise RuntimeError(f"Truncated LAK stage header in {path}.")
            item = np.frombuffer(raw, dtype=header, count=1)[0]
            ncol, nrow = int(item["ncol"]), int(item["nrow"])
            values = np.fromfile(binary, dtype="<f8", count=ncol * nrow)
            if nrow != 1 or ncol != count or values.size != count:
                raise RuntimeError(f"Unexpected LAK stage dimensions in {path}.")
            result.append((float(item["totim"]), values))
    return result


def _period_rows(handoff: Handoff, run_workspace: Path, initial_heads: np.ndarray,
                 initial_lake_stages: np.ndarray | None, phase: str, phase_year: int,
                 elapsed_days: float, include_initial: bool,
                 runtime_schedule: RuntimeSchedule | None = None,
                 step_metadata: list[SpinupStep] | None = None) -> list[dict]:
    """Return monitored initial and stress-period-end states for one post-spinup year."""
    names = handoff.manifest.get("monitoring_head_point_names", [])
    ix = handoff.array("/monitoring/head_points_resolved_i_x", int).ravel()
    iy = handoff.array("/monitoring/head_points_resolved_i_y", int).ravel()
    layers = handoff.array("/monitoring/head_points_resolved_layer_top_down", int).ravel()
    if len(names) != len(ix):
        names = [f"head_{number + 1:02d}" for number in range(len(ix))]
    z = handoff.array("/grid/Z"); nlay = z.shape[2] - 1
    nrow = handoff.array("/grid/ZTop").shape[1]
    first = {"phase": phase, "phase_year": phase_year,
             "event": "initial" if elapsed_days == 0.0 else "phase_start",
             "time_days": elapsed_days, "phase_time_days": 0.0, "duration_days": 0.0}
    if step_metadata:
        first.update({"spinup_stage": step_metadata[0].stage,
                      "stage_year": step_metadata[0].stage_year,
                      "stage_time_days": 0.0})
    for name, x, y, layer in zip(names, ix, iy, layers):
        first[f"{name}_m"] = float(initial_heads[int(layer) - 1, nrow - int(y), int(x) - 1])
    nlakes = int(handoff.scalar("/surface_water/n_lakes"))
    stages = initial_lake_stages
    if stages is None:
        stages = np.asarray([handoff.scalar(f"/surface_water/lakes/lake_{number}/initial_stage_m")
                             for number in range(1, nlakes + 1)])
    for number, stage in enumerate(stages, 1):
        first[f"lake{number}_stage_m"] = float(stage)
    rows = [first] if include_initial else []
    head_file = flopy.utils.HeadFile(run_workspace / "bdam.hds")
    cbc = flopy.utils.CellBudgetFile(run_workspace / "bdam.cbc", precision="double")
    stages_by_time = _read_lake_stage_series(run_workspace / "bdam.lak.stage", nlakes)
    times = np.asarray(head_file.get_times(), dtype=float)
    if len(times) != len(stages_by_time):
        raise RuntimeError("Head and LAK-stage output records do not match.")
    flux_path = run_workspace / FLUX_OUTPUT
    if not flux_path.is_file():
        raise RuntimeError(f"Annual workspace is missing flux output: {flux_path}")
    with flux_path.open(newline="") as stream:
        flux_rows = list(csv.DictReader(stream))
    if len(flux_rows) != len(times):
        raise RuntimeError("Flux monitoring and state outputs have inconsistent saved-step counts.")
    period_lengths = (runtime_schedule.perlen_days if runtime_schedule is not None
                      else handoff.array("/calendar/perlen_days").ravel())
    period_endpoints = np.cumsum(period_lengths)
    if step_metadata is not None and len(step_metadata) != len(period_endpoints):
        raise RuntimeError("Spinup step labels do not match the runtime schedule.")
    previous = 0.0
    for index, (time, (_, lake_stages)) in enumerate(zip(times, stages_by_time)):
        if not np.any(np.isclose(time, period_endpoints, atol=1.0e-8)):
            continue
        time = float(time); row = {"phase": phase, "phase_year": phase_year,
                                   "event": "completed_step", "time_days": elapsed_days + time,
                                   "phase_time_days": time, "duration_days": time - previous}
        previous = time
        if step_metadata is not None:
            label = step_metadata[index]
            row.update({"phase": label.phase, "phase_year": label.stage_year,
                        "phase_time_days": label.stage_time_days,
                        "spinup_stage": label.stage, "stage_year": label.stage_year,
                        "stage_time_days": label.stage_time_days})
        heads = head_file.get_data(totim=time)
        for name, x, y, layer in zip(names, ix, iy, layers):
            row[f"{name}_m"] = float(heads[int(layer) - 1, nrow - int(y), int(x) - 1])
        for number, stage in enumerate(lake_stages, 1):
            row[f"lake{number}_stage_m"] = float(stage)
        ghb_records = cbc.get_data(text="GHB", totim=time)
        if ghb_records:
            record = ghb_records[0]
            row["ghb_net_volume_m3"] = float(np.sum(record["q"])) * row["duration_days"]
        flux = flux_rows[index]
        if not np.isclose(float(flux["time"]), time, atol=1.0e-8, rtol=0.0) or not np.isclose(
                float(flux["duration_days"]), row["duration_days"], atol=1.0e-8, rtol=0.0):
            raise RuntimeError("Flux monitoring and summary intervals are misaligned.")
        for name, value in flux.items():
            if name not in {"time", "duration_days"}:
                row[name] = float(value)
        rows.append(row)
    return rows


def _write_summary(path: Path, rows: list[dict]) -> None:
    """Write a compact state and budget summary."""
    if not rows:
        return
    fields = list(rows[0])
    for row in rows[1:]:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def _analytical_initial_heads(handoff: Handoff) -> np.ndarray:
    """Create a bounded water table with lateral rise and an upslope head correction."""
    top = mf2(handoff.array("/grid/ZTop"))
    x = mf2(handoff.array("/grid/X"))
    y = mf2(handoff.array("/grid/Y"))
    channel = mf2(handoff.array("/surface_water/channel_mask", bool))
    z = handoff.array("/grid/Z")
    nlay = z.shape[2] - 1
    bottom = mf3(z[:, :, :-1])[-1]
    if x.shape != top.shape or y.shape != top.shape or channel.shape != top.shape or not np.any(channel):
        raise ValueError("Analytical initial heads require matching grid coordinates and a nonempty channel mask.")
    channel_xy = np.column_stack((x[channel], y[channel]))
    channel_bed = top[channel]
    points = np.column_stack((x.ravel(), y.ravel()))
    nearest_bed = np.empty(points.shape[0], dtype=float)
    nearest_distance = np.empty(points.shape[0], dtype=float)
    # Chunking avoids a grid-by-channel temporary array for large user grids.
    for start in range(0, points.shape[0], 4096):
        stop = min(start + 4096, points.shape[0])
        delta = points[start:stop, np.newaxis, :] - channel_xy[np.newaxis, :, :]
        distance2 = np.sum(delta * delta, axis=2)
        nearest = np.argmin(distance2, axis=1)
        nearest_bed[start:stop] = channel_bed[nearest]
        nearest_distance[start:stop] = np.sqrt(distance2[np.arange(stop - start), nearest])
    offset = handoff.scalar("/mf6_parameters/initial_head_channel_offset_m")
    gradient = handoff.scalar("/mf6_parameters/initial_head_lateral_gradient_m_per_m")
    upslope_reduction = handoff.scalar("/mf6_parameters/initial_head_upslope_reduction_m_per_m")
    if offset < 0.0 or gradient < 0.0 or upslope_reduction < 0.0:
        raise ValueError("Analytical initial-head parameters must be nonnegative.")
    surface = (nearest_bed + offset + gradient * nearest_distance).reshape(top.shape)
    lower_bound = bottom + np.maximum(1.0e-6, (top - bottom) * 1.0e-9)
    surface = np.minimum(top, np.maximum(surface, lower_bound))
    direction = handoff.manifest.get("longitudinal_direction")
    if direction == "y":
        first_mean, last_mean = float(np.mean(top[0, :])), float(np.mean(top[-1, :]))
        outlet_coordinate = float(np.mean(y[0, :] if first_mean <= last_mean else y[-1, :]))
        longitudinal_coordinate = y
    elif direction == "x":
        first_mean, last_mean = float(np.mean(top[:, 0])), float(np.mean(top[:, -1]))
        outlet_coordinate = float(np.mean(x[:, 0] if first_mean <= last_mean else x[:, -1]))
        longitudinal_coordinate = x
    else:
        raise ValueError("Analytical initial heads require longitudinal_direction 'x' or 'y'.")
    distance_upslope = np.abs(longitudinal_coordinate - outlet_coordinate)
    if np.any(~np.isfinite(distance_upslope)):
        raise ValueError("Longitudinal distance from the outlet is non-finite.")
    surface = np.minimum(top, np.maximum(surface - upslope_reduction * distance_upslope, lower_bound))
    if not np.all(np.isfinite(surface)) or np.any(surface > top) or np.any(surface <= bottom):
        raise RuntimeError("Analytical initial water table is non-finite or outside the model bounds.")
    return np.repeat(surface[np.newaxis, :, :], nlay, axis=0)


def _default_heads(handoff: Handoff) -> np.ndarray:
    return _analytical_initial_heads(handoff)


def _map_uzf_state(source: Handoff, target: Handoff, source_wc: np.ndarray | None) -> np.ndarray | None:
    """Map UZF states by groundwater cell and initialize only genuinely new features."""
    if source_wc is None:
        return None
    source_cells = uzf_cells(source)
    target_cells = uzf_cells(target)
    values = np.asarray(source_wc, dtype=float).ravel()
    if values.size != len(source_cells) or not np.all(np.isfinite(values)):
        raise ValueError("Source UZF restart state does not match its feature cells.")
    by_cell = dict(zip(source_cells, values))
    initial = target.scalar("/mf6_parameters/uzf_thti")
    mapped = np.asarray([by_cell.get(cell, initial) for cell in target_cells], dtype=float)
    common = sum(cell in by_cell for cell in target_cells)
    if common != len(set(source_cells).intersection(target_cells)):
        raise RuntimeError("UZF cell-state mapping did not preserve every common feature.")
    return mapped


def _read_final_state(handoff: Handoff, workspace: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nlak = int(handoff.scalar("/surface_water/n_lakes"))
    nuzf = int(np.count_nonzero(mf3(handoff.array("/uzf/eligible_mask", bool))))
    try:
        return (
            flopy.utils.HeadFile(workspace / "bdam.hds").get_data(),
            _read_mf6_array_last(workspace / "bdam.lak.stage", (nlak,)),
            _read_mf6_array_last(workspace / "bdam.uzf.wc", (nuzf,)),
        )
    except Exception as exc:
        raise RuntimeError("MF6 completed but its final head, lake-stage, or UZF water-content state could not be read.") from exc


def _last_binary_time(path: Path, budget: bool = False) -> float:
    reader = (flopy.utils.CellBudgetFile(path, precision="double") if budget
              else flopy.utils.HeadFile(path))
    try:
        times = reader.get_times()
        if not times:
            raise RuntimeError(f"No saved simulation times were found in {path}.")
        return float(times[-1])
    finally:
        close = getattr(reader, "close", None)
        if close is not None:
            close()


def _validate_monitoring_outputs(workspace: Path, expected_final_time: float, enabled: bool) -> None:
    existing = [name for name in MONITORING_OUTPUTS if (workspace / name).exists()]
    if not enabled:
        if existing:
            raise RuntimeError(f"Spinup workspace contains prohibited monitoring outputs: {existing}")
        return
    missing = [name for name in MONITORING_OUTPUTS
               if not (workspace / name).is_file() or (workspace / name).stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Monitored workspace is missing observation outputs: {missing}")
    for name in MONITORING_OUTPUTS:
        with (workspace / name).open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise RuntimeError(f"Monitoring output has no result rows: {name}")
        time_name = next((key for key in rows[-1] if key.upper() == "TIME"), None)
        if time_name is None or not np.isclose(float(rows[-1][time_name]), expected_final_time, atol=1.0e-8):
            raise RuntimeError(f"Monitoring output {name} does not end at {expected_final_time:.12g} days.")
        for row in rows:
            if any(not np.isfinite(float(value)) for value in row.values()):
                raise RuntimeError(f"Monitoring output contains a non-finite value: {name}")


def _validate_flux_output(workspace: Path, expected_final_time: float) -> None:
    path = workspace / FLUX_OUTPUT
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Annual workspace is missing required derived flux output: {path}")
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not np.isclose(float(rows[-1]["time"]), expected_final_time, atol=1.0e-8):
        raise RuntimeError(f"Flux output does not end at {expected_final_time:.12g} days: {path}")
    for row in rows:
        if any(not np.isfinite(float(value)) for value in row.values()):
            raise RuntimeError(f"Flux output contains a non-finite value: {path}")


def _validate_completed_workspace(handoff: Handoff, workspace: Path, expected_final_time: float,
                                  save_monitoring: bool) -> None:
    """Prove that a closed annual workspace is complete and restartable."""
    workspace = Path(workspace)
    listing = workspace / "mfsim.lst"
    if not listing.is_file() or "Normal termination of simulation." not in listing.read_text(errors="replace"):
        raise RuntimeError(f"Workspace does not contain a normal MF6 termination marker: {workspace}")
    empty = [name for name in REQUIRED_BINARY_OUTPUTS
             if not (workspace / name).is_file() or (workspace / name).stat().st_size == 0]
    if empty:
        raise RuntimeError(f"Workspace has missing or empty required binary outputs: {empty}")

    nlakes = int(handoff.scalar("/surface_water/n_lakes"))
    nuzf = int(np.count_nonzero(mf3(handoff.array("/uzf/eligible_mask", bool))))
    head_reader = flopy.utils.HeadFile(workspace / "bdam.hds")
    try:
        head_times = head_reader.get_times()
        if not head_times:
            raise RuntimeError("Head output contains no saved times.")
        final_heads = head_reader.get_data(totim=head_times[-1])
    finally:
        close = getattr(head_reader, "close", None)
        if close is not None:
            close()
    if not np.all(np.isfinite(final_heads)):
        raise RuntimeError("Final groundwater heads contain non-finite values.")

    stage_time, stages = _read_mf6_array_final(workspace / "bdam.lak.stage", (nlakes,))
    wc_time, water_content = _read_mf6_array_final(workspace / "bdam.uzf.wc", (nuzf,))
    if not np.all(np.isfinite(stages)) or not np.all(np.isfinite(water_content)):
        raise RuntimeError("Final LAK or UZF restart state contains non-finite values.")
    final_times = {
        "heads": float(head_times[-1]),
        "GWF budget": _last_binary_time(workspace / "bdam.cbc", budget=True),
        "LAK stage": stage_time,
        "LAK budget": _last_binary_time(workspace / "bdam.lak.bud", budget=True),
        "UZF water content": wc_time,
        "UZF budget": _last_binary_time(workspace / "bdam.uzf.bud", budget=True),
    }
    wrong = {name: value for name, value in final_times.items()
             if not np.isclose(value, expected_final_time, atol=1.0e-8)}
    if wrong:
        raise RuntimeError(f"Required outputs do not end at {expected_final_time:.12g} days: {wrong}")

    qa_path = workspace / "bdam.water_balance.json"
    if not qa_path.is_file() or json.loads(qa_path.read_text()).get("status") != "pass":
        raise RuntimeError("Workspace is missing passing water-budget QA.")
    solver_stats_path = workspace / SOLVER_STATS_OUTPUT
    if (not solver_stats_path.is_file() or
            json.loads(solver_stats_path.read_text()).get("status") != "normal_termination"):
        raise RuntimeError("Workspace is missing valid solver statistics.")
    _validate_monitoring_outputs(workspace, expected_final_time, save_monitoring)
    _validate_flux_output(workspace, expected_final_time)


def _workspace_size_manifest(workspace: Path) -> dict[str, int]:
    return {str(path.relative_to(workspace)): path.stat().st_size
            for path in workspace.rglob("*") if path.is_file()}


def _publish_workspace(staging_workspace: Path, final_workspace: Path,
                       validator: Callable[[Path], None]) -> None:
    """Copy a closed staged run, verify the copy, and atomically expose it."""
    staging_workspace, final_workspace = Path(staging_workspace), Path(final_workspace)
    if final_workspace.exists():
        raise FileExistsError(f"Refusing to replace existing annual workspace: {final_workspace}")
    final_workspace.parent.mkdir(parents=True, exist_ok=True)
    incoming = final_workspace.parent / f".{final_workspace.name}.publishing-{uuid.uuid4().hex[:10]}"
    try:
        shutil.copytree(staging_workspace, incoming)
        source_sizes = _workspace_size_manifest(staging_workspace)
        published_sizes = _workspace_size_manifest(incoming)
        if source_sizes != published_sizes:
            raise RuntimeError("Published workspace file sizes do not match the staged source.")
        validator(incoming)
        incoming.rename(final_workspace)
    except Exception as exc:
        raise RuntimeError(
            f"Could not publish validated run. Staging retained at {staging_workspace}; "
            f"partial publication retained at {incoming}."
        ) from exc
    try:
        shutil.rmtree(staging_workspace)
    except OSError as exc:
        print(f"WARNING: published run is valid, but staging cleanup failed at {staging_workspace}: {exc}")


def _create_staging_workspace(staging_root: Path, phase: str, year: int) -> Path:
    staging_root = Path(staging_root).expanduser().resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"bdam-{phase}-year_{year:02d}-", dir=staging_root))


def _next_backup_path(runs_workspace: Path, when: dt.datetime | None = None) -> Path:
    when = when or dt.datetime.now()
    stem = f"{runs_workspace.name}_backup_{when.strftime('%Y%m%d_%H%M%S')}"
    candidate = runs_workspace.with_name(stem)
    suffix = 2
    while candidate.exists():
        candidate = runs_workspace.with_name(f"{stem}_{suffix:02d}")
        suffix += 1
    return candidate


def _prepare_runs_workspace(runs_workspace: Path) -> Path | None:
    """Archive an existing nonempty Runs directory and return its backup path."""
    runs_workspace = Path(runs_workspace)
    if not runs_workspace.exists() or not any(runs_workspace.iterdir()):
        runs_workspace.mkdir(parents=True, exist_ok=True)
        return None
    backup = _next_backup_path(runs_workspace)
    runs_workspace.rename(backup)
    runs_workspace.mkdir(parents=True, exist_ok=True)
    return backup


def _run_year(h5_path: Path, handoff: Handoff, workspace: Path, heads: np.ndarray,
              stages: np.ndarray | None, wc: np.ndarray | None, save_monitoring: bool,
              staging_root: Path, phase: str, year: int,
              runtime_schedule: RuntimeSchedule | None = None, solver_profile: str = "balanced",
              save_inner_iterations: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    resolution = handoff.manifest.get("time_resolution")
    if resolution not in {"weekly", "daily"}:
        raise ValueError("Handoff is missing a valid time_resolution metadata value.")
    staging_workspace = _create_staging_workspace(staging_root, phase, year)
    expected_final_time = float(np.sum(runtime_schedule.perlen_days if runtime_schedule is not None
                                       else handoff.array("/calendar/perlen_days").ravel()))
    ntrailwaves = _positive_integer(
        handoff.scalar("/mf6_parameters/uzf_ntrailwaves"), "uzf_ntrailwaves")
    nwavesets = _positive_integer(
        handoff.scalar("/mf6_parameters/uzf_nwavesets"), "uzf_nwavesets")
    robust_initialization = wc is None
    try:
        simulation = build_from_handoff(
            h5_path, staging_workspace, resolution=resolution, initial_heads=heads,
            initial_lake_stages=stages, initial_uzf_wc=wc,
            runtime_schedule=runtime_schedule, save_monitoring=save_monitoring,
            solver_profile=solver_profile, save_inner_iterations=save_inner_iterations,
            robust_initialization=robust_initialization)
        _run(simulation, solver_profile, ntrailwaves, nwavesets, save_inner_iterations,
             robust_initialization)
        _write_flux_monitoring(handoff, staging_workspace)
        _validate_completed_workspace(handoff, staging_workspace, expected_final_time, save_monitoring)
        validator = lambda path: _validate_completed_workspace(
            handoff, path, expected_final_time, save_monitoring)
        _publish_workspace(staging_workspace, workspace, validator)
    except Exception as exc:
        raise RuntimeError(
            f"{phase} year {year} failed; diagnostic staging workspace retained at {staging_workspace}."
        ) from exc
    return _read_final_state(handoff, workspace)


def _resolve_handoffs(path: str | Path) -> tuple[Path, Path, Path]:
    """Accept ModelInput or either paired handoff; return root, pre, post."""
    candidate = Path(path).resolve()
    if candidate.is_dir():
        root = candidate
    elif candidate.name == "preparation_handoff.h5" and candidate.parent.name in {"pre_dam", "post_dam"}:
        root = candidate.parent.parent
    else:
        raise ValueError("Pass the ModelInput directory or one of its paired scenario handoffs.")
    pre = root / "pre_dam" / "preparation_handoff.h5"
    post = root / "post_dam" / "preparation_handoff.h5"
    if not pre.is_file() or not post.is_file():
        raise FileNotFoundError("ModelInput must contain pre_dam and post_dam preparation_handoff.h5 files. Run MakeInputs.m first.")
    return root, pre, post


def run_from_handoff(path: str | Path, staging_root: str | Path | None = None,
                     solver_profile: str = "balanced",
                     save_inner_iterations: bool = False) -> None:
    """Spin up pre-dam conditions, then run the configured pre-/post-dam years."""
    _solver_settings(solver_profile, save_inner_iterations)
    model_input, pre_path, post_path = _resolve_handoffs(path)
    workspace = model_input.parent / "Runs"
    staging_root = (Path(staging_root) if staging_root is not None
                    else Path(tempfile.gettempdir()) / "bdam-staging")
    pre, post = load_handoff(pre_path), load_handoff(post_path)
    if pre.manifest["scenario"] != "pre_dam" or post.manifest["scenario"] != "post_dam":
        raise ValueError("Paired handoffs must be labeled pre_dam and post_dam.")
    spinup_names = ("fall_average_spinup_years", "monthly_spinup_years", "weekly_spinup_years")
    values = {name: int(pre.scalar(f"/mf6_parameters/{name}")) for name in
              (*spinup_names, "pre_dam_years", "post_dam_years")}
    for name, value in values.items():
        if value < 0 or post.scalar(f"/mf6_parameters/{name}") != value:
            raise ValueError(f"Paired handoffs have an invalid or inconsistent {name} value.")
    if values["pre_dam_years"] + values["post_dam_years"] < 1:
        raise ValueError("At least one monitored pre- or post-dam year is required.")
    backup = _prepare_runs_workspace(workspace)
    if backup is not None:
        print(f"Archived existing run outputs at {backup}.")
    print(f"Annual MF6 workspaces will be staged under {Path(staging_root).expanduser().resolve()}.")
    profile_description = ("COMPLEX initialization, MODERATE restarts"
                           if solver_profile == "balanced" else "COMPLEX for every solve")
    print(f"IMS solver profile: {solver_profile} ({profile_description}).")

    heads = _default_heads(pre)
    stages = wc = None
    spinup_rows: list[dict] = []
    spinup_counts = {name: values[name] for name in spinup_names}
    if sum(spinup_counts.values()):
        if spinup_counts["fall_average_spinup_years"]:
            relaxation_schedule = _fall_average_forcing_schedule(pre, 7.0)
            relaxation_ws = workspace / "spinup" / "initial_relaxation"
            heads, stages, wc = _run_year(
                pre_path, pre, relaxation_ws, heads, stages, wc,
                save_monitoring=True, staging_root=Path(staging_root),
                phase="initial_relaxation", year=1,
                runtime_schedule=relaxation_schedule,
                solver_profile=solver_profile,
                save_inner_iterations=save_inner_iterations)
            print("Completed 7-day initial relaxation with September--November average forcing.")
        schedule, metadata = _staged_spinup_schedule(pre, spinup_counts)
        spinup_ws = workspace / "spinup" / "staged"
        initial_heads, initial_stages = heads, stages
        heads, stages, wc = _run_year(pre_path, pre, spinup_ws, heads, stages, wc,
                                      save_monitoring=True, staging_root=Path(staging_root),
                                      phase="spinup", year=1, runtime_schedule=schedule,
                                      solver_profile=solver_profile,
                                      save_inner_iterations=save_inner_iterations)
        spinup_rows.extend(_period_rows(pre, spinup_ws, initial_heads, initial_stages,
                                        metadata[0].phase, metadata[0].stage_year, 0.0,
                                        include_initial=True, runtime_schedule=schedule,
                                        step_metadata=metadata))
        print("Completed continuous staged pre-dam spinup: "
              f"fall-average years={values['fall_average_spinup_years']}, "
              f"monthly years={values['monthly_spinup_years']}, "
              f"weekly years={values['weekly_spinup_years']}.")

    rows: list[dict] = []
    elapsed_days = 0.0
    for year in range(1, values["pre_dam_years"] + 1):
        run_ws = workspace / "pre_dam" / f"year_{year:02d}"
        include_initial = year == 1
        initial_heads, initial_stages = heads, stages
        heads, stages, wc = _run_year(pre_path, pre, run_ws, heads, stages, wc,
                                      save_monitoring=True, staging_root=Path(staging_root),
                                      phase="pre_dam", year=year, solver_profile=solver_profile,
                                      save_inner_iterations=save_inner_iterations)
        rows.extend(_period_rows(pre, run_ws, initial_heads, initial_stages,
                                 "pre_dam", year, elapsed_days, include_initial))
        elapsed_days += float(np.sum(pre.array("/calendar/perlen_days").ravel()))

    if values["post_dam_years"]:
        # Dam installation changes only LAK/UZF topology. Groundwater heads are
        # carried exactly; common UZF features are mapped by cell; and both new
        # lakes inherit the final pre-dam river stage.
        inherited_stage = (float(stages[0]) if stages is not None else
                           pre.scalar("/surface_water/lakes/lake_1/initial_stage_m"))
        stages = np.repeat(inherited_stage, int(post.scalar("/surface_water/n_lakes")))
        wc = _map_uzf_state(pre, post, wc)
    for year in range(1, values["post_dam_years"] + 1):
        run_ws = workspace / "post_dam" / f"year_{year:02d}"
        initial_heads, initial_stages = heads, stages
        heads, stages, wc = _run_year(post_path, post, run_ws, heads, stages, wc,
                                      save_monitoring=True, staging_root=Path(staging_root),
                                      phase="post_dam", year=year, solver_profile=solver_profile,
                                      save_inner_iterations=save_inner_iterations)
        rows.extend(_period_rows(post, run_ws, initial_heads, initial_stages,
                                 "post_dam", year, elapsed_days, include_initial=(year == 1)))
        elapsed_days += float(np.sum(post.array("/calendar/perlen_days").ravel()))
    _write_summary(workspace / "spinup_summary.csv", spinup_rows)
    _write_summary(workspace / f"{pre.manifest['time_resolution']}_summary.csv", rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, help="sole input: preparation_handoff.h5")
    parser.add_argument("--staging-root", type=Path, default=None,
                        help="local scratch directory for annual MF6 workspaces (default: system temporary directory)")
    parser.add_argument("--solver-profile", choices=sorted(SOLVER_PROFILES), default="balanced",
                        help="IMS tuning policy (default: balanced; use conservative if a restart fails)")
    parser.add_argument("--solver-inner-output", action="store_true",
                        help="also save detailed inner-iteration CSV diagnostics")
    args = parser.parse_args()
    run_from_handoff(args.handoff, staging_root=args.staging_root,
                     solver_profile=args.solver_profile,
                     save_inner_iterations=args.solver_inner_output)


if __name__ == "__main__":
    main()
