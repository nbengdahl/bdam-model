"""Conservative MVR routing, serialization and rejection of incomplete budgets."""
import json
from pathlib import Path
import tempfile
import unittest

import flopy
import numpy as np

import build_bdam_simulation as model


DTYPE = [("node", int), ("node2", int), ("q", float)]


class LakeMoverTests(unittest.TestCase):
    def setUp(self):
        self.routing = dict(n_lakes=3, outlets=[dict(outlet=i, provider=i, receiver=i+1 if i<3 else 0)
                                               for i in range(1, 4)])
        self.transfers = np.array([(1, 2, -10.), (2, 3, -8.)], dtype=DTYPE)
        self.debit = np.array([(1, 1, -10.), (2, 2, -8.), (3, 3, 0.)], dtype=DTYPE)
        self.credit = np.array([(1, 1, 0.), (2, 2, 10.), (3, 3, 8.)], dtype=DTYPE)
        self.external = np.array([(1, 1, 0.), (2, 2, 0.), (3, 3, -7.)], dtype=DTYPE)

    def check(self, **changes):
        values = dict(transfers=self.transfers, to_mvr=self.debit,
                      from_mvr=self.credit, external=self.external)
        values.update(changes)
        return model._check_mover_transfers(self.routing, **values)

    def test_matches_each_edge_and_excludes_internal_export(self):
        self.assertEqual(self.check(), (0., 10.))

    def test_zero_flow_edges_are_required_and_conservative(self):
        for records in (self.transfers, self.debit, self.credit, self.external):
            records["q"] = 0.
        self.assertEqual(self.check(), (0., 0.))
        with self.assertRaisesRegex(RuntimeError, "Missing"):
            self.check(transfers=self.transfers[:1])

    def test_missing_duplicate_misrouted_and_nonfinite_edges_fail(self):
        bad = self.transfers.copy(); bad["node2"][0] = 3
        nan = self.transfers.copy(); nan["q"][0] = np.nan
        reverse = self.transfers.copy(); reverse["q"][0] *= -1
        for records in (self.transfers[:1], self.transfers[[0, 0]], bad, nan, reverse):
            with self.subTest(records=records), self.assertRaises(RuntimeError):
                self.check(transfers=records)

    def test_missing_or_mismatched_debits_and_credits_fail(self):
        for key, original in (("to_mvr", self.debit), ("from_mvr", self.credit)):
            bad = original.copy(); bad["q"][1] += 1.
            for records in (original[:2], original[[0, 0, 2]], bad):
                with self.subTest(key=key, records=records), self.assertRaises(RuntimeError):
                    self.check(**{key: records})

    def test_external_double_counting_and_terminal_mover_fail(self):
        external = self.external.copy(); external["q"][0] = -10.
        debit = self.debit.copy(); debit["q"][-1] = -7.
        for change in (dict(external=external), dict(to_mvr=debit)):
            with self.assertRaises(RuntimeError):
                self.check(**change)

    def test_external_residual_limit_is_separate_from_transfer_conservation(self):
        external = self.external.copy(); external["q"][0] = 9e-5
        self.assertEqual(self.check(external=external), (0., 10.))
        external["q"][0] = -1.0001e-4
        with self.assertRaisesRegex(RuntimeError, "external residual"):
            self.check(external=external)
        debit = self.debit.copy(); debit["q"][0] += 1e-6
        with self.assertRaisesRegex(RuntimeError, "debit/credit"):
            self.check(to_mvr=debit)

    def test_lake_balance_handles_near_zero_without_weakening_real_flow_checks(self):
        residual, percent = model._check_lake_balances(np.array([1e-10]), np.array([3e-10]), .1)
        self.assertAlmostEqual(float(residual[0]), -2e-10)
        self.assertAlmostEqual(float(percent[0]), -100.)
        with self.assertRaisesRegex(RuntimeError, "Per-lake budget"):
            model._check_lake_balances(np.array([.01]), np.array([.02]), .1)

    def test_receipt_validation_checks_native_balances_without_rewriting_audit(self):
        class Budget:
            def get_times(self):
                return [7.]

            def get_unique_record_names(self):
                return [s.encode() for s in ("GWF", "RAINFALL", "EVAPORATION", "RUNOFF", "EXT-INFLOW",
                                             "WITHDRAWAL", "EXT-OUTFLOW", "STORAGE", "CONSTANT")]

            def get_data(self, text, totim):
                return [np.array([(1, 1, {"GWF": 1., "STORAGE": -1.}.get(text, 0.))], dtype=DTYPE)]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bdam.lake_routing.json').write_text(json.dumps(dict(version=1, n_lakes=1,
                method='MVR', outlets=[dict(outlet=1, provider=1, receiver=0)])))
            model._lake_routing_budget_qa(root, Budget(), .1)
            audit = root / 'bdam.lake_routing_balance.csv'
            before = audit.read_bytes(), audit.stat().st_mtime_ns
            model._lake_routing_budget_qa(root, Budget(), .1, write_output=False)
            self.assertEqual(before, (audit.read_bytes(), audit.stat().st_mtime_ns))
            audit.write_text(audit.read_text().replace('7.0,1,0.0,', '7.0,1,2.0,'))
            with self.assertRaisesRegex(RuntimeError, 'disagrees with native'):
                model._lake_routing_budget_qa(root, Budget(), .1, write_output=False)

    def test_serialization_preserves_laws_and_rejects_routing_or_control_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sim = flopy.mf6.MFSimulation(sim_ws=root)
            sim.simulation_data.float_precision = 18
            flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1., 1, 1.)])
            gwf = flopy.mf6.ModflowGwf(sim, modelname="bdam")
            flopy.mf6.ModflowGwfdis(gwf, nlay=1, nrow=1, ncol=3, top=1., botm=0.)
            original = [(0, 0, 1, "MANNING", .125, 2., .04, .005),
                        (1, 1, 2, "WEIR", 1.5, 3., 0., 0.),
                        (2, 2, -1, "MANNING", .01, 2., .04, .005)]
            outlets = model._build_lake_mover(gwf, original, 3, root)
            flopy.mf6.ModflowGwflak(gwf, pname="LAK_MAIN", mover=True, nlakes=3, noutlets=3,
                packagedata=[(i, .1, 1) for i in range(3)],
                connectiondata=[(i, 0, (0, 0, i), "VERTICAL", .1, 0., 0., 0., 0.) for i in range(3)],
                outlets=outlets)
            sim.write_simulation(silent=True)
            path = root / "bdam.lak"
            model.validate_lak_outlet_routes(path)
            self.assertEqual([r[2] for r in outlets], [-1, -1, -1])
            self.assertEqual([r[3:] for r in outlets], [r[3:] for r in original])
            mvr_path = root / "bdam.mvr"; text = mvr_path.read_text()
            mvr_path.write_text(text.replace("LAK_MAIN  1  LAK_MAIN  2", "LAK_MAIN  1  LAK_MAIN  3"))
            with self.assertRaises(ValueError):
                model.validate_lak_outlet_routes(path)
            mvr_path.write_text(text)
            path.write_text(path.read_text().replace("WEIR", "MANNING"))
            with self.assertRaisesRegex(ValueError, "control changed"):
                model.validate_lak_outlet_routes(path)


if __name__ == "__main__":
    unittest.main()
