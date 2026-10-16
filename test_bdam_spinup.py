"""Fast convergence, annual orchestration and study continuation tests; no MF6."""
import contextlib
import csv
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import numpy as np

import bdam
import bdam_runtime as rt
import bdam_spinup as sp
import build_bdam_simulation as model

HERE = Path(__file__).resolve().parent


class CriteriaTests(unittest.TestCase):
    def test_standalone_exit_code_is_specific_to_dnc(self):
        with patch.object(model, 'main', side_effect=sp.SpinupDidNotConverge('DNC')):
            with self.assertRaises(SystemExit) as stopped:
                model.cli()
        self.assertEqual(stopped.exception.code, 3)
        with patch.object(model, 'main', side_effect=ValueError('bad input')):
            with self.assertRaises(ValueError):
                model.cli()

    def test_references_match_mf6_orientation_and_local_lake_bed(self):
        class Handoff:
            def array(self, path, dtype=float):
                values = {'/grid/Z': np.arange(12).reshape(2, 2, 3),
                          '/grid/ZTop': np.array([[10., 11.], [12., 13.]]),
                          '/surface_water/lakes/lake_1/footprint_mask': [[0, 1], [0, 1]]}
                return np.asarray(values[path], dtype=dtype)
            def scalar(self, path):
                return 1
        refs = sp.references(Handoff())
        np.testing.assert_array_equal(refs[0], model.mf3(Handoff().array('/grid/Z')[:, :, :-1]))
        np.testing.assert_array_equal(refs[1], [11.])

    def test_relative_formula_floors_symmetry_and_datum(self):
        old, new, ref = np.array([0., 10.]), np.array([.001, 10.01]), np.zeros(2)
        result = sp.metric(old, new, ref, 1.)
        self.assertAlmostEqual(result['relative_max'], .001)
        self.assertEqual(result['controlling_index'], [0])
        self.assertAlmostEqual(result['absolute_max'], .01)
        self.assertEqual(result, sp.metric(new, old, ref, 1.))
        shifted = sp.metric(old+1000, new+1000, ref+1000, 1.)
        self.assertAlmostEqual(result['relative_max'], shifted['relative_max'])

    def test_each_criterion_and_exact_threshold(self):
        config = sp.settings({})
        old = (np.zeros((1, 1, 2)), np.zeros(2), np.zeros(2))
        refs = (np.zeros((1, 1, 2)), np.zeros(2), 0.)
        for index, name in enumerate(sp.FLOORS):
            for factor, passed in ((1., True), (1.001, False)):
                current = [a.copy() for a in old]
                current[index].flat[-1] = config[f'spinup_{name}_relative_tolerance']*sp.FLOORS[name]*factor
                row = sp.comparison(old, current, refs, config)
                self.assertEqual(row['passed'], passed)
                self.assertEqual(row[f'{name}_pass'], passed)
                self.assertEqual(row[f'{name}_controlling_index'][-1], 1)

    def test_invalid_states_and_shapes(self):
        for value in (np.nan, np.inf, -1e30, 1e30):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sp.metric(np.array([value]), np.array([value]), 0., 1.)
        with self.assertRaises(ValueError):
            sp.metric(np.ones(2), np.ones(3), 0., 1.)

    def test_config_and_boolean_csv_roundtrip(self):
        schema = bdam.load_schema(HERE)
        resolved = bdam.resolve_case({}, {}, schema)
        self.assertEqual(sp.settings(resolved['mf6_parameters']), sp.DEFAULTS)
        for field, value in (('spinup_until_converged', 'true'), ('spinup_until_converged', 1),
                             ('spinup_max_weekly_years', 2), ('spinup_head_relative_tolerance', 0),
                             ('spinup_stage_relative_tolerance', np.inf),
                             ('spinup_water_content_relative_tolerance', True)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                bdam.resolve_case({'mf6_parameters.'+field: value}, {}, schema)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'cases.csv'
            path.write_text('case_id,mf6_parameters.spinup_until_converged\na,true\nb,false\n')
            rows = bdam.read_cases(path)
            self.assertEqual([r['mf6_parameters.spinup_until_converged'] for r in rows], [True, False])
            self.assertTrue(bdam.resolve_case({'mf6_parameters.spinup_until_converged': True}, {}, schema)['mf6_parameters']['spinup_until_converged'])


class OrchestrationTests(unittest.TestCase):
    def exercise(self, changes, cap, monthly=0, diagnostic=False):
        config = sp.settings(dict(spinup_until_converged=True, spinup_max_weekly_years=cap))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        model_input = root/'ModelInput'
        for phase in ('pre_dam', 'post_dam'):
            (model_input/phase).mkdir(parents=True)
            (model_input/phase/'preparation_handoff.h5').touch()

        class Handoff:
            def __init__(self, phase):
                self.manifest = dict(scenario=phase, time_resolution='daily')

            def scalar(self, path):
                return dict(fall_average_spinup_years=0, monthly_spinup_years=monthly,
                            weekly_spinup_years=9, pre_dam_years=1, post_dam_years=0)[path.split('/')[-1]]

            def array(self, path):
                return np.ones(365)

        schedule = model.RuntimeSchedule(np.full(52, 365/52), np.ones(52, int),
                                         np.linspace(0, 365, 53), {}, np.zeros((1, 53)))
        calls, weekly = [], []

        def run(*args, **kwargs):
            phase = kwargs.get('phase', args[9] if len(args) > 9 else '')
            heads = args[3].copy()
            if phase == 'spinup_weekly':
                heads += changes[len(weekly)]
                weekly.append((args, kwargs))
            calls.append((phase, args, kwargs))
            return heads, np.array([.2]), np.array([.15])

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sp, 'handoff_settings', return_value=config))
            stack.enter_context(patch.object(sp, 'references', return_value=(np.zeros((1, 1, 1)), np.zeros(1), 0.)))
            stack.enter_context(patch.object(model, 'load_handoff', side_effect=[Handoff('pre_dam'), Handoff('post_dam')]))
            stack.enter_context(patch.object(model, '_default_heads', return_value=np.ones((1, 1, 1))))
            stack.enter_context(patch.object(model, '_run_year', side_effect=run))
            stack.enter_context(patch.object(model, '_period_rows', return_value=[dict(time_days=365)]))
            stack.enter_context(patch.object(model, '_staged_spinup_schedule', return_value=(schedule, [model.SpinupStep('spinup_monthly', 'monthly', 1, 365.)])))
            stack.enter_context(patch.object(model, '_split_first_spinup_year', return_value=(schedule, [model.SpinupStep('spinup_monthly', 'monthly', 1, 365.)], None, [])))
            try:
                model.run_from_handoff(model_input, stop_after_monthly_spinup=diagnostic)
                outcome = 'converged'
            except sp.SpinupDidNotConverge:
                outcome = 'DNC'
        return root, config, calls, weekly, outcome

    def test_earliest_stop_restart_and_weekly_schedule_with_daily_monitoring(self):
        root, cfg, calls, weekly, outcome = self.exercise([.1, 0, 0], 10)
        self.assertEqual(outcome, 'converged')
        self.assertEqual(len(weekly), 3)
        self.assertEqual(calls[-1][0], 'pre_dam')
        self.assertEqual(weekly[0][1]['solver_profile'], 'conservative')
        self.assertEqual(weekly[1][1]['solver_profile'], 'balanced')
        np.testing.assert_array_equal(weekly[1][0][3], np.full((1, 1, 1), 1.1))
        np.testing.assert_array_equal(calls[-1][1][3], np.full((1, 1, 1), 1.1))
        self.assertEqual(len(weekly[0][1]['runtime_schedule'].perlen_days), 52)
        self.assertAlmostEqual(sum(weekly[0][1]['runtime_schedule'].perlen_days), 365)
        report = sp.validate_report(root/'Runs', cfg)
        self.assertEqual(report['years_completed'], 3)
        schema = bdam.load_schema(HERE)
        resolved = bdam.resolve_case({'mf6_parameters': dict(cfg, monthly_spinup_years=0, pre_dam_years=1, post_dam_years=0)}, {}, schema)
        rt.write(root/'resolved_config.json', resolved)
        self.assertEqual(rt.expected_workspaces(root), [(f'spinup/weekly/year_{i:02d}', 'pre_dam', 365., 52) for i in range(1, 4)]+[('pre_dam/year_01', 'pre_dam', 365., 52)])

    def test_failure_resets_streak_and_cap_skips_monitoring(self):
        root, cfg, calls, weekly, outcome = self.exercise([0, 0, .1, 0], 4)
        self.assertEqual(outcome, 'DNC')
        self.assertEqual(len(weekly), 4)
        self.assertNotIn('pre_dam', [c[0] for c in calls])
        report = sp.validate_report(root/'Runs', cfg, require_converged=False)
        self.assertEqual([r['consecutive_passes'] for r in report['comparisons']], [0, 1, 0, 1])
        with self.assertRaises(ValueError):
            sp.validate_report(root/'Runs', cfg)
        self.assertTrue((root/'Runs/spinup_summary.csv').is_file())
        self.assertFalse((root/'completion.json').exists())

    def test_warmup_does_not_count_and_monthly_diagnostic_does_not_certify(self):
        root, cfg, calls, weekly, outcome = self.exercise([0, 0, 0], 3, monthly=1)
        self.assertEqual(calls[0][0], 'spinup_first_annual')
        self.assertEqual(weekly[0][1]['solver_profile'], 'balanced')
        self.assertEqual(len(weekly), 3)
        diagnostic, _, calls, weekly, _ = self.exercise([], 3, monthly=1, diagnostic=True)
        self.assertEqual(len(weekly), 0)
        self.assertFalse((diagnostic/'Runs/spinup_convergence.json').exists())

    def test_reports_reject_tampering_and_recompute_retained_states(self):
        root, cfg, _, _, _ = self.exercise([0, 0, 0], 3)
        report = sp.validate_report(root/'Runs', cfg)
        states = {relative.replace('/', '_')+'_'+key: value
                  for relative in report['weekly_workspaces']
                  for key, value in zip(('heads', 'stages', 'water_content'),
                                        (np.ones((1, 1, 1)), np.array([.2]), np.array([.15])))}
        with patch.object(sp, 'references', return_value=(np.zeros((1, 1, 1)), np.zeros(1), 0.)):
            sp.validate_states(report, None, states)
            states['spinup_weekly_year_03_heads'] += .1
            with self.assertRaises(ValueError):
                sp.validate_states(report, None, states)
        (root/'Runs/spinup_convergence.csv').write_text('tampered')
        with self.assertRaises(ValueError):
            sp.validate_report(root/'Runs', cfg)

    def test_compact_reuse_rechecks_retained_convergence_evidence(self):
        root, cfg, _, _, _ = self.exercise([0, 0, 0], 3)
        report = sp.validate_report(root/'Runs', cfg)
        states = {relative.replace('/', '_')+'_'+key: value
                  for relative in report['weekly_workspaces']
                  for key, value in zip(('heads', 'stages', 'water_content'),
                                        (np.ones((1, 1, 1)), np.array([.2]), np.array([.15])))}
        rt.write(root/'resolved_config.json', dict(mf6_parameters=cfg))
        rt.write(root/'prepared.json', dict(handoff_hashes={}))
        def receipt():
            np.savez_compressed(root/'Runs/restart_states.npz', **states)
            rt.write(root/'completion.json', dict(fingerprint='test', status='pass', retention='compact',
                                                result_hashes=rt.result_hashes(root)))
        receipt()
        with patch.object(rt, 'verify_snapshot'), patch.object(model, 'load_handoff'), patch.object(
                sp, 'references', return_value=(np.zeros((1, 1, 1)), np.zeros(1), 0.)):
            self.assertTrue(rt.complete(root, 'test'))
            states['spinup_weekly_year_03_heads'] += .1
            receipt()  # Even matching hashes cannot hide inconsistent convergence evidence.
            self.assertFalse(rt.complete(root, 'test'))


class StudyTests(unittest.TestCase):
    def test_dnc_exit_maps_to_case_status_and_next_member_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            study = bdam.Study(Path(folder)/'study', dict(source=str(HERE)))
            batch = study.submit([dict(case_id='dnc', mf6_parameters=dict(spinup_until_converged=True)),
                                  dict(case_id='next', K_constant=.04)], 'batch')
            member, next_member = batch['members']
            path = Path(member['path'])
            config = sp.settings(rt.read(path/'resolved_config.json')['mf6_parameters'])
            (path/'Runs').mkdir()
            rows = [dict(weekly_year=1, passed=False, consecutive_passes=0)]
            previous = (np.ones((1, 1, 1)), np.ones(1), np.ones(1))
            for year in range(2, 11):
                row = sp.comparison(previous, tuple(v+year for v in previous), (0., 0., 0.), config)
                rows.append(dict(row, weekly_year=year, consecutive_passes=0))
            # Create the report inside the mocked runner, after archival of prior Runs.
            def process(*args, **kwargs):
                (path/'Runs').mkdir(exist_ok=True)
                sp.write_report(path/'Runs', config, rows, 'DNC')
                return CompletedProcess(args[0], sp.DNC_EXIT_CODE)

            rt.write(path/'prepared.json', dict(fingerprint=member['fingerprint'], handoff_hashes={}))
            with patch.object(rt.subprocess, 'run', side_effect=process):
                status = rt.run_member(dict(root=str(study.root)), member)
            self.assertEqual(status['status'], 'DNC')
            self.assertFalse((path/'completion.json').exists())
            self.assertFalse(rt.complete(path, member['fingerprint']))
            for m in batch['members']:
                rt.write(Path(m['path'])/'prepared.json', {})
            evaluated = []
            def evaluate(manifest, candidate, retention):
                evaluated.append(candidate['id'])
                return dict(status='DNC' if candidate['id']==member['id'] else 'pass')
            with patch.object(study, 'prepare'), patch.object(rt, 'run_member', side_effect=evaluate):
                result = study.evaluate('batch')
            self.assertEqual(evaluated, [member['id'], next_member['id']])
            self.assertEqual(result[0]['status'], 'DNC')
            self.assertEqual(result[0]['error']['phase'], 'spinup')
            with (study.root/'results/batch/case_index.csv').open() as stream:
                self.assertEqual(list(csv.DictReader(stream))[0]['status'], 'DNC')


if __name__ == '__main__':
    unittest.main()
