# resin-mesh-tools

A small collection of Blender-headless Python scripts for prepping resin-print STL/OBJ files when your slicer's own tools (auto-hollow, mesh repair) aren't trusted or don't do quite what you need. Built for real problems hit while kitbashing and hollowing AI-generated and kitbashed models for MSLA/DLP resin printing — thin-protrusion handling, hollowing without cracking at complex geometry, removing an unwanted fused base, scaling a model to real-world units, and more.

Every script is standalone and run via Blender's `--background --python` mode (or plain Python for the one script that needs `trimesh`). No Blender add-on installation needed — these are just scripts.

## Requirements

- [Blender](https://www.blender.org/) 4.x or later (tested on 5.2). All scripts run via:
  ```
  "path/to/blender.exe" --background --factory-startup --python <script.py> -- <args>
  ```
  (Everything after the bare `--` is the script's own argument list — Blender's own flags go before it.)
- One script (`voxel_inner_shell.py`) needs a regular Python environment with `trimesh`, `scipy`, and `scikit-image` (not available in Blender's bundled Python):
  ```
  pip install -r requirements.txt
  ```

Run any script with `--help` (after the `--`) for its full argument list — each script's docstring also explains what it's for and why, worth reading before using it on an unfamiliar model.

## Scripts

### Diagnostics — run these first

- **`zslice_footprint.py <mesh> [--bins N] [--zmin Z] [--zmax Z] [--axis x|y|z]`** — buckets a mesh's vertices into N bins along one axis and reports each bin's vertex count and XY footprint. Use this to find where a mesh's footprint suddenly widens or narrows — e.g. distinguishing an unwanted display base fused to a model from the model's real geometry, or finding where a thin connecting "neck" gives way to the real body.

- **`mesh_health_check.py <mesh> [--max-islands N] [--max-clusters N]`** — reports disconnected mesh islands (a "1 mesh" object in Blender's viewport can still be several unwelded pieces underneath) and clusters open/non-manifold edges by connectivity, so you can tell "one big real hole" apart from "several tiny harmless pre-existing pinholes" apart from "an unwelded patch object sitting in the same spot as a hole, never actually joined to it."

- **`render_views.py <mesh> <out_dir> [--prefix name] [--views iso,front,top,underside] [--color R G B]`** — renders a consistent iso/front/top/underside view set using Blender Workbench + Studio lighting. Always render and actually look before/after a mesh fix rather than trusting bounding-box numbers or a "successful" bmesh operation alone — a fill face can render as a dome despite genuinely flat geometry if shading is wrong (see `remove_and_cap.py` below), and that kind of defect is invisible to numeric checks.

- **`check_wall_thickness.py <mesh> [--zmax Z] [--samples N]`** — ray-casts inward from the outer surface at many sample points to measure real local wall thickness, reporting the thinnest spots found. **Mandatory after any hollow operation** — a hollowed model can look completely fine (correct exterior bbox, zero open edges) and still have a genuine near-zero-thickness or fully-gapped spot in a geometrically complex area, invisible to a bbox/open-edge check but a real structural weak point.

### Fixing geometry

- **`scale_uniform.py <in> <out> --target-x-mm N`** — uniformly rescales a mesh so its X dimension matches a target real-world mm value. Needed when a raw STL comes in at some arbitrary native unit scale rather than real millimeters — other scripts here (hollow thickness, thicken factors) all operate in the file's *current* units, so get real-world scale sorted first.

- **`remove_and_cap.py <in> <out> --zmax Z [--xy-center CX CY --xy-radius R --neck-zmax Z2] [--flatten-to min|max|avg]`** — deletes faces matching a Z-threshold and/or a narrow XY-radius "neck" region (built for the common "AI-generated model came with an unwanted display base fused to the tracks/feet" problem), flattens the resulting boundary loop to one consistent height, fills it, and **sets the new fill face(s) to flat shading**. That last step isn't optional — skipping it leaves a fake domed appearance from stale smooth-shaded vertex normals, *even when the underlying geometry is genuinely flat*.

- **`thicken_region.py <in> <out> --zmin Z1 --zmax Z2 --factor N [--blend-fraction F]`** — thickens a Z-range of a mesh radially about *each Z-slice's own local centroid* (not one fixed axis), so a tapered or leaning support pillar gets fatter without losing its shape. Ramps smoothly at both ends of the range so there's no visible seam.

### Hollowing

Two different techniques, with a real tradeoff between them:

- **`hollow_shell.py <in> <out> --thickness N [--flip] [--voxel-size N]`** and **`hollow_shell_partial.py <in> <out> --axis {x,y,z} --cutoff Z --keep-side {below,above} --thickness N [--flip]`** — the simpler, single-script approach: voxel-remesh a disposable cutting-tool copy, offset it inward per-vertex along its own normal, then Boolean-difference it out of the untouched original. The `_partial` variant hollows only one side of a cutoff plane, leaving a base/pillar (or an already-open cavity like a vehicle's troop bay) fully solid. Fast and simple, but the per-vertex-offset method has a real, inherent limitation: it can pinch to a literal 0.000mm breach at geometrically complex concave corners. It's a flaw in the method itself, not something voxel-size tuning fully fixes — **always follow with `check_wall_thickness.py`** and treat any flagged near-zero spot as something to reinforce after printing (a dab of CA glue or resin), not something to algorithmically eliminate beforehand.

- **`voxel_inner_shell.py <in> <inner_out> --thickness N [--voxel-size N]`** (run with regular `python.exe`, **not** `blender.exe`) **+ `apply_boolean_diff.py <original> <inner> <out>`** (Blender) — a true volumetric-erosion alternative for when the per-vertex-offset method's thin-spot risk actually matters (a showoff/display piece, or re-hollowing something that already cracked). Voxelizes the whole solid into a 3D grid, erodes it with a spherical structuring element (a morphological shrink that can't self-intersect at concave corners the way a per-vertex offset can), then reconstructs the inner wall via marching cubes — `apply_boolean_diff.py` then cuts it out of the original using the same Boolean EXACT solver `hollow_shell.py` uses. In direct side-by-side testing on the same model, this eliminated every true zero-thickness breach and no-inner-wall gap that the per-vertex-offset method left behind, though a handful of sub-0.3mm thin spots can still remain — most likely genuine close-together geometry in the source mesh rather than a technique artifact. Costs more setup (a second Python environment) and runs as two steps instead of one — use `hollow_shell.py` for routine hollowing, reach for this when the extra robustness is worth it.

### Utility

- **`extract_goo_thumbnail.ps1 -SourcePath <goo> -OutPath <png> [-Size N]`** (plain Windows PowerShell — run via `powershell -NoProfile -ExecutionPolicy Bypass -File extract_goo_thumbnail.ps1 ...`) — pulls the embedded preview thumbnail out of a sliced `.goo` file (Elegoo Satellite's proprietary, undocumented format) as a real PNG, useful for reviewing a print's orientation/supports without needing a manual slicer screenshot. Works by asking Windows itself for the same thumbnail Explorer already renders for the file (via `IShellItemImageFactory`, the same shell mechanism Explorer's folder-view thumbnails use), rather than trying to reverse-engineer the binary format.

## Recommended workflow

1. **Before touching a new model**: `mesh_health_check.py` and `zslice_footprint.py` to understand what you're working with — real scale, any unwanted fused geometry, any pre-existing mesh defects.
2. **Fix geometry issues** (`scale_uniform.py`, `remove_and_cap.py`, `thicken_region.py`) as needed, rendering with `render_views.py` before/after each change to confirm it visually.
3. **Hollow** with `hollow_shell.py`/`hollow_shell_partial.py` for routine cases, or `voxel_inner_shell.py` + `apply_boolean_diff.py` for a piece where the extra robustness is worth the setup.
4. **Always** run `check_wall_thickness.py` on the hollowed output before trusting it. Reinforce any flagged thin spot after printing rather than chasing it algorithmically beforehand.

## License

MIT — see `LICENSE`.
