# Boundary and monthly-spinup validation — 14 October 2026

**Implemented and numerically validated in the main working tree.** Monthly-first spinup is faster, and downstream controls no longer require inferred remote heads or river stages. The comparisons also expose substantial remaining groundwater sensitivity to boundary resistance. The setup cannot be described as artifact-free or field-calibrated.

## Changes

- Default downstream groundwater boundary is local outflow-only DRN, with a threshold at the modeled outlet bed. Constant GHB is an explicit assumed-head sensitivity option. No remote rating curve, slope projection or upstream-flow-derived groundwater head remains in active preparation, export or runtime.
- Surface outlet invert and initial river depth are independent local terrain-based inputs. The old GHB-derived outlet was 0.592455 m; the new default is the modeled bed, 0.001567 m. Changing a groundwater reference level cannot change the outlet.
- Gross groundwater inflow and outflow are summed by cell sign before netting and included in coupled budgets. DRN cannot inject groundwater; GHB-only columns are zero in drain mode.
- Handoff v5 requires explicit mode, levels and outlet inverts. Older handoffs must be regenerated; they are not silently migrated. Every workspace includes a checked boundary_assumptions.json.
- Native LAK rainfall/evaporation observation units are documented correctly as m³/day. Their separately supplied forcing depths are m/day. Monitoring descriptions were regenerated with the owning source function; target CSV bytes stayed identical and numerical results were untouched.

## Monthly-first performance

The two constant fall-average years were replaced by two additional monthly-climatology years: **0 fall, 4 monthly, 1 weekly spinup years**. Total spinup remains five years. Zero fall years omits the separate 7-day fall relaxation. The historical first_annual folder contains 12 monthly periods. Every period still has one time step; the two monitored pre-dam and two post-dam years retain their weekly calendar.

| Measure | Prior annual-start plan | Monthly-first plan |
|---|---:|---:|
| Spinup solver time | 174.50 s | 72.61 s |
| Entire simulation solver time | 301.35 s | 195.06 s |
| Maximum spinup outer iterations | 1485 | 28 |
| Spinup time steps | 79 | 100 |

Spinup solver time decreased **58.39%**; entire-run solve time decreased **35.27%**. These are workstation measurements, not guaranteed runtimes elsewhere. The changed forcing path also changes initial conditions: maximum head differences are **0.2349 m after spinup**, **0.1438 m after the pre-dam years**, and **0.04545 m after the post-dam years**. This compares two conditioning paths, not merely execution speed at identical forcing.

## Boundary sensitivities

All five boundary cases use the same monthly-first spinup, five-layer 50 × 100 grid, atmosphere/stream forcing, material properties and BDA treatment. The legacy case deliberately retains the previous coupled boundary physics for comparison. The table below compares saved steps in **monitored year 2** against local DRN. The legacy difference includes both its groundwater reference assumptions and its elevated surface outlet; it does not isolate either one individually.

| Case | Max groundwater-head difference anywhere, pre/post | Max near-dam head difference, pre/post |
|---|---:|---:|
| Constant GHB, bed +0.10 m | 0.0357 / 0.0456 m | 0.0161 / 0.0137 m |
| DRN conductance ×10 | 0.2804 / 0.4791 m | 0.1403 / 0.1620 m |
| Surface outlet +0.10 m | 0.0773 / 0.0736 m | 0.0187 / 0.0130 m |
| Previous coupled setup | 0.5903 / 0.5771 m | 0.4405 / 0.2762 m |

The old arrangement materially influenced groundwater throughout the reach, despite small GHB flows relative to total stream inflow. Its approximately 0.59 m elevated outlet also maintained a pre-dam lake/river pool. Removing hidden coupling is therefore consequential. But eliminating remote-head inputs does **not** eliminate boundary uncertainty: a tenfold conductance change still shifts near-dam heads by about 0.16 m and some cells by 0.48 m. Effective resistance must be justified/calibrated or tested with a longer downstream domain before calling groundwater predictions boundary-insensitive.

## Inflow, outflow and storage

Rates are duration-weighted annual means in m³/day for monitored year 2. Positive storage means retention in combined GWF+UZF+LAK. Stream inflow remains 86.4 m³/day in all cases. GHB gross flows here are audited directly by cell sign, including the legacy case whose original summaries netted first.

| Case | Phase | Surface out | Gross groundwater in | Gross groundwater out | Annual storage increase |
|---|---|---:|---:|---:|---:|
| Local DRN (default) | pre_dam | 86.528316 | 0.000000 | 0.026347 | -15.938 m³ |
| Local DRN (default) | post_dam | 85.808263 | 0.000000 | 0.048839 | 148.109 m³ |
| Constant GHB, bed +0.10 m | pre_dam | 86.533280 | 0.000000 | 0.020528 | -15.453 m³ |
| Constant GHB, bed +0.10 m | post_dam | 85.817996 | 0.000000 | 0.042964 | 146.885 m³ |
| DRN conductance ×10 | pre_dam | 86.485146 | 0.000000 | 0.065129 | -15.125 m³ |
| DRN conductance ×10 | post_dam | 85.708937 | 0.000000 | 0.161906 | 141.484 m³ |
| Surface outlet +0.10 m | pre_dam | 86.517817 | 0.000000 | 0.027988 | -15.406 m³ |
| Surface outlet +0.10 m | post_dam | 85.804599 | 0.000000 | 0.050277 | 146.539 m³ |
| Previous coupled setup | pre_dam | 86.501553 | 0.004447 | 0.006453 | -0.610 m³ |
| Previous coupled setup | post_dam | 85.976794 | 0.000382 | 0.019566 | 97.062 m³ |

Surface outflow and stream inflow need not match: atmospheric exchange, groundwater export and changing storage also contribute. Actual lake precipitation/evaporation depend on wetted area; identical depth forcing does not guarantee identical realized flux when the outlet changes stage. All years and atmospheric components are retained in the numerical table, not only year 2.

## Important remaining limitations

- The free-outlet pre-dam LAK has only **0.33–2.33%** of its fixed connection footprint below simulated stage, versus **65.33–65.67%** in the legacy case. A single flat-stage LAK is a lumped reservoir, **not a routed sloping stream**. Its stage must not be interpreted as a longitudinal river profile. Local river-stage/wetting conclusions require a routed-channel representation or a justified alternative.
- Fixed maximum LAK footprints omit layer-1 UZF even where locally dry. This atmospheric partitioning limitation becomes more conspicuous with the low outlet and must be considered when interpreting infiltration and evaporation.
- DRN excludes regional groundwater import; the free outlet excludes external backwater; upstream and lateral groundwater edges remain no-flow. These are explicit conceptual assumptions, not observations beyond the model edge.
- Monthly-first spinup is faster but does not prove equilibrium. Initial-state sensitivity remains, and post-dam groundwater storage is still increasing during the monitored years. Sequential pre/post changes combine treatment response with continued transients.

## Numerical validation and provenance

All **28 final-package fast tests passed**. All **37 successful workspaces** across six complete simulations (five monthly-first cases plus the annual-start benchmark) passed normal termination, required nonempty outputs, expected saved times, solver-statistics and water-balance checks. Maximum coupled discrepancy was **0.00035037%**, against the unchanged 0.1% limit. Strict head/flow closure and damping were retained. No extra hidden time steps or years were added.

The annual-start experiment first exhausted caps of 100 and 1000. The lake residual kept decreasing; MF6 scales it to depth by time-step length/wetted area, making the shallow lake’s annual step stringent. An allowance of 2000 yielded convergence at 1485, close to its trend prediction. Monthly-first then required at most 28 spinup iterations. The allowance is recorded in solver statistics and does not force extra iterations after convergence. Both cap-limited workspaces and their logs remain preserved. One MATLAB runtime crash after geometry export was resolved by one unchanged retry; no model script assertion was reported.

Software: MATLAB R2025b Update 7; persistent Python 3.12; FloPy 3.10.0; h5py 3.16.0; NumPy 2.5.2; MODFLOW 6 6.7.0 (2026-02-05). Existing unrelated dependency compatibility warnings were already recorded during setup; all required tests and runs succeeded. Existing user layer and monitored-duration edits were preserved. Changes remain uncommitted in main.

Run root: `/Users/nick.engdahl/BDamRuns/boundary-fix-20261014`. Current default results are `monthly_drain/Runs`; other cases have their own Runs directories. Full numerical tables: `boundary_matrix_metrics.csv` and `.json`; spatial/point comparisons: `boundary_matrix_head_differences.json`; completion checks: `all_completion_checks.json`; performance: `spinup_benchmark.json`; figure: `boundary_sensitivity.png`; unit-documentation checks: `monitoring_documentation_checks.json`. All scripts, preparation/runner logs, closed results and diagnostic staging are retained.

Preserved failed staging folders: `local_drain-staging/bdam-spinup_first_annual-year_01-7f1svm1e` (100 cap) and `local_drain-staging/bdam-spinup_first_annual-year_01-cpd52tes` (1000 cap). Neither is an accepted simulation.

References: [MODFLOW 6 DRN](https://modflow6.readthedocs.io/en/latest/_mf6io/gwf-drn.html); [MODFLOW 6.7 LAK residual scaling and observations](https://raw.githubusercontent.com/MODFLOW-ORG/modflow6/6.7.0/src/Model/GroundWaterFlow/gwf-lak.f90).
