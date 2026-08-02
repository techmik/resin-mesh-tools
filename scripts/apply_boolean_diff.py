"""
Boolean-DIFFERENCE an already-built inner shell (from voxel_inner_shell.py)
out of the original mesh, using Blender's EXACT solver -- the same trusted
boolean step hollow_shell.py already uses. Kept as a separate script from
voxel_inner_shell.py (which needs trimesh/scipy, not available in Blender's
bundled Python) so this only changes how the inner cutting tool is built,
not the boolean step itself.

See voxel_inner_shell.py's docstring for why this two-script approach
exists and how it compares to hollow_shell.py.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \\
        --python apply_boolean_diff.py -- <original_path> <inner_path> <out_path>
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
    parser.add_argument("original_path")
    parser.add_argument("inner_path")
    parser.add_argument("out_path")
    args = parser.parse_args(get_script_args())

    original = import_mesh(args.original_path)
    orig_size = bbox_size(original)
    print(f"Original bbox: {orig_size}")

    # import_mesh() resets the scene (read_factory_settings), which would
    # delete `original` if called again -- import the inner shell directly
    # into the existing scene instead.
    lower = args.inner_path.lower()
    if lower.endswith(".stl"):
        bpy.ops.wm.stl_import(filepath=args.inner_path)
    elif lower.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=args.inner_path)
    else:
        raise ValueError(f"Unsupported extension for {args.inner_path}")
    inner = [o for o in bpy.context.selected_objects if o.type == 'MESH'][0]
    inner_size = bbox_size(inner)
    print(f"Inner shell bbox: {inner_size}")

    boolean = original.modifiers.new(name="Boolean", type='BOOLEAN')
    boolean.operation = 'DIFFERENCE'
    boolean.object = inner
    boolean.solver = 'EXACT'
    result = _apply_modifier_on(original, boolean)
    print(f"Boolean modifier_apply result: {result}")

    bpy.data.objects.remove(inner, do_unlink=True)

    final_size = bbox_size(original)
    print(f"After boolean hollow: bbox size = {final_size}")
    exploded = any(final_size[i] > orig_size[i] * 1.2 for i in range(3))
    if exploded:
        print("ERROR: exterior bbox changed significantly -- something went wrong, do not trust this output.")
    else:
        print("Exterior bbox unchanged -- looks correct.")

    bm = bmesh.new()
    bm.from_mesh(original.data)
    open_edges = [e for e in bm.edges if len(e.link_faces) < 2]
    print(f"Open edges in result: {len(open_edges)} (should be 0 for a fully sealed shell)")
    bm.free()

    export_mesh(original, args.out_path)
    print(f"Exported: {args.out_path}")
    print("Reminder: run check_wall_thickness.py on this output before trusting it.")


if __name__ == "__main__":
    main()
