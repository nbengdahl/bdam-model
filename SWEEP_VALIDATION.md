# Parameter-sweeps implementation validation

Validated on October 10, 2026, on macOS with MATLAB R2025b, Python 3.14.6,
FloPy 3.10.0, h5py 3.16.0, NumPy 2.5.2 and MF6 6.7.0 (2026-02-05).

## Passed

- 42 fast tests: the 22 existing workflow tests plus 20 forcing/campaign tests.
- MATLAB syntax checks and default 70 x 140-cell geometry generation.
- The ordinary all-scalar MakeInputs workflow created paired handoffs in the
  usual ModelInput directories without launching a solver.
- Four Cartesian members from precipitation shifts [-14,14] days and inflow
  widths [0.8,1.2], with baseline omission and n_parallel_runs=2, prepared
  serially through the final MATLAB/Python campaign interface.
- All four member source/config/input fingerprints and prepared-handoff
  checksums validated. Native handoff shapes are 70 x 140 x 5; staged spinup
  has 131 saved steps over 2555 days. The seven-day relaxation is separate.
- Every forcing variant retained an identical reference rating curve.
- Cross-process capacity tests observed no more than two simultaneous workers.
  POSIX descriptor inheritance retained a claim after its launcher closed it.
- Baseline skip/reuse, native-array distinctions, dependent defaults, failed
  member collection, compact retention and resume-integrity tests passed.
- git diff --check passed. The original main checkout retained only its
  pre-existing MakeInputs.m change.

## Full baseline result: not numerically qualified

The baseline configured five layers, 70 x 140 cells, 3/2/2 spinup and two
pre-dam plus two post-dam years. The seven-day relaxation completed and was
published with passing budget QA. The first 365-day fall-average solve then
reported:

```text
Simulation convergence failure occurred 1 time(s).
Premature termination of simulation.
```

The first annual solve took approximately 88 seconds and reported about
287.8 MB of MF6 allocation. It used the existing conservative profile. The
launcher exited nonzero, recorded a failed member, retained its staging data
and did not emit scientific ensemble rows for that member. Solver profiles,
closure tolerances, wave capacity and the one-step annual calendar were not
changed to force a pass.

This establishes a numerical tuning issue for the next modeling stage. Full
spinup, the monitored 2/2 years, serial-versus-parallel scientific comparisons,
legacy-versus-periodic baseline comparison and compact retention on a completed
production run remain unqualified. The four-member factorial was prepared but
was not launched after this baseline failure.

## Local evidence

Persistent checkout: `/Users/nick.engdahl/BDamRuns/parameter-sweeps`.

Archived diagnostics: `/Users/nick.engdahl/BDamRuns/parameter-sweeps-validation`:

- `baseline/`: complete baseline campaign, published relaxation, failed annual
  staging, member index and attempt log.
- `factorial/`: four prepared members, configs, forcing reviews and handoffs.
- `logs/`: geometry, baseline preparation, factorial preparation, scalar-mode
  preparation and launcher logs; factorial override JSON.

Archived snapshots retain their original absolute path records as immutable
provenance. Original baseline and factorial campaign folders also remain in
`/private/tmp/BDam-baseline-validation-v2` and
`/private/tmp/BDam-factorial-preparation`. Prepare a new persistent campaign
for further execution rather than rewriting archived configurations.
