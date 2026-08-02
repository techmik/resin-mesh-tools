"""
Mesh health check: connected-component (island) analysis + non-manifold/open
edge detection, with the open edges clustered into distinct groups by
connectivity rather than just reported as one raw count.

Why cluster the open edges instead of just counting them: a raw count like
"240 open edges" doesn't tell you whether that's one big real hole, a handful
of tiny pre-existing pinhole defects scattered around the model (common on
Meshy/Rodin output -- gun muzzle bores, small hardware gaps -- and usually
harmless), or an unwelded separate patch object someone placed in the same
spot but never actually joined to the mesh. Clustering by connectivity tells
you which of those you're actually looking at, so you know whether it's safe
to ignore, needs remove_and_cap.py, or needs an actual Bridge Edge Loops /
Merge by Distance pass in Blender's GUI.

Also flags whole-mesh islands (disconnected floating pieces) separately from
the open-edge clusters, since a "1 mesh" object in Blender's viewport can
still be several unconnected pieces underneath -- object count is not the
same as connected-component count.

Usage:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \
        --python mesh_health_check.py -- <mesh_path> [--max-islands N] [--max-clusters N]
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mesh_io import import_mesh, get_script_args

import bmesh


def connected_components(verts_iter, edges_of_vert):
    """Generic connected-component finder over an arbitrary vertex set + adjacency."""
    visited = set()
    components = []
    for start in verts_iter:
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        comp = set()
        while stack:
            v = stack.pop()
            comp.add(v)
            for e in edges_of_vert(v):
                other = e.other_vert(v)
                if other not in visited:
                    visited.add(other)
                    stack.append(other)
        components.append(comp)
    return components


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh_path")
    parser.add_argument("--max-islands", type=int, default=10, help="how many whole-mesh islands to detail (largest first)")
    parser.add_argument("--max-clusters", type=int, default=15, help="how many open-edge clusters to detail (largest first)")
    args = parser.parse_args(get_script_args())

    obj = import_mesh(args.mesh_path)
    mw = obj.matrix_world

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    print(f"Total verts: {len(bm.verts)}, total faces: {len(bm.faces)}\n")

    # --- whole-mesh connected components (islands) ---
    islands = connected_components(bm.verts, lambda v: v.link_edges)
    islands.sort(key=len, reverse=True)
    print(f"Connected mesh islands (disconnected pieces): {len(islands)}")
    for i, comp in enumerate(islands[:args.max_islands]):
        coords = [mw @ v.co for v in comp]
        xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
        cx, cy, cz = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2
        print(f"  island {i}: {len(comp)} verts, bbox=({max(xs)-min(xs):.3f},{max(ys)-min(ys):.3f},{max(zs)-min(zs):.3f}), center=({cx:.3f},{cy:.3f},{cz:.3f})")
    if len(islands) > args.max_islands:
        print(f"  ... and {len(islands) - args.max_islands} more, not shown")

    # --- open / non-manifold edges, clustered ---
    open_edges = [e for e in bm.edges if len(e.link_faces) < 2]
    print(f"\nTotal open/non-manifold edges: {len(open_edges)}")

    if open_edges:
        vert_to_open_edges = {}
        for e in open_edges:
            for v in e.verts:
                vert_to_open_edges.setdefault(v, []).append(e)
        open_verts = list(vert_to_open_edges.keys())
        clusters = connected_components(open_verts, lambda v: vert_to_open_edges[v])
        clusters.sort(key=len, reverse=True)
        print(f"Distinct open-edge clusters (by connectivity): {len(clusters)}")
        for i, comp in enumerate(clusters[:args.max_clusters]):
            coords = [mw @ v.co for v in comp]
            xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
            cx, cy, cz = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2
            print(f"  cluster {i}: {len(comp)} verts, bbox=({max(xs)-min(xs):.3f},{max(ys)-min(ys):.3f},{max(zs)-min(zs):.3f}), center=({cx:.3f},{cy:.3f},{cz:.3f})")
        if len(clusters) > args.max_clusters:
            print(f"  ... and {len(clusters) - args.max_clusters} more, not shown")
        print("\nRule of thumb: one large cluster with many verts is usually a real hole worth capping")
        print("(see remove_and_cap.py). Several small clusters (a handful of verts each) scattered")
        print("far apart are usually harmless pre-existing details (bores, vents). A cluster that")
        print("sits in the same spot as a suspiciously separate island above is likely an unwelded")
        print("patch object that needs Bridge Edge Loops or a proper weld, not just a fill.")

    bm.free()


if __name__ == "__main__":
    main()
