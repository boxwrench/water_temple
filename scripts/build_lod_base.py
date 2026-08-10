"""Repair the model into a clean base for the resolution tiers.

This is step one of producing lower-resolution copies for other uses (game,
real-time). It does NO decimation. It exists because decimating a broken mesh
makes it worse -- the same weld-before-decimate rule the glTF donors taught,
applied to the whole model rather than to one donor.

Why it works on mesh datablocks, not objects
--------------------------------------------
The model is built from linked duplicates. Measured: 419 objects share 356
unique meshes, and seven instanced datablocks carry 98.7% of all faces --

    CORINTHIAN_CAPITAL_MASTER   249,999 x 10 = 2,499,990   29.6%
    LEAFSCROLL_MASTER.002       200,000 x 10 = 2,000,000   23.6%
    LEAFSCROLL_MASTER.001       200,000 x 10 = 2,000,000   23.6%
    TRIPO_LION_MASK_MASTER       99,960 x 10 =   999,600   11.8%
    ANTHEMION_PLAQUE_MASTER      80,000 x 10 =   800,000    9.5%

So repairing (and later decimating) the datablocks does the work once and it
lands on every instance. Touching objects instead would either repeat the work
tenfold or, if the meshes were made single-user first, multiply the model's
memory by ten.

The repair, in order
--------------------
1. **Weld** -- merge coincident vertices. Measured per mesh against a no-weld
   baseline exactly as donor_prep.weld does, because welding is not always an
   improvement and blanket-welding damages meshes that are already stitched.
2. **Dissolve degenerate** -- zero-area faces and zero-length edges, which
   decimation turns into pinch artefacts.
3. **Delete loose** geometry -- verts and edges attached to no face.
4. **Recalculate normals** outward, which is what fixes inverted-normal pairs.

Order matters twice over:

* Welding first is what lets everything after it see a connected surface.
  Recalculating normals before welding would compute them across cracks.
* Dissolving degenerate faces BEFORE deleting loose geometry, not after.
  Collapsing a degenerate face strands the verts and edges that bounded it, so
  cleaning loose geometry first removes some and then manufactures more. The
  first run of this script had these two the other way round and took the model
  from 148 loose to 1,108. See the inline note in repair().

Reports per-mesh and whole-model integrity before and after. Read-only with
respect to temple-model/; writes lod/.

Run:  blender --background --python scripts/build_lod_base.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import LOD, chain_blend, lod_blend                     # noqa: E402

SOURCE = chain_blend("frieze-ring-v6")
OUT = lod_blend("base")

# Weld thresholds to trial, as a fraction of each mesh's bounding-box diagonal.
# The range reaches further than donor_prep's because this is repairing
# procedurally-built geometry, not a glTF export: its cracks are not exactly
# coincident duplicates and need a real tolerance to close. 3e-4 of the diagonal
# is 0.03% of the object -- far below any feature these meshes carry.
WELD_CANDIDATES = (1e-7, 1e-6, 1e-5, 3e-5, 1e-4, 3e-4)

# A mesh smaller than this is left alone: the repair costs more than it can
# possibly return, and tiny procedural pieces are already clean.
MIN_FACES = 64


def log(*a):
    print("[lod-base]", *a)
    sys.stdout.flush()


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
    res = {"verts": len(bm.verts), "faces": len(bm.faces),
           "boundary": boundary, "nonmanifold": nonmanifold,
           "loose": loose, "degenerate": degenerate, "flipped": flipped}
    bm.free()
    res["score"] = boundary + nonmanifold + loose + degenerate + flipped
    return res


def diagonal(me):
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in me.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    return (hi - lo).length


def best_weld(me, diag):
    """The weld distance that most improves this mesh, or 0.0 for none.

    Trials each candidate on a throwaway bmesh and scores boundary +
    non-manifold. A mesh that is already stitched scores best un-welded and is
    left alone -- blanket welding such a mesh actively damages it.
    """
    base = stats(me)
    best_rel, best_score = 0.0, base["boundary"] + base["nonmanifold"]
    for rel in WELD_CANDIDATES:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=diag * rel)
        b = sum(1 for e in bm.edges if len(e.link_faces) == 1)
        nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        bm.free()
        if b + nm < best_score:
            best_rel, best_score = rel, b + nm
    return best_rel


def repair(me):
    diag = diagonal(me)
    rel = best_weld(me, diag)

    bm = bmesh.new()
    bm.from_mesh(me)
    if rel:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=diag * rel)
    # Degenerate faces become pinch artefacts once collapsed.
    bmesh.ops.dissolve_degenerate(bm, dist=diag * 1e-6, edges=bm.edges[:])
    # Strip loose geometry AFTER dissolving, not before: collapsing a degenerate
    # face strands the verts and edges that bounded it, so cleaning first leaves
    # more loose geometry behind than it removed. The first run of this script
    # did exactly that and took the model from 148 loose to 1,108.
    loose = [v for v in bm.verts if not v.link_faces]
    loose += [e for e in bm.edges if not e.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        stranded = [e for e in bm.edges if not e.link_faces]
        if stranded:
            bmesh.ops.delete(bm, geom=stranded, context="EDGES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    me.update()
    return rel


def main():
    os.makedirs(LOD, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=SOURCE)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    log(f"source {os.path.basename(SOURCE)}")

    used = {}
    for o in bpy.data.objects:
        if o.type == "MESH":
            used[o.data.name] = used.get(o.data.name, 0) + 1

    targets = [me for me in bpy.data.meshes
               if me.name in used and len(me.polygons) >= MIN_FACES]
    log(f"{len(used)} unique meshes in use, {len(targets)} above {MIN_FACES} faces")

    def totals():
        agg = {k: 0 for k in ("faces", "boundary", "nonmanifold",
                              "loose", "degenerate", "flipped")}
        for me in bpy.data.meshes:
            if me.name not in used:
                continue
            s = stats(me)
            n = used[me.name]
            for k in agg:
                agg[k] += s[k] * n
        return agg

    before = totals()
    log("")
    log(f"{'mesh':36s} {'uses':>5s} {'faces':>8s} {'weld':>8s} "
        f"{'bound':>8s} {'nonmf':>7s} {'degen':>6s} {'flip':>6s}")
    log("-" * 96)

    report = []
    for me in sorted(targets, key=lambda m: -len(m.polygons) * used[m.name]):
        n = used[me.name]
        b4 = stats(me)
        rel = repair(me)
        af = stats(me)
        report.append({"mesh": me.name, "uses": n, "weld_rel": rel,
                       "before": b4, "after": af})
        if b4["score"] != af["score"] or len(targets) <= 12:
            log(f"{me.name[:36]:36s} {n:5d} {af['faces']:8d} "
                f"{(f'{rel:.0e}' if rel else '-'):>8s} "
                f"{b4['boundary']:>4d}->{af['boundary']:<3d} "
                f"{b4['nonmanifold']:>3d}->{af['nonmanifold']:<3d} "
                f"{b4['degenerate']:>3d}->{af['degenerate']:<2d} "
                f"{b4['flipped']:>3d}->{af['flipped']:<2d}")

    after = totals()
    log("")
    log(f"{'whole model':22s} {'before':>12s} {'after':>12s} {'change':>12s}")
    log("-" * 62)
    for k in ("faces", "boundary", "nonmanifold", "loose", "degenerate", "flipped"):
        d = after[k] - before[k]
        log(f"{k:22s} {before[k]:12,d} {after[k]:12,d} {d:+12,d}")

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    log("")
    log("SAVED " + OUT)

    with open(os.path.join(LOD, "lod-base-report.json"), "w") as f:
        json.dump({"source": SOURCE, "out": OUT,
                   "before": before, "after": after,
                   "meshes": report}, f, indent=2)


if __name__ == "__main__":
    main()
