# River formulation in v0.2.0

The model targets comparative hydrologic balances rather than detailed channel hydraulics. Coarse LAK pools retain the 1 m terrain and groundwater grid without requiring a separate SFR reach for every groundwater cell.

## Selected formulation

Pre-dam pools use spacing equal to half the along-centerline distance from outlet to dam. The default terrain produces eight pools at 12.803 m spacing. After installation, the upstream pools merge into one pond and two downstream pools remain. Manning outlets use width 2 m, roughness 0.04 and the terrain channel grade; the dam crest remains a 2 m WEIR. The groundwater boundary remains local outflow-only DRN, with independent constant GHB available for sensitivity tests.

Only the pond's upper banks are excluded from direct groundwater exchange: connections extend to 1.25 m above the transverse thalweg. Full connected DEM topography still determines depth, area and volume. Downstream river exchange remains broad. All groundwater cells remain active. Surface storage is conserved when upstream pools merge; groundwater heads carry forward exactly and common UZF states are mapped by cell. `Runs/dam_installation_storage_audit.json` records the transition.

Settings are in `MakeInputs.m` under `river_settings`. Two downstream pools are the supported configuration; other counts are rejected. Legacy pre-dam width/depth variables construct intermediate geometry only and do not control the coarse river. Pools initialize 0.10 m above their local low bed. Post-dam preview depth does not override the conserved installation state. Regenerate both handoffs: schema v6 includes separate storage and groundwater-exchange masks, outlet laws and the coarse-river descriptor.

## Evidence for the choice

The default five-layer 0/4/1 spinup and weekly two-year pre-/post-dam workflow completed twice with identical scientific outputs. A matched two-year no-dam continuation isolates treatment effects from ongoing adjustment. In year 2 the dam changed annual surface outflow by -259.283 m³, storage accumulation by +156.359 m³, groundwater boundary export by +8.744 m³ and upstream surface-to-groundwater exchange by +201.573 m³. Relative to full pond-bank exchange, those treatment effects differed by 0.24%, 0.33%, 2.27% and 0.67%. Trimming removed 20.9% of pond connections while retaining full storage. At day 730, excluded flooded-bank heads were a median 2.3 cm below the broad-exchange case, maximum 7.3 cm; compensation is gradual.

An aggressive downstream bed-only exchange trim produced much larger local head differences and was rejected. A four-downstream-pool trial failed with a native solver crash during initial monthly spinup and is not an approved configuration. Do not alter closures or calendars to make failed variants pass.

## Interpretation limits

Each pool has a uniform stage: stepped stages and dry gaps remain. Transfers lack receiving-pool backwater feedback. Full storage footprints exclude surface UZF even where dry, omitting dry-bank land atmospheric treatment. The tested pre-dam regime gains groundwater; losing/disconnected regimes and general sensitivity rankings remain unvalidated. Two monitored post-dam years do not establish periodic equilibrium. Use matched no-dam controls when attributing changes to the dam, retain storage in the balance, and assess interannual change before interpreting parameter rankings.

Native `lakeN` stage/flux IDs identify individual features and differ between phases. Derived `lake1_to_groundwater` and `lake2_to_groundwater` columns aggregate geographic upstream/downstream exchange in both phases. The last outlet is external; post-dam outlet 1 is the crest transfer. Numerical budget closure validates accounting, not these physical assumptions.
