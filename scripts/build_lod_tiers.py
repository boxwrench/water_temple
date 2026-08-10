"""Decimate the repaired base into resolution tiers.

Runs after build_lod_base.py and never before it: decimating unrepaired geometry
tears cracks open instead of collapsing them, which is the whole reason the
repair is a separate step.

Every tier is decimated **from the base**, never from the tier above it.
Decimating an already-decimated mesh is a different operation from decimating
the original once, and the error compounds down the chain.

Budgeting
---------
Because 98.7% of the model is seven instanced datablocks, a tier's cost is
dominated by `faces x users` on a handful of meshes. So the ratio is solved for
the whole-model target rather than applied blindly per mesh:

    target = fixed_faces + ratio * sum(faces * users for decimatable meshes)

Meshes below KEEP_FACES are excluded and counted as fixed. They are the
building's own structure -- drum, architrave, meander, cap stones, well braid --
which is only 1.3% of the model but carries its entire silhouette. Decimating
those buys almost nothing and costs the shape.

Naming
------
Output files are named after the *measured* triangle count, not the nominal
target above (paths.lod_tri_blend / triangle_label) -- e.g. lod570k, lod7.4m.
The old lod1/lod2/lod3 names promised a reduction the solver did not always
deliver: the "working" 50,000-face target still lands near 90-100k once
KEEP_FACES-protected structure is added back in, so a file called lod3 was
lying about its own size. A name built from the real post-decimation count
cannot.

Run:  blender --background --python scripts/build_lod_tiers.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import LOD, lod_blend, lod_tri_blend                   # noqa: E402

BASE = lod_blend("structure")

# Whole-model face targets, used only to steer the decimation solver -- the
# output filename is the *measured* triangle count after the fact (see
# lod_tri_blend), not this nominal target, because the solver's actual yield
# routinely lands well off the target (KEEP_FACES-protected structure alone is
# 45,028 faces, so the "working" tier can never reach anywhere near 50,000).
# A file called lod3 promised a reduction it did not deliver; a file called by
# its real count cannot lie. The tags below are just labels for the log.
TIERS = [
    ("hero",     500_000),   # hero prop / close-up
    ("standard", 150_000),   # standard in-scene
    ("working",   50_000),   # the working target
]

# Ceiling on the "leave it alone" threshold. The threshold itself is per tier
# (see keep_threshold): protecting a fixed 2,000 faces meant 45,028 faces of
# structure were exempt, which is MORE than the 40k and 12k targets -- so those
# tiers could not be solved at all and came out identical to each other.
KEEP_FACES = 2000

# If plain collapse lands more than this multiple above the mesh's share of the
# budget, it has floored and the mesh gets remeshed instead. See remesh_then_
# decimate() for why collapse floors at all.
FLOOR_TOLERANCE = 1.35

# Voxel remesh is enabled again, but ONLY because it can no longer reach the
# structure. build_lod_structure.py rebuilds every structural piece as a lathe
# first, leaving them all under KEEP_FACES and therefore untouchable here. What
# remains above the threshold is ornament -- organic, undercut, exactly what a
# remesh suits -- so the tool now only sees the geometry it is right for.
#
# The history that matters: run against the raw model it hit every target
# beautifully and produced
# perfectly manifold output -- lod1's boundary edges fell from 10,706 to 466 --
# and it destroys the building. A remesh rebuilds a surface from a distance
# field, which suits organic blobs and ruins flat plates, thin shells, sharp
# arrises and fluting. The 0.02-thick architrave fragments at any voxel coarse
# enough to matter; the fluted shafts shred; the capitals melt.
#
# Left in the code because it is the right tool for a purely organic asset, and
# because the failure is worth not rediscovering. Collapse decimation preserves
# shape and is what tiers are built with.
REMESH_ENABLED = True

# Voxel size search bounds, as a fraction of the mesh's bounding-box diagonal.
VOXEL_LO, VOXEL_HI = 0.002, 0.120
VOXEL_STEPS = 7


def log(*a):
    print("[lod-tiers]", *a)
    sys.stdout.flush()


def integrity(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    b = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.free()
    return b, nm


def triangles(me):
    """Real triangle count, not polygon count -- an ngon is loop_total - 2
    triangles once rendered/exported, and Decimate's output is not purely
    triangulated, so faces and triangles diverge enough to matter for a
    filename meant to promise a GPU/export budget.
    """
    return sum(p.loop_total - 2 for p in me.polygons)


def usage():
    used = {}
    for o in bpy.data.objects:
        if o.type == "MESH":
            used[o.data.name] = used.get(o.data.name, 0) + 1
    return used


def keep_threshold(target):
    """Below how many faces a mesh is left alone.

    Fixed, not scaled to the target. Scaling it down for the small tiers does
    let the solver reach the number, but it reaches it by decimating the
    building's own structure -- and the structure is the silhouette. A shredded
    architrave at 40,000 faces is worth less than an intact one at 300,000.
    The 45,028 faces of structure are 0.5% of the model; they are not the
    problem and must not be spent.
    """
    return KEEP_FACES


def solve_ratio(used, target, keep):
    """Ratio to apply to the decimatable meshes so the model lands on target."""
    fixed = 0
    variable = 0
    for me in bpy.data.meshes:
        n = used.get(me.name)
        if not n:
            continue
        f = len(me.polygons)
        if f <= keep:
            fixed += f * n
        else:
            variable += f * n
    if variable <= 0:
        return 1.0, fixed, variable
    ratio = (target - fixed) / variable
    return max(0.0008, min(1.0, ratio)), fixed, variable


def decimate_shared(scratch, me, ratio, objs):
    """Collapse-decimate a datablock that ten objects share, keeping them shared.

    `modifier_apply` refuses multi-user data outright, so the mesh cannot be
    decimated in place while its instances point at it. Instead: copy it (the
    copy has one user, the scratch object), decimate the copy, then repoint every
    instance at the result and drop the original.

    Doing it the obvious way -- making each object single-user first -- would
    decimate the same geometry ten times and multiply the file's memory by ten.
    """
    new = me.copy()
    scratch.data = new
    bpy.ops.object.select_all(action="DESELECT")
    scratch.select_set(True)
    bpy.context.view_layer.objects.active = scratch

    m = scratch.modifiers.new("DEC", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = ratio
    bpy.ops.object.modifier_apply(modifier="DEC")

    result = scratch.data
    for o in objs:
        o.data = result
    return result


def mesh_diagonal(me):
    lo = [1e18] * 3
    hi = [-1e18] * 3
    for v in me.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    return sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5


def _voxel_try(scratch, src, voxel, mats):
    """Voxel-remesh a copy of `src` at `voxel` and return the resulting mesh."""
    new = src.copy()
    scratch.data = new
    bpy.ops.object.select_all(action="DESELECT")
    scratch.select_set(True)
    bpy.context.view_layer.objects.active = scratch
    new.remesh_voxel_size = voxel
    new.remesh_voxel_adaptivity = 0.0
    try:
        bpy.ops.object.voxel_remesh()
    except RuntimeError:
        # The remesher refuses a voxel too coarse for the mesh's thickness --
        # a thin shell simply falls between samples and nothing is produced.
        # Report it as "no faces" so the search moves to a finer voxel.
        return None
    out = scratch.data
    # Voxel remesh discards material slots; put them back or the tier renders
    # at Blender's default near-white, which reads as a geometry fault.
    out.materials.clear()
    for m in mats:
        out.materials.append(m)
    return out


def remesh_then_decimate(scratch, src, target, objs):
    """Rebuild topology, then decimate -- for meshes collapse cannot reduce.

    Collapse decimation refuses any edge whose removal would create non-manifold
    geometry. The Corinthian capital's deeply undercut acanthus has many touching
    leaves, so it floors at ~24,000 faces at ANY ratio: measured 24,366 at 0.01,
    23,818 after three passes, and 42,739 (worse) after a heavy weld, because
    welding fuses still more junctions.

    A voxel remesh sidesteps this entirely by discarding the input topology and
    rebuilding a clean manifold shell from a distance field. That shell then
    decimates freely. Fine detail is lost -- which is the intent at a distant
    tier, and the reason this is not used on the high ones.

    Voxel size is bisected against the face count rather than guessed, aiming
    above target so the final collapse can land exactly.
    """
    diag = mesh_diagonal(src)
    mats = [m for m in src.materials]
    aim = target * 2.5

    lo, hi = VOXEL_LO, VOXEL_HI
    best = None
    for _ in range(VOXEL_STEPS):
        mid = (lo + hi) / 2.0
        out = _voxel_try(scratch, src, diag * mid, mats)
        n = 0 if out is None else len(out.polygons)
        if n:
            best = (mid, n)
        # Smaller voxels -> more faces. A failure counts as "too few".
        if n > aim:
            lo = mid
        else:
            hi = mid
        if n and 0.8 * aim <= n <= 1.25 * aim:
            break

    if best is None:
        # Nothing the remesher could do with this mesh -- the caller keeps
        # whatever collapse managed.
        return None, None, 0

    voxel, n = best
    if len(scratch.data.polygons) != n:
        # The last trial was not the best one; rebuild at the size that worked.
        _voxel_try(scratch, src, diag * voxel, mats)
    result = scratch.data
    if n > target:
        m = scratch.modifiers.new("DEC", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = max(0.002, target / n)
        bpy.ops.object.modifier_apply(modifier="DEC")
        result = scratch.data
    for o in objs:
        o.data = result
    return result, voxel, n


def build_tier(tag, target):
    bpy.ops.wm.open_mainfile(filepath=BASE)
    used = usage()
    keep = keep_threshold(target)
    ratio, fixed, variable = solve_ratio(used, target, keep)

    log("")
    log(f"=== {tag}: target {target:,} faces")
    log(f"    protected (<= {keep} f): {fixed:,} faces across the structure")
    log(f"    decimatable: {variable:,} faces  ->  ratio {ratio:.5f}")

    # One scratch object, reused, so applying the modifier never disturbs the
    # real objects or their transforms.
    scratch = bpy.data.objects.new("LOD_SCRATCH", bpy.data.meshes.new("scratch"))
    bpy.context.scene.collection.objects.link(scratch)

    # Snapshot the work list before touching anything -- the loop adds and
    # removes datablocks, so iterating bpy.data.meshes live would be unsafe.
    work = []
    for me in bpy.data.meshes:
        n = used.get(me.name)
        if n and len(me.polygons) > keep:
            objs = [o for o in bpy.data.objects
                    if o.type == "MESH" and o.data is me]
            work.append((len(me.polygons), me, objs))
    work.sort(key=lambda t: -t[0])

    rows = []
    for before, me, objs in work:
        name = me.name
        share = max(12, int(before * ratio))
        new = decimate_shared(scratch, me, ratio, objs)
        after = len(new.polygons)
        how = "collapse"
        voxel = None

        # If collapse floored well above this mesh's share of the budget,
        # rebuild its topology instead of fighting it.
        if REMESH_ENABLED and after > share * FLOOR_TOLERANCE:
            src = me if me.users else new
            new2, voxel, pre = remesh_then_decimate(scratch, src, share, objs)
            if new2 is None:
                log(f"    {name[:34]:34s} collapse floored at {after:,} "
                    f"(share {share:,}); remesh not possible -- keeping collapse")
                for o in objs:
                    o.data = new
            else:
                log(f"    {name[:34]:34s} collapse floored at {after:,} "
                    f"(share {share:,}) -> remesh @ {voxel:.4f} diag, {pre:,} f")
                if new.users == 0:
                    bpy.data.meshes.remove(new)
                new = new2
                after = len(new.polygons)
                how = "remesh"

        if me.users == 0:
            bpy.data.meshes.remove(me)
        new.name = name
        b, nm = integrity(new)
        rows.append({"mesh": name, "uses": len(objs), "before": before,
                     "after": after, "boundary": b, "nonmanifold": nm,
                     "method": how, "voxel": voxel})
        log(f"    {name[:34]:34s} x{len(objs):<3d} {before:8,d} -> {after:7,d}  "
            f"boundary {b:6d}  nonmf {nm:5d}  [{how}]")

    bpy.data.objects.remove(scratch, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)

    used = usage()
    total = sum(len(me.polygons) * used[me.name]
                for me in bpy.data.meshes if me.name in used)
    tris = sum(triangles(me) * used[me.name]
               for me in bpy.data.meshes if me.name in used)
    tb = sum(integrity(me)[0] * used[me.name]
             for me in bpy.data.meshes if me.name in used)
    objs = sum(1 for o in bpy.data.objects if o.type == "MESH")

    out = lod_tri_blend(tris)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    log(f"    RESULT {objs} objects, {total:,} faces / {tris:,} triangles "
        f"({total / target:.2f}x target), {tb:,} boundary edges")
    log(f"    SAVED {os.path.basename(out)}")
    return {"tier": tag, "target": target, "ratio": ratio,
            "faces": total, "triangles": tris, "objects": objs,
            "boundary": tb, "meshes": rows, "out": out}


def main():
    os.makedirs(LOD, exist_ok=True)
    if not os.path.exists(BASE):
        raise SystemExit(f"{BASE} missing -- run build_lod_base.py first")

    results = []
    for tag, target in TIERS:
        results.append(build_tier(tag, target))

    log("")
    log(f"{'tier':>10s} {'target':>12s} {'faces':>12s} {'triangles':>12s} "
        f"{'ratio':>9s} {'boundary':>10s} {'objects':>8s}  file")
    log("-" * 100)
    for r in results:
        log(f"{r['tier']:>10s} {r['target']:12,d} {r['faces']:12,d} "
            f"{r['triangles']:12,d} {r['ratio']:9.5f} {r['boundary']:10,d} "
            f"{r['objects']:8d}  {os.path.basename(r['out'])}")

    with open(os.path.join(LOD, "lod-tiers-report.json"), "w") as f:
        json.dump({"base": BASE, "keep_faces": KEEP_FACES,
                   "tiers": results}, f, indent=2)


if __name__ == "__main__":
    main()
