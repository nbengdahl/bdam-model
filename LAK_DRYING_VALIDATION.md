# LAK dry-out fixes and validation — 2026-10-21

Implemented on `parameters-table` in commit `297bada`, based on `dc13802688db7d37e0429fe2f6db3571374fa619`. The subsequent user-selected LAK maximum stage change is **5e-7 m in both branches**. This supersedes the implementation recommendations in the investigation report; the original report/evidence remains unchanged.

## Changes

- Pond tables begin at the actual minimum connected terrain bed (default 0.0898476462222413 m), with **exactly zero volume** and 1 m² onset area. All terrain breakpoints supplement the configured sampling; the default pond now has 1423 rows instead of 81. Connected masks, capped extent, and upper linear volume extension are retained. Storage is recomputed from connected terrain, not corrected by subtracting a volume offset.
- MATLAB preparation and the Python builder reject trapped storage at the minimum VERTICAL connection stage and reject storage extending below the lowest connection. The old failing handoff is rejected before MF6 starts, with instructions to regenerate preparation.
- MF6 binary `DHDRY` (−1e30) becomes the physical empty-stage elevation in final/restart states and summaries. Annual restarts, conservative pre/post installation transfer, retained states, and adaptive spinup comparisons use decoded stages. Other invalid/inactive sentinels are errors. Positive water volumes are not snapped away.
- A separate rapid-recession test exposed oscillation even with valid geometry. LAK's internal `MAXIMUM_STAGE_CHANGE` is now **5e-7 m**, tighter than MF6's 1e-5 m default. MF6 also derives its lake finite-difference increment from this setting. It is recorded as `lak_maximum_stage_change_m` in solver statistics. **IMS profiles, 2000 outer iterations, IMS closures, budget thresholds, production calendars, and UZF capacities are unchanged.**

## Updated tolerance validation at 5e-7 m

Fresh local validation root: `/Users/nick.engdahl/BDamRuns/bdam-lak-5e7-20261021/table`.
MakeInputs regenerated default geometry and both handoffs from the updated source.
All 106 Python tests pass, including the exact recorded 5e-7 tolerance check.

The complete unchanged 0/4/1 default workflow passes: six workspaces, 308 saved
endpoints, 101 spinup-summary rows and 210 monitored-summary rows. Independent
checks verify normal termination, required binaries, saved times/counts, the
explicit 5e-7 LAK input and solver record, strict budgets, monitoring and
restart states. Maximum coupled discrepancy is **0.000002317809180317562%**
(limit 0.1%). Installation conserves 3.2072414433358545 m³ with an error of
-4.440892098500626e-16 m³, within the unchanged 1e-8 m³ criterion.
See `completion_checks.json` and `model_runner.log`.

Against the original 1e-7 reference across every saved endpoint, maximum
groundwater-head difference is 7.146457869922074e-10 m and maximum lake-stage
difference is 2.3314683517128287e-15 m. These differences are measured, not
silently treated as binary identity. No model process remains active.

The three-solve full-grid diagnostic passes with seven seven-day steps / 49 days.
Empty pools retain genuine MF6 DHDRY output through restart and volume-conserving
installation. Pond volumes are 0 → 0.637284643092 → 0.00101420688527 → 0 m³.
Maximum diagnostic coupled discrepancy is **0.001426206914609108%** (limit 0.1%).
The matched-input pre/post comparison with main also passes: shared numerical
MF6 inputs, including LAK, are identical; main intentionally omits the three
zero-total edge WEL packages. The comparison receipt is in the sibling
`main/parity/parity.json` directory.

## Original validation at 1e-7 m

All 106 Python tests pass. MATLAB preparation, monitoring, pool routing/segmentation and table-bridge tests pass; MATLAB static checks on changed preparation/test code are clean. All 16 viewer tests pass against completed full output (including the two tests initially skipped without a completed-output fixture). `git diff --check` passes.

The final three-solve full-grid diagnostic (`tools/verify_lake_drying.py`) passes strict completion and budget checks, with seven seven-day steps / 49 diagnostic days. These short schedules are separate tests; they do not change production calendars or create production completion receipts.

1. Eight pre-dam pools remain at **exactly zero volume** under evaporation for two steps; raw binary stages are DHDRY and decoded stages equal physical beds.
2. A dry annual restart preserves zero volume. Decoded dry stages pass the spinup metric without sentinel errors.
3. Installation merges the empty pools into an empty pond: before/after storage = **0 / 0 m³**, error = **0**. The pond then rewets to **0.637284643092 m³**, partially recedes to **0.00101420688527 m³**, and reaches **exactly zero volume** under stronger evaporation. All downstream pools also finish at exactly zero volume, with genuine DHDRY output. Initial and endpoint summaries contain physical stages throughout.

Maximum diagnostic coupled discrepancy: **0.0014262069%**, below the unchanged **0.1%** limit. Partial recession leaves real water because implicit end-stage evaporation is area-dependent; the test preserves that storage rather than forcing it to zero.

The partial recession is also the regression for the additional numerical issue: the original 1e-5 LAK tolerance failed after all 2000 outer iterations. A saved-state replay with 1000 local lake iterations still oscillated and was intentionally stopped after hundreds of outer iterations to limit wasted runtime. The same saved-state replay at 1e-7 converged and passed strict budgets. The final combined-cycle test then passed with the production setting.

## Original full default workflow at 1e-7 m

All six workspaces pass the runner's staged and published completion checks: normal termination; readable GWF/LAK/UZF binary output; monitoring, boundary and flux files; solver statistics; strict budgets. Independent final inspection confirms **308 saved steps**, 101 spinup-summary rows, 210 monitored-summary rows, finite decoded restart states, and conservative dam installation (error **0 m³**).

| Workspace | Saved steps | Final local days | Maximum coupled discrepancy |
| --- | ---: | ---: | ---: |
| spinup/first_annual | 12 | 365 | 8.462013e-07% |
| spinup/staged | 88 | 1460 | 1.9145174e-06% |
| pre_dam/year_01 | 52 | 365 | 1.810255e-06% |
| pre_dam/year_02 | 52 | 365 | 1.8036673e-06% |
| post_dam/year_01 | 52 | 365 | 8.3104468e-07% |
| post_dam/year_02 | 52 | 365 | 2.3178058e-06% |

Maximum default coupled discrepancy: **2.3178058e-06%** (limit 0.1%).

## Original baseline comparison

Against the October 16 prepared default, all 386 pre-dam HDF5 datasets are identical. Of 272 post-dam datasets, only the pond's stage/volume/area arrays and their shapes differ. Atmospheric masks, exchange footprints, conductivities, forcing and boundaries are unchanged. The old default numerical reference is the completed October 15 run.

A first full run containing the geometry/decoding changes, before tightening LAK's local tolerance, completed successfully; its spinup/pre-dam heads, stages, LAK budgets, UZF contents and UZF budgets were byte-identical to that reference. GWF budget binaries differ because the current branch also contains zero-default edge WEL packages absent from the older reference.

The final full run includes the stricter local LAK setting. Across all workspaces, maximum final groundwater-head change versus the trusted reference is **4.2395331e-08 m**; maximum lake-1 endpoint-stage change is **1.7611e-07 m**. These comparisons are recorded, not silently treated as byte-identical output.

## Original retained evidence and scope

Runtime: Python 3.14.6, FloPy 3.10.0, h5py 3.16.0, NumPy 2.5.2, MATLAB R2025b, MF6 6.7.0 (02/05/2026). All models and active source copies ran on nonsynchronized local storage. No dependencies or executables were upgraded.

Full final outputs: `/private/tmp/bdam-lak-fix-20261021/source/Runs`. Dry-cycle output: `/private/tmp/bdam-lak-fix-20261021/drying-final`. The first complete workflow is preserved as `source/Runs_backup_20261021_084235`. Test logs, failed-test workspaces, numerical controls and comparison scripts are retained under `/private/tmp/bdam-lak-fix-20261021/`. Small durable receipts/logs are copied to the project-level `lak-fix-evidence-2026-10-21/` directory.

There were 21 MF6 attempts during implementation: two full six-workspace default workflows, an initial short diagnostic, a three-workspace diagnostic that exposed the second failure, two isolated saved-state controls (one deliberately stopped), and the final three-workspace regression. The second complete workflow was necessary after the stricter LAK setting was added. Concurrency never exceeded the user's eight-simulation ceiling. No model process remains active.

Old inconsistent handoffs require fresh preparation from this source. No existing frozen study, generated handoff or historical model result was edited. The colleague's exact case remains unavailable; these tests establish the two repaired failure mechanisms and default regression behavior, not convergence for every possible parameter set.
