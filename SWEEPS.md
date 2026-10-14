# Parameter sweeps and sensitivity runs

This branch defaults to 70 x 140 cells at 1 m spacing, five layers, 0 fall-average / 5 monthly / 2 weekly spinup years (no initial seven-day
relaxation with zero fall-average years), and
two monitored pre-dam plus two post-dam years. These are starting settings;
use interannual state changes to assess whether spinup is adequate.

## Configure and preview

Use a local nonsynchronized checkout and one persistent Python installation
with `requirements.txt`. Place a local `bin/mf6` in the checkout or an ancestor.
Edit the user input section in `MakeInputs.m`:

```matlab
K_constant = [0.01 0.03 0.06];
specific_yield = [0.10 0.20];
n_parallel_runs = 2;
forcing_controls.inflow.width_factor = [0.8 1 1.2];
```

This example has 18 Cartesian combinations. The default reference is included
once if it is among those combinations; otherwise an additional reference is
added. The reference uses branch defaults for swept fields and supplied scalar
values for fixed fields. Repeated candidate values are deduplicated.

All registered numeric scalar parameters, including nested `mf6_parameters`,
`dam_settings`, `post_dam` and forcing controls, accept candidate vectors.
Monthly climate vectors, layer-property vectors and hydrofacies tables keep
their array meanings. Strings/paths are fixed inputs. `n_parallel_runs` must
remain one positive integer. `[]` retains automatic defaults for optional
centers, dam sample spacing, layer arrays and GHB conductivity. An empty GHB
conductivity inherits each member's `K_constant`; explicit GHB candidates form
an independent axis. Empty layer arrays are generated after selecting `n_layers`.

```zsh
export BDAM_PYTHON="$(command -v python3)"
export BDAM_CAMPAIGN_ROOT=/absolute/local/path/my-campaign
matlab -batch "run('MakeGrid.m')"
BDAM_PREVIEW=1 matlab -batch "run('MakeInputs.m')"
```

Preview writes `campaign.json`, resolved configurations and immutable source
snapshots; it does not prepare HDF5 or launch MF6. All resolved scalar candidates
are checked first; full geometric/package validation occurs during serial
preparation, before any simulation starts. Invalid combinations are reported
with their values and never silently discarded. Choose a new campaign root
when changing its configuration or source. Existing manifests cannot be replaced
with different settings.

Optional `BDAM_CONFIG=/absolute/path/overrides.json` overlays the same input
schema before expansion. For example:

```json
{
  "K_constant": [0.01, 0.03],
  "specific_yield": [0.1, 0.2],
  "n_parallel_runs": 2,
  "forcing_controls": {
    "precipitation": {"shift_days": [-20, 0, 20]}
  }
}
```

To omit the reference, set `BDAM_SKIP_BASELINE=1` when planning with MATLAB,
or use `bdam_sweeps.py plan request.json ROOT --skip-baseline`. This also removes
an exact reference combination from the Cartesian product. No baseline result
is required to skip it. All-scalar settings with the baseline skipped generate
an empty campaign. Without an explicit campaign root and without sweep axes,
`MakeInputs.m` retains the usual `ModelInput/pre_dam` and `post_dam` layout.

## Prepare, run and resume

```zsh
matlab -batch "run('MakeInputs.m')"
python3 bdam_sweeps.py run "$BDAM_CAMPAIGN_ROOT/campaign.json"
```

Alternatively, prepare an existing preview with
`python3 bdam_sweeps.py prepare "$BDAM_CAMPAIGN_ROOT/campaign.json"`.
Preparation uses one serial MATLAB session and an exclusive campaign lock.
Each member has its own geometry copy, handoffs, staging, results, cache and
attempt logs; installed Python dependencies and the local executable are shared.

`n_parallel_runs` bounds active MF6 simulations, including every spinup phase.
Multiple launchers or agents sharing the same campaign obey the same OS capacity
locks and member claims. The model CLI also guards its exact output directory.
Do not bypass the campaign launcher, delete lock files, or edit snapshots.
On POSIX hosts, solver subprocesses inherit locks so a surviving MF6 process
continues to own its slot if its launcher exits. Windows uses byte-range locks;
the cross-process campaign tests are validated on macOS.

Repeat `run` to resume. Matching completed members are revalidated and skipped.
Prior failed outputs/staging remain under attempt directories. Independent
members continue after failures; the campaign exits nonzero when any member
fails. Inspect `members/ID/BDam/status.json` and `attempt-NNN/model_runner.log`;
live solver progress is in that attempt's staging `bdam.lst`. A quiet member
may be waiting for a slot.

`--reuse-baseline /path/to/completed/member/BDam` imports a completed reference
only when source/input/configuration fingerprints and result validation match.
Scheduling capacity and runtime paths do not change member identity. The
reference rating curve can be prepared even when baseline simulation is omitted.

## Periodic forcing and interpretation

Each driver (`precipitation`, `et`, `inflow`) has `magnitude_scale=1`,
`shift_days=0`, `width_factor=1` and `center_day=[]` by default. Positive shifts
delay the season. Centers are elapsed water-year days: zero is October 1. The
automatic center is the first maximum in the baseline daily curve.

Nonnegative cyclic Hermite cubics join in both value and first derivative
across every year boundary. Source annual integrals are preserved. The minimum
background remains; the excess is transported through a circular warp:

```text
theta' = 2 atan2(width_factor * sin(theta/2), cos(theta/2))
```

Widths above one broaden the peak region; widths below one narrow it. Timing
and width preserve annual mass; magnitude scales both background and excess.
Width is a local time dilation, not an exact standard-deviation multiplier.
Review actual circular RMS width in `forcing_diagnostics.json`. Constants and
zero forcing remain well defined. The smooth curves are integrated into MF6
STEPWISE interval means, so neighboring MF6 rates can still differ; annual
continuous periodicity does not require the first and last interval means to
be equal. Handoffs include exact monthly and weekly integrals for staged spinup.
The historical equal-month September/October/November fall average is retained.

Land infiltration follows transformed precipitation and the existing calendar
recharge factors; changing rain timing can therefore change annual infiltration.
Lake evaporation follows transformed ET. The baseline downstream rating curve
is held fixed across forcing variants with the same boundary configuration.
Out-of-range linear extrapolation is reported; stages below the downstream bed
are rejected. Every member uses its modified drivers throughout its own spinup
and monitored phases.

`forcing_mode="legacy"` retains the original stepwise source construction and
requires identity controls. Compare legacy and smooth baselines before interpreting
the effect of smooth forcing as a parameter sensitivity.

## Outputs and retention

`member_index.csv` records parameters, status, elapsed time, provenance location
and output paths. `ensemble_summary.csv` combines the original scientific summary
rows with member IDs and sweep values. Failed/pending members appear in the index
and are excluded from scientific result rows. Existing member summary formats
are retained. One locked collector writes campaign CSVs atomically; invoke
`bdam_sweeps.py collect campaign.json` to refresh them.

Full retention is the default. Explicit `run ... --retention compact` removes
large successful MF6 binaries/package inputs only after complete validation.
It keeps all scientific CSVs, JSON QA and solver statistics, listings, attempt
logs, forcing diagnostics, configuration/source/input provenance and extracted
restart arrays in `Runs/restart_states.npz`. Compact results do not support the
binary Results Viewer. Failed attempts always retain their complete diagnostics.

The older release disk/runtime figures describe a smaller grid and shorter run.
Measure the full-output baseline and peak simultaneous staging before allocating
a large campaign. Never weaken solver/budget checks to make a member pass.

## Validation

```zsh
MPLCONFIGDIR=/absolute/local/cache python3 -m unittest -v \
  test_bdam_workflow.py test_bdam_sweeps.py
```

Pilot acceptance requires the full 0/5/2 + 2/2 baseline, then a small factorial
campaign run serially and with two active solvers. Compare scientific summary
CSV values; timestamps and runtime logs are not scientific differences. Report
water-balance QA, saved-step counts, runtime, memory, storage and interannual
state changes. Random/interannual weather and distributed execution are deferred.
