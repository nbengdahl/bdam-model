# Local downstream boundary contract

The monthly-first default and boundary sensitivity matrix pass full numerical
validation; substantial physical sensitivity and representation limits remain.
See [BOUNDARY_VALIDATION.md](BOUNDARY_VALIDATION.md) before interpreting results.

The default does not require a head or river-stage observation outside the
modeled domain. This removes the previous upstream-flow-derived remote stage,
0.50 m rating-curve swing, downstream slope projection and dependence of the
surface outlet on the first GHB head. Numerical closure does not establish
that any boundary is physically correct.

## Independent controls

| Control | Source | Default | Meaning |
|---|---|---|---|
| Groundwater mode | `groundwater_boundary_mode` | `drain` | Outflow-only DRN; cannot supply groundwater |
| Drain elevation | Modeled downstream channel bed + `drain_elevation_above_outlet_bed_m` | bed + 0 m | Discharge threshold; simulated heads remain unknowns |
| Optional constant GHB | Bed + `constant_ghb_head_above_outlet_bed_m` | bed + 0.10 m | Explicit assumed head; active only in `constant_ghb` mode |
| Boundary conductance | `groundwater_boundary_k_m_per_day * cell_face_area / effective_resistance_length` | background K; resistance = domain length | Uncalibrated lumped resistance, not a remote control position |
| External surface outlet | Bed + `external_outlet_height_above_bed_m` | bed + 0 m | Independent Manning discharge control, never a GHB head |
| Initial river stage | Each pool's lowest bed + 0.10 m | local bed + 0.10 m | Initial condition only; later stages evolve |

All boundaries are located on the low-elevation longitudinal model edge.
Only cells whose bottoms lie below the selected reference level are eligible.
All transverse columns must be represented. The constant GHB and DRN levels
stay fixed through relaxation, spinup and all monitored years; changing
upstream inflow cannot change them. There is no exported or unused remote
river-stage series. Handoff v6 stores mode, levels, resistance, conductance and
independent outlet inverts. Older handoffs require source regeneration.

## What remains assumed

- DRN assumes an open groundwater discharge path at the outlet elevation. It
  excludes regional groundwater import and cannot represent external backwater.
- The default conductance uses full eligible cell-face areas and an effective
  resistance length of one domain length. This remains a conceptual response
  parameter; it is not an observation of geology beyond the model edge.
- A Manning outlet at the modeled bed is an effective free-discharge approximation. Its
  width and optional height are still assumptions. It does not route a river
  outside the domain or calculate downstream backwater.
- Upstream and lateral groundwater edges are no-flow. Regional lateral
  groundwater supply is therefore excluded and domain extent matters.
- Each coarse LAK pool has one stage. Manning transfers approximate a sloping
  river without receiving-pool backwater feedback. Fixed maximum footprints omit layer-1
  UZF even where the simulated lake is locally dry, as already documented.
- Synthetic inflow scaling, aquifer/lakebed properties, precipitation-to-
  infiltration partitioning and ET are assumptions independent of downstream
  heads. Planar heads and initial lake stages are initial states, not boundary
  observations. Spinup preserves storage; it does not guarantee equilibrium.

These limits must be reported with results. Boundary independence removes
hidden coupling; it does not remove physical uncertainty or validate a field
model. External backwater or groundwater import requires a justified
alternative boundary representation and supporting data or explicit scenarios.

## Outputs and checks

Every workspace publishes `boundary_assumptions.json` with the active package,
local level, conductance, resistance, independent outlet and limitations.
`bdam.groundwater_boundary_flux.csv` is signed net exchange. The derived flux
and summary tables separately sum positive and negative **cell** rates as
`groundwater_boundary_inflow` and `groundwater_boundary_outflow`. In DRN mode
the first must be zero and `drain_outflow` supplies the second; GHB-only columns
are zero. In GHB mode the GHB-only columns hold gross exchange. Their
difference is the net boundary rate. All rates have matching interval volumes.

Surface inflow/outflow, atmospheric terms and combined GWF+UZF+LAK storage are
reported independently. The coupled residual includes the active DRN or GHB,
not a netted substitute for gross external totals. The runner rejects mixed
DRN/GHB budget terms, missing boundary records, changing reference levels,
invalid conductance and incomplete assumption audits. Required numerical
closure tolerances and the October–September calendar remain unchanged.

Native LAK rainfall and evaporation **observations** are volumetric m³/day,
as are their budget terms. The supplied atmospheric forcing depths are m/day.
The model calculates volumetric lake atmospheric exchange from the active lake
area, so identical forcing depths do not guarantee identical realized fluxes
when the outlet changes the wetted footprint.

## Sensitivity procedure

Use isolated source copies and regenerate geometry and both handoffs. Preserve
forcing, aquifer properties, treatment, calendar and solver settings. Compare
the same pre/post year and point locations; retain all storage changes.

1. Compare default drainage with explicit constant GHB to expose the effect of
   allowing groundwater import and of an assumed reference level.
2. Decrease or increase effective resistance by a factor of ten, changing
   conductance inversely while keeping the outlet and drainage level fixed.
3. Test a plausible local surface-control height independently of groundwater
   level. Compare lake stages, heads, wet/dry footprint, storage and outflow.
4. Test drainage elevation and a longer downstream domain when local head
   conclusions approach their tolerances. Domain extension changes geometry;
   compare matched physical locations, not row numbers or moving fractional
   monitoring points. It also changes the default resistance length unless
   that parameter is adjusted to keep conductance comparable.

Acceptability requires a scientific tolerance for the intended lake/head/flow
outcome. If results depend materially on plausible controls, retain that
uncertainty and obtain local outlet information or extend/change the domain.
Do not hide the dependence by prescribing unobserved heads or stages.

References: [MODFLOW 6 DRN](https://modflow6.readthedocs.io/en/latest/_mf6io/gwf-drn.html),
[MODFLOW 6 LAK outlets](https://modflow6.readthedocs.io/en/latest/_mf6io/gwf-lak.html).
