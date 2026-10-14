# River refinement handoff

## Objective and agreed scope

Investigate whether the representation of the river produces credible longitudinal
stages, wetted area and groundwater exchange before and after dam installation.
The user accepts that downstream conditions must remain assumptions. Retain the
local outflow-only groundwater drain as the default, constant GHB as an explicit
sensitivity option, and the independently specified local surface outlet. Assume
the external aquifer has the same hydraulic conductivity as the domain. Do not
make obtaining unavailable downstream heads or stages a prerequisite for progress.

The user requested no additional tests or simulations during this handoff task.
None were run for this commit. A future investigation should establish its run
scope with the user and follow AGENTS.md for local execution and validation.

## Current implementation

Main uses handoff schema v5. Regenerate inputs rather than silently migrating v4.
MakeInputs.m defines the local boundary and surface outlet independently;
ExportPreparationForFloPy.m exports them; build_bdam_simulation.py builds DRN or
constant GHB and LAK, and audits gross external budgets. Default spinup is zero
fall-average years, four monthly years and one weekly year, with two monitored
pre-dam and two post-dam years. Both IMS profiles allow 2000 outer iterations;
closure tolerances and damping were retained. Monthly-first spinup reduced measured
spinup solver time from 174.50 to 72.61 seconds and maximum iterations from 1485
to 28. Conditioning paths differ, so faster convergence is not proof of equilibrium.

The parameter-sweeps branch receives solver/spinup infrastructure separately;
that synchronization does not port the v5 boundary physics. Check its schema and
source before comparing campaigns with main. Existing campaign snapshots should
remain immutable; prepare a new campaign for changed source/configuration.

## Evidence behind the concern

The pre-dam river is one LAK feature with a single stage across a sloping channel.
After dam installation, separate LAK features represent the upstream pond and
downstream river. A spatially constant stage can be appropriate for a pond but
does not resolve a flowing river's longitudinal water-surface gradient.

The previous external outlet was derived from a projected GHB head, approximately
0.592455 m. The corrected default outlet is at the local bed, 0.001567 m. Removing
that undocumented elevated control substantially changes river wetting and heads:
in monitored year 2, only 0.333–2.333% of the fixed 300-cell pre-dam lake footprint
lies below simulated stage in the local-drain case, compared with about 65% in the
legacy coupled setup. The post-dam upstream pond remains about 86% wetted.

These percentages are geometry/stage diagnostics, not proof that every remaining
LAK cell has zero exchange. Inspect actual connection and budget behavior. Cells
in the fixed lake footprint are excluded from layer-1 UZF even when dry. This can
affect rainfall, evaporation and infiltration partitioning. Equal atmospheric
forcing depths therefore do not guarantee equal realized atmospheric volumes.

The combined legacy boundary/outlet comparison changed near-dam groundwater
heads by up to 0.44 m before the dam and 0.28 m afterward. This comparison changes
multiple controls; do not attribute its entire difference to the river outlet.
Raising only the new surface outlet by 0.10 m changed near-dam heads by about
0.019 m pre-dam and 0.013 m post-dam. A tenfold drain conductance changed near-dam
heads by about 0.16 m, illustrating conceptual boundary sensitivity rather than
an identified conductivity error. The accepted same-K downstream assumption does
not independently determine the effective flow length in C = K A/L.

## Suggested investigation path

1. Trace river masks, LAK stage/area/volume tables, bed elevations, connection
   elevations and conductances, outlet equations, and UZF exclusions from geometry
   through export to FloPy. Map their dependence on stage and identify what a dry
   river-footprint cell actually does in each package.
2. Use existing results first. Plot longitudinal bed and water-surface elevation,
   wetted width/area, LAK–GWF exchange by connection/location, infiltration and ET
   inside versus outside the river footprint, and downstream discharge. Distinguish
   native signed exchange from gross inflow/outflow and check units. LAK rainfall
   and evaporation observations are m3/day; forcing depths are m/day.
3. Define a physically meaningful reference for this demonstration geometry:
   flowing water should have a plausible longitudinal profile and local depth,
   exchange should follow local river–aquifer gradients, dry channel land should
   have an explicit atmospheric treatment, and the dam should create an upstream
   impoundment without imposing a flat surface on the entire downstream reach.
   Do not restore the old elevated outlet merely to make more cells wet.
4. Assess an SFR representation for pre-dam and downstream flowing reaches, while
   retaining LAK for the pond. Investigate supported SFR–LAK transfers through MVR
   and explicitly account for BDA overflow and porous exchange. A segmented LAK
   alternative may be simpler, but its inter-segment hydraulics and artificial
   controls need justification. Read current official MF6/FloPy documentation
   before choosing or implementing a formulation; no architecture has been selected.
5. Propose the smallest coherent change and a matched comparison. Keep aquifer
   properties, accepted downstream assumptions, upstream inflow, atmospheric
   forcing and dam geometry fixed. Compare integrated budgets, longitudinal stages,
   wetting, near-dam heads and dam response. Preserve restart mapping, forcing
   integration, gross boundary accounting and closure criteria. Do not loosen
   tolerances or add time steps simply to obtain convergence.
6. Assess conditioning separately from river formulation: monthly versus annual
   conditioning changed maximum heads by 0.235 m after spinup and 0.045 m at the
   end of the post-dam years. Interannual drift remains; neither numerical closure
   nor these five spinup years establish a periodic steady state.

## Existing evidence and deliverables

Read BOUNDARY_VALIDATION.md and BOUNDARY_ASSUMPTIONS.md first. Full local evidence
is in `/Users/nick.engdahl/BDamRuns/boundary-fix-20261014`: cases monthly_drain,
constant_ghb, raised_surface_outlet, low_resistance, legacy, and the annual-start
local_drain benchmark. Useful artifacts include boundary_matrix_metrics.csv,
boundary_matrix_head_differences.json, boundary_sensitivity.png,
spinup_benchmark.json and all_completion_checks.json. The previous work passed
28 workflow tests and completion checks for 37 successful workspaces; that is
historical validation, not validation of a future river change.

Deliver an explicit diagnosis of any river/atmospheric artifact, a justified
formulation choice, the implementation/restart implications and a comparison plan.
Keep accepted conceptual assumptions visible without treating their unavoidable
uncertainty as a blocker. Separate numerical closure from physical credibility.
