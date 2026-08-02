"""
Hollow only the region on one side of a cutoff plane along a chosen axis,
leaving everything on the other side (e.g. a base + support pillar, or --
the case this was extended for -- an already-open troop bay that shouldn't
get a second, conflicting cavity cut into it) fully solid.

Originally Z-only (a height cutoff, for a base+pillar that should stay
solid below a body that gets hollowed above). Generalized to
--axis {x,y,z} + --keep-side {below,above} after a real model's hull/bay
split turned out to run along X (front hull vs. rear open bay), not Z.
--keep-side below/above always means "below/above the cutoff on the
chosen axis" -- e.g. --axis x --cutoff 36 --keep-side above keeps
everything with x > 36 solid and hollows x < 36.

Same validated core hollow as hollow_shell.py (voxel-remesh a disposable
cutting-tool duplicate, per-vertex normal offset, Boolean EXACT difference
against the untouched original) -- see that script's docstring for the
full reasoning, including why a SECOND remesh pass on the offset shape was
tried and reverted. Always run check_wall_thickness.py on the result -- a
few near-zero-thickness spots can still slip through in geometrically
complex areas, and that's an accepted, reinforce-after-printing tradeoff,
not something to try to algorithmically eliminate here.

How the "leave one side solid" part works (rewritten twice, see history
below): clip the cutting tool to the hollow-side of --cutoff
via a Boolean INTERSECT against a box, done IMMEDIATELY AFTER the voxel
remesh but BEFORE the per-vertex normal offset -- i.e. while the tool is
still a clean, well-formed mesh straight out of Blender's remesh, not yet
the self-intersecting shape the offset step deliberately produces. THEN
apply the offset to the already-clipped tool, and Boolean-DIFFERENCE it
out of the original as usual.

Two earlier approaches were tried and abandoned before this one:
1. Manually deleting cutting-tool faces past the cutoff and hole-filling
   the resulting boundary into a flat cap. Broke completely on one real
   model's X-axis cut (622 boundary edges filled into just 5 faces,
   producing a shattered, unusable result) -- a real cross-section can
   have several separate loops at once (here: hull outline plus both
   antennas), and one holes_fill() call across all of them isn't safe.
   The original Z-cutoff case only had one simple loop (a round pillar),
   which is why this wasn't caught until a more complex cut exposed it.
2. Boolean-INTERSECTing the ALREADY-OFFSET cutting tool directly against a
   clipping box. The box math was right (confirmed via a standalone debug
   script), but the offset tool has local self-intersections BY DESIGN
   (see hollow_shell.py's docstring) -- fine as input to the one DIFFERENCE
   operation this pipeline is actually validated on, but not safe as input
   to a different boolean type. Result was silently empty.
3. Hollowing the whole body first (proven), then separately cutting a
   clean solid chunk for the keep-side region out of the pristine original
   and Boolean-UNIONing it back onto the hollowed body. Both individual
   booleans looked reasonable on paper, but the union step HUNG for 5+
   minutes and was killed -- the hollowed body and the keep-chunk share
   near-identical exterior surface geometry over most of the model (both
   cut from the same original), and coincident/overlapping surfaces are a
   known hard case for boolean solvers. The current approach (clip before
   offset) avoids this entirely -- there's only ever one boolean per tool
   copy, no coincident-surface union involved.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \\
        --python hollow_shell_partial.py -- <in_path> <out_path> --axis z --cutoff Z --keep-side below --thickness 2.5 [--flip]
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
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z", help="which axis the cutoff plane is perpendicular to (default z)")
    parser.add_argument("--cutoff", type=float, required=True, help="cutoff position along --axis")
    parser.add_argument("--keep-side", choices=["below", "above"], default="below", help="which side of the cutoff stays fully solid -- 'below' matches the original z-cutoff behavior (base/pillar below stays solid, body above gets hollowed)")
    parser.add_argument("--thickness", type=float, default=2.5, help="wall thickness in mm (default 2.5)")
    parser.add_argument("--flip", action="store_true")
    parser.add_argument("--voxel-size", type=float, default=1.5)
    args = parser.parse_args(get_script_args())

    axis_idx = {"x": 0, "y": 1, "z": 2}[args.axis]

    obj = import_mesh(args.in_path)
    orig_size = bbox_size(obj)
    orig_pts = [v.co.copy() for v in obj.data.vertices]
    orig_mins = [min(p[i] for p in orig_pts) for i in range(3)]
    orig_maxs = [max(p[i] for p in orig_pts) for i in range(3)]
    print(f"Before hollow: bbox size = {orig_size}")

    inner_data = obj.data.copy()
    inner = bpy.data.objects.new("inner", inner_data)
    bpy.context.collection.objects.link(inner)

    remesh = inner.modifiers.new(name="Remesh", type='REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = args.voxel_size
    result = _apply_modifier_on(inner, remesh)
    print(f"Remesh (voxel_size={args.voxel_size}) result: {result}, verts now: {len(inner.data.vertices)}")

    # Clip the cutting tool to zero volume on the --keep-side of --cutoff
    # RIGHT NOW, while it's still the clean, well-formed remesh output --
    # NOT after the per-vertex offset below, which deliberately leaves it
    # with local self-intersections (see docstring, attempt #2).
    pad = max(orig_maxs[i] - orig_mins[i] for i in range(3)) + 10.0
    box_min = list(orig_mins)
    box_max = list(orig_maxs)
    for i in range(3):
        if i != axis_idx:
            box_min[i] -= pad
            box_max[i] += pad
    if args.keep_side == "below":
        box_min[axis_idx] = args.cutoff
        box_max[axis_idx] = orig_maxs[axis_idx] + pad
    else:
        box_min[axis_idx] = orig_mins[axis_idx] - pad
        box_max[axis_idx] = args.cutoff

    box_center = [(box_min[i] + box_max[i]) / 2 for i in range(3)]
    box_size = [box_max[i] - box_min[i] for i in range(3)]
    print(f"Clip box (keeps the tool's non-{args.keep_side} side, i.e. the hollow side): center={box_center}, size={box_size}")

    bpy.ops.mesh.primitive_cube_add(size=1, location=box_center)
    clip_box = bpy.context.active_object
    clip_box.scale = box_size
    # object.scale doesn't propagate to matrix_world (what the boolean
    # modifier actually evaluates) until the depsgraph is updated -- without
    # this, the modifier sees an un-scaled 1x1x1 box, which doesn't overlap
    # anything and silently produces an empty result. Confirmed the hard way.
    bpy.context.view_layer.update()

    clip_boolean = inner.modifiers.new(name="ClipBox", type='BOOLEAN')
    clip_boolean.operation = 'INTERSECT'
    clip_boolean.object = clip_box
    clip_boolean.solver = 'EXACT'
    result = _apply_modifier_on(inner, clip_boolean)
    print(f"Clip-box intersect result: {result}, tool verts now: {len(inner.data.vertices)}")

    bpy.data.objects.remove(clip_box, do_unlink=True)

    if len(inner.data.vertices) == 0:
        print("ERROR: clipped cutting tool is empty -- --cutoff is likely outside the model's range on this axis. Aborting.")
        bpy.data.objects.remove(inner, do_unlink=True)
        return

    clipped_size = bbox_size(inner)
    print(f"Inner tool after clipping: bbox size = {clipped_size}")

    sign = -1.0 if not args.flip else 1.0
    offset = sign * abs(args.thickness)

    bm = bmesh.new()
    bm.from_mesh(inner.data)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    for v in bm.verts:
        v.co = v.co + v.normal * offset
    bm.to_mesh(inner.data)
    inner.data.update()
    bm.free()

    offset_size = bbox_size(inner)
    print(f"Inner tool after per-vertex offset: bbox size = {offset_size}")

    boolean = obj.modifiers.new(name="Boolean", type='BOOLEAN')
    boolean.operation = 'DIFFERENCE'
    boolean.object = inner
    boolean.solver = 'EXACT'
    result = _apply_modifier_on(obj, boolean)
    print(f"Boolean modifier_apply result: {result}")

    bpy.data.objects.remove(inner, do_unlink=True)

    final_size = bbox_size(obj)
    print(f"After boolean hollow: bbox size = {final_size}")
    # Checks both directions -- growth (an exploded boolean) AND shrinkage (a
    # botched clip eating into the exterior) -- both are real failure modes
    # seen while building this script, not just a hypothetical.
    changed = any(abs(final_size[i] - orig_size[i]) > orig_size[i] * 0.02 for i in range(3))
    print("ERROR: bbox changed significantly -- don't trust this output." if changed else "Exterior bbox unchanged -- looks correct.")

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    open_edges = [e for e in bm.edges if len(e.link_faces) < 2]
    print(f"Open edges in result: {len(open_edges)}")
    bm.free()

    export_mesh(obj, args.out_path)
    print(f"Exported: {args.out_path}")
    print("Reminder: run check_wall_thickness.py and mesh_health_check.py on this output before trusting it.")


if __name__ == "__main__":
    main()
