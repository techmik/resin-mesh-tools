"""
Thicken a Z-range of a mesh radially (in XY) about each Z-slice's own local
centroid -- not a single fixed axis -- so a tapered or leaning support
pillar keeps its shape while getting fatter, rather than assuming it's a
straight vertical post.

Use zslice_footprint.py first to find the real boundaries of the thin
section (base vs. pillar vs. body, by where the footprint jumps).

Ramps the scale factor smoothly from 1.0x at --zmin/--zmax up to the full
factor in the middle (smoothstep over --blend-fraction of the range), so
there's no abrupt step/seam where the thickened section meets the
unmodified geometry above and below it.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \\
        --python thicken_region.py -- <in_path> <out_path> --zmin Z1 --zmax Z2 --factor 2.0
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, export_mesh, get_script_args

import bmesh


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("in_path")
    parser.add_argument("out_path")
    parser.add_argument("--zmin", type=float, required=True)
    parser.add_argument("--zmax", type=float, required=True)
    parser.add_argument("--factor", type=float, default=2.0, help="peak radial scale factor at the center of the range")
    parser.add_argument("--slices", type=int, default=60, help="number of Z slices used to compute each slice's local centroid")
    parser.add_argument("--blend-fraction", type=float, default=0.2, help="fraction of the range at each end used to ramp the scale up/down smoothly")
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.in_path)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    zrange = args.zmax - args.zmin
    in_range = [v for v in bm.verts if args.zmin <= v.co.z <= args.zmax]
    print(f"Verts in thicken range [{args.zmin}, {args.zmax}]: {len(in_range)} / {len(bm.verts)}")
    if not in_range:
        print("Nothing in range -- check --zmin/--zmax against zslice_footprint.py's output. Exiting without changes.")
        export_mesh(obj, args.out_path)
        return

    slice_h = zrange / args.slices
    buckets = [[] for _ in range(args.slices)]
    for v in in_range:
        idx = min(int((v.co.z - args.zmin) / slice_h), args.slices - 1)
        buckets[idx].append(v)

    centroids = []
    for verts in buckets:
        if verts:
            cx = sum(v.co.x for v in verts) / len(verts)
            cy = sum(v.co.y for v in verts) / len(verts)
            centroids.append((cx, cy))
        else:
            centroids.append(None)
    # fill any empty slices from the nearest non-empty neighbor
    for i in range(len(centroids)):
        if centroids[i] is None:
            for d in range(1, len(centroids)):
                if i - d >= 0 and centroids[i - d] is not None:
                    centroids[i] = centroids[i - d]
                    break
                if i + d < len(centroids) and centroids[i + d] is not None:
                    centroids[i] = centroids[i + d]
                    break

    blend_z = zrange * args.blend_fraction

    for v in in_range:
        idx = min(int((v.co.z - args.zmin) / slice_h), args.slices - 1)
        cx, cy = centroids[idx]

        dist_from_min = v.co.z - args.zmin
        dist_from_max = args.zmax - v.co.z
        ramp_in = smoothstep(dist_from_min / blend_z) if blend_z > 0 else 1.0
        ramp_out = smoothstep(dist_from_max / blend_z) if blend_z > 0 else 1.0
        ramp = min(ramp_in, ramp_out)

        local_factor = 1.0 + (args.factor - 1.0) * ramp
        v.co.x = cx + (v.co.x - cx) * local_factor
        v.co.y = cy + (v.co.y - cy) * local_factor

    print(f"Thickened {len(in_range)} verts, peak factor {args.factor}x at center, ramped over {args.blend_fraction*100:.0f}% blend at each end")

    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()

    export_mesh(obj, args.out_path)
    print(f"Exported: {args.out_path}")


if __name__ == "__main__":
    main()
