"""Characterize v8's last defects before fixing: 1 boundary edge, 87 non-manifold.

Read-only. Reports exact positions/face-counts so the fix (next script) is
targeted instead of guessed.

Run:  blender --background --python scripts/diagnose_capital_v8_remainder.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS                  # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v8.blend")


def log(*a):
    print("[diag-v8]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]
    bm = bmesh.new()
    bm.from_mesh(ob.data)

    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    nonmanifold = [e for e in bm.edges if len(e.link_faces) > 2]
    log(f"boundary: {len(boundary)}  non-manifold: {len(nonmanifold)}")

    for e in boundary:
        log(f"boundary edge: verts {tuple(round(c,6) for c in e.verts[0].co)} -> "
            f"{tuple(round(c,6) for c in e.verts[1].co)}  length={e.calc_length():.6f}")

    # Group non-manifold edges by face-count to see if it's one consistent pattern
    from collections import Counter
    counts = Counter(len(e.link_faces) for e in nonmanifold)
    log(f"non-manifold link_faces-count histogram: {dict(counts)}")

    # Check for exact duplicate faces (same vertex set) among faces touching
    # non-manifold edges specifically.
    touched_faces = set()
    for e in nonmanifold:
        for f in e.link_faces:
            touched_faces.add(f)
    log(f"{len(touched_faces)} distinct faces touch a non-manifold edge")

    by_vertset = {}
    for f in touched_faces:
        key = frozenset(v.index for v in f.verts)
        by_vertset.setdefault(key, []).append(f)
    dup_groups = {k: v for k, v in by_vertset.items() if len(v) > 1}
    log(f"{len(dup_groups)} exact-duplicate-vertex-set face groups among them "
        f"(covers {sum(len(v) for v in dup_groups.values())} faces)")

    # For non-manifold edges NOT explained by exact duplicate faces, sample a
    # few and report their surrounding face areas/normals to see if it's
    # near-duplicate (slightly offset) geometry instead.
    unexplained = []
    for e in nonmanifold:
        faces = e.link_faces
        keys = set(frozenset(v.index for v in f.verts) for f in faces)
        if len(keys) == len(faces):  # all distinct vertex sets -> not exact dup
            unexplained.append(e)
    log(f"{len(unexplained)} non-manifold edges NOT explained by exact-duplicate faces")
    for e in unexplained[:6]:
        mid = (e.verts[0].co + e.verts[1].co) / 2
        areas = [round(f.calc_area(), 8) for f in e.link_faces]
        log(f"  at {tuple(round(c,5) for c in mid)}  nfaces={len(e.link_faces)}  "
            f"face_areas={areas}")

    # Cluster non-manifold edges spatially (connected via shared verts) to see
    # if 87 edges is really just a handful of localized problem spots.
    by_vert = {}
    for e in nonmanifold:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen = set()
    clusters = []
    for e0 in nonmanifold:
        if id(e0) in seen:
            continue
        ce = []
        stack = [e0]
        seen.add(id(e0))
        while stack:
            e = stack.pop()
            ce.append(e)
            for v in e.verts:
                for e2 in by_vert.get(v, []):
                    if id(e2) not in seen:
                        seen.add(id(e2))
                        stack.append(e2)
        clusters.append(ce)
    clusters.sort(key=len, reverse=True)
    log(f"{len(clusters)} spatial clusters of non-manifold edges; sizes: "
        f"{[len(c) for c in clusters[:15]]}")

    bm.free()


if __name__ == "__main__":
    main()
