"""Storage conservation and routing checks independent of the native solver."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from build_bdam_simulation import _coarse_restart_stages, validate_lak_outlet_routes


class Storage:
    def __init__(self, areas, downstream_segments=2):
        self.areas = areas
        self.downstream_segments = downstream_segments

    def scalar(self, key):
        return self.downstream_segments if key.endswith('downstream_segments') else len(self.areas)

    def array(self, key):
        i = int(key.split('/lake_')[1].split('/')[0]) - 1
        return np.array([0., 10.]) * (self.areas[i] if key.endswith('volume_m3') else 1.)


class CoarseRiverTests(unittest.TestCase):
    def test_merger_preserves_upstream_and_downstream_volumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = _coarse_restart_stages(Storage([2, 3, 4, 5]), Storage([10, 4, 5]),
                                            np.array([1., 2., 3., 4.]), root)
            np.testing.assert_allclose(stages, [.8, 3., 4.])
            audit = json.loads((root/'dam_installation_storage_audit.json').read_text())
            self.assertAlmostEqual(audit['before_volume_m3'], 40.)
            self.assertAlmostEqual(audit['error_m3'], 0.)

    def test_variable_segment_restart_preserves_each_downstream_volume(self):
        for count in (1,2,3):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                pre=Storage([2,3]+[4]*count,count)
                post=Storage([10]+[4]*count,count)
                stages=np.array([1.,2.]+[3.]*count)
                result=_coarse_restart_stages(pre,post,stages,Path(directory))
                np.testing.assert_allclose(result,[.8]+[3.]*count)

    def test_invalid_restart_cannot_silently_clip_or_drop_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            for stages in ([1., 2.], [1., 2., 3., 11.], [1., 2., 3., np.nan]):
                with self.assertRaises(ValueError):
                    _coarse_restart_stages(Storage([2, 3, 4, 5]), Storage([10, 4, 5]),
                                           np.array(stages), Path(directory))

    def test_insufficient_pond_capacity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            _coarse_restart_stages(Storage([20, 30, 4, 5]), Storage([1, 4, 5]),
                                   np.array([1., 2., 3., 4.]), Path(directory))

    def test_coarse_chain_rejects_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.lak'
            rows = [f'{i} {i} {i+1 if i<8 else 0} MANNING 0 2 .04 .0025' for i in range(1, 9)]
            path.write_text('BEGIN OUTLETS\n'+'\n'.join(rows)+'\nEND OUTLETS\n')
            validate_lak_outlet_routes(path)
            path.write_text(path.read_text().replace('2 2 3 MANNING', '2 2 4 MANNING'))
            with self.assertRaises(ValueError):
                validate_lak_outlet_routes(path)
