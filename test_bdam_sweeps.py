"""Fast scientific and scheduler tests; no MATLAB or MODFLOW processes launched."""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import h5py

from bdam_forcing import PeriodicCurve, TransformedCurve, generate
from bdam_sweeps import (expand, get, put, read, write, lock, slot, resolve,
                         validate, expected_workspaces, compact, run_member,
                         collect, plan, verify_snapshot, complete, result_hashes,
                         lock_fds, digest, geometry_fingerprint)

HERE = Path(__file__).resolve().parent
SCHEMA = read(HERE/"bdam_parameter_schema.json")


def configuration():
    cfg = {}
    for name, value in SCHEMA["scalar_defaults"].items():
        put(cfg, name, value)
    cfg.update(n_parallel_runs=1, time_resolution="weekly", forcing_interpolation="STEPWISE",
               forcing_mode="periodic", hydraulic_conductivity_mode="constant", longitudinal_direction="y",
               source_geometry_file="Geometry/BDamGeometry.mat", usgs_hydrograph_file="usgs_13348000_hydrograph.csv",
               hydrofacies_points_file="", hydrofacies_points=[], hydrofacies_class_properties=[dict(hydrofacies_id=1,K_m_per_day=.03,K33_m_per_day=.003)],
               K_by_layer_top_to_bottom=[], K33_by_layer_top_to_bottom=[], ghb_k_mean_m_per_day=[],
               pullman_monthly_precipitation_mm=[67.8,49.3,52.1,49.8,46,31,11.2,12.2,16.5,45.7,66.5,70.4],
               synthetic_land_et_monthly_factor=[.18,.22,.4,.7,1.1,1.55,1.8,1.6,1.2,.7,.35,.2],
               synthetic_recharge_monthly_factor=[1.2,1.2,1.1,1,.85,.6,.25,.25,.45,.85,1.1,1.2])
    return cfg


def slot_probe(root, capacity, queue, delay):
    with slot(root, capacity) as number:
        queue.put(("start", time.monotonic(), number))
        time.sleep(delay)
        queue.put(("end", time.monotonic(), number))


class ForcingTests(unittest.TestCase):
    def setUp(self):
        t = np.arange(365)+.5
        self.daily = .3+np.exp(4*(np.cos(2*np.pi*(t-90)/365)-1))
        self.curve = PeriodicCurve(self.daily)

    def test_periodic_c1_at_all_knots_and_year_boundary(self):
        for t in (0, 365, .5, 90.5, 364.5):
            self.assertAlmostEqual(float(self.curve.value(t-1e-7)), float(self.curve.value(t+1e-7)), places=7)
            self.assertAlmostEqual(float(self.curve.value(t-1e-7, True)), float(self.curve.value(t+1e-7, True)), places=7)
        for t in np.linspace(-1000, 1000, 100):
            self.assertAlmostEqual(float(self.curve.value(t)), float(self.curve.value(t+365)), places=12)
            self.assertAlmostEqual(float(self.curve.value(t, True)), float(self.curve.value(t+365, True)), places=12)

    def test_exact_source_and_transformed_integrals(self):
        self.assertAlmostEqual(float(self.curve.integral(0,365)), self.daily.sum(), places=11)
        for width in (.3, .8, 1, 1.5, 3):
            for shift in (-400.25, 0, 300.75):
                curve = TransformedCurve(self.curve, 1.7, shift, width)
                self.assertAlmostEqual(float(curve.integral(0,365)), self.daily.sum()*1.7, places=9)
                for edges in (np.arange(366), np.linspace(0,365,53), np.r_[0,np.cumsum([31,30,31,31,28,31,30,31,30,31,31,30])]):
                    self.assertAlmostEqual(float(np.dot(curve.means(edges), np.diff(edges))), self.daily.sum()*1.7, places=9)
                self.assertGreaterEqual(curve.value(np.linspace(0,365,3000)).min(), curve.source.floor*1.7-1e-12)

    def test_transformed_seam_and_warp_antipode(self):
        curve = TransformedCurve(self.curve, shift_days=300.75, width_factor=.4)
        for t in (0,365,curve.center+curve.shift+182.5):
            eps=1e-4
            self.assertAlmostEqual(float(curve.value(t)),float(curve.value(t+365)),places=10)
            left=(curve.value(t)-curve.value(t-eps))/eps
            right=(curve.value(t+eps)-curve.value(t))/eps
            self.assertAlmostEqual(float(left),float(right),places=5)

    def test_width_and_shift_have_the_requested_direction(self):
        widths = [TransformedCurve(self.curve,width_factor=w).diagnostics()["seasonal_rms_days"] for w in (.5,1,1.5)]
        self.assertLess(widths[0],widths[1]); self.assertLess(widths[1],widths[2])
        base=TransformedCurve(self.curve); shifted=TransformedCurve(self.curve,shift_days=300.25)
        t=np.linspace(0,365,1000)
        np.testing.assert_allclose(shifted.value(t+300.25),base.value(t),rtol=1e-12,atol=1e-12)

    def test_constant_zero_and_invalid_controls(self):
        for constant in (0.,2.):
            curve=TransformedCurve(PeriodicCurve(np.full(365,constant)),2,-29,.25)
            np.testing.assert_allclose(curve.value(np.linspace(0,365,100)),constant*2)
            self.assertAlmostEqual(float(curve.integral(0,365)),constant*730)
        for kwargs in (dict(width_factor=0),dict(magnitude_scale=-1),dict(shift_days=float('nan'))):
            with self.assertRaises(ValueError): TransformedCurve(self.curve,**kwargs)
        # MATLAB jsondecode/jsonencode maps automatic null centers back to [].
        automatic = TransformedCurve(self.curve,center_day=[])
        self.assertEqual(automatic.center,self.curve.peak)

    def test_atmospheric_linkage_and_frozen_reference(self):
        cfg=resolve(configuration()); cfg['source_root']=str(HERE)
        edges=np.linspace(0,365,53)
        base=generate(cfg,edges)
        cfg['forcing_controls']['precipitation']['shift_days']=120
        cfg['forcing_controls']['inflow']['magnitude_scale']=2
        changed=generate(cfg,edges)
        np.testing.assert_allclose(changed['reference_inflow'],base['reference_inflow'])
        np.testing.assert_allclose(changed['rates']['upstream_inflow_m3_per_day'],np.array(base['rates']['upstream_inflow_m3_per_day'])*2)
        np.testing.assert_allclose(changed['rates']['lake_evaporation_m_per_day'],np.array(changed['rates']['land_et_m_per_day'])*.85)
        self.assertAlmostEqual(base['diagnostics']['precipitation']['annual_integral'],changed['diagnostics']['precipitation']['annual_integral'])
        self.assertNotAlmostEqual(base['diagnostics']['annual_land_infiltration_m'],changed['diagnostics']['annual_land_infiltration_m'])


class CampaignTests(unittest.TestCase):
    def test_cartesian_product_and_native_arrays(self):
        cfg=configuration(); cfg['K_constant']=[.01,.03,.06]; cfg['specific_yield']=[.1,.2]
        cfg['mf6_parameters']['uzf_eps']=[2,3.5]
        members,baseline,axes=expand(cfg,SCHEMA['scalar_defaults'])
        self.assertEqual(len(members),12)
        self.assertEqual(len(axes),3)
        self.assertEqual(len(baseline['pullman_monthly_precipitation_mm']),12)
        self.assertTrue(all(m['ghb_k_mean_m_per_day']==m['K_constant'] for m in members))

    def test_dependent_defaults_and_explicit_ghb_axis(self):
        cfg=configuration(); cfg['n_layers']=[3,5,7]; cfg['ghb_k_mean_m_per_day']=[.02,.03]
        members,_,_=expand(cfg,SCHEMA['scalar_defaults'])
        self.assertEqual(len(members),6)
        for m in members: self.assertEqual(len(m['K_by_layer_top_to_bottom']),m['n_layers'])

    def test_skip_baseline_and_extra_reference(self):
        cfg=configuration(); cfg['K_constant']=[.01,.02]
        members,_,_=expand(cfg,SCHEMA['scalar_defaults']); self.assertEqual(len(members),3)
        members,_,_=expand(cfg,SCHEMA['scalar_defaults'],True); self.assertEqual(len(members),2)
        cfg['K_constant']=[.01,.03]
        members,_,_=expand(cfg,SCHEMA['scalar_defaults'],True); self.assertEqual(len(members),1)
        members,_,_=expand(configuration(),SCHEMA['scalar_defaults']); self.assertEqual(len(members),1)
        members,_,_=expand(configuration(),SCHEMA['scalar_defaults'],True); self.assertEqual(len(members),0)

    def test_invalid_combinations_and_capacity_are_rejected(self):
        cfg=configuration(); cfg['n_layers']=[2,5]
        with self.assertRaisesRegex(ValueError,'Invalid combination'): expand(cfg,SCHEMA['scalar_defaults'])
        for n in (0,1.5,[1,2]):
            cfg=configuration(); cfg['n_parallel_runs']=n
            with self.assertRaises(ValueError): expand(cfg,SCHEMA['scalar_defaults'])
        cfg=configuration(); cfg['K_constant']=[float('nan'),.03]
        with self.assertRaises(ValueError): expand(cfg,SCHEMA['scalar_defaults'])
        cfg=configuration(); cfg['specific_yield']=[[.1,.2],[.3,.4]]
        with self.assertRaisesRegex(ValueError,'matrix'): expand(cfg,SCHEMA['scalar_defaults'])

    def test_manifest_snapshot_and_provenance_are_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source'; source.mkdir()
            for name in ('bdam_parameter_schema.json','usgs_13348000_hydrograph.csv'):
                (source/name).write_bytes((HERE/name).read_bytes())
            (source/'Geometry').mkdir()
            with h5py.File(source/'Geometry'/'BDamGeometry.mat','w') as geometry:
                for name in ('X','Y','ZTop','dx','dy','parameters','post_dam','dam_settings'):
                    geometry.create_dataset(name,data=np.ones(1))
            cfg=configuration(); write(source/'request.json',cfg)
            manifest=plan(source/'request.json',Path(temp)/'campaign',source)
            member=Path(manifest['members'][0]['path']); verify_snapshot(member)
            manifest2=plan(source/'request.json',Path(temp)/'campaign',source)
            self.assertEqual(manifest,manifest2)
            (member/'usgs_13348000_hydrograph.csv').write_text('tampered')
            with self.assertRaises(ValueError): verify_snapshot(member)

    def test_member_lock_and_slots_across_processes(self):
        with tempfile.TemporaryDirectory() as temp:
            with lock(Path(temp)/'member.lock') as first:
                self.assertTrue(first)
                with lock(Path(temp)/'member.lock') as second: self.assertFalse(second)
            context=mp.get_context('spawn'); queue=context.Queue()
            workers=[context.Process(target=slot_probe,args=(temp,2,queue,.12)) for _ in range(5)]
            for worker in workers: worker.start()
            events=[queue.get(timeout=20) for _ in range(10)]
            for worker in workers: worker.join(20); self.assertEqual(worker.exitcode,0)
            active=maximum=0
            for event,_,_ in sorted(events,key=lambda item:item[1]):
                active+=1 if event=='start' else -1; maximum=max(maximum,active)
            self.assertEqual(maximum,2); self.assertEqual(active,0)

    @unittest.skipUnless(os.name=='posix','POSIX inherited descriptor contract')
    def test_child_keeps_claim_after_launcher_closes_its_descriptor(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'claim.lock'
            with lock(path) as acquired:
                self.assertTrue(acquired)
                child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(.25)'],pass_fds=lock_fds())
            try:
                with lock(path) as acquired: self.assertFalse(acquired)
            finally:
                child.wait(timeout=5)
            with lock(path) as acquired: self.assertTrue(acquired)

    def test_default_workspace_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            write(Path(temp)/'resolved_config.json',resolve(configuration()))
            workspaces=expected_workspaces(temp)
            self.assertEqual(len(workspaces),7)
            self.assertEqual(workspaces[2],('spinup/staged','pre_dam',2190.,130))
            self.assertEqual([w[0] for w in workspaces[-4:]],['pre_dam/year_01','pre_dam/year_02','post_dam/year_01','post_dam/year_02'])
            cfg=resolve(configuration())
            for name in ('fall_average_spinup_years','monthly_spinup_years','weekly_spinup_years'):
                cfg['mf6_parameters'][name]=0
            write(Path(temp)/'resolved_config.json',cfg)
            self.assertEqual(len(expected_workspaces(temp)),4)

    def test_registered_scalar_defaults_match_editable_script(self):
        script=(HERE/'MakeInputs.m').read_text()
        scalar_assignments=re.findall(r'^([A-Za-z]\w*(?:\.\w+)?)\s*=\s*([-+\d.e]+);\s*% #User_Defined',script,re.M)
        for name,value in scalar_assignments:
            if name!='n_parallel_runs':
                self.assertIn(name,SCHEMA['scalar_defaults'])
                self.assertEqual(float(value),SCHEMA['scalar_defaults'][name])

    def test_compact_completion_and_resume_validate_results_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); (path/'Runs').mkdir()
            np.savez_compressed(path/'Runs'/'restart_states.npz',heads=np.ones((1,2,2)))
            (path/'Runs'/'weekly_summary.csv').write_text('phase,time_days\npre_dam,365\n')
            checksums=result_hashes(path)
            write(path/'completion.json',dict(fingerprint='x',status='pass',retention='compact',result_hashes=checksums))
            with patch('bdam_sweeps.verify_snapshot',return_value={}):
                self.assertTrue(complete(path,'x'))
                self.assertTrue(complete(path,'x'))
                self.assertEqual(result_hashes(path),checksums)
                self.assertFalse(complete(path,'other'))
                (path/'Runs'/'weekly_summary.csv').write_text('changed')
                self.assertFalse(complete(path,'x'))

    def test_baseline_reuse_requires_matching_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            source=(Path(temp)/'reference').resolve(); target=(Path(temp)/'target').resolve(); source.mkdir(); target.mkdir()
            (source/'Runs').mkdir(); (source/'Runs'/'weekly_summary.csv').write_text('phase,time_days\npre_dam,365\n')
            write(source/'completion.json',dict(fingerprint='x',status='pass',retention='compact',elapsed_seconds=1))
            member=dict(id='a',fingerprint='x',path=str(target),baseline=True)
            manifest=dict(root=temp,n_parallel_runs=1)
            with patch('bdam_sweeps.verify_snapshot',return_value={'fingerprint':'x'}):
                with patch('bdam_sweeps.complete',side_effect=lambda path, fingerprint: Path(path)==source and fingerprint=='x'):
                    result=run_member(manifest,member,reuse_baseline=source)
            self.assertTrue(result['reused'])
            self.assertEqual((target/'Runs'/'weekly_summary.csv').read_bytes(),(source/'Runs'/'weekly_summary.csv').read_bytes())

    def test_geometry_identity_ignores_export_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'geometry.mat'
            with h5py.File(path,'w') as stream:
                for name in ('X','Y','ZTop','dx','dy','parameters','post_dam','dam_settings'):
                    stream.create_dataset(name,data=np.ones(1))
                stream.create_dataset('exported_at',data=[1])
            before=geometry_fingerprint(path)
            with h5py.File(path,'a') as stream: stream['exported_at'][0]=2
            self.assertEqual(geometry_fingerprint(path),before)
            with h5py.File(path,'a') as stream: stream['ZTop'][0]=2
            self.assertNotEqual(geometry_fingerprint(path),before)

    def test_compact_retains_scientific_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); runs=root/'Runs'; runs.mkdir()
            for name in ('bdam.hds','bdam.fluxes.csv','bdam.water_balance.json','restart_states.npz','bdam.lst'):
                (runs/name).write_text('data')
            compact(root)
            self.assertFalse((runs/'bdam.hds').exists())
            self.assertEqual(len(list(runs.iterdir())),4)

    def test_failure_is_retained_and_not_collected_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'member'; path.mkdir()
            write(path/'resolved_config.json',resolve(configuration()))
            manifest=dict(root=temp,n_parallel_runs=1,axes={},members=[dict(id='a',path=str(path),fingerprint='x',baseline=False)])
            with patch('bdam_sweeps.verify_snapshot',side_effect=ValueError('changed snapshot')):
                result=run_member(manifest,manifest['members'][0])
            self.assertEqual(result['status'],'failed')
            index=collect(manifest); self.assertEqual(index[0]['status'],'failed')
            self.assertEqual(len((Path(temp)/'ensemble_summary.csv').read_text().splitlines()),1)


if __name__ == '__main__': unittest.main()
