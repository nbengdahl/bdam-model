"""Case contract and persistent evaluation tests without MATLAB or MF6."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

import bdam
import bdam_runtime as rt

HERE=Path(__file__).resolve().parent
SCHEMA=rt.read(HERE/"bdam_parameter_schema.json")


class ResolutionTests(unittest.TestCase):
    def resolve(self,values=None,shared=None):
        return bdam.resolve_case(values or {},shared or {},SCHEMA)

    def test_defaults_are_generated_and_not_sweep_axes(self):
        cfg=self.resolve()
        self.assertEqual(cfg["river_settings"]["downstream_segments"],2)
        self.assertEqual(cfg["geometry"]["domain_length_y_m"],140)
        self.assertEqual(cfg["groundwater_boundary_k_m_per_day"],cfg["K_constant"])
        with self.assertRaises(ValueError): self.resolve({"K_constant":[.01,.02]})

    def test_row_defaults_arrays_and_indexed_overrides(self):
        cfg=self.resolve({"n_layers":3,"K_constant":.1,"geometry.bottom_widths_m[1]":3}, {"specific_yield":.15})
        self.assertEqual(cfg["K_by_layer_top_to_bottom"],[.03]*3)
        self.assertEqual(cfg["groundwater_boundary_k_m_per_day"],.1)
        self.assertEqual(cfg["specific_yield"],.15)
        self.assertEqual(cfg["geometry"]["bottom_widths_m"],[3,10])
        with self.assertRaises(ValueError): self.resolve({"geometry.bottom_widths_m":[2,10],"geometry.bottom_widths_m[1]":3})
        with self.assertRaises(ValueError): self.resolve({"geometry.bottom_widths_m[3]":3})

    def test_bad_values_and_unsupported_fields(self):
        for override in ({"K_constant":True},{"K_constant":None},{"K_constant":float("nan")},
                         {"specific_yield":""},{"river_settings.downstream_segments":0},
                         {"river_settings.downstream_segments":1.2},{"source_geometry_file":"old.mat"},
                         {"geometry.dam_relative_distance_upstream":1},{"longitudinal_direction":"x"},
                         {"geometry.domain_length_y_m":140.5},{"unknown":1}):
            with self.subTest(override=override),self.assertRaises(ValueError): self.resolve(override)

    def test_segment_counts_one_two_three(self):
        for n in (1,2,3):
            self.assertEqual(self.resolve({"river_settings.downstream_segments":n})["river_settings"]["downstream_segments"],n)

    def test_designs_are_external_and_seeded(self):
        self.assertEqual(len(bdam.grid_cases({"K_constant":[.01,.02],"specific_yield":[.1,.2]})),4)
        a=bdam.random_cases({"K_constant":[.01,.1]},3,42)
        self.assertEqual(a,bdam.random_cases({"K_constant":[.01,.1]},3,42))
        self.assertNotEqual(a,bdam.random_cases({"K_constant":[.01,.1]},3,43))

    def test_csv_preserves_names_pairs_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"cases.csv"
            path.write_text("case_id,K_constant,geometry.bottom_widths_m[1],metadata.label\na,0.01,3,first\nb,0.02,4,second\n")
            rows=bdam.read_cases(path)
            self.assertEqual([r["K_constant"] for r in rows],[.01,.02])
            self.assertEqual(rows[0]["geometry.bottom_widths_m[1]"],3)
            self.assertEqual(bdam._row(rows[0],0)["metadata"],dict(label="first"))
            path.write_text("case_id,K_constant\na,\n")
            with self.assertRaises(ValueError): bdam.read_cases(path)


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study=bdam.Study(Path(self.temp.name)/"study",dict(source=str(HERE)))

    def test_paired_rows_duplicates_and_mixed_failures(self):
        batch=self.study.submit([{"case_id":"a","K_constant":.01,"specific_yield":.1},
                                 {"case_id":"b","K_constant":.02,"specific_yield":.2},
                                 {"case_id":"copy","K_constant":.01,"specific_yield":.1},
                                 {"case_id":"bad","K_constant":-1}],"one")
        self.assertEqual(len(batch["cases"]),4)
        self.assertEqual(len(batch["members"]),2)
        self.assertEqual(batch["cases"][0]["execution_id"],batch["cases"][2]["execution_id"])
        self.assertEqual(batch["cases"][3]["error"]["phase"],"resolution")
        results=self.study.collect("one")
        self.assertEqual([r["case_id"] for r in results],["a","b","copy","bad"])
        self.assertEqual(results[-1]["status"],"failed")
        self.assertEqual(results[-1]["requested_parameters"]["K_constant"],-1)

    def test_batch_identity_and_subsequent_optimizer_batch(self):
        first=self.study.submit([{"K_constant":.02}],"iteration-1")
        self.assertEqual(first,self.study.submit([{"K_constant":.02}],"iteration-1"))
        with self.assertRaises(ValueError): self.study.submit([{"K_constant":.03}],"iteration-1")
        second=self.study.submit([{"K_constant":.02},{"K_constant":.04}],"iteration-2")
        self.assertEqual(first["members"][0]["id"],second["members"][0]["id"])
        self.assertEqual(len(rt.read(self.study.root/"campaign.json")["members"]),2)

    def test_numpy_optimizer_candidates_and_native_arrays(self):
        batch=self.study.submit([{"K_constant":np.float64(.02),"n_layers":np.int64(3),
                                 "geometry.bottom_widths_m":np.array([2.,10.])}],"numpy")
        self.assertEqual(batch["cases"][0]["status"],"pending")
        self.assertEqual(batch["cases"][0]["resolved_parameters"]["n_layers"],3)

    def test_nonfinite_candidate_is_a_case_failure(self):
        batch=self.study.submit([{"K_constant":float("nan")},{"K_constant":.03}],"finite")
        self.assertEqual([r["status"] for r in batch["cases"]],["failed","pending"])
        self.assertIn("finite",batch["cases"][0]["error"]["message"])
        self.assertNotIn("n_parallel_runs",batch["cases"][1]["resolved_parameters"])

    def test_case_ids_are_unique_and_safe(self):
        with self.assertRaises(ValueError): self.study.submit([{"case_id":"a"},{"case_id":"a"}],"x")
        with self.assertRaises(ValueError): self.study.submit([{}],"../x")

    def test_metadata_and_paths_do_not_change_identity(self):
        a=self.study.submit([{"case_id":"a","metadata":{"label":"first"}}],"a")
        b=self.study.submit([{"case_id":"b","metadata":{"label":"second"}}],"b")
        self.assertEqual(a["members"],b["members"])

    def test_snapshot_tampering_is_rejected(self):
        batch=self.study.submit([{}],"one")
        path=Path(batch["members"][0]["path"])
        rt.verify_snapshot(path)
        (path/"buildBDamGeometry.m").write_text("changed")
        with self.assertRaises(ValueError): rt.verify_snapshot(path)

    def test_runtime_and_source_changes_invalidate_reuse(self):
        a=self.study.submit([{}],"a")["members"][0]["id"]
        with patch("bdam.rt.runtime_provenance",return_value={"different":"runtime"}):
            b=self.study.submit([{}],"b")["members"][0]["id"]
        self.assertNotEqual(a,b)

    def test_csv_and_json_bridge_inputs_match_python(self):
        cases=Path(self.temp.name)/"cases.csv"
        cases.write_text("case_id,K_constant,specific_yield\na,0.01,0.1\nb,0.02,0.2\n")
        a=self.study.submit(cases,"csv")
        b=self.study.submit([{"case_id":"a","K_constant":.01,"specific_yield":.1},
                             {"case_id":"b","K_constant":.02,"specific_yield":.2}],"python")
        self.assertEqual(a["members"],b["members"])
        from bdam_matlab_bridge import main
        request=Path(self.temp.name)/"request.json"; response=request.with_name("response.json")
        rt.write(request,dict(root=str(self.study.root),batch_id="matlab",action="submit",settings=None,
                              cases=b["request"]["cases"]))
        main(request,response)
        self.assertEqual(rt.read(response)["members"],b["members"])

    def test_matlab_partial_settings_preserve_existing_capacity(self):
        from bdam_matlab_bridge import main
        study=bdam.Study(Path(self.temp.name)/"two-workers",dict(source=str(HERE),execution=dict(n_parallel_runs=2)))
        request=Path(self.temp.name)/"request.json"; response=request.with_name("response.json")
        rt.write(request,dict(root=str(study.root),batch_id="matlab",action="submit",settings=dict(source=str(HERE)),cases=[{}]))
        main(request,response)
        self.assertEqual(rt.read(response)["n_parallel_runs"],2)

    def test_summary_duplicates_and_failure_exclusion(self):
        batch=self.study.submit([{"case_id":"a","K_constant":.02},
                                 {"case_id":"duplicate","K_constant":.02},
                                 {"case_id":"bad","K_constant":-1}],"one")
        path=Path(batch["members"][0]["path"]); (path/"Runs").mkdir()
        (path/"Runs"/"weekly_summary.csv").write_text("time_days,stage_m\n365,1.2\n")
        rt.write(path/"completion.json",dict(elapsed_seconds=1))
        with patch("bdam.rt.complete",return_value=True):
            results=self.study.collect("one")
        self.assertEqual([r["status"] for r in results],["pass","pass","failed"])
        self.assertTrue(results[1]["reused"])
        with (self.study.root/"results"/"one"/"ensemble_summary.csv").open() as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual([r["case_id"] for r in rows],["a","duplicate"])
        self.assertEqual(rows[0]["parameter.K_constant"],"0.02")
        self.assertNotIn("parameter.pullman_monthly_precipitation_mm",rows[0])

    def test_manifest_edits_are_detected(self):
        self.study.submit([{}],"original")
        path=self.study.root/"batches"/"original.json"
        batch=rt.read(path); batch["cases"][0]["metadata"]={"edited":True}; rt.write(path,batch)
        with self.assertRaises(ValueError): self.study.collect("original")

    def test_settings_are_immutable(self):
        with self.assertRaises(ValueError): bdam.Study(self.study.root,dict(execution=dict(n_parallel_runs=2)))

    def test_concurrent_submission_merges_registry(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            batches=list(pool.map(lambda n:self.study.submit([{"K_constant":.01*n}],f"batch-{n}"),[1,2]))
        registry=rt.read(self.study.root/"campaign.json")
        self.assertEqual({m["id"] for m in registry["members"]}, {b["members"][0]["id"] for b in batches})

    def test_external_file_changes_invalidate_identity(self):
        file=Path(self.temp.name)/"hydro.csv"
        file.write_bytes((HERE/"usgs_13348000_hydrograph.csv").read_bytes())
        a=self.study.submit([{"usgs_hydrograph_file":str(file)}],"file-a")
        file.write_text(file.read_text()+"\n")
        b=self.study.submit([{"usgs_hydrograph_file":str(file)}],"file-b")
        self.assertNotEqual(a["members"][0]["id"],b["members"][0]["id"])
        rt.verify_snapshot(a["members"][0]["path"])

    def test_scientific_source_change_creates_new_execution(self):
        original=rt.file_hash
        a=self.study.submit([{}],"original")
        with patch("bdam.rt.file_hash",side_effect=lambda path:"changed" if Path(path).name=="buildBDamGeometry.m" else original(path)):
            # Copy verification also sees the substituted digest; identity must still differ.
            b=self.study.submit([{}],"changed")
        self.assertNotEqual(a["members"][0]["id"],b["members"][0]["id"])

    def test_frozen_campaign_rejected(self):
        import subprocess,sys
        manifest=Path(self.temp.name)/"legacy.json"
        rt.write(manifest,dict(version="bdam-campaign-v2"))
        process=subprocess.run([sys.executable,str(HERE/"bdam_sweeps.py"),"run",str(manifest)],capture_output=True,text=True)
        self.assertNotEqual(process.returncode,0)
        self.assertIn("Frozen sweep campaigns",process.stderr)

    def test_cli_template_roundtrip(self):
        import subprocess,sys
        path=Path(self.temp.name)/"template.csv"
        subprocess.run([sys.executable,"-m","bdam","template",str(path)],check=True)
        batch=self.study.submit(path,"template")
        self.assertEqual(batch["cases"][0]["status"],"pending")

    def test_evaluation_continues_after_preparation_failure(self):
        batch=self.study.submit([{"case_id":"ok"},{"case_id":"bad","river_settings.downstream_segments":200}],"mixed")
        good,bad=batch["members"]
        rt.write(Path(good["path"])/"prepared.json",{})
        rt.write(Path(bad["path"])/"status.json",dict(status="failed",phase="preparation",error="empty pool"))
        with patch.object(self.study,"prepare"),patch("bdam.rt.run_member") as run:
            results=self.study.evaluate("mixed")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1]["id"],good["id"])
        self.assertEqual(results[1]["error"]["phase"],"preparation")

    def test_empty_batch_does_not_start_matlab(self):
        self.study.submit([],"empty")
        self.assertEqual(self.study.evaluate("empty"),[])


if __name__=="__main__":
    unittest.main()
