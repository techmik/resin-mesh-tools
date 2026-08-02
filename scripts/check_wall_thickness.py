"""
Measures local wall thickness across a mesh by ray-casting inward from the
outer surface at many sample points and finding the first self-intersection
(the inner cavity wall) -- the standard "3D print toolbox"-style thickness
check.

Built after a real crack was found on a printed, hollowed model: the hollow
scripts here (hollow_shell.py / hollow_shell_partial.py) print a healthy
median wall thickness (close to the requested value) almost everywhere, but
can still leave a few near-zero-thickness or fully-gapped spots in
geometrically complex areas (e.g. where a hull meets a track assembly) --
invisible in a bbox/open-edge check, but a real structural weak point that
can crack under completely normal handling, not just heavy stress.

ALWAYS run this on a hollowed mesh before trusting it enough to print.
Report the thinnest points found -- if any are near zero relative to the
intended wall thickness, that's a real weak spot, not noise. The fix isn't
automatic: manually reinforce that specific area (a bit of resin or CA glue
worked into a real crack after printing is fine; for a pre-print fix,
consider a locally thicker wall or accepting that specific feature as
solid) rather than assuming a script will always catch and correct it.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \\
        --python check_wall_thickness.py -- <mesh_path> [--zmax Z] [--samples N]
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, get_script_args

import bmesh
from mathutils.bvhtree import BVHTree


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mesh_path")
    parser.add_argument("--zmax", type=float, default=None, help="only sample vertices with world z at or below this (e.g. to focus on a belly/bottom panel); default samples the whole mesh")
    parser.add_argument("--samples", type=int, default=3000, help="max number of surface points to sample")
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.mesh_path)
    mw = obj.matrix_world.copy()

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.normal_update()

    bvh = BVHTree.FromBMesh(bm)

    if args.zmax is not None:
        candidates = [v for v in bm.verts if (mw @ v.co).z <= args.zmax]
        print(f"Verts at or below z={args.zmax}: {len(candidates)} / {len(bm.verts)}")
    else:
        candidates = list(bm.verts)
        print(f"Sampling across the whole mesh: {len(candidates)} verts")

    step = max(1, len(candidates) // args.samples)
    sampled = candidates[::step]
    print(f"Sampling {len(sampled)} of them")

    results = []
    EPS = 1e-4
    for v in sampled:
        origin = v.co + v.normal * -EPS  # nudge slightly inward first, past the starting face itself
        direction = -v.normal
        hit = bvh.ray_cast(origin, direction)
        if hit[0] is not None:
            thickness = (hit[0] - v.co).length
            results.append((thickness, mw @ v.co))
        else:
            # No inward hit at all -- either not actually hollow here, or a
            # gap/hole in the inner wall lets the ray escape without hitting anything.
            results.append((None, mw @ v.co))

    measured = [r for r in results if r[0] is not None]
    missed = [r for r in results if r[0] is None]

    print(f"\nPoints with a measurable inward wall: {len(measured)}")
    print(f"Points where the ray found NO inner surface at all (possible hole/gap): {len(missed)}")

    if measured:
        measured.sort(key=lambda r: r[0])
        print(f"\nThinnest 15 points found:")
        for thickness, pos in measured[:15]:
            print(f"  thickness={thickness:.3f}mm at world pos ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")

        mid = measured[len(measured) // 2][0]
        print(f"\nOverall: min={measured[0][0]:.3f}mm  median={mid:.3f}mm  max={measured[-1][0]:.3f}mm")

    if missed:
        print(f"\nFirst 10 no-hit points (potential real gaps in the inner shell):")
        for _, pos in missed[:10]:
            print(f"  world pos ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")

    bm.free()


if __name__ == "__main__":
    main()
