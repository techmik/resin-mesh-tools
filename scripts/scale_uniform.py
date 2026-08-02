"""
Uniformly scale a mesh so its X dimension matches a target real-world mm
value, preserving aspect ratio (Y and Z scale by the same factor).

Useful for a model whose raw STL is at some arbitrary native unit scale
(not real millimeters) -- check the actual bbox size first (e.g. via
zslice_footprint.py or mesh_health_check.py); if it's wildly larger or
smaller than a real print (a model at ~1900mm native, say, when it should
be closer to 100mm), it needs this before any further mesh work, since
other scripts here (hollow thickness, thicken factors) operate in the
file's current units.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \\
        --python scale_uniform.py -- <in_path> <out_path> --target-x-mm 122.0
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, export_mesh, get_script_args

import bmesh


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("in_path")
    parser.add_argument("out_path")
    parser.add_argument("--target-x-mm", type=float, required=True)
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.in_path)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    xs = [v.co.x for v in bm.verts]
    current_x = max(xs) - min(xs)
    factor = args.target_x_mm / current_x
    print(f"Current X size: {current_x:.4f}  Target: {args.target_x_mm}  Scale factor: {factor:.6f}")

    for v in bm.verts:
        v.co = v.co * factor

    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    print(f"Resulting bbox: X={max(v.co.x for v in bm.verts) - min(v.co.x for v in bm.verts):.3f} "
          f"Y={max(ys) - min(ys):.3f} Z={max(zs) - min(zs):.3f}")

    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()

    export_mesh(obj, args.out_path)
    print(f"Exported: {args.out_path}")


if __name__ == "__main__":
    main()
