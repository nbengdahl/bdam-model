"""Year-end repeatability criteria shared by the runner and receipt validation."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

DEFAULTS = dict(spinup_until_converged=False, spinup_max_weekly_years=10,
                spinup_head_relative_tolerance=0.001,
                spinup_stage_relative_tolerance=0.01,
                spinup_water_content_relative_tolerance=0.005)
FLOORS = dict(head=1.0, stage=0.1, water_content=0.05)
DNC_EXIT_CODE = 3


class SpinupDidNotConverge(RuntimeError):
    """The configured weekly-year limit was reached without repeatability."""


def settings(values):
    result = {name: values.get(name, default) for name, default in DEFAULTS.items()}
    if type(result['spinup_until_converged']) is not bool:
        raise ValueError('mf6_parameters.spinup_until_converged requires true or false.')
    cap = result['spinup_max_weekly_years']
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not np.isfinite(cap) or int(cap) != cap or cap < 3:
        raise ValueError('spinup_max_weekly_years must be an integer >= 3.')
    result['spinup_max_weekly_years'] = int(cap)
    for name in DEFAULTS:
        if name.endswith('_tolerance'):
            value = result[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive.')
    return result


def handoff_settings(handoff):
    # Old v8 handoffs have no opt-in flag and retain their fixed schedule.
    try:
        handoff.scalar('/mf6_parameters/spinup_until_converged')
    except KeyError:
        return settings({})
    except ValueError as exc:
        if str(exc).startswith('Missing required handoff dataset:'):
            return settings({})
        raise
    values = {name: handoff.scalar('/mf6_parameters/'+name) for name in DEFAULTS}
    if values['spinup_until_converged'] not in (0, 1):
        raise ValueError('Handoff convergence flag must be 0 or 1.')
    values['spinup_until_converged'] = bool(values['spinup_until_converged'])
    return settings(values)


def metric(previous, current, reference, floor):
    previous, current = np.asarray(previous), np.asarray(current)
    reference = np.asarray(reference)
    if previous.shape != current.shape or not previous.size:
        raise ValueError('Convergence states must have identical nonempty shapes.')
    if reference.shape not in ((), current.shape):
        raise ValueError('Convergence reference does not match the state shape.')
    if any(np.any(~np.isfinite(a)) or np.any(np.abs(a) >= 1e20) for a in (previous, current, reference)):
        raise ValueError('Invalid or sentinel value in convergence state/reference.')
    absolute = np.abs(current-previous)
    relative = absolute / np.maximum(np.maximum(np.abs(previous-reference), np.abs(current-reference)), floor)
    index = int(np.argmax(relative))
    return dict(relative_max=float(relative.flat[index]), absolute_max=float(np.max(absolute)),
                controlling_index=list(map(int, np.unravel_index(index, current.shape))),
                controlling_absolute_change=float(absolute.flat[index]))


def comparison(previous, current, references, config):
    row = {}
    for name, old, new, ref in zip(FLOORS, previous, current, references):
        result = metric(old, new, ref, FLOORS[name])
        tolerance = config[f'spinup_{name}_relative_tolerance']
        row.update({f'{name}_{key}': value for key, value in result.items()})
        row[f'{name}_tolerance'] = tolerance
        row[f'{name}_pass'] = result['relative_max'] <= tolerance
    row['passed'] = all(row[f'{name}_pass'] for name in FLOORS)
    return row


def references(handoff):
    # Match the runner's native MATLAB -> MF6 orientation exactly.
    bottom = handoff.array('/grid/Z')[:, :, :-1].transpose(2, 1, 0)[::-1, ::-1, :]
    top = handoff.array('/grid/ZTop')
    beds = [float(np.min(top[handoff.array(f'/surface_water/lakes/lake_{i}/footprint_mask', bool)]))
            for i in range(1, int(handoff.scalar('/surface_water/n_lakes'))+1)]
    return bottom, np.asarray(beds), 0.0


def write_report(workspace, config, rows, outcome):
    from bdam_runtime import write
    workspace = Path(workspace)
    report = dict(version=1, outcome=outcome, settings=config, denominator_floors=FLOORS,
                  required_consecutive_passes=2, years_completed=len(rows),
                  weekly_workspaces=[f'spinup/weekly/year_{i:02d}' for i in range(1, len(rows)+1)],
                  comparisons=rows)
    csv_path = workspace/'spinup_convergence.csv'
    temporary = csv_path.with_suffix('.csv.tmp')
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with temporary.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()} for row in rows])
    temporary.replace(csv_path)
    write(workspace/'spinup_convergence.json', report)
    return report


def validate_report(workspace, config, require_converged=True):
    """Check settings, comparison evidence, stopping point and CSV consistency."""
    workspace = Path(workspace)
    report = json.loads((workspace/'spinup_convergence.json').read_text())
    rows = report['comparisons']
    count = report['years_completed']
    if (report.get('version') != 1 or report['settings'] != config or
            report['denominator_floors'] != FLOORS or report['required_consecutive_passes'] != 2 or
            type(count) is not int or count != len(rows) or not 1 <= count <= config['spinup_max_weekly_years'] or
            report['weekly_workspaces'] != [f'spinup/weekly/year_{i:02d}' for i in range(1, count+1)]):
        raise ValueError('Invalid spinup convergence report metadata.')
    streak = 0
    for year, row in enumerate(rows, 1):
        if row['weekly_year'] != year:
            raise ValueError('Noncontiguous spinup comparisons.')
        if year == 1:
            if row['passed'] is not False:
                raise ValueError('First weekly year cannot establish convergence.')
        else:
            for name in FLOORS:
                for key in ('relative_max', 'absolute_max', 'controlling_absolute_change'):
                    value = row[f'{name}_{key}']
                    if not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                        raise ValueError('Invalid convergence metric.')
                tolerance = config[f'spinup_{name}_relative_tolerance']
                if row[f'{name}_tolerance'] != tolerance or row[f'{name}_pass'] is not (row[f'{name}_relative_max'] <= tolerance):
                    raise ValueError('Inconsistent convergence criterion.')
            if row['passed'] is not all(row[f'{name}_pass'] for name in FLOORS):
                raise ValueError('Inconsistent convergence decision.')
        streak = streak+1 if row['passed'] else 0
        if row['consecutive_passes'] != streak or (streak >= 2 and year != count):
            raise ValueError('Invalid convergence stopping point.')
    outcome = 'converged' if streak >= 2 else 'DNC' if count == config['spinup_max_weekly_years'] else 'running'
    if report['outcome'] != outcome or (require_converged and outcome != 'converged'):
        raise ValueError('Spinup did not establish convergence.')
    with (workspace/'spinup_convergence.csv').open(newline='') as stream:
        actual = list(csv.DictReader(stream))
    fields = list(dict.fromkeys(key for row in rows for key in row))
    expected = [{k: '' if row.get(k) is None else json.dumps(row[k]) if isinstance(row[k], list) else str(row[k])
                 for k in fields} for row in rows]
    if actual != expected:
        raise ValueError('Spinup convergence CSV and JSON disagree.')
    return report


def validate_states(report, handoff, states):
    """Recompute every comparison from retained annual final states, also in compact mode."""
    previous = None
    refs = references(handoff)
    for relative, row in zip(report['weekly_workspaces'], report['comparisons']):
        prefix = relative.replace('/', '_')
        current = tuple(states[f'{prefix}_{name}'] for name in ('heads', 'stages', 'water_content'))
        # Validate the baseline year too, including sentinels.
        calculated = comparison(previous if previous is not None else current, current, refs, report['settings'])
        if previous is not None and any(row.get(k) != v for k, v in calculated.items()):
            raise ValueError('Spinup convergence evidence differs from retained final states.')
        previous = current
