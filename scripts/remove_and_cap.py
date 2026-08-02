"""
Remove geometry matching a cut criterion and flat-cap the resulting hole.

Built for the recurring "Meshy/Rodin generated model came with an unwanted
display base fused to the tracks/feet" problem: the base is wide-and-low, and
often connects to the real model through a narrow "neck". This script deletes
whatever matches your cut criteria, flattens the boundary loop it leaves
behind to one consistent height, and fills it as a single flat-shaded face --
NOT a smooth-shaded one. That last part matters: we learned the hard way that
even genuinely flat geometry renders as a fake "dome" if the fill face is left
smooth-shaded, because it inherits stale vertex normals from the curved
surface it used to be part of. Setting the new fill face(s) to flat shading
(face.smooth = False) is what actually fixes it, not the flattening itself.

Cut criteria (combine as needed -- a face is deleted if it matches ANY of them):
  --zmax Z            delete faces where every vertex has world z < Z
                       (use for a wide, flat base/plinth)
  --xy-center CX CY --xy-radius R --neck-zmax Z
                       delete faces within radius R of (CX, CY) in the XY plane
                       AND with world z < Z (use for a narrow connecting "neck"
                       that a plain z-threshold would either miss or overreach)

Tip for finding the right cut values: run zslice_footprint.py first on the
same mesh. Look for where the XY footprint size jumps sharply between
adjacent bins -- that jump is usually exactly the boundary between "base/neck"
and "real model" you want to cut at.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \
        --python remove_and_cap.py -- <in_path> <out_path> --zmax -0.49 [--xy-center 0.02 0.0 --xy-radius 0.15 --neck-zmax -0.48]
"""
import sys
import os
import argparse
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, export_mesh, get_script_args

import bmesh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("in_path")
    parser.add_argument("out_path")
    parser.add_argument("--zmax", type=float, default=None)
    parser.add_argument("--xy-center", type=float, nargs=2, default=None, metavar=("CX", "CY"))
    parser.add_argument("--xy-radius", type=float, default=None)
    parser.add_argument("--neck-zmax", type=float, default=None)
    parser.add_argument("--flatten-to", choices=["min", "max", "avg"], default="min",
                         help="which height to flatten the boundary loop to before capping (default: min, so the cap never protrudes below existing geometry)")
    parser.add_argument("--margin", type=float, default=0.3,
                         help="how far (in world units) beyond the deleted region's bounding box to still treat an open edge as 'belonging' to this hole, so unrelated pre-existing openings elsewhere (e.g. a gun muzzle bore) don't get swept in and flattened too")
    args = parser.parse_args(get_script_args())

    if args.zmax is None and args.xy_center is None:
        print("Provide at least one cut criterion: --zmax and/or --xy-center/--xy-radius/--neck-zmax")
        sys.exit(1)

    obj = import_mesh(args.in_path)
    mw = obj.matrix_world.copy()

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    def face_matches(f):
        pts = [(mw @ v.co) for v in f.verts]
        if args.zmax is not None and all(p.z < args.zmax for p in pts):
            return True
        if args.xy_center is not None and args.xy_radius is not None and args.neck_zmax is not None:
            cx, cy = args.xy_center
            if all((p.x - cx) ** 2 + (p.y - cy) ** 2 <= args.xy_radius ** 2 and p.z < args.neck_zmax for p in pts):
                return True
        return False

    faces_to_delete = [f for f in bm.faces if face_matches(f)]
    print(f"Faces matching cut criteria: {len(faces_to_delete)} / {len(bm.faces)}")
    if not faces_to_delete:
        print("Nothing matched -- check your cut criteria against zslice_footprint.py's output. Exiting without changes.")
        return

    deleted_verts_world = [(mw @ v.co) for f in faces_to_delete for v in f.verts]
    dxs = [p.x for p in deleted_verts_world]; dys = [p.y for p in deleted_verts_world]; dzs = [p.z for p in deleted_verts_world]
    region_min = mathutils.Vector((min(dxs) - args.margin, min(dys) - args.margin, min(dzs) - args.margin))
    region_max = mathutils.Vector((max(dxs) + args.margin, max(dys) + args.margin, max(dzs) + args.margin))

    bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES_KEEP_BOUNDARY')

    def in_region(v):
        p = mw @ v.co
        return (region_min.x <= p.x <= region_max.x and region_min.y <= p.y <= region_max.y and region_min.z <= p.z <= region_max.z)

    boundary_edges = [e for e in bm.edges if len(e.link_faces) < 2 and all(in_region(v) for v in e.verts)]
    other_open = [e for e in bm.edges if len(e.link_faces) < 2 and e not in boundary_edges]
    print(f"Boundary edges from this cut: {len(boundary_edges)}  (other open edges elsewhere, left untouched: {len(other_open)})")

    if not boundary_edges:
        print("No boundary edges found near the deleted region -- the cut may have removed the whole mesh, or the margin is too small. Nothing filled.")
    else:
        boundary_verts = {v for e in boundary_edges for v in e.verts}
        world_zs = [(mw @ v.co).z for v in boundary_verts]
        target_z = {"min": min, "max": max, "avg": lambda l: sum(l) / len(l)}[args.flatten_to](world_zs)
        print(f"Flattening {len(boundary_verts)} boundary verts to world z={target_z:.5f} (was {min(world_zs):.5f} to {max(world_zs):.5f})")

        mw_inv = mw.inverted()
        for v in boundary_verts:
            wc = mw @ v.co
            v.co = mw_inv @ mathutils.Vector((wc.x, wc.y, target_z))

        fill_res = bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
        new_faces = fill_res.get('faces', [])
        print(f"Faces created by hole fill: {len(new_faces)}")
        for f in new_faces:
            f.smooth = False  # critical -- see module docstring

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    obj.data.update()

    remaining_open = [e for e in bm.edges if len(e.link_faces) < 2]
    print(f"Final open-edge count in whole mesh: {len(remaining_open)}")
    bm.free()

    export_mesh(obj, args.out_path)
    print(f"Exported: {args.out_path}")


if __name__ == "__main__":
    main()
