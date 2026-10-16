"""Fast edge allocation/package contracts; no native solver is launched."""
import json
from pathlib import Path
import tempfile
import unittest

import flopy
import numpy as np

import build_bdam_simulation as model


class EdgeFluxTests(unittest.TestCase):
    class Handoff:
        def __init__(self, totals=(3., -5., 7.)):
            self.values = {"/grid/ZTop": np.zeros((4, 3)), "/grid/Z": np.zeros((4, 3, 6))}
            self.values.update({f"/boundaries/edge_flux/{edge}_m3_per_day": np.asarray([q])
                                for edge, q in zip(model.EDGE_NAMES, totals)})

        def array(self, name):
            return self.values[name]

        def scalar(self, name):
            return float(self.values[name].ravel()[0])

    def test_bottom_layer_faces_orientation_and_corners(self):
        records = model._edge_flux_records(self.Handoff())
        expected = {"x_min": {(4, r, 0) for r in range(3)},
                    "x_max": {(4, r, 3) for r in range(3)},
                    "y_max": {(4, 0, c) for c in range(4)}}
        for edge, total in zip(model.EDGE_NAMES, (3, -5, 7)):
            self.assertEqual({r[0] for r in records[edge]}, expected[edge])
            self.assertAlmostEqual(sum(r[1] for r in records[edge]), total)
            self.assertTrue(all(r[1] == total / len(expected[edge]) for r in records[edge]))
        self.assertEqual(expected["x_max"] & expected["y_max"], {(4, 0, 3)})
        corner = [r[1] for data in records.values() for r in data if r[0] == (4, 0, 3)]
        self.assertEqual(len(corner), 2)
        self.assertLess(corner[0], 0)
        self.assertGreater(corner[1], 0)
        self.assertEqual(model.mf_cell(1, 1, 3, 5, 3), (4, 0, 0))

    def test_zero_packages_and_prescribed_extraction_without_reduction(self):
        for totals in ((0, 0, 0), (3, -5, 7)):
            with self.subTest(totals=totals), tempfile.TemporaryDirectory() as directory:
                ws = Path(directory)
                (ws / "boundary_assumptions.json").write_text('{}')
                sim = flopy.mf6.MFSimulation(sim_ws=ws)
                flopy.mf6.ModflowTdis(sim, nper=2, perioddata=[(1., 1, 1.), (1., 1, 1.)])
                gwf = flopy.mf6.ModflowGwf(sim)
                flopy.mf6.ModflowGwfdis(gwf, nlay=5, nrow=3, ncol=4, botm=[-1, -2, -3, -4, -5])
                model._build_edge_fluxes(gwf, self.Handoff(totals), ws)
                for edge, total in zip(model.EDGE_NAMES, totals):
                    package = gwf.get_package(f"WEL_{edge.upper()}")
                    self.assertIsNone(package.auto_flow_reduce.get_data())
                    self.assertTrue(package.save_flows.get_data())
                    data = package.stress_period_data.get_data()[0]
                    self.assertAlmostEqual(float(data['q'].sum()), total)
                    self.assertEqual(set(package.stress_period_data.get_data()), {0})
                audit = json.loads((ws / "boundary_assumptions.json").read_text())
                self.assertEqual(audit['specified_edge_fluxes']['x_min']['total_m3_per_day'], totals[0])

    def test_invalid_handoff_totals_fail(self):
        for value in (np.asarray([np.nan]), np.asarray([np.inf]), np.asarray([1, 2])):
            h = self.Handoff()
            h.values['/boundaries/edge_flux/x_min_m3_per_day'] = value
            with self.assertRaisesRegex(ValueError, 'finite scalar'):
                model._edge_flux_records(h)

    def test_package_budgets_keep_opposing_corner_flows_separate(self):
        class Budget:
            def get_data(self, text, totim, paknam2):
                self.assertions = (text, totim)
                q = {'WEL_X_MIN': [1, 1, 1], 'WEL_X_MAX': [-2, -1, -2], 'WEL_Y_MAX': [3, 4]}[paknam2]
                return [np.array([(v,) for v in q], dtype=[('q', float)])]
        rates = model._edge_budget_rates(Budget(), 1.)
        self.assertEqual(rates, dict(x_min=3, x_max=-5, y_max=7))
        self.assertEqual(sum(max(q, 0) for q in rates.values()), 10)
        self.assertEqual(sum(max(-q, 0) for q in rates.values()), 5)


if __name__ == '__main__':
    unittest.main()
