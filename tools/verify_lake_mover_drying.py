#!/usr/bin/env python3
"""Bounded all-lake wet/dry MVR stress tests, never production receipts.

Seven-day diagnostic periods deliberately apply extreme evaporation to test
water-availability limits near the connected bed. Production calendars and
forcing are untouched; no positive storage is rounded away.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bdam_simulation as model
from verify_lake_drying import schedule


def observations(workspace, count):
    with (workspace / 'bdam.lake_fluxes.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    return np.asarray([[float(r[f'LAKE{i}_VOLUME']) for i in range(1, count + 1)] for r in rows])


def require_depleted(handoff, workspace, volumes):
    # Newton closure may retain real trace storage. Bound it by the existing
    # stage tolerance; never snap it away or substitute a dry sentinel.
    count = int(handoff.scalar('/surface_water/n_lakes'))
    shape = handoff.array('/properties/K').shape
    lakes = model._lake_data(handoff, shape[2], shape[1])
    bottoms = model._lake_bottoms(handoff)
    allowed = np.asarray([np.interp(bed + model.LAK_STAGE_TOLERANCE, lake['table'][:, 0], lake['table'][:, 1])
                          for bed, lake in zip(bottoms, lakes)])
    assert np.all(volumes >= 0.) and np.all(volumes <= allowed), (workspace, volumes, allowed)
    raw = model._read_mf6_array_last(workspace / 'bdam.lak.stage', (count,))
    physical = model._decode_lake_stages(handoff, raw)
    assert np.all(physical >= bottoms) and np.all(physical - bottoms <= model.LAK_STAGE_TOLERANCE)
    calculated = np.asarray([np.interp(s, lake['table'][:, 0], lake['table'][:, 1]) for s, lake in zip(physical, lakes)])
    np.testing.assert_allclose(volumes[-1], calculated, atol=1e-11, rtol=1e-10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--inputs', type=Path, default=SOURCE / 'ModelInput')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    for path in (root, SOURCE):
        if any(name in str(path) for name in ("My Drive", "Google Drive", "OneDrive", "Dropbox", "Mobile Documents")):
            raise ValueError("Run only from local nonsynchronized storage.")
    root.mkdir(parents=True, exist_ok=False)
    pre_path, post_path = [args.inputs / p / 'preparation_handoff.h5' for p in ('pre_dam', 'post_dam')]
    pre, post = map(model.load_handoff, (pre_path, post_path))
    initial_heads = model._planar_initial_heads(pre) - 1.
    initial_wet = model._lake_bottoms(pre) + .1
    install = root / 'wet_installation'; install.mkdir()
    installed = model._coarse_restart_stages(pre, post, initial_wet, install)
    audit = json.loads((install / 'dam_installation_storage_audit.json').read_text())
    assert audit['before_volume_m3'] > 0. and abs(audit['error_m3']) <= 1e-8
    results = []
    for phase, path, h, start in (('pre', pre_path, pre, initial_wet),
                                   ('post', post_path, post, installed)):
        count = int(h.scalar('/surface_water/n_lakes'))
        shape = h.array('/properties/K').shape
        lakes = model._lake_data(h, shape[2], shape[1])
        assert all(np.interp(s, l['table'][:, 0], l['table'][:, 1]) > 0. for s, l in zip(start, lakes))
        workspace = root / (phase + '_wet_to_dry')
        heads, stages, wc = model._run_year(path, h, workspace, initial_heads.copy(), start.copy(), None, True,
            root / 'staging', phase + '_wet_to_dry', 1,
            runtime_schedule=schedule(h, [0., 0.], [10000., 10000.]), solver_profile='conservative')
        volumes = observations(workspace, count); require_depleted(h, workspace, volumes)
        results.append(dict(case=workspace.name, volumes_m3=volumes.tolist(),
                            budget=json.loads((workspace / 'bdam.water_balance.json').read_text())))
        workspace = root / (phase + '_rewet_restart')
        # Inherited stages (including trace water) and GWF/UZF restart unchanged.
        heads, stages, wc = model._run_year(path, h, workspace, heads, stages, wc, True,
            root / 'staging', phase + '_rewet_restart', 1,
            runtime_schedule=schedule(h, [8640., 0., 0.], [0., 10000., 10000.]), solver_profile='balanced')
        volumes = observations(workspace, count)
        assert np.all(volumes[0] > 0.), (phase, 'not every pool rewetted', volumes)
        require_depleted(h, workspace, volumes[1:])
        results.append(dict(case=workspace.name, volumes_m3=volumes.tolist(),
                            budget=json.loads((workspace / 'bdam.water_balance.json').read_text())))
        print(phase, 'all lakes depleted within existing stage closure and rewetted; trace storage preserved', flush=True)
    mixed = initial_wet.copy(); mixed[::2] = model._lake_bottoms(pre)[::2]
    workspace = root / 'mixed_wet_dry_neighbors'
    model._run_year(pre_path, pre, workspace, initial_heads.copy(), mixed, None, True,
        root / 'staging', 'mixed_wet_dry_neighbors', 1,
        runtime_schedule=schedule(pre, [0.], [10000.]), solver_profile='conservative')
    volumes = observations(workspace, len(mixed)); require_depleted(pre, workspace, volumes)
    results.append(dict(case=workspace.name, volumes_m3=volumes.tolist(),
                        budget=json.loads((workspace / 'bdam.water_balance.json').read_text())))
    assert not list(root.rglob('completion.json'))
    receipt = dict(status='pass', validation_only=True, native_solves=5, saved_steps=11,
                   diagnostic_days=77, wet_installation=audit, results=results)
    (root / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
