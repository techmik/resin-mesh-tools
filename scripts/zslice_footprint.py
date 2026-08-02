"""
Z-slice footprint analyzer.

Buckets a mesh's vertices into N bins along one axis and reports each bin's
vertex count and XY footprint bounding box. Use this to find where a mesh's
footprint suddenly widens or narrows -- e.g. distinguishing a small display
base/plinth fused to a model's tracks from the model's real geometry, or
finding the exact height a thin connecting "neck" gives way to the real body.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \
        --python zslice_footprint.py -- <mesh_path> [--bins N] [--zmin Z] [--zmax Z] [--axis x|y|z]

Prints a plain-text table to stdout: one row per bin, with z-range, vertex
count, XY footprint size, and XY min/max. A sudden jump in footprint size
between adjacent bins is usually the boundary you're looking for.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, get_script_args

import bmesh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh_path")
    parser.add_argument("--bins", type=int, default=60)
    parser.add_argument("--zmin", type=float, default=None, help="restrict to this axis range (default: full extent)")
    parser.add_argument("--zmax", type=float, default=None)
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z", help="which axis to slice along (default z, the usual up-axis)")
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.mesh_path)
    mw = obj.matrix_world

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    axis_idx = {"x": 0, "y": 1, "z": 2}[args.axis]
    other_axes = [i for i in range(3) if i != axis_idx]

    coords = [mw @ v.co for v in bm.verts]
    axis_vals = [c[axis_idx] for c in coords]
    lo = args.zmin if args.zmin is not None else min(axis_vals)
    hi = args.zmax if args.zmax is not None else max(axis_vals)
    if hi <= lo:
        print(f"Invalid range: {args.axis} min {lo} >= max {hi}")
        return

    n_bins = args.bins
    bin_h = (hi - lo) / n_bins
    bins = [[] for _ in range(n_bins)]
    for c in coords:
        v = c[axis_idx]
        if lo <= v <= hi:
            idx = min(int((v - lo) / bin_h), n_bins - 1)
            bins[idx].append(c)

    a1, a2 = other_axes
    names = ["x", "y", "z"]
    print(f"Full mesh {args.axis} range: {min(axis_vals):.5f} to {max(axis_vals):.5f}")
    print(f"Analyzing range: {lo:.5f} to {hi:.5f} in {n_bins} bins\n")
    header = f"{'bin':>4} {args.axis+'_lo':>10} {args.axis+'_hi':>10} {'count':>7} {names[a1]+'_size':>9} {names[a2]+'_size':>9} {names[a1]+'_min':>9} {names[a1]+'_max':>9} {names[a2]+'_min':>9} {names[a2]+'_max':>9}"
    print(header)
    for i, b in enumerate(bins):
        bin_lo = lo + i * bin_h
        bin_hi = bin_lo + bin_h
        if not b:
            print(f"{i:>4} {bin_lo:10.5f} {bin_hi:10.5f} {0:7d}")
            continue
        v1 = [c[a1] for c in b]
        v2 = [c[a2] for c in b]
        print(f"{i:>4} {bin_lo:10.5f} {bin_hi:10.5f} {len(b):7d} {max(v1)-min(v1):9.4f} {max(v2)-min(v2):9.4f} {min(v1):9.4f} {max(v1):9.4f} {min(v2):9.4f} {max(v2):9.4f}")

    bm.free()


if __name__ == "__main__":
    main()
