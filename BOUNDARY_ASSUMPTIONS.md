# Groundwater and surface boundary contract

The historical monthly-first default and downstream boundary sensitivity matrix
passed full numerical validation. The prescribed edge-flux addition uses bounded
short verification; see [EDGE_FLUX_VALIDATION.md](EDGE_FLUX_VALIDATION.md).
Substantial physical sensitivity and representation limits remain.
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
| Boundary conductance | `groundwater_boundary_k_m_per_day * cell_face_area / effective_resistance_length` | automatic K follows `K_constant`; resistance = domain length | Uncalibrated lumped resistance, not a remote control position |
| Prescribed groundwater edges | `groundwater_edge_flux.{x_min,x_max,y_max}_m3_per_day` | 0 m³/day each | Signed total per bottom-layer edge; positive inflow, negative outflow; uniform allocation via separate WEL packages |
| External surface outlet | Bed + `external_outlet_height_above_bed_m` | bed + 0 m | Independent Manning discharge control, never a GHB head |
| Initial river stage | Each pool's lowest bed + 0.10 m | local bed + 0.10 m | Initial condition only; later stages evolve |

The downstream DRN/GHB and free surface outlet are located on the low-elevation
longitudinal edge (minimum Y). For DRN/GHB, only cells whose bottoms lie below
the selected reference level are eligible, and all transverse columns must be
represented. Prescribed groundwater totals act independently on the bottom-layer
minimum-X, maximum-X and maximum-Y edges. The constant GHB and DRN levels
stay fixed through relaxation, spinup and all monitored years; changing
upstream inflow cannot change them. There is no exported or unused remote
river-stage series. Handoff v7 stores mode, levels, resistance, conductance and
independent outlet inverts, plus the three signed edge totals. Older handoffs
require fresh preparation with the current source.

## What remains assumed

- DRN assumes an open groundwater discharge path at the outlet elevation. It
  excludes groundwater inflow through that downstream drain and cannot represent
  external backwater. Other edges can independently supply prescribed inflow.
- The default conductance uses full eligible cell-face areas and an effective
  resistance length of one domain length. This remains a conceptual response
  parameter; it is not an observation of geology beyond the model edge.
- A Manning outlet at the modeled bed is an effective free-discharge approximation. Its
  width and optional height are still assumptions. It does not route a river
  outside the domain or calculate downstream backwater.
- Upstream and lateral groundwater edges default to zero flux. Three explicit
  bottom-layer edge totals can prescribe regional import or export; other
  exterior faces remain no-flow. Domain extent and assumed totals matter.
- Each coarse LAK pool has one stage. Manning transfers approximate a sloping
  river without receiving-pool backwater feedback. Fixed maximum footprints omit layer-1
  UZF even where the simulated lake is locally dry, as already documented.
- Synthetic inflow scaling, aquifer/lakebed properties, precipitation-to-
  infiltration partitioning and ET are assumptions independent of downstream
  heads. Planar heads and initial lake stages are initial states, not boundary
  observations. Spinup preserves storage; it does not guarantee equilibrium.

These limits must be reported with results. Boundary independence removes
hidden coupling; it does not remove physical uncertainty or validate a field
model. External backwater requires an alternative surface representation. Groundwater
import requires justified prescribed edge totals or an explicit GHB scenario.

## Outputs and checks

Every workspace publishes `boundary_assumptions.json` with the active package,
local level, conductance, resistance, independent outlet and limitations.
`bdam.groundwater_boundary_flux.csv` retains signed **downstream-only** exchange.
`bdam.specified_groundwater_flux.csv` reports realized signed x_min, x_max and
y_max rates and interval volumes from the three WEL packages. Positive means
into the domain. `boundary_assumptions.json` records totals, allocation, layer,
package names and disabled automatic flow reduction.

Derived `groundwater_boundary_inflow` / `groundwater_boundary_outflow` include
downstream and prescribed edges. Sum gross flows before opposing corner
contributions cancel. `drain_outflow`, `ghb_inflow`, `ghb_outflow` and
`ghb_net_volume_m3` remain downstream-only. `specified_*_net` fields identify
the individual edges; `specified_groundwater_inflow/outflow` give their gross
totals. All rates have corresponding interval volumes. A DRN cannot supply
inflow, but combined groundwater inflow can be positive when edges supply water.

Surface, atmospheric and combined GWF+UZF+LAK storage terms remain independent.
The coupled residual includes both downstream and prescribed edges. The runner
checks actual per-edge WEL totals against inputs, rejects mixed DRN/GHB terms,
and retains the strict closure tolerances and production calendar.

## Prescribed edge allocation

`groundwater_edge_flux.{x_min,x_max,y_max}_m3_per_day` specifies total m³/day
along each edge, default zero. Positive enters; negative leaves. Only bottom-layer
cells receive flux, distributed uniformly along edge length (equal shares on the
current uniform grid). Corner cells retain independent contributions from each
adjoining edge. At minimum-Y corners the downstream DRN/GHB also remains active.
The totals persist unchanged through every phase and restart. Separate WEL
packages implement these prescribed boundary terms; no pumping reduction is
allowed. An infeasible extraction must fail QA rather than silently change Q.
The inputs are regional exchange assumptions, not calibrated observations.

Native LAK rainfall and evaporation **observations** are volumetric m³/day,
as are their budget terms. The supplied atmospheric forcing depths are m/day.
The model calculates volumetric lake atmospheric exchange from the active lake
area, so identical forcing depths do not guarantee identical realized fluxes
when the outlet changes the wetted footprint.

## Sensitivity procedure

Use explicit case rows and generate fresh geometry and paired handoffs through
`Study.prepare` / `Study.evaluate`. Preserve
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
