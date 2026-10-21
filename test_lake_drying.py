"""Dry-state geometry, output decoding and conservative installation regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import build_bdam_simulation as model


class LakeHandoff:
    def __init__(self, count=3):
        self.count = count
        self.top = np.arange(count, dtype=float).reshape(count, 1) + .125
        self.tables = [np.array([[bed, 0., 1.], [bed + 1., 1., 1.]]) for bed in self.top[:, 0]]

    def scalar(self, path):
        if path.endswith('downstream_segments'):
            return 2
        return self.count

    def array(self, path, dtype=float):
        if path == '/grid/ZTop':
            return self.top.copy()
        if path == '/grid/Z':
            return np.stack((self.top - 2., self.top), axis=2)
        i = int(path.split('/lake_')[1].split('/')[0]) - 1
        field = path.split('/')[-1]
        if field in ('storage_footprint_mask', 'footprint_mask'):
            return (np.arange(self.count) == i).reshape(self.count, 1)
        values = {'connection_i_x': [i + 1], 'connection_i_y': [1],
                  'connection_layer_native': [1], 'stage_m': self.tables[i][:, 0],
                  'volume_m3': self.tables[i][:, 1], 'area_m2': self.tables[i][:, 2]}
        return np.asarray(values[field], dtype=dtype)


class LakeDryingTests(unittest.TestCase):
    def test_dry_decoding_preserves_wet_values_and_time_series(self):
        h = LakeHandoff()
        raw = np.array([[-1e30, 1.5, 2.5], [.3, -1e30, -1e30]])
        decoded = model._decode_lake_stages(h, raw)
        np.testing.assert_array_equal(decoded, [[.125, 1.5, 2.5], [.3, 1.125, 2.125]])
        self.assertEqual(raw[0, 0], -1e30)  # Never mutate binary-reader buffers.
        for invalid in (np.nan, np.inf, 1e30, -1e29):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                model._decode_lake_stages(h, [invalid, 1.5, 2.5])
        with self.assertRaises(ValueError):
            model._decode_lake_stages(h, [0.])

    def test_final_state_decodes_dry_lake_before_restart(self):
        h = LakeHandoff()
        # UZF has one feature here; its actual topology is irrelevant to decoding.
        original = h.array
        h.array = lambda p, dtype=float: np.ones((1, 1, 1), dtype=bool) if p == '/uzf/eligible_mask' else original(p, dtype)
        with patch.object(model.flopy.utils, 'HeadFile') as heads, patch.object(
                model, '_read_mf6_array_last', side_effect=[np.full(3, -1e30), np.array([.1])]):
            heads.return_value.get_data.return_value = np.zeros((1, 1, 1))
            state = model._read_final_state(h, Path('unused'))
        np.testing.assert_array_equal(state[1], h.top[:, 0])

    def test_storage_invariant_rejects_trapped_water_and_unrepresented_beds(self):
        h = LakeHandoff()
        lakes = [dict(number=i + 1, table=t.copy()) for i, t in enumerate(h.tables)]
        model._validate_lake_storage(h, lakes)
        for bad in (np.array([[.1, 0., 0.], [1., 1., 1.]]),
                    np.array([[.125, .01, 1.], [1., 1., 1.]]),
                    np.array([[.125, 0., 1.], [1., 0., 1.]])):
            with self.subTest(table=bad), self.assertRaises(ValueError):
                model._validate_lake_storage(h, [dict(number=1, table=bad)])
        h.top[0, 0] -= .1
        # Hold the connected bed fixed while lowering the storage terrain.
        with patch.object(model, '_lake_bottoms', return_value=np.array([.125])):
            with self.assertRaisesRegex(ValueError, 'below its connected bed'):
                model._validate_lake_storage(h, lakes[:1])

    def test_dry_and_mixed_installation_preserves_volume(self):
        pre, post = LakeHandoff(4), LakeHandoff(3)
        for stages, expected_volume in ((np.full(4, -1e30), 0.),
                                         (np.array([-1e30, 1.375, 2.625, -1e30]), .75)):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                result = model._coarse_restart_stages(pre, post, stages, path)
                audit = json.loads((path/'dam_installation_storage_audit.json').read_text())
                self.assertAlmostEqual(audit['before_volume_m3'], expected_volume)
                self.assertAlmostEqual(audit['after_volume_m3'], expected_volume)
                self.assertEqual(audit['error_m3'], 0.)
                self.assertTrue(np.all(result >= post.top[:, 0]))
                if expected_volume == 0:
                    np.testing.assert_array_equal(result, post.top[:, 0])
