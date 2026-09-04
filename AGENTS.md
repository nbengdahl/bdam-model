# Instructions for AI agents

Follow this file exactly. Do not improvise around a failed or quiet run.

## Non-negotiable rules

1. Read `README.md` and `END_USER_QUICK_START.md` before running anything.
2. Never run MATLAB, Python, or MODFLOW from Google Drive, OneDrive, Dropbox,
   iCloud Drive, a network share, or this source folder if it is synchronized.
3. By default, copy the unopened tarball to a persistent, local,
   non-synchronized run directory under `~/BDamRuns` and extract it there.
   Keep source packages and model runs separate. If the user directs a
   different run folder, use it provided it is local, non-synchronized, and
   has enough free space.
4. Install every package in `requirements.txt` once for the selected
   `python3` interpreter and reuse that interpreter for every BDam run. Never
   create `.venv` or install Python packages inside an individual run
   directory. The Python installation may come from any provider; do not
   assume or require a particular package manager.
5. Use the packaged default settings unless the user explicitly requests a
   configuration change.
6. Run the three build/run commands in the documented order. Do not skip a
   step and do not hand-edit `Geometry`, `ModelInput`, or `Runs`.
7. Never add MODFLOW time steps or change the daily/weekly calendar to address
   convergence or output problems. Unless the user explicitly requests
   sub-steps, each configured fall-average year has exactly 1 stress period,
   1 time step, and 1 output; each monthly year has 12; and each weekly year
   has 52. Counts scale only with configured years (for example, 2/1/1 gives
   2 annual, 12 monthly, and 52 weekly outputs). The 7-day initial relaxation
   remains exactly 1 stress period, 1 time step, and 1 output.
8. Before starting MODFLOW, check for an existing `build_bdam_simulation.py`
   or `mf6` process. If another model run is active, stop and ask the user
   whether it should remain active. Do not start a duplicate run.
9. A quiet terminal does not mean the run is stuck. The runner captures MF6
   stdout. Check the active `bdam.lst`, file growth, and process activity.
10. Do not restart a progressing run merely because it is quiet.
11. Do not declare success from the MF6 termination line alone. Apply every
    completion check below.
12. Work through routine environment restrictions without changing the model.
    Stop only when correctness is uncertain, a required dependency is truly
    unavailable, validation fails, or proceeding would require a model change.

## Exact run procedure

The paths below are examples. Replace the source tarball path and choose a
unique local run name. The default location under the user's home directory
persists across restarts.

### 1. Make a clean local run copy

```zsh
mkdir -p "$HOME/BDamRuns/bdam-run-YYYYMMDD"
cp /absolute/path/to/BDam-v0.1.0.tar.gz \
  "$HOME/BDamRuns/bdam-run-YYYYMMDD/BDam-v0.1.0.tar.gz"
tar -xzf "$HOME/BDamRuns/bdam-run-YYYYMMDD/BDam-v0.1.0.tar.gz" \
  -C "$HOME/BDamRuns/bdam-run-YYYYMMDD"
cd "$HOME/BDamRuns/bdam-run-YYYYMMDD/BDam"
```

Confirm that `pwd` does not contain the name of a cloud or synchronized
folder. If it does, stop and relocate the run.

Check available local space before setup:

```zsh
df -h ..
```

Reserve at least 4 GB for the default staged 1/1/1 spinup plus weekly 1/1
pre-/post-dam run. More is needed if
backups will be retained. Confirm that the selected home-directory path is on
a local disk and is not redirected into a synchronized or network folder.

### 2. Put MODFLOW in the local run tree

The executable must be named `mf6`. Copy it; do not reference an executable
inside a synchronized folder during the run.

```zsh
mkdir -p ../bin
cp /absolute/path/to/mf6 ../bin/mf6
chmod +x ../bin/mf6
../bin/mf6 -v
```

Expected validated version: `6.7.0 02/05/2026`. Report a different version.

### 3. Install the Python packages and run fast tests

Install the requirements once for the user's selected Python 3.12-or-newer
interpreter. This is a machine setup step, not a per-run step. The `--user`
location is shared by all runs made with that interpreter and does not require
administrator access. If the requirements are already installed, pip verifies
them without creating duplicates. Never create a `.venv` in the run tree.

```zsh
python3 --version
python3 -m pip install --user -r requirements.txt
mkdir -p ../matplotlib-cache
MPLCONFIGDIR=../matplotlib-cache \
  python3 -m unittest -v test_bdam_workflow.py
```

All tests must pass. If dependency installation fails because network access
is blocked, request network permission and retry the same install command.
Do not change package versions or substitute a different interpreter between
setup and execution. If the selected Python provider manages packages through
its own environment mechanism, install `requirements.txt` once into that
persistent environment and continue using its `python3`; do not create an
environment inside each BDam run.

### 4. Check for duplicate runs

```zsh
pgrep -fl 'build_bdam_simulation.py|mf6' || true
```

If this shows another real model process, do not start. Identify its run
directory and ask the user whether to wait for it or terminate it. Never kill
an existing process without authorization.

Some managed agent sandboxes do not allow `pgrep` to read the process list and
may print `Cannot get process list` or a `sysmon` error. That is an environment
restriction, not a model failure. Request read-only process-inspection
permission and retry with:

```zsh
ps -axo pid,ppid,state,etime,%cpu,%mem,command | \
  rg 'build_bdam_simulation|/mf6' | rg -v 'rg ' || true
```

If `rg` is unavailable, use `grep -E` for this diagnostic only. A process-list
check that prints no matching model process is a clean result.

### 5. Build inputs in order

Run from the local `BDam` directory:

```zsh
matlab -batch "run('MakeGrid.m')"
matlab -batch "run('MakeInputs.m')"
```

In a managed sandbox, MATLAB may exit with code 1 and no diagnostic because it
cannot reach its runtime, preferences, or license service. This is not a
reason to edit a MATLAB script. First locate MATLAB with `command -v matlab`,
then request permission to run that same installed executable with its normal
runtime/license access and retry the unchanged `-batch` expression once. If
the permitted retry still fails, stop and report its output.

Do not continue unless these files exist and are nonempty:

```text
Geometry/BDamGeometry.mat
ModelInput/pre_dam/preparation_handoff.h5
ModelInput/post_dam/preparation_handoff.h5
```

### 6. Run the model with a visible agent log

Use unbuffered Python output, a writable Matplotlib cache, an explicit local
staging directory, and `pipefail` so logging cannot hide a failed exit code.

```zsh
mkdir -p ../staging
set -o pipefail
MPLCONFIGDIR=../matplotlib-cache PYTHONUNBUFFERED=1 \
  python3 build_bdam_simulation.py ModelInput \
  --staging-root ../staging 2>&1 | tee ../model_runner.log
```

Do not run this command a second time while the first process is active.

The 7-day September--November-average relaxation from analytical initial
conditions uses the robust COMPLEX initialization settings. The runner then
uses the `conservative` profile only for the first 365-day annual run and
returns to the faster `balanced` profile for every subsequent run,
including every remaining fall-average, monthly, and weekly part of staged
spinup and all monitored pre-dam and post-dam years. The strict closure
tolerances remain unchanged between profiles. Do not pass
`--solver-profile conservative`; the runner manages the one conservative
annual solve internally and prevents conservative settings from being applied
globally. If MF6 specifically reports that UZF `NWAVESETS` must be increased, change
`mf6_parameters.uzf_nwavesets` from 20 to 40 in `MakeInputs.m`, regenerate the
paired handoffs, and rerun. Never increase wave sets automatically or alter
the calendar. Use `--solver-inner-output` only for detailed solver diagnosis.

FloPy may print a line resembling the following during each phase setup:

```text
<flopy.mf6.data.mfstructure.MFDataItemStructure object at 0x...>
```

This is harmless diagnostic noise, not an exception. A real Python failure
contains `Traceback`, an exception name, or a nonzero command exit status.

## How to monitor a quiet run

The Python log reports phase-level information, but MF6 progress is written
to `bdam.lst` in the active staging workspace. `mfsim.lst` mostly contains
startup and final status, so it is the wrong file for live progress.

Find the active workspace:

```zsh
find ../staging -mindepth 1 -maxdepth 1 -type d -name 'bdam-*' -print
```

There should be at most one active staging workspace for this run. Use the
printed directory in these guarded checks:

```zsh
active_workspace=$(find ../staging -mindepth 1 -maxdepth 1 \
  -type d -name 'bdam-*' | head -1)
if [[ -n "$active_workspace" && -s "$active_workspace/bdam.lst" ]]; then
  rg -o 'STRESS PERIOD +[0-9]+' "$active_workspace/bdam.lst" | tail -1
  ls -lh "$active_workspace/bdam.lst"
  du -sh "$active_workspace"
else
  echo "No active bdam.lst yet; the runner may be between annual workspaces."
fi
pgrep -fl 'build_bdam_simulation.py|mf6' || true
```

A growing `bdam.lst` or output workspace plus an active `mf6` process means
the model is progressing. An empty `Runs` directory is normal while an annual
workspace is staged: a year appears in `Runs` only after it passes validation.

At an annual transition, the new staging directory can exist for a few seconds
before `bdam.lst` is created. A one-time missing-file result at that boundary
is normal. Wait briefly and repeat the guarded check; do not restart. The
default phase sequence is `spinup` → `pre_dam` → `post_dam`. The runner prints
an explicit spinup completion line, but it may begin post-dam setup without a
separate `Completed pre-dam` line. The new post-dam staging directory is the
evidence that the pre-dam year was published successfully.

Model time follows an October 1--September 30 water year. All forcing,
downstream-stage, and GHB series must retain this alignment; elapsed model-time
counters remain ordinary days from zero.

If no files change and the `mf6` process uses no CPU across repeated checks,
collect the active staging path and the ends of `bdam.lst` and `mfsim.lst`,
then report the evidence. Do not change model settings or restart blindly.

## Completion checklist

The default staged-spinup plus weekly pre-/post-dam run should produce these directories:

```text
Runs/spinup/initial_relaxation
Runs/spinup/first_annual
Runs/spinup/staged
Runs/pre_dam/year_01
Runs/post_dam/year_01
```

For every completed workspace, verify all of the following:

- `mfsim.lst` contains `Normal termination of simulation.`
- `bdam.hds`, `bdam.cbc`, `bdam.lak.stage`, `bdam.lak.bud`,
  `bdam.uzf.wc`, and `bdam.uzf.bud` exist and are nonempty.
- The runner accepted the configured final saved time (7 days for the initial
  relaxation, 365 days for the first annual spinup workspace, the configured
  remainder duration for `spinup/staged`, and 365 days for each monitored
  annual workspace).
- `bdam.water_balance.json` exists and contains `"status": "pass"`.
- `bdam.solver_stats.json` exists and reports normal termination, the selected
  profile, UZF wave capacity, solve time, iteration totals, and MF6 version.
- Raw point-observation CSVs and `bdam.fluxes.csv` are present in every
  spinup, pre-dam, and post-dam year.
- `Runs/spinup_summary.csv` and `Runs/weekly_summary.csv` exist for the default
  run. Daily mode uses `Runs/daily_summary.csv` instead.
- No Python or `mf6` process from the run remains active.

The runner may exit without printing a final celebratory message. Exit status
zero plus the complete validation checklist is success. Do not require an
extra phrase that the runner does not promise to print.

The default run is expected to use about 2.1 GB in `Runs`. Report the
absolute run and output paths, configuration, dependency versions, tests,
completion checks, warnings, and any retained diagnostic staging directory.

## Common mistakes to avoid

- Running inside the project’s Google Drive folder.
- Starting another run because the terminal is quiet.
- Watching `mfsim.lst` instead of the active `bdam.lst`.
- Running several copies of MODFLOW and making all of them slow.
- Treating a nonfatal Matplotlib cache warning as a model failure. Set
  `MPLCONFIGDIR` as shown above.
- Treating an empty `Runs` directory during staging as a failure.
- Deleting or overwriting `Runs_backup_*` or retained diagnostic staging data
  without the user’s permission.
- Editing generated files or weakening validation to force a pass.

## Error-handling ladder

Use this order. Do not jump directly to changing source code or model inputs.

| Symptom | Correct action |
|---|---|
| Pip cannot resolve or connect to PyPI in a sandbox | Request network permission and retry the unchanged pinned install command. |
| Pip says its normal cache directory is unwritable | Continue; this only disables the cache. Do not use `sudo`. |
| Matplotlib reports an unwritable home cache | Set `MPLCONFIGDIR` to the documented local cache and continue. |
| `pgrep` cannot inspect processes | Request read-only process permission and use the documented `ps` fallback. |
| MATLAB exits 1 with no output in a sandbox | Request MATLAB runtime/license access and retry the same command once. |
| FloPy prints an `MFDataItemStructure object` line | Continue; it is cosmetic. |
| Active staging directory temporarily lacks `bdam.lst` | Treat it as a possible annual transition and repeat the guarded check shortly. |
| `Runs` is empty while MF6 is active and staging files grow | Continue monitoring; publication happens only after annual validation. |
| Required test fails, MATLAB reports a script/model assertion, MF6 exits nonzero, a required output is unreadable, final time is not 365 days, or water balance does not pass | Stop. Preserve the diagnostic staging workspace and report exact evidence. Do not alter physics, calendar, solver rules, or validation. |
| First 365-day annual solve needs the more robust IMS profile | The runner applies `conservative` only to that annual solve and automatically resumes every remaining staged-spinup and monitored solve with `balanced`; never apply `conservative` globally. |
| MF6 reports that UZF `NWAVESETS` must be increased | Change the user-defined value from 20 to 40, regenerate both handoffs with `MakeInputs.m`, and rerun. Increase further only if MF6 repeats the same error. |

## Reproducibility comparisons

When comparing two successful runs, compare scientific content instead of
expecting every generated text file to have the same bytes.

- Summary CSVs, monitoring CSVs, water-balance JSON, and binary GWF/LAK/UZF
  results should be compared directly.
- FloPy input text files contain generation timestamps.
- MODFLOW listing files contain timestamps, executable paths, and elapsed
  runtime information.
- MATLAB geometry files contain an `exported_at` value and a file-creation
  header.
- Human-readable preparation manifests contain `exported_at` and the absolute
  hydrograph path.
- HDF5 container bytes can differ even when every dataset and attribute is
  identical; compare HDF5 datasets and attributes, not only file hashes.

Timestamp, path, container-layout, and elapsed-time differences are expected.
Any numerical dataset, summary, monitoring, budget, or state difference is
substantive and must be reported.
