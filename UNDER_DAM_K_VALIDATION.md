# Independent under-dam conductivity — 21 October 2026

Verified on `main` first, then ported and verified on `parameters-table` in
the `bdam-sweeps` checkout. Both branches remain uncommitted; existing halo
work, historical results and frozen studies were preserved.

## Definition

`dam_settings.under_dam_k_m_per_day` is a finite positive absolute conductivity,
default **1.0 m/day**. Every core cell has K = K33 equal to that scalar,
independently of background facies, layer or conductivity. Values below,
equal to or above background are accepted.

The actual core footprint is preserved. `leakage_halo_cells = 1` adds its
eight-neighbor plan-view halo in the same treated layers, clipped at domain
edges; 0 disables the halo. Halo K = (local background K + core K)/2 and
halo K33 = (local background K33 + core K)/2. At current background defaults,
halo K = **0.515** and K33 = **0.5015 m/day**. Pre-dam properties and cells
outside the union remain background.

Separate core/halo masks and union masks remain auditable. Main retains HDF5
v6; parameters-table retains HDF5 v8 and advances its parameter registry to
v7. Both table multiplier fields are removed and rejected, not converted
into m/day. Use fresh studies to adopt the new source. Old prepared handoffs
retain their stored physical arrays.

## Verification

| Check | main | parameters-table |
|---|---:|---:|
| Python suite | 36 passed | 107 passed |
| Full default saved endpoints | 308 | 308 |
| Maximum coupled discrepancy (%) | 0.00000334505 | 0.00000244029 |
| Installation volume error (m³) | 0 | -4.44e-16 |
| Dry/restart/rewet regression | Passed, 7 endpoints | Passed, 7 endpoints |

Each complete default has six workspaces, 101 spinup-summary rows and 210
monitored-summary rows. Independent completion audits verify readable
required binaries, counts/times, strict budgets, monitoring and valid restart
states. Calendars, IMS profiles, the 2000 outer cap, LAK tolerance 5e-7 m and
0.1% budget limit are unchanged. Installation conserves surface volume to
floating-point precision and preserves groundwater/common UZF states.

MATLAB helper/routing and the table branch's monitoring, pool-edge, case-table
and member-preparation suites pass. Cases cover uniform core K across
heterogeneous backgrounds, component-wise halo midpoints, shifted/diagonal
and boundary-clipped footprints, unchanged depth, halo disabled, invalid
values and below/equal/above-background conductivities. All 16 viewer tests
pass against fresh actual outputs, with zero failures and zero skips.
The synthetic constant-field contour warning is expected.

## Compatibility and study cases

- Absolute K = 0.15 m/day reproduces all 362 pre-dam and 248 post-dam shared
  datasets from the earlier constant-background halo preparation. The earlier
  flow comparison remains historical evidence at 0.15 m/day.
- Independent preparations with matched geometry and legacy forcing agree
  exactly in all 362 pre-dam and 252 post-dam shared datasets. The two MF6
  builders serialize identical shared physical inputs; the table branch's
  three zero-total edge WEL packages are explicitly excluded. Different native
  branch defaults are not claimed to produce identical results.
- Fresh study cases at explicit 0.5, inherited shared 0.2 and halo-disabled
  0.8 m/day pass resolution, preparation, immutable-snapshot and conductivity
  checks. The helper and v7 registry are included in each snapshot. These
  cases were prepared only; no production completion receipts were issued.
- The two branches use byte-identical conductivity helpers. Current guides,
  registry mirrors, generated reference, examples and override tests agree.

## Evidence and reproduction

Persistent local root:
`/Users/nick.engdahl/BDamRuns/bdam-absolute-k-20261021`.
`evidence/REPORT.md` contains the consolidated report. Completion, array,
parity, test and fresh-study receipts are in `evidence/`; full results are in
`main/Runs` and `parameters-table/Runs`; bounded drying results are separate.
Runtime is MATLAB R2025b, Python 3.14.6, FloPy 3.10.0, NumPy 2.5.2, h5py 3.16.0
and stock MF6 6.7.0. Initial test-wrapper configuration/path mistakes are
retained and excluded explicitly in the report; no model or solver changes
were made to bypass them.

Follow each branch's AGENTS.md for local setup, preparation and full-run
acceptance. Run `tools/verify_conductivity_halo.py` after preparation; its
`--under-dam-k` defaults to 1.0 and accepts 0.15 for the historical control.
Run the existing drying verifier separately. Reproduction helpers and source
hashes are retained with the receipts. These checks validate implementation
and the tested numerical runs, not field calibration or all possible K values.
