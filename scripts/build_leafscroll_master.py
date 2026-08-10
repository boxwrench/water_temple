"""Build a leaf-scroll master from donors/leafscroll.glb.

The scroll is the only frieze element that never had a master: the frieze script
imports the raw donor twice per module and the ring ends up carrying twenty
copies of 1,424,782 faces -- about 93% of the whole model's face count, for the
smallest ornament on the building. It also carries the donor's 45,910 glTF
split-seam boundary edges into every one of those copies.

Two things this fixes, in the order that matters:

  1. weld, then decimate (donor_prep.weld / donor_prep.decimate). Reversing
     those two tears the split seams open into real gaps -- the defect baked
     into the first two lion masters.
  2. one shared, reviewed level of detail instead of twenty raw imports.

**Frame: deliberately the donor's own.** Every other master is normalised into a
canonical frame, but the scroll's placement is already approved geometry:
orient_leafscroll() in integrate_cornice_frieze_v1.py rotates, scales, re-anchors
and mirrors it, and those steps were tuned against the reference photo. Handing
that function a re-framed mesh would silently move approved work. So the master
keeps the donor's axes exactly, and the only thing that changes downstream is
mesh density. `orient_leafscroll()` needs no edit at all.

Detail budget: the scroll is fine leafwork and may not take the same 100k cut the
lion did, so this renders a sweep of candidate budgets side by side for review
before committing. Set SWEEP_ONLY = True to render the sweep without writing a
master.

Run:  blender --background --python scripts/build_leafscroll_master.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Vector                                      # noqa: E402

import donor_prep                                                 # noqa: E402
from donor_prep import bounds, import_donor                       # noqa: E402
from paths import DONORS, MASTERS, RENDERS                        # noqa: E402

DONOR = os.path.join(DONORS, "leafscroll.glb")
OUT_BLEND = os.path.join(MASTERS, "leafscroll-master.blend")
OUT_RENDER = os.path.join(RENDERS, "leafscroll-master")
MASTER_NAME = "LEAFSCROLL_MASTER"

# Candidate budgets to render for review. The lion took 100k comfortably, but it
# is a broad-form mask; the scroll's value is in thin, deeply undercut leaf
# edges, which are exactly what COLLAPSE decimation eats first.
SWEEP_TRIS = [400000, 200000, 100000, 60000]
CHOSEN_TRIS = 200000
SWEEP_ONLY = False

RES = 1100


def log(*a):
    print("[scroll-master]", *a)
    sys.stdout.flush()


def setup_scene():
    """Ortho camera looking down -X at the scroll's carved face.

    The donor's face is +X in its own frame: orient_leafscroll() rotates +90 deg
    about Z, which maps (x, y, z) -> (-y, x, z), carrying +X onto +Y -- and +Y is
    the outward face once the element is seated on the drum.
    """
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    clay = bpy.data.materials.new("CLAY")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.80

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # A raking key is the point here: decimation damage to leaf edges shows up
    # as a change in the shadow line long before it shows in flat lighting.
    def sun(energy, pitch, yaw):
        li = bpy.data.lights.new("sun", "SUN")
        li.energy = energy
        o = bpy.data.objects.new("sun", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
        return o

    sun(3.2, 32.0, 118.0)
    sun(1.0, 60.0, 60.0)
    return cam, clay


def aim(cam, ctr, size, zoom=1.0, pitch_deg=0.0):
    pitch = math.radians(pitch_deg)
    dist = max(size) * 3.0
    cam.data.ortho_scale = max(size) * 1.08 * zoom
    cam.location = (ctr.x + dist * math.cos(pitch), ctr.y, ctr.z + dist * math.sin(pitch))
    cam.rotation_euler = (math.radians(90.0) - pitch, 0.0, math.radians(90.0))


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    ob = import_donor(DONOR, name="LEAFSCROLL_DONOR")
    weld_rel = donor_prep.weld(ob)
    welded = ob.data.copy()          # the common starting point for every budget

    lo, hi = bounds(ob)
    size = hi - lo
    ctr = (lo + hi) / 2.0
    log(f"welded donor size {size.x:.4f} x {size.y:.4f} x {size.z:.4f}")

    cam, clay = setup_scene()
    ob.data.materials.clear()
    ob.data.materials.append(clay)
    donor_prep.shade_smooth(ob)

    def render(tag):
        for zoom, pitch, suffix in ((1.0, 0.0, "full"), (0.34, 0.0, "detail"),
                                    (0.55, 34.0, "raking")):
            aim(cam, ctr, size, zoom=zoom, pitch_deg=pitch)
            bpy.context.scene.render.filepath = os.path.join(
                OUT_RENDER, f"{tag}_{suffix}")
            bpy.ops.render.render(write_still=True)
        log(f"WROTE {tag}_(full|detail|raking).png")

    results = {}
    ob.data.calc_loop_triangles()
    results["welded_raw"] = {"tris": len(ob.data.loop_triangles),
                             **donor_prep.integrity(ob.data)}
    render("00_welded_raw")

    for target in SWEEP_TRIS:
        m = welded.copy()
        old = ob.data
        ob.data = m
        if old is not welded:
            bpy.data.meshes.remove(old)
        ob.data.materials.clear()
        ob.data.materials.append(clay)
        donor_prep.decimate(ob, target)
        donor_prep.shade_smooth(ob)
        ob.data.calc_loop_triangles()
        results[f"tris_{target}"] = {"tris": len(ob.data.loop_triangles),
                                     **donor_prep.integrity(ob.data)}
        render(f"{target:07d}")

    log("")
    log(f"{'budget':>14s} {'tris':>9s} {'boundary':>9s} {'nonmf':>7s}")
    for k, r in results.items():
        log(f"{k:>14s} {r['tris']:9d} {r['boundary']:9d} {r['nonmanifold']:7d}")

    with open(os.path.join(OUT_RENDER, "sweep.json"), "w") as f:
        json.dump({"donor": DONOR, "weld_rel_diag": weld_rel,
                   "chosen_tris": CHOSEN_TRIS, "sweep": results}, f, indent=2)

    if SWEEP_ONLY:
        log("SWEEP_ONLY -- no master written")
        return

    # Rebuild at the chosen budget from the welded original rather than reusing
    # whichever sweep entry happened to be last: decimating an already-decimated
    # mesh is not the same operation as decimating the original once.
    old = ob.data
    ob.data = welded.copy()
    bpy.data.meshes.remove(old)
    donor_prep.decimate(ob, CHOSEN_TRIS)
    donor_prep.shade_smooth(ob)
    ob.data.materials.clear()

    donor_prep.stamp_provenance(
        ob,
        source_asset="Leaf scroll, original work by the project owner (donors/leafscroll.glb)",
        derivation=(f"welded at {weld_rel:.0e}*diag, decimated to ~{CHOSEN_TRIS} tris, "
                    f"shade smooth; donor axes preserved so orient_leafscroll() in "
                    f"integrate_cornice_frieze_v1.py applies unchanged"),
        weld_rel_diag=weld_rel,
        frame="donor axes as imported (face +X, length +Y, up +Z)",
    )
    final = donor_prep.report(ob, "MASTER")
    donor_prep.save_master(ob, OUT_BLEND, MASTER_NAME)

    with open(os.path.join(OUT_RENDER, "master_report.json"), "w") as f:
        json.dump({"master": MASTER_NAME, "blend": OUT_BLEND,
                   "chosen_tris": CHOSEN_TRIS, "weld_rel_diag": weld_rel,
                   "size": [size.x, size.y, size.z],
                   "integrity": final}, f, indent=2)


if __name__ == "__main__":
    main()
