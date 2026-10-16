#!/usr/bin/env python3
"""Small-grid, full-weekly-year smoke verification; no production receipts.

Uses deliberately loose TEST-ONLY relative tolerances (1.0) to bound the
adaptive run at three years. Fixed control uses identical annual boundaries.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import bdam
import bdam_runtime as rt
import bdam_spinup as sp
import build_bdam_simulation as model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='Fresh local validation directory')
    parser.add_argument('--matlab', default='matlab')
    parser.add_argument('--resume-control', action='store_true',
                        help='Reuse completed adaptive/three control spinup years; finish monitored control only')
    args = parser.parse_args()
    root = rt.local_path(args.root)
    rt.local_path(SOURCE)
    root.mkdir(parents=True, exist_ok=args.resume_control)
    os.environ['BDAM_PYTHON'] = sys.executable
    shared = dict(n_layers=3, geometry=dict(domain_length_x_m=30, domain_length_y_m=40,
        spacing_x_m=2, spacing_y_m=2, sine_amplitude_m=0, bottom_widths_m=[2, 4], depths_m=[.5, .5]),
        mf6_parameters=dict(fall_average_spinup_years=0, monthly_spinup_years=0, weekly_spinup_years=3,
            spinup_until_converged=True, spinup_max_weekly_years=3, pre_dam_years=1, post_dam_years=0,
            spinup_head_relative_tolerance=1., spinup_stage_relative_tolerance=1.,
            spinup_water_content_relative_tolerance=1.))
    if args.resume_control:
        batch = rt.read(root/'study/batches/smoke.json')
    else:
        study = bdam.Study(root/'study', dict(source=str(SOURCE), shared=shared,
            execution=dict(matlab=args.matlab)))
        batch = study.submit([dict(case_id='adaptive-test-only')], 'smoke')
    if batch['cases'][0]['status'] == 'failed':
        raise RuntimeError(batch['cases'][0]['error'])
    if not args.resume_control:
        study.prepare('smoke')
    execution = Path(batch['cases'][0]['output_path'])
    if not args.resume_control:
        model.run_from_handoff(execution/'ModelInput', staging_root=root/'staging')
    records = rt.validate_results(execution)
    report = sp.validate_report(execution/'Runs', sp.settings(shared['mf6_parameters']))
    assert report['years_completed'] == 3
    handoff_path = execution/'ModelInput/pre_dam/preparation_handoff.h5'
    handoff = model.load_handoff(handoff_path)
    schedule, _ = model._staged_spinup_schedule(handoff, dict(fall_average_spinup_years=0,
        monthly_spinup_years=0, weekly_spinup_years=1))
    heads = model._default_heads(handoff)
    stages = wc = None
    compared = []
    for year in range(1, 5):
        workspace = root/'fixed-control'/(f'year_{year:02d}' if year <= 3 else 'monitored_year_01')
        if args.resume_control and year <= 3:
            model._validate_completed_workspace(handoff, workspace, 365., True)
            heads, stages, wc = model._read_final_state(handoff, workspace)
        else:
            heads, stages, wc = model._run_year(handoff_path, handoff, workspace, heads, stages, wc,
                True, root/'staging', 'control', year, runtime_schedule=schedule if year <= 3 else None,
                solver_profile='conservative' if year == 1 else 'balanced')
        relative = f'spinup/weekly/year_{year:02d}' if year <= 3 else 'pre_dam/year_01'
        actual = execution/'Runs'/relative
        for name in model.REQUIRED_BINARY_OUTPUTS:
            if (actual/name).read_bytes() != (workspace/name).read_bytes():
                raise AssertionError(f'Adaptive/control output differs: {relative}/{name}')
            compared.append(f'{relative}/{name}')
        with model.flopy.utils.HeadFile(actual/'bdam.hds') as reader:
            np.testing.assert_allclose(reader.get_times(), np.linspace(0, 365, 53)[1:], rtol=0, atol=1e-8)
    if list(root.rglob('completion.json')):
        raise AssertionError('Smoke verification must not produce production completion receipts.')
    receipt = dict(validation_only=True, test_only_relative_tolerances=1.0,
        execution=str(execution), control=str(root/'fixed-control'), grid=[15, 20, 3],
        adaptive_saved_steps=208, control_saved_steps=208, records=records,
        compared_binary_files=compared, convergence=report,
        runtime=rt.runtime_provenance(SOURCE))
    rt.write(root/'validation.json', receipt)
    print(json.dumps(dict(status='pass', receipt=str(root/'validation.json'), execution=str(execution))))


if __name__ == '__main__':
    main()
