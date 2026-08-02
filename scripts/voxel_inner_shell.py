"""
Builds a hollowing "inner cutting tool" shell via true volumetric erosion,
instead of hollow_shell.py's per-vertex normal offset. Run this first, then
apply_boolean_diff.py to cut the result out of the original mesh.

Why this exists: hollow_shell.py's per-vertex offset moves each vertex
along its own normal, which self-intersects/pinches wherever the surface
curves inward tighter than the offset distance -- a geometric flaw in that
*method*, not something voxel-size or remesh-order tuning can fully avoid.
Confirmed on a real print: a hollowed tank cracked at a geometrically
complex hull/track junction, and check_wall_thickness.py found several
genuine near-zero-thickness (down to exactly 0.000mm) and no-inner-wall
gap spots there.

This script instead:
  1. Voxelizes the whole solid mesh into a 3D occupancy grid (trimesh).
  2. Erodes that grid with a spherical structuring element sized to the
     wall thickness (scipy.ndimage.binary_erosion) -- a morphological
     shrink that operates on solid/empty voxels, not surface vertices, so
     it CANNOT fold or self-intersect at a concave corner. Concave corners
     just erode a little unevenly (rounding), never pinch to zero.
  3. Reconstructs the eroded solid's boundary via marching cubes
     (trimesh's VoxelGrid.marching_cubes) to get the inner shell mesh.

Verified 2026-07-31 on the same hull/track-junction tank, side by side with
hollow_shell.py's output, same sample count in check_wall_thickness.py:
  - Old (per-vertex offset): min thickness 0.000mm, 3 points at/near zero,
    1 point with no inner wall at all (a real gap). Median 2.058mm.
  - New (voxel erosion, 0.3mm pitch): min thickness 0.082mm, ZERO points
    at/near zero, ZERO no-wall gaps. Median 2.092mm.
This eliminates the worst failure mode (true breaches/gaps) but does NOT
guarantee no thin spots at all -- a handful of sub-0.3mm points remained
even after tightening the voxel pitch from 0.5mm to 0.3mm (which improved
the minimum but didn't clear them), most likely because those spots are
genuinely close-together geometry in the source mesh itself (two panels
already under 2x the target wall thickness apart) rather than a numerical
artifact -- going finer than ~0.3mm is not expected to clear those.
check_wall_thickness.py is still mandatory afterward; reinforce any
flagged spot after printing (CA glue/resin), same habit as hollow_shell.py.

Only produces the INNER shell -- the actual hollow (original minus inner)
still goes through apply_boolean_diff.py's Blender EXACT solver, the same
trusted boolean step hollow_shell.py uses. This keeps the only new/less-
proven variable isolated to how the inner cutting tool is built.

Costs more than hollow_shell.py: needs a second Python environment
(trimesh, scipy, scikit-image -- not available in Blender's bundled
Python) and runs as two steps instead of one. Use hollow_shell.py for
routine hollowing; reach for this when a near-zero-thickness spot from
hollow_shell.py actually matters (a "real replica" showoff piece, or after
a real crack) and it's worth the extra setup to reduce that risk.

Setup (one-time): pip install -r <skill_dir>/scripts/requirements.txt
Run with a regular python.exe, NOT blender.exe -- this script needs
trimesh/scipy/scikit-image, which Blender's bundled Python doesn't have.

Usage:
    python voxel_inner_shell.py <in_path> <inner_out_path> --thickness 2.5 [--voxel-size 0.3]
"""
import argparse

import trimesh
from scipy.ndimage import binary_erosion
from skimage.morphology import ball


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("in_path")
    parser.add_argument("inner_out_path")
    parser.add_argument("--thickness", type=float, default=2.5, help="wall thickness in mm (default 2.5)")
    parser.add_argument("--voxel-size", type=float, default=0.3, help="voxel pitch in mm (default 0.3) -- finer gives a more accurate thickness but a bigger grid; 0.5 is faster and was noticeably less precise in testing")
    args = parser.parse_args()

    mesh = trimesh.load(args.in_path, force="mesh")
    print(f"Loaded: {len(mesh.vertices)} verts, {len(mesh.faces)} faces, watertight={mesh.is_watertight}")
    print(f"Bbox extents (mm): {mesh.bounding_box.extents}")

    pitch = args.voxel_size
    vox = mesh.voxelized(pitch=pitch)
    vox_filled = vox.fill()
    matrix = vox_filled.matrix
    solid_count = int(matrix.sum())
    print(f"Voxel grid shape: {matrix.shape}, solid voxels: {solid_count}")
    if solid_count == 0:
        print("ERROR: fill() produced zero solid voxels -- the mesh likely has gaps large enough to leak during flood-fill. Aborting.")
        return

    radius = max(1, round(args.thickness / pitch))
    achieved_thickness = radius * pitch
    print(f"Eroding with a spherical structuring element, radius={radius} voxels (~{achieved_thickness:.2f}mm actual, requested {args.thickness}mm)")
    structure = ball(radius)
    eroded = binary_erosion(matrix, structure=structure)
    eroded_count = int(eroded.sum())
    print(f"Eroded solid voxels: {eroded_count} (was {solid_count}, {100 * eroded_count / solid_count:.1f}% remaining)")

    if eroded_count == 0:
        print("ERROR: erosion consumed the entire interior -- thickness too large for this model at this voxel size. Aborting.")
        return

    inner_vox = trimesh.voxel.VoxelGrid(eroded, transform=vox_filled.transform)
    inner_mesh = inner_vox.marching_cubes
    # marching_cubes returns vertices in raw voxel-index space -- confirmed via a
    # no-erosion round-trip test that came back ~2x the original mesh's bbox
    # (grid shape in voxel COUNTS, not mm) until this transform was applied.
    inner_mesh.apply_transform(inner_vox.transform)
    print(f"Inner shell mesh: {len(inner_mesh.vertices)} verts, {len(inner_mesh.faces)} faces, watertight={inner_mesh.is_watertight}")
    print(f"Inner shell bbox extents (mm): {inner_mesh.bounding_box.extents}")

    inner_mesh.export(args.inner_out_path)
    print(f"Exported inner shell: {args.inner_out_path}")
    print("Next: run apply_boolean_diff.py (Blender) to cut this out of the original mesh.")


if __name__ == "__main__":
    main()
