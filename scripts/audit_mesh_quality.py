"""Audit mesh integrity of a frieze .blend -- the things a render will not show.

A picture only proves the visible surface looks right. It says nothing about
non-manifold edges, degenerate faces, loose geometry, duplicate vertices or
inverted normals, all of which survive rendering happily and then bite on
export, boolean operations, 3D print slicing, or any later mesh edit.

Reports per object and as a total, worst offenders first. Read-only.

Run:  blender --background --python scripts/audit_mesh_quality.py -- <blend> [name-filter]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                    # noqa: E402
import bpy                                                      # noqa: E402

from paths import TEMPLE_MODEL                                  # noqa: E402

AREA_EPS = 1e-12      # a face below this is degenerate, not merely small
EDGE_EPS = 1e-9
DOUBLE_DIST = 1e-6


def log(*a):
    print("[audit]", *a)
    sys.stdout.flush()


def args():
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    if not rest:
        raise SystemExit("usage: -- <blend> [name-filter]")
    blend = rest[0] if os.path.isabs(rest[0]) else os.path.join(TEMPLE_MODEL, rest[0])
    return blend, (rest[1] if len(rest) > 1 else None)


def audit(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # An edge with exactly 2 faces is manifold. 1 means a boundary (a hole in a
    # solid); 3+ means surfaces meeting in a way no solid can.
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    loose_edges = sum(1 for e in bm.edges if len(e.link_faces) == 0)
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < AREA_EPS)
    zero_edges = sum(1 for e in bm.edges if e.calc_length() < EDGE_EPS)

    doubles = bmesh.ops.find_doubles(bm, verts=bm.verts[:], dist=DOUBLE_DIST)
    n_doubles = len(doubles["targetmap"])

    # Consistent winding: neighbouring faces should agree on which side is out.
    flipped = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            a, b = e.link_faces
            if a.normal.dot(b.normal) < -0.999:
                flipped += 1

    res = {
        "verts": len(bm.verts), "faces": len(bm.faces),
        "boundary": boundary, "nonmanifold": nonmanifold,
        "loose_edges": loose_edges, "loose_verts": loose_verts,
        "degenerate": degenerate, "zero_edges": zero_edges,
        "doubles": n_doubles, "flipped": flipped,
    }
    bm.free()
    res["watertight"] = (boundary == 0 and nonmanifold == 0)
    res["problems"] = (boundary + nonmanifold + loose_edges + loose_verts
                       + degenerate + zero_edges + n_doubles + flipped)
    return res


def main():
    blend, name_filter = args()
    bpy.ops.wm.open_mainfile(filepath=blend)
    log(f"auditing {os.path.basename(blend)}"
        + (f"  filter={name_filter!r}" if name_filter else ""))

    rows = []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        if name_filter and name_filter not in ob.name:
            continue
        rows.append((ob.name, audit(ob)))

    if not rows:
        log("no matching mesh objects")
        return

    rows.sort(key=lambda r: -r[1]["problems"])
    hdr = (f"{'object':44s} {'verts':>7s} {'faces':>7s} {'bound':>6s} {'nonmf':>6s} "
           f"{'degen':>6s} {'0-edge':>6s} {'dbl':>5s} {'loose':>6s} {'flip':>5s}  tight")
    log(hdr)
    log("-" * len(hdr))
    for name, r in rows[:30]:
        log(f"{name[:44]:44s} {r['verts']:7d} {r['faces']:7d} {r['boundary']:6d} "
            f"{r['nonmanifold']:6d} {r['degenerate']:6d} {r['zero_edges']:6d} "
            f"{r['doubles']:5d} {r['loose_edges'] + r['loose_verts']:6d} "
            f"{r['flipped']:5d}  {'yes' if r['watertight'] else 'NO'}")
    if len(rows) > 30:
        log(f"... {len(rows) - 30} more objects with fewer problems")

    tot = {k: sum(r[k] for _, r in rows)
           for k in ("verts", "faces", "boundary", "nonmanifold", "degenerate",
                     "zero_edges", "doubles", "loose_edges", "loose_verts", "flipped")}
    clean = sum(1 for _, r in rows if r["problems"] == 0)
    tight = sum(1 for _, r in rows if r["watertight"])
    log("")
    log(f"TOTAL {len(rows)} objects, {tot['verts']} verts, {tot['faces']} faces")
    log(f"  fully clean:        {clean}/{len(rows)}")
    log(f"  watertight solids:  {tight}/{len(rows)}")
    log(f"  boundary edges (holes):   {tot['boundary']}")
    log(f"  non-manifold edges:       {tot['nonmanifold']}")
    log(f"  degenerate faces:         {tot['degenerate']}")
    log(f"  zero-length edges:        {tot['zero_edges']}")
    log(f"  duplicate verts:          {tot['doubles']}")
    log(f"  loose edges/verts:        {tot['loose_edges']}/{tot['loose_verts']}")
    log(f"  inverted-normal pairs:    {tot['flipped']}")


if __name__ == "__main__":
    main()
