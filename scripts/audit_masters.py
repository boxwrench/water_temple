"""Full integrity read on each approved master, before touching any of them.

donor_prep.integrity() only checks boundary/non-manifold (cheap, used during
building). This adds degenerate faces, loose geometry, flipped-normal pairs,
and duplicate/overlapping faces (a common decimate-COLLAPSE artifact and a
likely source of "non-manifold edges that don't make sense" -- an edge with
3+ linked faces often means two near-identical faces stacked on each other,
not a real branch in the surface).

Read-only. Prints one table, one master per row, plus a per-master detail dump.

Run:  blender --background --python scripts/audit_masters.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import (ANTHEMION_MASTER, CAPITAL_MASTER, LEAFSCROLL_MASTER,   # noqa: E402
                   LION_MASTER, LION_MASTER_OBJECT, CAPITAL_MASTER_OBJECT,
                   LEAFSCROLL_MASTER_OBJECT, ANTHEMION_MASTER)

MASTERS = [
    ("capital", CAPITAL_MASTER, CAPITAL_MASTER_OBJECT),
    ("leafscroll", LEAFSCROLL_MASTER, LEAFSCROLL_MASTER_OBJECT),
    ("lion", LION_MASTER, LION_MASTER_OBJECT),
    ("anthemion", ANTHEMION_MASTER, None),  # object name unknown, take the mesh
]


def log(*a):
    print("[audit-masters]", *a)
    sys.stdout.flush()


def dup_faces(bm):
    """Faces sharing the same vertex set as another face (stacked geometry)."""
    seen = {}
    dup = 0
    for f in bm.faces:
        key = frozenset(v.index for v in f.verts)
        if key in seen:
            dup += 1
        else:
            seen[key] = f.index
    return dup


def stats(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    loose = (sum(1 for e in bm.edges if not e.link_faces)
             + sum(1 for v in bm.verts if not v.link_edges))
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-12)
    flipped = sum(1 for e in bm.edges if len(e.link_faces) == 2
                  and e.link_faces[0].normal.dot(e.link_faces[1].normal) < -0.999)
    duplicate = dup_faces(bm)
    res = {"verts": len(bm.verts), "faces": len(bm.faces),
           "boundary": boundary, "nonmanifold": nonmanifold,
           "loose": loose, "degenerate": degenerate, "flipped": flipped,
           "duplicate": duplicate}
    bm.free()
    return res


def main():
    log(f"{'master':12s} {'faces':>8s} {'bound':>7s} {'nonmf':>6s} "
        f"{'loose':>6s} {'degen':>6s} {'flip':>6s} {'dup':>6s}")
    log("-" * 74)
    for tag, path, objname in MASTERS:
        if not os.path.exists(path):
            log(f"{tag:12s}  MISSING {path}")
            continue
        bpy.ops.wm.open_mainfile(filepath=path)
        if objname and objname in bpy.data.objects:
            ob = bpy.data.objects[objname]
        else:
            ob = next(o for o in bpy.data.objects if o.type == "MESH")
        s = stats(ob.data)
        log(f"{tag:12s} {s['faces']:8d} {s['boundary']:7d} {s['nonmanifold']:6d} "
            f"{s['loose']:6d} {s['degenerate']:6d} {s['flipped']:6d} {s['duplicate']:6d}")


if __name__ == "__main__":
    main()
