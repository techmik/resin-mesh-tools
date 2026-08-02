"""
Hollow a solid mesh to a given wall thickness -- a manual alternative when
Satellite's own "Hollow" feature isn't trusted or available.

A naive approach (bmesh.ops.solidify, or the Solidify modifier) explodes on
any mesh with thin protrusions (gun barrels, antennae) relative to the wall
thickness -- offsetting a feature thinner than 2x the wall thickness pushes
its surface through itself, and solidify's rim-stitching step turns that
into catastrophic self-intersecting geometry across the WHOLE mesh at once,
not just locally. (Confirmed on a real tank model: raw bmesh.ops.solidify
blew the bbox up ~5x, the Solidify modifier ~40x.)

The working recipe:
  1. Duplicate the mesh as a disposable "inner" cutting tool.
  2. Voxel-remesh "inner" -- coarser than the thin features, so they
     collapse into the bulk shape instead of surviving to explode. This is
     fine since a cavity shouldn't extend into an already-thin part anyway.
     The original mesh's own surface detail is never touched.
  3. Manually displace each of "inner"'s vertices inward along its own
     normal by the wall thickness (plain bmesh, not Solidify -- doesn't try
     to stitch new rim geometry, so a local self-intersection is just a
     folded patch on this throwaway tool, not a whole-mesh disaster).
  4. Boolean-DIFFERENCE "inner" out of the ORIGINAL, untouched mesh with
     Blender's EXACT solver -- keeps full exterior detail while cutting a
     clean cavity using the simplified/robust inner shape.

A SECOND voxel-remesh pass on the offset "inner" shape (before the boolean
step) was tried after a real crack turned up near a hull/track junction on
a printed model, reasoning that it would clean up self-intersecting folds
the same way step 2 does. It was WRONG and reverted: step 2's remesh runs
on the original, thick, chunky mesh, where only genuinely-too-thin features
(barrels, antennae) get erased. A second pass on the OFFSET shape runs on a
thin, contour-following SHELL instead -- to a coarse voxel grid, nearly the
entire shell reads as "thin detail," so it aggressively erodes huge swaths
of it rather than fixing one spot. The result printed see-through in large
areas, a much worse defect than the isolated near-zero spot it was meant
to fix. Do not add a second remesh pass here again.

IMPORTANT: this technique does not GUARANTEE a minimum wall thickness
everywhere -- a real print turned up a few near-zero-thickness spots near
a complex hull/track junction despite otherwise printing successfully.
ALWAYS run check_wall_thickness.py on the result before trusting it. If it
flags a near-zero spot, don't try to algorithmically re-fix the mesh for
it -- print anyway (this technique already produces a usable result almost
everywhere) and proactively reinforce that one spot after printing (a dab
of CA glue or resin, cured), the same fix that worked cleanly on the real
crack this was found from.

Offset direction isn't safe to assume blind -- compares bbox before/after;
if the shell grew instead of staying put, rerun with --flip.

Does NOT add drain/vent holes (needs the real print orientation -- a
separate, later step). Run mesh_health_check.py on the output too, to
check for severed connections (see hollow_shell_partial.py's docstring for
that specific failure mode).

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \\
        --python hollow_shell.py -- <in_path> <out_path> --thickness 2.5 [--flip] [--voxel-size 1.5]
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, export_mesh, get_script_args

import bpy
import bmesh


def bbox_size(mesh_obj):
    pts = [mesh_obj.matrix_world @ v.co for v in mesh_obj.data.vertices]
    mn = tuple(min(p[i] for p in pts) for i in range(3))
    mx = tuple(max(p[i] for p in pts) for i in range(3))
    return tuple(b - a for a, b in zip(mn, mx))


def _apply_modifier_on(obj, modifier):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
        return bpy.ops.object.modifier_apply(modifier=modifier.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("in_path")
    parser.add_argument("out_path")
    parser.add_argument("--thickness", type=float, default=2.5, help="wall thickness in mm (default 2.5)")
    parser.add_argument("--flip", action="store_true", help="flip offset direction if a first run offset outward instead of inward")
    parser.add_argument("--voxel-size", type=float, default=1.5, help="voxel remesh size (mm) for the inner cutting tool -- raise it for a model with fine surface detail (vents, pipes) if the default leaves a messy result; 0.8mm was needed on one real model vs. 1.5mm working fine on others")
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.in_path)
    orig_size = bbox_size(obj)
    print(f"Before hollow: bbox size = {orig_size}")

    inner_data = obj.data.copy()
    inner = bpy.data.objects.new("inner", inner_data)
    bpy.context.collection.objects.link(inner)

    remesh = inner.modifiers.new(name="Remesh", type='REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = args.voxel_size
    result = _apply_modifier_on(inner, remesh)
    print(f"Remesh (voxel_size={args.voxel_size}) result: {result}, verts now: {len(inner.data.vertices)}")

    sign = -1.0 if not args.flip else 1.0
    offset = sign * abs(args.thickness)

    bm = bmesh.new()
    bm.from_mesh(inner.data)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    sample_idx = [0, min(1000, len(bm.verts) - 1), len(bm.verts) - 1]
    sample_before = [bm.verts[i].co.copy() for i in sample_idx]
    for v in bm.verts:
        v.co = v.co + v.normal * offset
    sample_after = [bm.verts[i].co.copy() for i in sample_idx]
    for b, a in zip(sample_before, sample_after):
        print(f"  sample vert: before={tuple(b)} after={tuple(a)} moved={(a - b).length:.5f}")
    bm.to_mesh(inner.data)
    inner.data.update()
    bm.free()

    inner_size = bbox_size(inner)
    print(f"Inner shell after per-vertex offset (offset={offset}): bbox size = {inner_size}")
    # A correct inward offset can still grow the bbox by a small amount on one axis
    # (a locally overhanging detail's normal isn't perfectly aligned with that axis) --
    # only flag it as wrong-direction if growth is more than a couple mm, not any growth at all.
    grew = any(inner_size[i] > orig_size[i] + 2.0 for i in range(3))
    if grew:
        print("WARNING: inner shell grew noticeably on at least one axis -- offset likely went the "
              "wrong way (outward instead of inward). Rerun with --flip.")
        export_mesh(obj, args.out_path)  # export original untouched so a bad run is obvious, not silently overwritten
        print("Exported the ORIGINAL unmodified mesh instead, since the inner shell direction looks wrong.")
        return

    boolean = obj.modifiers.new(name="Boolean", type='BOOLEAN')
    boolean.operation = 'DIFFERENCE'
    boolean.object = inner
    boolean.solver = 'EXACT'
    result = _apply_modifier_on(obj, boolean)
    print(f"Boolean modifier_apply result: {result}")

    bpy.data.objects.remove(inner, do_unlink=True)

    final_size = bbox_size(obj)
    print(f"After boolean hollow: bbox size = {final_size}")
    exploded = any(final_size[i] > orig_size[i] * 1.2 for i in range(3))
    if exploded:
        print("ERROR: exterior bbox changed significantly -- something went wrong, do not trust this output.")
    else:
        print("Exterior bbox unchanged -- looks correct.")

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    open_edges = [e for e in bm.edges if len(e.link_faces) < 2]
    print(f"Open edges in result: {len(open_edges)} (should be 0 for a fully sealed shell)")
    bm.free()

    export_mesh(obj, args.out_path)
    print(f"Exported: {args.out_path}")
    print("Reminder: run check_wall_thickness.py and mesh_health_check.py on this output before trusting it.")


if __name__ == "__main__":
    main()
