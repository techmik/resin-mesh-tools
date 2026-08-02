"""
Shared import/export helpers for the other scripts in this repo.
Not a script to run on its own -- the other scripts in this folder read this
file's contents in as needed since Blender's --python invocation doesn't
reliably share a Python path across separate script runs.
"""
import bpy


def import_mesh(path):
    """Import an OBJ or STL into a fresh scene and return the single mesh object."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    lower = path.lower()
    if lower.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=path)
    elif lower.endswith(".stl"):
        bpy.ops.wm.stl_import(filepath=path)
    else:
        raise ValueError(f"Unsupported file extension for {path} (expected .obj or .stl)")
    objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not objs:
        raise RuntimeError(f"No mesh object found after importing {path}")
    return objs[0]


def export_mesh(obj, path):
    """Export a single mesh object as OBJ or STL, inferred from the path's extension."""
    import bpy
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    lower = path.lower()
    if lower.endswith(".obj"):
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
    elif lower.endswith(".stl"):
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True)
    else:
        raise ValueError(f"Unsupported output extension for {path} (expected .obj or .stl)")


def get_script_args():
    """Return the CLI args passed after '--' to `blender --python script.py -- <args>`."""
    import sys
    argv = sys.argv
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    return []
