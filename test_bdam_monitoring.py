"""Monitoring audit generation and HDF5-only metadata contracts; no native solve."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
import build_bdam_simulation as model


class MonitoringOutputTests(unittest.TestCase):
    class Handoff:
        manifest = {
            'scenario': 'pre_dam',
            'monitoring_head_point_names': ['head_csv_0003'],
            'monitoring_target_metadata': [dict(source='csv',csv_row=3,original_name='Well α / shallow',
                requested_depth_m=1.,requested_elevation_m=9.,resolved_z_m=8.5)],
            'monitoring_omitted_points': dict(csv_row=2,x=-1.,y=1.,z=1.,name='Outside',reason='outside horizontal model bounds'),
        }
        values = {
            '/monitoring/head_points_requested_xy_layer':np.array([[1.,1.,1.]]),
            '/monitoring/head_points_resolved_i_x':np.array([1]),
            '/monitoring/head_points_resolved_i_y':np.array([2]),
            '/monitoring/head_points_resolved_layer_top_down':np.array([1]),
            '/monitoring/head_points_resolved_xy':np.array([[1.,1.]])}

        def array(self,path,dtype=float):
            return np.asarray(self.values[path],dtype=dtype)

    def test_output_labels_depths_and_omission_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)
            h=self.Handoff()
            records=model._monitoring(h,3,3,2,workspace)
            self.assertEqual(records,[('head_csv_0003',(0,1,0))])
            text=(workspace/'monitoring_targets.csv').read_text()
            self.assertIn('Well α / shallow',text)
            self.assertIn('requested_depth_m',text)
            self.assertIn('Outside',(workspace/'monitoring_omitted.csv').read_text())
            model._validate_monitoring_metadata(h,workspace)
            (workspace/'monitoring_targets.csv').write_text(text.replace('Well α / shallow','Changed label'))
            with self.assertRaisesRegex(RuntimeError,'labels'):
                model._validate_monitoring_metadata(h,workspace)


if __name__=='__main__':
    unittest.main()
