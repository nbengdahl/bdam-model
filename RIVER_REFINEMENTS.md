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

Every pool initializes 0.10 m above its own lowest bed. The post-dam pond's
preparation seed is internal; actual installation conserves inherited pre-dam
surface volume and maps it into the post-dam storage tables. Groundwater heads
carry exactly, and common UZF features map by groundwater cell. Saturated /
inactive UZF zero sentinels restart at residual water content as required by MF6.
`Runs/dam_installation_storage_audit.json` records the surface transfer.

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
