"""Close the leafscroll master's tiny boundary/non-manifold defects.

Same scoped self-collapse technique proven on the capital (see
repair_capital_leafgaps3.py / repair_capital_final_cleanup.py in this
directory, and PIPELINE-GUIDE.md SS13): weld each defect's own vertices
together rather than filling a new face over them. fill operators
(holes_fill / triangle_fill / contextual_create) were confirmed unreliable
on this class of tiny non-planar gap during the capital repair and are not
worth re-testing here.

The leafscroll's defects are much smaller in scope than the capital's were:
52 boundary edges forming 26 closed 3-edge loops (all size 3 -- tiny
triangular gaps), plus 52 non-manifold edges each with exactly 3 linked
faces (a sliver face stacked against real geometry). Edge lengths for both
categories are ~0.0005-0.0015, several orders below the mesh's real feature
scale.

The two defect categories are NOT independent: 52 of the 78 boundary-loop
vertices are also non-manifold-edge endpoints (checked directly before
writing this), i.e. each of the 26 gap locations is one closed boundary
loop PLUS its own pair of non-manifold edges, all touching the same sliver
triangle. Tagging clusters by simple sequential overwrite (as the capital's
first final-cleanup attempt did, before the over-greedy-scope bug was found
there) would let a later cluster's tag silently evict vertices from an
earlier one at these shared points. Fixed with union-find over vertex
indices instead: any two verts that co-occur in the same boundary loop or
non-manifold edge end up in the same component, and each component is
welded as a single cluster -- so overlapping defects merge correctly
instead of one clobbering the other.

Run:  blender --background --python scripts/repair_leafscroll.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import LEAFSCROLL_MASTER, LEAFSCROLL_MASTER_OBJECT, MASTERS  # noqa: E402

OUT_PATH = os.path.join(MASTERS, "leafscroll-master-v2.blend")


def log(*a):
    print("[leafscroll-repair]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=LEAFSCROLL_MASTER)
    ob = bpy.data.objects[LEAFSCROLL_MASTER_OBJECT]
    bm = bmesh.new()
    bm.from_mesh(ob.data)

    tag = bm.verts.layers.int.new("cluster_tag")
    for v in bm.verts:
        v[tag] = -1

    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    nonmanifold_edges = [e for e in bm.edges if len(e.link_faces) > 2]
    log(f"before: boundary={len(boundary_edges)} nonmanifold={len(nonmanifold_edges)} "
        f"faces={len(bm.faces)}")

    # --- union-find over vertex indices: any two verts that co-occur in the
    # same boundary edge or non-manifold edge belong in the same cluster ---
    parent = {}

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    def union(a, b):
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in boundary_edges + nonmanifold_edges:
        v0, v1 = e.verts
        parent.setdefault(v0.index, v0.index)
        parent.setdefault(v1.index, v1.index)
        union(v0.index, v1.index)

    groups = {}
    for i in parent:
        groups.setdefault(find(i), []).append(i)
    clusters = list(groups.values())

    log(f"clusters to weld: {len(clusters)} (from {len(boundary_edges)} boundary + "
        f"{len(nonmanifold_edges)} nonmanifold edges)")

    idx_to_vert = {v.index: v for v in bm.verts}
    next_tag = 0
    dist_by_tag = {}
    for vidxs in clusters:
        verts = [idx_to_vert[i] for i in vidxs if i in idx_to_vert]
        if len(verts) < 2:
            continue
        coords = [v.co.copy() for v in verts]
        lo = coords[0].copy()
        hi = coords[0].copy()
        for c in coords[1:]:
            for i in range(3):
                lo[i] = min(lo[i], c[i])
                hi[i] = max(hi[i], c[i])
        diag = (hi - lo).length
        dist = diag * 1.5 + 1e-7
        for v in verts:
            v[tag] = next_tag
        dist_by_tag[next_tag] = max(dist, 1e-6)
        next_tag += 1

    for t in range(next_tag):
        verts = [v for v in bm.verts if v[tag] == t]
        if len(verts) < 2:
            continue
        bmesh.ops.remove_doubles(bm, verts=verts, dist=dist_by_tag[t])

    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    boundary_after = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold_after = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    log(f"after: boundary={boundary_after} nonmanifold={nonmanifold_after} "
        f"faces={len(bm.faces)}")

    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")


if __name__ == "__main__":
    main()
