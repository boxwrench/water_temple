"""Close the lion master's remaining tiny boundary/non-manifold defects.

Same scoped self-collapse technique proven on the capital and leafscroll
(see repair_leafscroll.py for the fullest writeup, PIPELINE-GUIDE.md SS13):
weld each defect's own vertices together via union-find over vertex
indices, rather than filling a new face over them -- fill operators were
confirmed unreliable on this class of tiny gap during the capital repair.

v3 already went through repair_masters.py's easy pass (246 boundary -> 100,
251 non-manifold -> 100). The remaining 100/100 is the exact same shape as
the leafscroll's defects: 51 closed boundary loops (mostly size 3, two of
size 2), heavily overlapping with the non-manifold edges (102 of 151
boundary-loop vertices are also non-manifold-edge endpoints) -- each
defect location is a sliver triangle contributing one closed boundary loop
plus its own pair of non-manifold edges. Union-find merges overlapping
defects into single clusters before welding, avoiding the over-greedy-scope
and sequential-tag-overwrite bugs hit earlier in this project.

Run:  blender --background --python scripts/repair_lion.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import LION_MASTER, LION_MASTER_OBJECT, MASTERS  # noqa: E402

OUT_PATH = os.path.join(MASTERS, "Tripo-lion-mask-master-v4.blend")


def log(*a):
    print("[lion-repair]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=LION_MASTER)
    ob = bpy.data.objects[LION_MASTER_OBJECT]
    bm = bmesh.new()
    bm.from_mesh(ob.data)

    tag = bm.verts.layers.int.new("cluster_tag")
    for v in bm.verts:
        v[tag] = -1

    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    nonmanifold_edges = [e for e in bm.edges if len(e.link_faces) > 2]
    log(f"before: boundary={len(boundary_edges)} nonmanifold={len(nonmanifold_edges)} "
        f"faces={len(bm.faces)}")

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
