#!/usr/bin/env python3
"""Four bounded short numerical configurations, separate from production receipts.

Optional --baseline-source uses a preserved pre-feature source copy to prepare
and run the zero configuration for comparison. This is a reference replay within
the zero test, not an additional parameter configuration. Every solve has two
one-day periods. The four configured pre/post pairs run serially by default.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import bdam
import bdam_runtime as rt
import build_bdam_simulation as model

CASES = {'zero': (0., 0., 0.), 'inflow': (3., 5., 7.),
         'outflow': (-3., -5., -7.), 'mixed': (3., -5., 7.)}
FORCING = ('upstream_inflow_m3_per_day', 'land_recharge_m_per_day', 'land_et_m_per_day',
           'lake_precipitation_m_per_day', 'lake_evaporation_m_per_day')


def short_schedule(module, handoff):
    # Repeat the first (October) exported forcing rate for both short periods.
    return module.RuntimeSchedule(np.ones(2), np.ones(2, dtype=int), np.arange(3.),
        {name: np.repeat(handoff.array(f'/forcing/{name}').ravel()[0], 3) for name in FORCING},
        np.repeat(handoff.array('/boundaries/groundwater/reference_level_m')[:, :1], 3, axis=1))


def run_pair(module, model_input, output):
    output.mkdir(parents=True, exist_ok=False)
    pre_path, post_path = [model_input / phase / 'preparation_handoff.h5' for phase in ('pre_dam', 'post_dam')]
    pre, post = module.load_handoff(pre_path), module.load_handoff(post_path)
    heads = module._planar_initial_heads(pre)
    stages = wc = None
    summaries = []
    for index, (phase, handoff, path) in enumerate((('pre_dam', pre, pre_path), ('post_dam', post, post_path))):
        if index:
            stages = module._coarse_restart_stages(pre, post, stages, output)
            wc = module._map_uzf_state(pre, post, wc)
        start_heads, start_stages = heads, stages
        schedule = short_schedule(module, handoff)
        workspace = output / phase
        heads, stages, wc = module._run_year(path, handoff, workspace, heads, stages, wc,
            True, output / 'staging', phase, 1, runtime_schedule=schedule,
            solver_profile='conservative' if index == 0 else 'balanced')
        summaries.extend(module._period_rows(handoff, workspace, start_heads, start_stages,
            phase, 1, index * 2., True, runtime_schedule=schedule))
        with module.flopy.utils.HeadFile(workspace / 'bdam.hds') as reader:
            if reader.get_times() != [1., 2.]:
                raise AssertionError('Short verification requires exactly two saved steps per phase.')
    module._write_summary(output / 'short_summary.csv', summaries)
    return {phase: json.loads((output / phase / 'bdam.water_balance.json').read_text())
            for phase in ('pre_dam', 'post_dam')}


def verify_reporting(output, totals):
    """Verify gross reporting and downstream-only fields without another solve."""
    edge_in, edge_out = sum(max(q, 0.) for q in totals), sum(max(-q, 0.) for q in totals)
    with (output / 'short_summary.csv').open() as stream:
        summary = list(csv.DictReader(stream))
    for phase in ('pre_dam', 'post_dam'):
        ws = output / phase
        with (ws / model.FLUX_OUTPUT).open() as stream:
            rows = list(csv.DictReader(stream))
        with (ws / 'bdam.groundwater_boundary_flux.csv').open() as stream:
            downstream_observations = list(csv.DictReader(stream))
        with model.flopy.utils.CellBudgetFile(ws / 'bdam.cbc', precision='double') as budget:
            term = model._groundwater_boundary_budget_term(budget)
            for row, observation in zip(rows, downstream_observations):
                time, duration = float(row['time']), float(row['duration_days'])
                downstream_in, downstream_out = model._gross_budget_flows(budget, term, time)
                expected = {'specified_groundwater_inflow': edge_in,
                    'specified_groundwater_outflow': edge_out,
                    'groundwater_boundary_inflow': downstream_in + edge_in,
                    'groundwater_boundary_outflow': downstream_out + edge_out,
                    'drain_outflow': downstream_out if term == 'DRN' else 0.,
                    'ghb_inflow': downstream_in if term == 'GHB' else 0.,
                    'ghb_outflow': downstream_out if term == 'GHB' else 0.,
                    **{f'specified_{edge}_net': q for edge, q in zip(model.EDGE_NAMES, totals)}}
                for name, rate in expected.items():
                    np.testing.assert_allclose(float(row[f'{name}_m3_per_day']), rate, atol=1e-9, rtol=1e-10)
                    np.testing.assert_allclose(float(row[f'{name}_m3']), rate * duration, atol=1e-9, rtol=1e-10)
                observed = float(next(v for k, v in observation.items() if k.upper() != 'TIME'))
                np.testing.assert_allclose(observed, downstream_in - downstream_out, atol=1e-8, rtol=1e-10)
                selected = [r for r in summary if r['phase'] == phase and r['event'] == 'completed_step'
                            and float(r['phase_time_days']) == time]
                if len(selected) != 1:
                    raise AssertionError('Expected exactly one matching summary interval.')
                np.testing.assert_allclose(float(selected[0]['groundwater_boundary_net_volume_m3']),
                    (downstream_in - downstream_out + sum(totals)) * duration, atol=1e-9, rtol=1e-10)
                np.testing.assert_allclose(float(selected[0]['ghb_net_volume_m3']),
                    (downstream_in - downstream_out) * duration if term == 'GHB' else 0., atol=1e-9)


def compare_prepared_zero(root):
    """Compare all pre-existing physical handoff datasets to the old zero case."""
    current_case = rt.read(root / 'preparation-study/batches/edge-flux.json')['cases'][0]
    reference_case = rt.read(root / 'zero-reference-study/batches/zero.json')['cases'][0]
    compared = 0
    added = []
    for phase in ('pre_dam', 'post_dam'):
        paths = [Path(case['output_path']) / 'ModelInput' / phase / 'preparation_handoff.h5'
                 for case in (current_case, reference_case)]
        with model.h5py.File(paths[0]) as current, model.h5py.File(paths[1]) as reference:
            def datasets(handle):
                result = []
                handle.visititems(lambda name, obj: result.append(name) if isinstance(obj, model.h5py.Dataset) else None)
                return set(result)
            current_names, reference_names = datasets(current), datasets(reference)
            if reference_names - current_names:
                raise AssertionError('Zero-case handoff lost a baseline dataset.')
            extra = current_names - reference_names
            expected_extra = {f'boundaries/edge_flux/{edge}_m3_per_day/{part}'
                              for edge in model.EDGE_NAMES for part in ('data', 'shape')}
            if extra != expected_extra:
                raise AssertionError(f'Unexpected handoff additions: {extra}')
            for name in reference_names:
                np.testing.assert_array_equal(current[name][...], reference[name][...], err_msg=f'{phase}/{name}')
                compared += 1
            added.extend(f'{phase}/{name}' for name in sorted(extra))
    return dict(identical_baseline_datasets=compared, added_edge_datasets=added)


def verify_case(case, totals, member, root):
    output = root / 'short-results' / case
    qa = run_pair(model, Path(member['output_path']) / 'ModelInput', output)
    for phase in ('pre_dam', 'post_dam'):
        ws = output / phase
        with (ws / model.EDGE_FLUX_OUTPUT).open() as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 2:
            raise AssertionError('Incorrect edge monitoring step count.')
        handoff = model.load_handoff(Path(member['output_path']) / 'ModelInput' / phase / 'preparation_handoff.h5')
        expected = model._edge_flux_records(handoff)
        with model.flopy.utils.CellBudgetFile(ws / 'bdam.cbc', precision='double') as budget:
            for time in (1., 2.):
                actual = model._edge_budget_rates(budget, time)
                for edge, total in zip(model.EDGE_NAMES, totals):
                    np.testing.assert_allclose(actual[edge], total, rtol=1e-10, atol=1e-10)
                    records = budget.get_data(text='WEL', paknam2=f'WEL_{edge.upper()}', totim=time)
                    if len(records) != 1:
                        raise AssertionError('Expected one independent budget record per edge.')
                    record = records[0]
                    cells = {tuple(np.unravel_index(int(n) - 1, (5, 140, 70))) for n in record['node']}
                    if cells != {entry[0] for entry in expected[edge]}:
                        raise AssertionError(f'Incorrect bottom-layer edge placement: {edge}')
                    np.testing.assert_allclose(record['q'], total / len(expected[edge]), rtol=1e-10, atol=1e-10)
    verify_reporting(output, totals)
    if list(output.rglob('completion.json')):
        raise AssertionError('Smoke verification must not publish production completion receipts.')
    return dict(totals_m3_per_day=totals, output=str(output), water_balance=qa, saved_steps=4)


def compare_zero(root, baseline_source, matlab):
    baseline_source = rt.local_path(baseline_source)
    reference_root = root / 'zero-reference-study'
    # Run preparation using the preserved baseline's own registry and runtime.
    code = ("import bdam; s=bdam.Study(" + repr(str(reference_root)) + ","
            + repr({'source': str(baseline_source), 'execution': {'matlab': matlab}}) + "); "
            "s.submit([{'case_id':'zero'}],'zero'); s.prepare('zero')")
    subprocess.run([sys.executable, '-c', code], cwd=baseline_source, check=True)
    batch = rt.read(reference_root / 'batches' / 'zero.json')
    member = batch['cases'][0]
    spec = importlib.util.spec_from_file_location('bdam_zero_reference_model', baseline_source / 'build_bdam_simulation.py')
    baseline = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = baseline
    spec.loader.exec_module(baseline)
    reference = root / 'zero-reference-results'
    run_pair(baseline, Path(member['output_path']) / 'ModelInput', reference)
    checked = []
    # New CBC contains additional WEL records; compare unchanged physical states,
    # LAK/UZF budgets and native observations byte for byte.
    names = ('bdam.hds', 'bdam.lak.stage', 'bdam.lak.bud', 'bdam.uzf.wc', 'bdam.uzf.bud',
             'bdam.heads.csv', 'bdam.lake_fluxes.csv', 'bdam.groundwater_boundary_flux.csv')
    for phase in ('pre_dam', 'post_dam'):
        for name in names:
            actual = root / 'short-results' / 'zero' / phase / name
            expected = reference / phase / name
            if actual.read_bytes() != expected.read_bytes():
                raise AssertionError(f'Zero-flux baseline differs: {phase}/{name}')
            checked.append(f'{phase}/{name}')
    return dict(status='identical', compared_files=checked, reference_output=str(reference),
                prepared_handoffs=compare_prepared_zero(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='Fresh local verification directory; must not exist')
    parser.add_argument('--matlab', default='matlab')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=1)
    parser.add_argument('--baseline-source', type=Path, help='Preserved pre-feature local source for zero-case replay')
    args = parser.parse_args()
    root = rt.local_path(args.root)
    rt.local_path(SOURCE)
    if root.exists():
        parser.error('Use a fresh directory to preserve previous verification evidence.')
    root.mkdir(parents=True)
    os.environ.setdefault('BDAM_PYTHON', sys.executable)
    study = bdam.Study(root / 'preparation-study', {'source': str(SOURCE),
        'execution': {'matlab': args.matlab, 'n_parallel_runs': args.workers}})
    batch = study.submit([{'case_id': name, **{f'groundwater_edge_flux.{edge}_m3_per_day': value
        for edge, value in zip(model.EDGE_NAMES, totals)}} for name, totals in CASES.items()], 'edge-flux')
    if len(batch['cases']) != 4 or any(case['status'] == 'failed' for case in batch['cases']):
        raise RuntimeError('Exactly four valid numerical configurations are required.')
    study.prepare('edge-flux')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {name: pool.submit(verify_case, name, totals, member, root)
                   for (name, totals), member in zip(CASES.items(), batch['cases'])}
        cases = {name: future.result() for name, future in futures.items()}
    reference = compare_zero(root, args.baseline_source, args.matlab) if args.baseline_source else None
    receipt = dict(status='pass', kind='short-edge-flux-verification', configuration_count=4,
        max_workers=args.workers, days_per_case=4, production_completion=False,
        feature_native_solves=8, zero_reference_native_solves=2 if reference else 0,
        source=str(SOURCE), python=sys.version, executable=str(model._mf6_executable()),
        mf6_version=subprocess.check_output([str(model._mf6_executable()), '-v'], text=True).strip(),
        cases=cases, zero_baseline=reference)
    rt.write(root / 'edge_flux_verification.json', receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
