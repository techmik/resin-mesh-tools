"""
Render a consistent set of orthographic views of a mesh for visual before/after
comparison -- used constantly for verifying a mesh edit actually worked rather
than trusting bounding-box numbers alone. A "genuinely flat" fill can still
look domed if shading is wrong (see remove_and_cap.py's docstring), and a
"successful" bmesh operation can still look visually broken -- always render
and look before calling a mesh fix done.

Renders, by default: an isometric 3/4 view, a straight front view, a straight
top view, and a bottom-up "underside" view (useful for checking a model's
belly/base after removing a plinth). Uses Blender Workbench with Studio
lighting and cavity shading, matte grey material -- fast, no texture/lighting
setup needed, good enough for structural verification (not a final render).

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \
        --python render_views.py -- <mesh_path> <out_dir> [--prefix name] [--views iso,front,top,underside] [--color 0.8 0.55 0.5]
"""
import sys
import os
import argparse
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, get_script_args

import bpy


def setup_shading(scene, color):
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'SINGLE'
    scene.display.shading.single_color = tuple(color)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'


def clear_cameras():
    for c in list(bpy.data.objects):
        if c.type == 'CAMERA':
            bpy.data.objects.remove(c, do_unlink=True)


def render_one(scene, out_path, loc, rot, ortho_scale, resx, resy):
    clear_cameras()
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = ortho_scale
    cam_obj = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = loc
    cam_obj.rotation_euler = rot
    scene.camera = cam_obj
    scene.render.resolution_x = resx
    scene.render.resolution_y = resy
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print("rendered", out_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh_path")
    parser.add_argument("out_dir")
    parser.add_argument("--prefix", default="render")
    parser.add_argument("--views", default="iso,front,top,underside", help="comma-separated: iso,front,top,underside")
    parser.add_argument("--color", type=float, nargs=3, default=[0.75, 0.75, 0.78], metavar=("R", "G", "B"))
    parser.add_argument("--res", type=int, default=1600, help="long-edge resolution in pixels")
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.mesh_path)
    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]; ys = [c.y for c in corners]; zs = [c.z for c in corners]
    minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys); minz, maxz = min(zs), max(zs)
    cx, cy, cz = (minx+maxx)/2, (miny+maxy)/2, (minz+maxz)/2
    sizex, sizey, sizez = maxx-minx, maxy-miny, maxz-minz

    scene = bpy.context.scene
    setup_shading(scene, args.color)

    requested = [v.strip() for v in args.views.split(",") if v.strip()]

    if "iso" in requested:
        diag = max(sizex, sizey, sizez) * 1.4
        render_one(scene, f"{args.out_dir}\\{args.prefix}_iso.png",
                   (cx + diag*0.7, cy - diag*0.9, cz + diag*0.6), (1.1, 0, 0.65), diag,
                   args.res, int(args.res * 0.75))

    if "front" in requested:
        scale = max(sizex, sizez) * 1.1
        render_one(scene, f"{args.out_dir}\\{args.prefix}_front.png",
                   (cx, miny - max(sizex, sizez) * 1.2, cz), (1.5708, 0, 0), scale,
                   args.res, int(args.res * sizez / sizex) if sizex else args.res)

    if "top" in requested:
        scale = max(sizex, sizey) * 1.05
        render_one(scene, f"{args.out_dir}\\{args.prefix}_top.png",
                   (cx, cy, maxz + max(sizex, sizey)), (0, 0, 0), scale,
                   args.res, int(args.res * sizey / sizex) if sizex else args.res)

    if "underside" in requested:
        scale = max(sizex, sizey) * 1.05
        render_one(scene, f"{args.out_dir}\\{args.prefix}_underside.png",
                   (cx, cy, minz - max(sizex, sizey)), (3.14159265, 0, 0), scale,
                   args.res, int(args.res * sizey / sizex) if sizex else args.res)

    print(f"\nBBOX: size=({sizex:.4f}, {sizey:.4f}, {sizez:.4f})  center=({cx:.4f}, {cy:.4f}, {cz:.4f})")


if __name__ == "__main__":
    main()
