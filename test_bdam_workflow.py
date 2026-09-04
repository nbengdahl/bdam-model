#!/usr/bin/env python3
"""Fast workflow tests; this module never launches MODFLOW 6."""
from __future__ import annotations

import csv
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import numpy as np

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "bdam-matplotlib"))

from build_bdam_simulation import (  # noqa: E402
    MONITORING_OUTPUTS,
    SOLVER_INNER_OUTPUT,
    SOLVER_OUTER_OUTPUT,
    SOLVER_STATS_OUTPUT,
    _create_staging_workspace,
    _duration_weighted_period_means,
    _execute_mf6,
    _next_backup_path,
    _positive_integer,
    _prepare_runs_workspace,
    _publish_workspace,
    _solver_settings,
    _validate_calendar,
    _validate_monitoring_outputs,
    _write_solver_stats,
    _write_summary,
    run_from_handoff,
)


class BDamWorkflowTests(unittest.TestCase):
    def test_solver_profiles_preserve_strict_tolerances(self) -> None:
        balanced = _solver_settings("balanced")
        balanced_initial = _solver_settings("balanced", robust_initialization=True)
        conservative = _solver_settings("conservative", save_inner_iterations=True)
        self.assertEqual(balanced["complexity"], "MODERATE")
        self.assertEqual(conservative["complexity"], "COMPLEX")
        for settings in (balanced, conservative):
            self.assertEqual(settings["outer_dvclose"], 1.0e-5)
            self.assertEqual(settings["inner_dvclose"], 1.0e-6)
            self.assertEqual(settings["rcloserecord"], "1e-6 strict")
            self.assertEqual(settings["linear_acceleration"], "BICGSTAB")
            self.assertEqual(settings["csv_outer_output_filerecord"], SOLVER_OUTER_OUTPUT)
        self.assertNotIn("csv_inner_output_filerecord", balanced)
        self.assertEqual(conservative["csv_inner_output_filerecord"], SOLVER_INNER_OUTPUT)
        self.assertEqual(balanced_initial["complexity"], "COMPLEX")
        with self.assertRaises(ValueError):
            _solver_settings("unknown")

    def test_uzf_wave_capacities_are_positive_integers(self) -> None:
        self.assertEqual(_positive_integer(7.0, "uzf_ntrailwaves"), 7)
        self.assertEqual(_positive_integer(20.0, "uzf_nwavesets"), 20)
        for invalid in (0.0, -1.0, 20.5, np.nan):
            with self.assertRaises(ValueError):
                _positive_integer(invalid, "uzf_nwavesets")

    def test_solver_statistics_capture_iterations_memory_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "mfsim.lst").write_text(
                "MODFLOW 6\nVERSION 6.7.0 02/05/2026\n"
                "MEMORY MANAGER TOTAL STORAGE BY DATA TYPE, IN MEGABYTES\n"
                " Total            289.30164     \n"
                "Normal termination of simulation.\n"
            )
            with (workspace / SOLVER_OUTER_OUTPUT).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "total_inner_iterations", "kper", "kstp", "nouter"])
                writer.writeheader()
                writer.writerow({"total_inner_iterations": 4, "kper": 1, "kstp": 1, "nouter": 1})
                writer.writerow({"total_inner_iterations": 7, "kper": 1, "kstp": 1, "nouter": 2})
                writer.writerow({"total_inner_iterations": 9, "kper": 2, "kstp": 1, "nouter": 1})
            _write_solver_stats(workspace, "balanced", 7, 20, 12.5, False, True)
            stats = __import__("json").loads((workspace / SOLVER_STATS_OUTPUT).read_text())
            self.assertEqual(stats["solver_profile"], "balanced")
            self.assertEqual(stats["ims_complexity"], "COMPLEX")
            self.assertEqual(stats["solver_variant"], "robust_initialization")
            self.assertEqual(stats["mf6_version"], "6.7.0")
            self.assertEqual(stats["time_step_count"], 2)
            self.assertEqual(stats["total_outer_iterations"], 3)
            self.assertEqual(stats["total_inner_iterations"], 9)
            self.assertEqual(stats["maximum_outer_iterations_per_time_step"], 2)
            self.assertGreater(stats["reported_memory_allocation_bytes"], 289 * 1024 ** 2)

    def test_daily_and_weekly_calendars_have_one_step_per_period(self) -> None:
        _validate_calendar(np.ones(365), np.ones(365, int), "daily")
        _validate_calendar(np.full(52, 365.0 / 52.0), np.ones(52, int), "weekly")
        with self.assertRaises(ValueError):
            _validate_calendar(np.full(52, 7.0), np.ones(52, int), "weekly")
        with self.assertRaises(ValueError):
            _validate_calendar(np.ones(365), np.full(365, 2), "daily")

    def test_duration_weighted_weekly_means_preserve_annual_volume(self) -> None:
        daily_edges = np.arange(366, dtype=float)
        daily_rates = 1.0 + np.arange(365, dtype=float) / 365.0
        weekly_edges = np.linspace(0.0, 365.0, 53)
        weekly = _duration_weighted_period_means(daily_edges, daily_rates, weekly_edges)
        self.assertAlmostEqual(
            float(np.sum(daily_rates)),
            float(np.sum(weekly * np.diff(weekly_edges))),
            places=10,
        )

    def test_backup_path_is_timestamped_and_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory) / "Runs"
            moment = dt.datetime(2026, 8, 20, 12, 34, 56)
            first = _next_backup_path(runs, moment)
            self.assertEqual(first.name, "Runs_backup_20260820_123456")
            first.mkdir()
            self.assertEqual(_next_backup_path(runs, moment).name, "Runs_backup_20260820_123456_02")

    def test_existing_runs_are_archived_without_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory) / "Runs"
            runs.mkdir()
            (runs / "evidence.txt").write_text("preserve me")
            backup = _prepare_runs_workspace(runs)
            self.assertIsNotNone(backup)
            self.assertEqual((backup / "evidence.txt").read_text(), "preserve me")
            self.assertTrue(runs.is_dir())
            self.assertEqual(list(runs.iterdir()), [])

    def test_staging_workspace_is_created_under_requested_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _create_staging_workspace(Path(directory), "pre_dam", 2)
            self.assertEqual(workspace.parent, Path(directory).resolve())
            self.assertTrue(workspace.name.startswith("bdam-pre_dam-year_02-"))

    def test_successful_publication_validates_copy_before_exposing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "result.bin").write_bytes(b"closed output")
            final = root / "Runs" / "pre_dam" / "year_01"
            validated = []

            def validator(path: Path) -> None:
                validated.append(path)
                self.assertEqual((path / "result.bin").read_bytes(), b"closed output")

            _publish_workspace(stage, final, validator)
            self.assertEqual(len(validated), 1)
            self.assertTrue(final.is_dir())
            self.assertFalse(stage.exists())

    def test_blocking_process_contract_uses_exit_code_and_listing_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "mfsim.lst").write_text("Normal termination of simulation.\n")
            completed = CompletedProcess(["mf6"], 0, "normal stdout")
            with patch("build_bdam_simulation._mf6_executable", return_value=Path("/fake/mf6")):
                with patch("build_bdam_simulation.subprocess.run", return_value=completed) as runner:
                    _execute_mf6(workspace)
            self.assertEqual(runner.call_args.kwargs["cwd"], workspace)
            self.assertFalse(runner.call_args.kwargs["check"])
            (workspace / "mfsim.lst").write_text("incomplete run\n")
            with patch("build_bdam_simulation._mf6_executable", return_value=Path("/fake/mf6")):
                with patch("build_bdam_simulation.subprocess.run", return_value=completed):
                    with self.assertRaises(RuntimeError):
                        _execute_mf6(workspace)

    def test_uzf_wave_capacity_failure_has_actionable_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            completed = CompletedProcess(
                ["mf6"], 1, "ERROR: UZF variable NWAVESETS needs to be increased.")
            with patch("build_bdam_simulation._mf6_executable", return_value=Path("/fake/mf6")):
                with patch("build_bdam_simulation.subprocess.run", return_value=completed):
                    with self.assertRaisesRegex(RuntimeError, "from 20 to 40"):
                        _execute_mf6(workspace)

    def test_failed_publication_retains_staging_and_hides_final_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "result.bin").write_bytes(b"bad output")
            final = root / "Runs" / "pre_dam" / "year_01"

            def reject(_: Path) -> None:
                raise RuntimeError("synthetic validation failure")

            with self.assertRaises(RuntimeError):
                _publish_workspace(stage, final, reject)
            self.assertTrue(stage.is_dir())
            self.assertFalse(final.exists())
            self.assertTrue(any(final.parent.glob(".year_01.publishing-*")))

    def test_monitoring_rules_distinguish_spinup_and_monitored_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            _validate_monitoring_outputs(workspace, 365.0, enabled=False)
            for name in MONITORING_OUTPUTS:
                with (workspace / name).open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["time", "value"])
                    writer.writeheader()
                    writer.writerow({"time": 365.0, "value": 1.0})
            _validate_monitoring_outputs(workspace, 365.0, enabled=True)
            with self.assertRaises(RuntimeError):
                _validate_monitoring_outputs(workspace, 365.0, enabled=False)

    def test_summary_writer_preserves_initial_and_completed_step_rows(self) -> None:
        rows = [
            {"phase": "pre_dam", "event": "initial", "time_days": 0.0},
            {"phase": "pre_dam", "event": "completed_step", "time_days": 365.0 / 52.0},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekly_summary.csv"
            _write_summary(path, rows)
            with path.open(newline="") as stream:
                written = list(csv.DictReader(stream))
        self.assertEqual([row["event"] for row in written], ["initial", "completed_step"])

    def test_zero_spinup_starts_first_monitored_year_directly(self) -> None:
        class FakeHandoff:
            def __init__(self, scenario: str) -> None:
                self.manifest = {"scenario": scenario, "time_resolution": "weekly"}

            def scalar(self, path: str) -> float:
                values = {
                    "/mf6_parameters/mean_forcing_spinup_years": 0,
                    "/mf6_parameters/monthly_spinup_years": 0,
                    "/mf6_parameters/weekly_spinup_years": 0,
                    "/mf6_parameters/pre_dam_years": 1,
                    "/mf6_parameters/post_dam_years": 0,
                }
                return values[path]

            def array(self, path: str, dtype=float) -> np.ndarray:
                self.assert_calendar_path(path)
                return np.asarray([365.0], dtype=dtype)

            @staticmethod
            def assert_calendar_path(path: str) -> None:
                if path != "/calendar/perlen_days":
                    raise AssertionError(f"Unexpected array request: {path}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_input = root / "ModelInput"
            for scenario in ("pre_dam", "post_dam"):
                scenario_path = model_input / scenario
                scenario_path.mkdir(parents=True)
                (scenario_path / "preparation_handoff.h5").touch()
            pre = FakeHandoff("pre_dam")
            post = FakeHandoff("post_dam")
            initial_heads = np.ones((1, 1, 1))
            completed_heads = initial_heads + 1.0
            summary_rows = [{"phase": "pre_dam", "event": "initial", "time_days": 0.0}]
            written: dict[str, list[dict]] = {}

            with patch("build_bdam_simulation.load_handoff", side_effect=[pre, post]):
                with patch("build_bdam_simulation._default_heads", return_value=initial_heads):
                    with patch("build_bdam_simulation._staged_spinup_schedule") as staged:
                        with patch("build_bdam_simulation._run_year", return_value=(
                                completed_heads, np.asarray([2.0]), np.asarray([0.15]))) as run_year:
                            with patch("build_bdam_simulation._period_rows", return_value=summary_rows):
                                with patch("build_bdam_simulation._write_summary",
                                           side_effect=lambda path, rows: written.__setitem__(path.name, rows)):
                                    run_from_handoff(model_input, staging_root=root / "staging",
                                                     solver_profile="conservative",
                                                     save_inner_iterations=True)

            staged.assert_not_called()
            self.assertEqual(run_year.call_count, 1)
            self.assertEqual(run_year.call_args.kwargs["phase"], "pre_dam")
            self.assertEqual(run_year.call_args.kwargs["solver_profile"], "conservative")
            self.assertTrue(run_year.call_args.kwargs["save_inner_iterations"])
            self.assertEqual(written["spinup_summary.csv"], [])
            self.assertEqual(written["weekly_summary.csv"], summary_rows)

    def test_packaged_terrain_defaults_remain_synchronized(self) -> None:
        package = Path(__file__).resolve().parent
        script = (package / "MakeGrid.m").read_text()
        app = (package / "BDamTerrainApp.m").read_text()
        self.assertTrue((package / "MakeInputs.m").is_file())
        for expected in (
            "parameters.domain_length_x_m = 50;",
            "parameters.domain_length_y_m = 100;",
            "parameters.sine_periods = 1;",
            "parameters.sine_amplitude_m = 5;",
            "parameters.regional_longitudinal_slope = 0.005;",
        ):
            self.assertIn(expected, script)
        for expected in (
            '"Domain X length (m)",50',
            '"Domain Y length (m)",100',
            '"Sine-wave periods",1',
            '"Meander amplitude (m)",5',
            '"Regional Y slope",0.005',
        ):
            self.assertIn(expected, app)


if __name__ == "__main__":
    unittest.main()
