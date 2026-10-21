#!/usr/bin/env python3
"""Compare serialized MF6 physics against a local parameters-table source copy.

Builds inputs only; never launches MF6. Both builders receive the same actual
single-run handoff. The reference adapter supplies its schema-specific zero edge
totals; monitoring output is disabled in both builds. The reference's additional
zero WEL packages are reported separately, not claimed as identical files.
"""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]


def load(name, source):
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location(name, source/'build_bdam_simulation.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def normalized(path):
    return '\n'.join(line.strip().lower() for line in path.read_text().splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, default=SOURCE/'ModelInput')
    args = parser.parse_args()
    for path in (SOURCE, args.reference.resolve(), args.root.resolve()):
        if any(word in str(path) for word in ('My Drive', 'Google Drive', 'Dropbox', 'OneDrive', 'Mobile Documents')):
            raise ValueError('Use local nonsynchronized source and output directories.')
    args.root.mkdir(parents=True, exist_ok=False)
    current, reference = load('_single_model', SOURCE), load('_table_model', args.reference)
    shared = ('_solver_settings', '_lake_data', '_lake_bottoms', '_decode_lake_stages',
              '_validate_lake_storage', '_uzf_records', '_planar_initial_heads', '_map_uzf_state')
    trees = [ast.parse((p/'build_bdam_simulation.py').read_text()) for p in (SOURCE, args.reference)]
    functions = [{node.name: ast.dump(node, include_attributes=False) for node in tree.body
                  if isinstance(node, ast.FunctionDef)} for tree in trees]
    for name in shared:
        assert functions[0][name] == functions[1][name], f'Different numerical function: {name}'

    class ReferenceView(reference.Handoff):
        def array(self, path, dtype=float):
            if path.startswith('/boundaries/edge_flux/'):
                return np.array([0.], dtype=dtype)
            return super().array(path, dtype)

    comparisons = {}
    for phase in ('pre_dam', 'post_dam'):
        path = args.inputs/phase/'preparation_handoff.h5'
        handoff = current.load_handoff(path)
        a, b = args.root/phase/'single', args.root/phase/'table'
        first = current.build_from_handoff(path, a, save_monitoring=False)
        view = ReferenceView(path, {**handoff.manifest, 'schema_version': reference.SCHEMA})
        with patch.object(reference, 'load_handoff', return_value=view):
            second = reference.build_from_handoff(path, b, save_monitoring=False)
        first.write_simulation(silent=True)
        second.write_simulation(silent=True)
        # Exclude package registries (the reference adds WEL) and human audits.
        files = sorted(p.name for p in a.iterdir() if p.suffix in {
            '.lak', '.ims', '.dis', '.ic', '.npf', '.sto', '.uzf', '.drn', '.ghb',
            '.tdis', '.ts', '.tab', '.oc'})
        assert any(name.endswith('.lak') for name in files)
        for name in files:
            assert normalized(a/name) == normalized(b/name), f'Numerical input mismatch: {phase}/{name}'
        comparisons[phase] = files
    report = dict(status='pass', native_solves=0, shared_functions=list(shared),
                  identical_numerical_files=comparisons,
                  reference_only_packages='Three zero-total edge WEL packages; not part of main.',
                  scope='Matched supplied physical inputs; native branch defaults are not assumed identical.')
    (args.root/'parity.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
