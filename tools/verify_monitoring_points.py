#!/usr/bin/env python3
"""Two serial short monitoring cases; never create production completion receipts."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import bdam
import bdam_runtime as rt
import build_bdam_simulation as model
from verify_edge_fluxes import short_schedule


def run_case(member, output):
    output.mkdir(parents=True, exist_ok=False)
    execution=Path(member['output_path'])
    (output/'Geometry').mkdir()
    shutil.copy2(execution/'Geometry/BDamGeometry.mat', output/'Geometry/BDamGeometry.mat')
    paths=[execution/'ModelInput'/phase/'preparation_handoff.h5' for phase in ('pre_dam','post_dam')]
    pre,post=[model.load_handoff(path) for path in paths]
    heads=model._planar_initial_heads(pre)
    stages=wc=None
    summary=[]
    runs=output/'Runs';runs.mkdir()
    for index,(phase,handoff,path) in enumerate(zip(('pre_dam','post_dam'),(pre,post),paths)):
        if index:
            stages=model._coarse_restart_stages(pre,post,stages,runs)
            wc=model._map_uzf_state(pre,post,wc)
        initial_heads,initial_stages=heads,stages
        schedule=short_schedule(model,handoff)
        workspace=runs/phase/'year_01'
        heads,stages,wc=model._run_year(path,handoff,workspace,heads,stages,wc,True,
            output/'staging',phase,1,runtime_schedule=schedule,
            solver_profile='conservative' if index==0 else 'balanced')
        summary.extend(model._period_rows(handoff,workspace,initial_heads,initial_stages,
            phase,1,2.*index,True,runtime_schedule=schedule))
        with model.flopy.utils.HeadFile(workspace/'bdam.hds') as reader:
            assert reader.get_times()==[1.,2.]
            with (workspace/'monitoring_targets.csv').open() as stream:
                targets=list(csv.DictReader(stream))
            with (workspace/'bdam.heads.csv').open() as stream:
                observations=list(csv.DictReader(stream))
            assert len(observations)==2
            for time,observed in zip((1.,2.),observations):
                normalized={name.lower():float(value) for name,value in observed.items()}
                native=reader.get_data(totim=time)
                for target in targets:
                    cell=tuple(int(target[name]) for name in ('mf6_layer_zero_based','mf6_row_zero_based','mf6_column_zero_based'))
                    np.testing.assert_allclose(normalized[target['name']],native[cell],atol=1e-9,rtol=1e-10)
        # Prove the HDF5 file alone preserves labels, row IDs and omission metadata.
        with tempfile.TemporaryDirectory(dir=output) as temporary:
            alone=Path(temporary)/'preparation_handoff.h5'
            shutil.copy2(path,alone)
            loaded=model.load_handoff(alone)
            for key in ('monitoring_head_point_names','monitoring_target_metadata'):
                assert loaded.manifest[key]==handoff.manifest[key],key
            model._monitoring(loaded,heads.shape[0],heads.shape[1],heads.shape[2],Path(temporary))
    model._write_summary(runs/'weekly_summary.csv',summary)
    return dict(output=str(output),saved_steps=4,qa={phase:json.loads((runs/phase/'year_01/bdam.water_balance.json').read_text())
        for phase in ('pre_dam','post_dam')})


def validate_layout(root):
    grid=root/'short-results/grid/Runs'; custom=root/'short-results/csv/Runs'
    identical=[]
    for phase in ('pre_dam','post_dam'):
        left=grid/phase/'year_01';right=custom/phase/'year_01'
        for name in (*model.REQUIRED_BINARY_OUTPUTS,model.FLUX_OUTPUT,'bdam.lake_fluxes.csv',
                     'bdam.groundwater_boundary_flux.csv',model.EDGE_FLUX_OUTPUT):
            assert (left/name).read_bytes()==(right/name).read_bytes(),f'Physical output differs: {phase}/{name}'
            identical.append(f'{phase}/{name}')
        with (left/'monitoring_targets.csv').open() as stream:
            original=list(csv.DictReader(stream))
        with (right/'monitoring_targets.csv').open() as stream:
            targets=list(csv.DictReader(stream))
        assert len(original)==10 and len(targets)==8
        assert targets[:4]==original[:4]
        assert [target['name'] for target in targets[4:]]==['head_csv_0001','head_csv_0003','head_csv_0004','head_csv_0007']
        assert targets[4]['original_name']=='Shallow α'
        assert targets[5]['original_name']=='Deep same column'
        assert int(targets[4]['resolved_layer_top_down'])<int(targets[5]['resolved_layer_top_down'])
        with (right/'monitoring_omitted.csv').open() as stream:
            omitted=list(csv.DictReader(stream))
        assert [int(row['csv_row']) for row in omitted]==[2,5,6]
    return identical


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path,help='Fresh local output directory')
    parser.add_argument('--matlab',default='matlab')
    args=parser.parse_args()
    root=rt.local_path(args.root);rt.local_path(SOURCE)
    if root.exists(): parser.error('Use a fresh directory; prior verification evidence is retained.')
    root.mkdir(parents=True)
    points=root/'monitoring_input.csv'
    points.write_text('x,y,z,name\n20,70,0.05,Shallow α\n-1,70,1,Outside X\n'
        '20,70,4.5,Deep same column\n0,0,0,Surface boundary\n20,70,-1,Above terrain\n'
        '20,70,100,Below bottom\n50,105,2,Upstream bank\n',encoding='utf-8')
    os.environ.setdefault('BDAM_PYTHON',sys.executable)
    study=bdam.Study(root/'preparation-study',dict(source=str(SOURCE),execution=dict(matlab=args.matlab,n_parallel_runs=1)))
    batch=study.submit([dict(case_id='grid'),dict(case_id='csv',monitoring_points_file=str(points))],'monitoring')
    assert len(batch['cases'])==2 and all(case['status']=='pending' for case in batch['cases'])
    study.prepare('monitoring')
    cases={case['case_id']:run_case(case,root/'short-results'/case['case_id']) for case in batch['cases']}
    identical=validate_layout(root)
    assert not list(root.rglob('completion.json'))
    tests=str(SOURCE/'tests').replace("'", "''")
    output=str(root/'short-results/csv').replace("'", "''")
    viewer_receipt=str(root/'viewer_verification.json').replace("'", "''")
    expression=(f"addpath('{tests}'); r=verifyMonitoringViewer('{output}'); "
                f"writeBDamJson('{viewer_receipt}',r)")
    with (root/'viewer_verification.log').open('w') as log:
        subprocess.run([args.matlab,'-batch',expression],cwd=SOURCE,stdout=log,stderr=subprocess.STDOUT,check=True)
    viewer=rt.read(root/'viewer_verification.json')
    receipt=dict(status='pass',kind='short-monitoring-verification',configuration_count=2,max_workers=1,
        native_solves=4,days_per_case=4,production_completion=False,cases=cases,
        identical_physical_files=identical,viewer=viewer,source=str(SOURCE),python=sys.version,
        mf6_version=subprocess.check_output([str(model._mf6_executable()),'-v'],text=True).strip())
    rt.write(root/'monitoring_verification.json',receipt)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    main()
