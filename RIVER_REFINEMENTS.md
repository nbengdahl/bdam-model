# Coarse-river formulation

The model targets comparative hydrologic balances rather than detailed channel
hydraulics. Coarse LAK pools retain the terrain/groundwater grid while representing
longitudinal surface storage and one-way outlet transfers.

## Current configuration

`river_settings.downstream_segments` is a positive integer (default 2). Divide
the centerline distance from the outlet to the dam by this count to obtain the
nominal interval. Extend that spacing upstream before installation; add an
upstream remainder to the upstream-most pool instead of making a short extra
pool. If the upstream reach is shorter than an interval, it forms one pool.
Requests beyond available longitudinal channel cells or producing an empty pool
fail preparation; the code never lowers a requested count.

The default 70 × 140 terrain yields eight pre-dam pools and a post-dam pond plus
two downstream pools. Post-dam upstream pools merge; downstream pools remain
separate. Pools are ordered upstream to downstream. Native LAK numbers do not
track a fixed location across installation or across cases. Derived
`lake1_to_groundwater` / `lake2_to_groundwater` aggregate geographic upstream /
downstream exchange in both phases.

Channel transfers use Manning outlets (`river_settings.manning_width_m=2` m,
`manning_roughness=0.04`, terrain channel grade); the crest uses a WEIR with
`post_dam_weir_width_m=2` m. River inverts use the lowest channel-bed elevation
on each pool's downstream-most row (minimum Y). Interior/off-channel depressions
do not lower that outlet. The external outlet retains the independent local-bed
control; the pond weir retains the crest. The table interface currently supports
positive longitudinal slopes and minimum-Y downstream geometry only.

The runner delivers each internal outlet's discharge through MVR FACTOR 1,
with its native LAK receiver set to external, and preserves the physical chain
in `bdam.lake_routing.json`. This makes received water available consistently
to the lake solve and residual check in MF6 6.7.0. The final surface outlet
has no mover receiver. Native `outletN_flow` observations retain their hydraulic
outlet meaning; MVR records give the transferred rate. The small signed
difference after MF6's final outlet update remains in the external budget,
including inward residuals. The per-internal-outlet limit is 1e-4 m³/day;
debit/credit agreement remains 1e-8 m³/day. No residual is rounded away.

Every lake's native budget is checked using the existing 0.1% criterion with
an explicit 1e-8 m³/day absolute criterion at near-zero flow. Both absolute
and relative residuals are reported. This avoids interpreting roundoff at an
empty pool as a large physical imbalance. See `MVR_ROUTING_VALIDATION.md`.

Every pool initializes 0.10 m above its own lowest bed. The post-dam pond's
preparation seed is internal; actual installation conserves inherited pre-dam
surface volume and maps it into the post-dam storage tables. Groundwater heads
carry exactly, and common UZF features map by groundwater cell. Saturated /
inactive UZF zero sentinels restart at residual water content as required by MF6.
`Runs/dam_installation_storage_audit.json` records the surface transfer.

Pond tables start at the actual lowest connected terrain bed with zero volume
and positive onset area. Terrain elevations supplement the configured
`dam_settings.stage_table_rows` sampling, so exported tables may have more rows.
Connected storage is recomputed at those elevations; the capped area and linear
volume extension above the maximum footprint remain in effect. Preparation and
the MF6 builder reject trapped storage or storage below the lowest connection.
Regenerate old handoffs rather than editing their tables. MF6 dry stage values
(`DHDRY`, −1e30 in binary stage output) become physical bed elevations in restart
states and summaries, preserving zero volume through installation and spinup
comparisons. Inactive lake sentinels remain errors.

From a local copy with freshly prepared default `ModelInput`, run
`python3 tools/verify_lake_drying.py /absolute/local/new-verification-folder`
for bounded empty-state persistence, dry annual restart, conservative dry
installation, rewetting and recession checks. Its three full-grid diagnostic
solves retain the strict budget checks and produce no production receipt.
Recession may leave trace storage within MF6's existing stage closure; it is
preserved rather than rounded away. Exact zero-volume states remain reachable.
LAK's internal `MAXIMUM_STAGE_CHANGE` is 5e-7 m, tighter than its MF6 default
1e-5 m. MF6 derives its lake finite-difference increment from this tolerance;
the smaller increment prevents the reproduced rapid-recession oscillation.
IMS profiles/closures and budget tolerances are unchanged.

`tools/verify_lake_mover_drying.py` adds bounded wet-to-bed recession,
upstream-to-downstream rewetting, mixed wet/dry neighbors and inherited-state
restarts for every pre/post lake. It preserves trace water within the existing
stage tolerance. The original verifier separately requires genuine exact-zero
and DHDRY states through dry restart and installation. These diagnostic
calendars and extreme evaporation stressors never modify production forcing.

Only the pond's upper banks are excluded from direct groundwater exchange:
`pond_exchange_height_above_thalweg_m=1.25` m selects its connection footprint.
Full connected DEM topography supplies pond storage; downstream river exchange
remains broad. `river_storage_height_above_highest_bed_m=0.50` m limits river
storage tables. `dam_settings` controls pond table resolution/extent and the
under-dam K/K33 band; that property band is not the lake connection mask. Unity
property multipliers are valid. All groundwater cells remain active.

Use case/shared overrides in [PARAMETERS.md](PARAMETERS.md), not old editable
MakeInputs sections. Registry v4 rejects removed intermediate width/depth
controls. Regenerate v6 handoffs from current source; retain old studies with
their original snapshots. Geometry tests cover counts 1/2/3, upstream remainders,
resolution failures, channel outlet selection, crest/invert preservation and
small dams with unchanged under-dam conductivity. Numerical test coverage and
remaining convergence limits are in [PARAMETER_VALIDATION.md](PARAMETER_VALIDATION.md)
and [CLEANUP_VALIDATION.md](CLEANUP_VALIDATION.md).

## Historical formulation evidence (pre-table interface)

The default five-layer 0/4/1 spinup and weekly two-year pre-/post-dam workflow completed twice with identical scientific outputs. A matched two-year no-dam continuation isolates treatment effects from ongoing adjustment. In year 2 the dam changed annual surface outflow by -259.283 m³, storage accumulation by +156.359 m³, groundwater boundary export by +8.744 m³ and upstream surface-to-groundwater exchange by +201.573 m³. Relative to full pond-bank exchange, those treatment effects differed by 0.24%, 0.33%, 2.27% and 0.67%. Trimming removed 20.9% of pond connections while retaining full storage. At day 730, excluded flooded-bank heads were a median 2.3 cm below the broad-exchange case, maximum 7.3 cm; compensation is gradual.

An aggressive downstream bed-only exchange trim produced much larger local head differences and was rejected. A historical four-downstream-pool trial failed with a native solver crash during initial monthly spinup. This records that trial, not a categorical restriction on current configurable counts. Do not alter closures or calendars to make failed variants pass.

## Interpretation limits

Each pool has a uniform stage: stepped stages and dry gaps remain. Transfers lack receiving-pool backwater feedback. Full storage footprints exclude surface UZF even where dry, omitting dry-bank land atmospheric treatment. The tested pre-dam regime gains groundwater; losing/disconnected regimes and general sensitivity rankings remain unvalidated. Two monitored post-dam years do not establish periodic equilibrium. Use matched no-dam controls when attributing changes to the dam, retain storage in the balance, and assess interannual change before interpreting parameter rankings.

Native `lakeN` stage/flux IDs identify individual features and differ between phases. Derived `lake1_to_groundwater` and `lake2_to_groundwater` columns aggregate geographic upstream/downstream exchange in both phases. The last outlet is external; post-dam outlet 1 is the crest transfer. Numerical budget closure validates accounting, not these physical assumptions.
