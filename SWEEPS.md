# Deprecated vector-sweep adapter

New work uses explicit rows through [bdam.Study](PARAMETERS.md). The old MATLAB
vector expansion workflow and `BDAM_CAMPAIGN_ROOT` / `BDAM_SKIP_BASELINE`
variables are no longer active. `MakeInputs.m` does not interpret numeric
vectors as candidate axes.

## Supported compatibility path

`bdam_sweeps.py` is retained only to translate an old **request object** into a
fresh table study. Its `plan` command expands registered numeric scalars,
deduplicates candidates, and inserts the old default reference. `--skip-baseline`
removes that reference, including a matching Cartesian combination. These rules
belong to the adapter; the core table interface never adds/drops cases implicitly.

```sh
python3 bdam_sweeps.py plan legacy-request.json /absolute/local/new-study
python3 bdam_sweeps.py prepare /absolute/local/new-study/batches/grid.json
python3 bdam_sweeps.py run /absolute/local/new-study/batches/grid.json
python3 bdam_sweeps.py collect /absolute/local/new-study/batches/grid.json
```

The request must contain the complete legacy scientific settings/native arrays
expected by `expand`, not just a few axes. Inactive fields removed in registry v4
are not accepted by the new study. The obsolete `source_geometry_file` selection
is ignored: fresh case geometry comes from registry defaults unless geometry
parameters are supplied. Legacy requests with removed controls should be rewritten
as explicit rows rather than silently migrated. For new Cartesian designs, use:

```python
from bdam import Study, grid_cases

study = Study('/absolute/local/new-study')
rows = grid_cases({'K_constant': [0.01, 0.03], 'specific_yield': [0.1, 0.2]})
study.submit(rows, 'factorial')  # Exactly four rows; no added reference.
results = study.evaluate('factorial')
```

The adapter's prepare/run/collect commands accept new `batches/*.json` manifests.
Frozen old `campaign.json` manifests are rejected with a message to use their
original source snapshots. Old external-baseline import is no longer part of
the active runtime; identical validated executions within a study are reused
through scientific identity and completion receipts.

Forcing transforms, parallel execution, retention and result collection remain
supported by the current interface; see `PARAMETERS.md`. Historical sweep results
and their original calendars/physics are preserved in
[SWEEP_VALIDATION.md](SWEEP_VALIDATION.md), not used as current operating commands.
