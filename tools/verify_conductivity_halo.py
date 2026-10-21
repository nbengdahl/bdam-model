#!/usr/bin/env python3
"""Audit prepared core/halo arrays and their serialized MF6 conductivities.

Run only from a local nonsynchronized source copy after MakeGrid/MakeInputs.
This builds and reloads MF6 input files, without running the simulator.
"""
import argparse
import json
from pathlib import Path
import sys

import flopy
import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import build_bdam_simulation as model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--inputs', type=Path, default=SOURCE/'ModelInput')
    parser.add_argument('--halo-cells', type=int, choices=(0, 1), default=1)
    parser.add_argument('--layers', type=int, default=3)
    parser.add_argument('--under-dam-k', type=float, default=1., help='Independent isotropic core K in m/day')
    args = parser.parse_args()
    for path in (SOURCE, args.root.resolve()):
        if any(s in str(path) for s in ('My Drive', 'Google Drive', 'OneDrive', 'Dropbox', 'Mobile Documents')):
            raise ValueError('Use local nonsynchronized source and output paths.')
    args.root.mkdir(parents=True, exist_ok=False)
    receipt = {}
    for phase in ('pre_dam', 'post_dam'):
        path = args.inputs/phase/'preparation_handoff.h5'
        h = model.load_handoff(path)
        def read(name, dtype=float): return h.array('/properties/'+name, dtype)
        core, halo, union = [read('BDA_LEAKAGE_'+s, bool) for s in ('CORE_MASK', 'HALO_MASK', 'MASK')]
        cf, hf, uf = [read('BDA_LEAKAGE_'+s, bool) for s in ('CORE_FOOTPRINT', 'HALO_FOOTPRINT', 'FOOTPRINT')]
        assert not np.any(core & halo) and np.array_equal(core | halo, union)
        assert np.array_equal(cf | hf, uf) and not np.any(cf & hf)
        if phase == 'pre_dam':
            assert not np.any(union) and not np.any(uf)
        else:
            expected = np.zeros_like(cf)
            if args.halo_cells:
                padded = np.pad(cf, 1)
                for i in range(3):
                    for j in range(3): expected |= padded[i:i+cf.shape[0], j:j+cf.shape[1]]
                expected &= ~cf
            np.testing.assert_array_equal(hf, expected)
            for mask, footprint in ((core, cf), (halo, hf)):
                expected3 = np.zeros_like(mask)
                expected3[:, :, -args.layers:] = footprint[:, :, None]
                np.testing.assert_array_equal(mask, expected3)
        kb, vb, k, v = [read(s) for s in ('K_background', 'K33_background', 'K', 'K33')]
        target = np.full_like(kb, args.under_dam_k)
        ek, ev = kb.copy(), vb.copy()
        ek[core], ev[core] = target[core], target[core]
        ek[halo], ev[halo] = (kb[halo]+target[halo])/2, (vb[halo]+target[halo])/2
        np.testing.assert_array_equal(k, ek)
        np.testing.assert_array_equal(v, ev)
        ws = args.root/phase
        sim = model.build_from_handoff(path, ws)
        sim.write_simulation(silent=True)
        reloaded = flopy.mf6.MFSimulation.load(sim_ws=ws, verbosity_level=0)
        np.testing.assert_array_equal(reloaded.get_model('bdam').npf.k.array, model.mf3(ek))
        np.testing.assert_array_equal(reloaded.get_model('bdam').npf.k33.array, model.mf3(ev))
        receipt[phase] = {'status': 'pass', 'core_cells_top_down': np.count_nonzero(core, axis=(0, 1))[::-1].tolist(),
                         'halo_cells_top_down': np.count_nonzero(halo, axis=(0, 1))[::-1].tolist(),
                         'halo_K_range': [float(k[halo].min()), float(k[halo].max())] if np.any(halo) else None,
                         'halo_K33_range': [float(v[halo].min()), float(v[halo].max())] if np.any(halo) else None}
    (args.root/'validation.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
