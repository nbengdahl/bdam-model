"""Fast scientific and scheduler tests; no MATLAB or MODFLOW processes launched."""
from __future__ import annotations

import os
import subprocess
import sys
import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from bdam_forcing import PeriodicCurve, TransformedCurve, generate
from bdam_sweeps import expand
from bdam_runtime import (put, read, write, lock, slot, resolve, expected_workspaces,
                          compact, run_member, complete, result_hashes, lock_fds, digest)


HERE = Path(__file__).resolve().parent
SCHEMA = read(HERE/"bdam_parameter_schema.json")


def configuration():
    cfg = {}
    for name, value in SCHEMA["scalar_defaults"].items():
        put(cfg, name, value)
    cfg.update(groundwater_boundary_mode="drain", n_parallel_runs=1, time_resolution="weekly", forcing_interpolation="STEPWISE",
               forcing_mode="periodic", hydraulic_conductivity_mode="constant", longitudinal_direction="y",
               source_geometry_file="Geometry/BDamGeometry.mat", usgs_hydrograph_file="usgs_13348000_hydrograph.csv",
               hydrofacies_points_file="", hydrofacies_points=[], hydrofacies_class_properties=[dict(hydrofacies_id=1,K_m_per_day=.03,K33_m_per_day=.003)],
               K_by_layer_top_to_bottom=[], K33_by_layer_top_to_bottom=[], groundwater_boundary_k_m_per_day=[],
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
    def test_inflow_sweep_reference_uses_updated_mean(self):
        cfg = configuration()
        cfg['synthetic_mean_streamflow_m3_per_day'] = [4320, 17280]
        members, baseline, _ = expand(cfg, SCHEMA['scalar_defaults'])
        self.assertEqual(baseline['synthetic_mean_streamflow_m3_per_day'], 8640)
        self.assertEqual(len(members), 3)
        self.assertEqual({m['synthetic_mean_streamflow_m3_per_day'] for m in members},
                         {4320, 8640, 17280})
        self.assertTrue(all(m['reference_mean_streamflow_m3_per_day'] == 8640
                            for m in members))
        baseline['source_root'] = str(HERE)
        forcing = generate(baseline, np.linspace(0, 365, 53))
        self.assertAlmostEqual(
            forcing['diagnostics']['inflow']['annual_integral'], 8640 * 365,
            places=6)

    def test_cartesian_product_and_native_arrays(self):
        cfg=configuration(); cfg['K_constant']=[.01,.03,.06]; cfg['specific_yield']=[.1,.2]
        cfg['mf6_parameters']['uzf_eps']=[2,3.5]
        members,baseline,axes=expand(cfg,SCHEMA['scalar_defaults'])
        self.assertEqual(len(members),12)
        self.assertEqual(len(axes),3)
        self.assertEqual(len(baseline['pullman_monthly_precipitation_mm']),12)
        self.assertTrue(all(m['groundwater_boundary_k_m_per_day']==m['K_constant'] for m in members))

    def test_dependent_defaults_and_explicit_ghb_axis(self):
        cfg=configuration(); cfg['n_layers']=[3,5,7]; cfg['groundwater_boundary_k_m_per_day']=[.02,.03]
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

    def test_numeric_scalar_identity_deduplicates_reference(self):
        cfg=configuration()
        cfg['forcing_controls']['precipitation']['shift_days']=[0,14]
        cfg['forcing_controls']['inflow']['width_factor']=[1,1.2]
        members,baseline,_=expand(cfg,SCHEMA['scalar_defaults'])
        self.assertEqual(len(members),4)
        self.assertEqual(sum(m == baseline for m in members),1)
        members,_,_=expand(cfg,SCHEMA['scalar_defaults'],True)
        self.assertEqual(len(members),3)
        integer_cfg=configuration(); float_cfg=configuration()
        float_cfg['n_layers']=5.0
        float_cfg['forcing_controls']['precipitation']['shift_days']=0.0
        float_cfg['forcing_controls']['inflow']['width_factor']=1.0
        a,_,_=expand(integer_cfg,SCHEMA['scalar_defaults'])
        b,_,_=expand(float_cfg,SCHEMA['scalar_defaults'])
        self.assertEqual(digest(a),digest(b))

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

    def test_frozen_manifest_has_explicit_version(self):
        self.assertEqual(SCHEMA['version'], 'bdam-parameters-v7')

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
            self.assertEqual(len(workspaces),6)
            self.assertEqual(workspaces[1],('spinup/staged','pre_dam',1460.,88))
            self.assertEqual([w[0] for w in workspaces[-4:]],['pre_dam/year_01','pre_dam/year_02','post_dam/year_01','post_dam/year_02'])
            cfg=resolve(configuration())
            for name in ('fall_average_spinup_years','monthly_spinup_years','weekly_spinup_years'):
                cfg['mf6_parameters'][name]=0
            write(Path(temp)/'resolved_config.json',cfg)
            self.assertEqual(len(expected_workspaces(temp)),4)

    def test_registered_scalar_defaults_match_canonical_registry(self):
        for name,value in SCHEMA['scalar_defaults'].items():
            if name != 'groundwater_boundary_k_m_per_day':
                self.assertEqual(value,SCHEMA['parameters'][name]['default'])

    def test_compact_completion_and_resume_validate_results_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); (path/'Runs').mkdir()
            write(path/'resolved_config.json', resolve(configuration()))
            np.savez_compressed(path/'Runs'/'restart_states.npz',heads=np.ones((1,2,2)))
            (path/'Runs'/'weekly_summary.csv').write_text('phase,time_days\npre_dam,365\n')
            write(path/'prepared.json',dict(handoff_hashes={}))
            checksums=result_hashes(path)
            write(path/'completion.json',dict(fingerprint='x',status='pass',retention='compact',result_hashes=checksums))
            with patch('bdam_runtime.verify_snapshot',return_value={}):
                self.assertTrue(complete(path,'x'))
                self.assertTrue(complete(path,'x'))
                self.assertEqual(result_hashes(path),checksums)
                self.assertFalse(complete(path,'other'))
                (path/'Runs'/'weekly_summary.csv').write_text('changed')
                self.assertFalse(complete(path,'x'))

    def test_compact_retains_scientific_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); runs=root/'Runs'; runs.mkdir()
            for name in ('bdam.hds','bdam.fluxes.csv','bdam.water_balance.json','restart_states.npz','bdam.lst'):
                (runs/name).write_text('data')
            compact(root)
            self.assertFalse((runs/'bdam.hds').exists())
            self.assertEqual(len(list(runs.iterdir())),4)

    def test_snapshot_failure_is_retained_as_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'member'; path.mkdir()
            write(path/'resolved_config.json',resolve(configuration()))
            manifest=dict(root=temp,n_parallel_runs=1,axes={},members=[dict(id='a',path=str(path),fingerprint='x',baseline=False)])
            with patch('bdam_runtime.verify_snapshot',side_effect=ValueError('changed snapshot')):
                result=run_member(manifest,manifest['members'][0])
            self.assertEqual(result['status'],'failed')


if __name__ == '__main__': unittest.main()
