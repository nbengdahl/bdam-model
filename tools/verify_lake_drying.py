#!/usr/bin/env python3
"""Bounded full-grid drying/rewetting regression; never a production receipt.

Run from a local source copy after MakeInputs. Three diagnostic workspaces use
two, one, and four seven-day periods, respectively. IMS/budget tolerances
are unchanged; production calendars are not modified.
"""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import build_bdam_simulation as model


def schedule(handoff, inflow, evaporation):
    count = len(inflow)
    forcing = {name: np.zeros(count + 1) for name in (
        'upstream_inflow_m3_per_day', 'land_recharge_m_per_day',
        'land_et_m_per_day', 'lake_precipitation_m_per_day', 'lake_evaporation_m_per_day')}
    forcing['upstream_inflow_m3_per_day'] = np.r_[inflow, inflow[-1]]
    forcing['lake_evaporation_m_per_day'] = np.r_[evaporation, evaporation[-1]]
    # Nonzero external flow avoids an undefined relative closure at zero flow.
    forcing['land_recharge_m_per_day'][:] = .0002
    return model.RuntimeSchedule(np.full(count, 7.), np.ones(count, dtype=int),
        np.arange(count + 1) * 7., forcing,
        np.repeat(handoff.array('/boundaries/groundwater/reference_level_m')[:, :1], count + 1, axis=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--inputs', type=Path, default=SOURCE/'ModelInput')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    for path in (root, SOURCE):
        if any(name in str(path) for name in ("My Drive", "Google Drive", "OneDrive", "Dropbox", "Mobile Documents")):
            raise ValueError("Run only from local nonsynchronized storage.")
    root.mkdir(parents=True, exist_ok=False)
    pre_path, post_path = [args.inputs/phase/'preparation_handoff.h5' for phase in ('pre_dam', 'post_dam')]
    pre, post = map(model.load_handoff, (pre_path, post_path))
    heads = model._planar_initial_heads(pre) - 1.
    stages = model._lake_bottoms(pre)
    wc = None
    rows, budgets = [], {}
    cases = [('pre_dry', pre, pre_path, [0., 0.], [.01, .01]),
             ('pre_restart', pre, pre_path, [0.], [.01]),
             ('post_cycle', post, post_path, [0., .1, 0., 0.], [.01, 0., .05, .1])]
    elapsed = 0.
    for index, (name, handoff, path, inflow, evaporation) in enumerate(cases):
        if index == 2:
            stages = model._coarse_restart_stages(pre, post, stages, root)
            wc = model._map_uzf_state(pre, post, wc)
            audit = json.loads((root/'dam_installation_storage_audit.json').read_text())
            assert audit['before_volume_m3'] == audit['after_volume_m3'] == 0.
        start_heads, start_stages = heads.copy(), stages.copy()
        runtime = schedule(handoff, inflow, evaporation)
        workspace = root/name
        heads, stages, wc = model._run_year(path, handoff, workspace, heads, stages, wc, True,
            root/'staging', name, 1, runtime_schedule=runtime,
            solver_profile='conservative' if index == 0 else 'balanced')
        with (workspace/'bdam.lake_fluxes.csv').open(newline='') as stream:
            observations = list(csv.DictReader(stream))
        assert len(observations) == len(inflow)
        raw_series = model._read_lake_stage_series(workspace/'bdam.lak.stage', len(stages))
        bottoms = model._lake_bottoms(handoff)
        lakes = model._lake_data(handoff, heads.shape[0], heads.shape[1])
        for step, observed in enumerate(observations):
            for lake in range(1, int(handoff.scalar('/surface_water/n_lakes')) + 1):
                volume = float(observed[f'LAKE{lake}_VOLUME'])
                if name == 'post_cycle' and step == 1 and lake == 1:
                    assert volume > 0., 'Pond did not rewet.'
                elif name == 'post_cycle' and step == 2 and lake == 1:
                    # At this rate the implicit end-stage evaporation leaves
                    # real positive water, near the steep first area interval.
                    # This is the previously oscillating MF6 recession case.
                    assert 0. < volume < float(observations[1]['LAKE1_VOLUME'])
                elif name == 'post_cycle' and step == 3:
                    # The final rate can exhaust storage even at onset area.
                    assert_empty(volume, raw_series[step][1][lake-1], bottoms[lake-1], lakes[lake-1])
                else:
                    assert_empty(volume, raw_series[step][1][lake-1], bottoms[lake-1], lakes[lake-1])
        raw = model._read_mf6_array_last(workspace/'bdam.lak.stage', (len(stages),))
        assert np.all(raw == -1e30), 'Expected a genuine MF6 dry state.'
        np.testing.assert_array_equal(stages, model._lake_bottoms(handoff))
        if name == 'post_cycle':
            first_raw = model._read_lake_stage_series(workspace/'bdam.lak.stage', len(stages))[0][1]
            assert np.all(first_raw == -1e30), 'Expected an empty pond after dry installation.'
        rows.extend(model._period_rows(handoff, workspace, start_heads, start_stages, name, 1,
            elapsed, True, runtime_schedule=runtime))
        elapsed += float(sum(runtime.perlen_days))
        budgets[name] = json.loads((workspace/'bdam.water_balance.json').read_text())
        print(f'{name}: zero-volume state, restart and strict budgets passed', flush=True)
    model._write_summary(root/'drying_summary.csv', rows)
    for row in rows:
        assert all(np.isfinite(value) and abs(value) < 1e20
                   for key, value in row.items() if key.startswith('lake') and key.endswith('_stage_m'))
    assert not list(root.rglob('completion.json'))
    result = dict(status='pass', validation_only=True, native_solves=3, saved_steps=7,
        days=49, dry_pre_to_post_installation_volume_m3=0., budgets=budgets,
        mf6_version=subprocess.check_output([str(model._mf6_executable()), '-v'], text=True).strip())
    (root/'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


def assert_empty(volume, raw_stage, bed, lake):
    # TAB6 and DIS use different decimal formats. MF6 can therefore report
    # a few ULPs of volume at LAKEBOT. Require its actual DHDRY flag as well
    # as a bound derived from floating-point bed precision and onset area;
    # never accept a positive physical water depth as a dry state.
    roundoff = 8 * np.spacing(abs(bed)) * lake['table'][0, 2]
    assert raw_stage == -1e30, 'Expected a genuine MF6 dry state.'
    assert 0. <= volume <= roundoff, f'Empty volume exceeds serialization roundoff: {volume}'


if __name__ == '__main__':
    main()
