"""Easy-pass repair on each approved master, at the source, not just downstream.

scripts/audit_masters.py found real, fixable damage sitting in the masters
themselves -- not just in the whole-model lod/base copy build_lod_base.py
already cleans up on every run:

    master        faces    bound  nonmf  loose  degen  flip   dup
    capital      249999      300    129      2     62   652   166
    leafscroll   200000       52     52      0      0     2     0
    lion          99960      246    251      0      0     0     0
    anthemion     80000    26206      0      0      0     1     0

The anthemion number is the important one. build_lod_base.py's own history
records that a *narrow* weld search (1e-7..1e-6*diag, right for glTF-split
donors) only recovered 17% of this plaque's holes, and a *wide* search
(up to 3e-4*diag) recovered 95% (26,206 -> 1,246). That fix was applied to the
lod/base throwaway copy and never carried back into
masters/anthemion-plaque-master-v2.blend -- so every future build off the
master still starts from the broken 26,206-boundary mesh. This is the same
lesson donor_prep already teaches (weld before decimate), just not yet
applied where it actually pays off.

The pass, in the same order build_lod_base.py validated at whole-model scale:

1. **Weld**, trialled (never assumed) against the widened candidate list --
   a mesh that already scores best un-welded (the capital, per its own build
   script's docstring) is left alone.
2. **Remove duplicate faces** -- exact-same-vertex-set faces stacked on each
   other. Not a weld concern (the verts are already coincident, not distinct);
   found on the capital (166) and nowhere else. Each duplicate is a second
   face sealing an edge that one face already seals, which is exactly what
   pushes an edge's face count from 2 to 3+ and reads as "non-manifold" even
   though the surface itself is not branching.
3. **Dissolve degenerate** faces (zero area) and **delete loose** geometry,
   loose after degenerate for the reason recorded in build_lod_base.py.
4. **Recalculate normals** outward and consistent.

Never overwrites an approved master. Writes a new versioned file next to it
and leaves paths.py untouched -- swapping in the repaired version is a
one-line change for later, after this has been inspected.

Run:  blender --background --python scripts/repair_masters.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

from paths import (ANTHEMION_MASTER, CAPITAL_MASTER, CAPITAL_MASTER_OBJECT,   # noqa: E402
                   LEAFSCROLL_MASTER, LEAFSCROLL_MASTER_OBJECT, LION_MASTER,
                   LION_MASTER_OBJECT, MASTERS, RENDERS)

# Same wide range build_lod_base.py needed for procedurally-cracked geometry --
# see its docstring for why 1e-7..1e-6 (donor-glTF sized) was not enough.
WELD_CANDIDATES = (1e-7, 1e-6, 1e-5, 3e-5, 1e-4, 3e-4)

JOBS = [
    # tag, in-path, object name (None = the file's only mesh), out-path, out-object-name
    ("capital", CAPITAL_MASTER, CAPITAL_MASTER_OBJECT,
     os.path.join(MASTERS, "corinthian-capital-master-v2.blend"), CAPITAL_MASTER_OBJECT),
    ("leafscroll", LEAFSCROLL_MASTER, LEAFSCROLL_MASTER_OBJECT,
     os.path.join(MASTERS, "leafscroll-master-v2.blend"), LEAFSCROLL_MASTER_OBJECT),
    ("lion", LION_MASTER, LION_MASTER_OBJECT,
     os.path.join(MASTERS, "Tripo-lion-mask-master-v3.blend"), LION_MASTER_OBJECT),
    ("anthemion", ANTHEMION_MASTER, "ANTHEMION_PLAQUE_MASTER",
     os.path.join(MASTERS, "anthemion-plaque-master-v3.blend"), "ANTHEMION_PLAQUE_MASTER"),
]

OUT_RENDER = os.path.join(RENDERS, "master-repair-pass")


def log(*a):
    print("[repair-masters]", *a)
    sys.stdout.flush()


def stats(bm):
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    loose = (sum(1 for e in bm.edges if not e.link_faces)
             + sum(1 for v in bm.verts if not v.link_edges))
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-12)
    flipped = sum(1 for e in bm.edges if len(e.link_faces) == 2
                  and e.link_faces[0].normal.dot(e.link_faces[1].normal) < -0.999)
    seen, dup = set(), 0
    for f in bm.faces:
        key = frozenset(v.index for v in f.verts)
        if key in seen:
            dup += 1
        else:
            seen.add(key)
    return {"verts": len(bm.verts), "faces": len(bm.faces),
           "boundary": boundary, "nonmanifold": nonmanifold, "loose": loose,
           "degenerate": degenerate, "flipped": flipped, "duplicate": dup,
           "score": boundary + nonmanifold + loose + degenerate + flipped + dup}


def diagonal(me):
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in me.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    return (hi - lo).length


def best_weld(me, diag):
    bm = bmesh.new()
    bm.from_mesh(me)
    base = stats(bm)
    bm.free()
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
    # remove_doubles leaves vert .index stale (elements were freed/merged);
    # the dedup pass below keys on .index, so it must be refreshed first or it
    # groups faces by leftover, possibly-duplicate index values instead of by
    # actual shared vertices.
    bm.verts.index_update()

    # Duplicate (stacked, same-vertex-set) faces -- not a weld concern.
    seen, dupfaces = {}, []
    for f in bm.faces:
        key = frozenset(v.index for v in f.verts)
        if key in seen:
            dupfaces.append(f)
        else:
            seen[key] = f
    if dupfaces:
        bmesh.ops.delete(bm, geom=dupfaces, context="FACES")

    bmesh.ops.dissolve_degenerate(bm, dist=diag * 1e-6, edges=bm.edges[:])
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


def render_one(ob, out_dir, tag):
    os.makedirs(out_dir, exist_ok=True)
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    ctr = (lo + hi) / 2.0
    size = (hi - lo).length

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 900
    sc.render.resolution_y = 900
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.31, 0.34, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45

    for e, p, y in ((2.6, 42.0, -35.0), (1.6, 42.0, 35.0), (0.8, 10.0, 180.0)):
        li = bpy.data.lights.new("s", "SUN")
        li.energy = e
        o = bpy.data.objects.new("s", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(p), 0.0, math.radians(y))

    clay = bpy.data.materials.new("CLAY")
    clay.use_nodes = True
    clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.80
    ob.data.materials.clear()
    ob.data.materials.append(clay)
    for p in ob.data.polygons:
        p.use_smooth = True

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size * 1.05
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(name, yaw_deg, pitch_deg):
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        d = size * 2.2
        cam.location = ctr + Vector((-d * math.sin(yaw) * math.cos(pitch),
                                     d * math.cos(yaw) * math.cos(pitch),
                                     d * math.sin(pitch)))
        cam.rotation_euler = (ctr - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out_dir, f"{tag}_{name}.png")
        bpy.ops.render.render(write_still=True)
        log("WROTE " + os.path.basename(sc.render.filepath))

    shot("front", 0, 10)
    shot("threequarter", 40, 20)


def main():
    report = []
    log(f"{'master':12s} {'stage':9s} {'faces':>8s} {'bound':>7s} {'nonmf':>6s} "
        f"{'loose':>6s} {'degen':>6s} {'flip':>6s} {'dup':>6s}")
    log("-" * 78)

    for tag, in_path, objname, out_path, out_objname in JOBS:
        bpy.ops.wm.open_mainfile(filepath=in_path)
        ob = bpy.data.objects[objname] if objname in bpy.data.objects else \
            next(o for o in bpy.data.objects if o.type == "MESH")

        bm = bmesh.new()
        bm.from_mesh(ob.data)
        before = stats(bm)
        bm.free()
        log(f"{tag:12s} {'before':9s} {before['faces']:8d} {before['boundary']:7d} "
            f"{before['nonmanifold']:6d} {before['loose']:6d} {before['degenerate']:6d} "
            f"{before['flipped']:6d} {before['duplicate']:6d}")

        weld_rel = repair(ob.data)

        bm = bmesh.new()
        bm.from_mesh(ob.data)
        after = stats(bm)
        bm.free()
        log(f"{tag:12s} {'after':9s} {after['faces']:8d} {after['boundary']:7d} "
            f"{after['nonmanifold']:6d} {after['loose']:6d} {after['degenerate']:6d} "
            f"{after['flipped']:6d} {after['duplicate']:6d}"
            f"{'  weld ' + f'{weld_rel:.0e}*diag' if weld_rel else ''}")

        if after["score"] > before["score"]:
            log(f"{tag:12s} WARNING: score got worse ({before['score']} -> "
                f"{after['score']}) -- not saving, investigate before retrying")
            continue

        # Keep only this object in the output file, matching donor_prep.save_master.
        for other in list(bpy.data.objects):
            if other is not ob:
                bpy.data.objects.remove(other, do_unlink=True)
        ob.name = out_objname
        ob.data.name = out_objname
        os.makedirs(MASTERS, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out_path)
        log(f"{tag:12s} SAVED {out_path}")

        render_one(ob, OUT_RENDER, tag)

        report.append({"master": tag, "in": in_path, "out": out_path,
                       "weld_rel_diag": weld_rel, "before": before, "after": after})

    with open(os.path.join(OUT_RENDER, "repair_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    log("")
    log("WROTE " + os.path.join(OUT_RENDER, "repair_report.json"))
    log("")
    log("Nothing in masters.py or paths.py changed -- these are new files sitting")
    log("next to the approved ones. Swapping one in is a one-line paths.py change,")
    log("once you've inspected the renders and numbers above.")


if __name__ == "__main__":
    main()
