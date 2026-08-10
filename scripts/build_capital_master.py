"""Build a Corinthian capital master from
donors/corinthian-capital-temple-of-vesta-in-rome.glb.

Shape-specific notes, measured rather than assumed:

* **No mirroring.** The lion is a symmetric wall relief and needs a fitted mirror
  plane; a capital is a radial 3D element with four-fold plan symmetry and must
  not be put through that. Measured on the donor's abacus band, the max-radius
  profile peaks at 45/135/225/315 degrees and troughs at 0/90/180/270, i.e. the
  corners are on the diagonals and the flat faces already point along +-X/+-Y.
  The donor is axis-aligned as delivered; no yaw correction is needed.

* **The weld will decline to run, and that is correct.** Unlike the lion and the
  scroll, this donor is not glTF vertex-split: 381 boundary edges on 2,424,926
  faces, and welding makes it worse at every threshold (780 boundary / 390
  non-manifold at 1e-4*diag). donor_prep.weld() trials the candidates against a
  no-weld baseline and keeps the baseline here. See donor_prep's docstring.

* **Plan centre is the bounding-box centre, not the vertex mean.** The vertex
  mean is biased toward wherever the mesh is densest -- here the abacus, which
  carries a third of the vertices.

Canonical master frame, chosen so the seating script does no shape reasoning:

    up +Z, bottom (bell base) on z = 0, plan centred on x = y = 0,
    height normalised to exactly 1.0, abacus faces along +-X / +-Y

The two widths the seating needs are stamped on the object as custom properties
`bell_base_width` and `abacus_width`, both in that unit-height frame, so
seat_capitals.py can derive its scale factors without re-measuring the mesh.

Run:  blender --background --python scripts/build_capital_master.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                       # noqa: E402
import math                                                       # noqa: E402

import bpy                                                        # noqa: E402
from mathutils import Matrix, Vector                              # noqa: E402

import donor_prep                                                 # noqa: E402
from donor_prep import bounds, import_donor                       # noqa: E402
from paths import DONORS, MASTERS, RENDERS                        # noqa: E402

DONOR = os.path.join(DONORS, "corinthian-capital-temple-of-vesta-in-rome.glb")
OUT_BLEND = os.path.join(MASTERS, "corinthian-capital-master.blend")
OUT_RENDER = os.path.join(RENDERS, "corinthian-capital-master")
MASTER_NAME = "CORINTHIAN_CAPITAL_MASTER"

SWEEP_TRIS = [400000, 250000, 120000]
CHOSEN_TRIS = 250000
SWEEP_ONLY = False

# Bands used to measure the bell base. One thin slice at the very bottom, as a
# fraction of total height -- the bell base is the surface that has to land on
# the shaft top, and it is the widest thing in the lowest few percent.
BASE_BAND = 0.04

RES = 1000


def log(*a):
    print("[capital-master]", *a)
    sys.stdout.flush()


def canonicalise(ob):
    """Centre in plan, drop the bell base onto z = 0, normalise height to 1."""
    lo, hi = bounds(ob)
    h = hi.z - lo.z
    ob.data.transform(Matrix.Translation(Vector((
        -(lo.x + hi.x) / 2.0, -(lo.y + hi.y) / 2.0, -lo.z))))
    ob.data.update()
    ob.data.transform(Matrix.Scale(1.0 / h, 4))
    ob.data.update()
    lo, hi = bounds(ob)
    log(f"canonical: x {lo.x:+.5f}..{hi.x:+.5f}  y {lo.y:+.5f}..{hi.y:+.5f}  "
        f"z {lo.z:+.5f}..{hi.z:+.5f}   (donor height was {h:.5f})")
    return h


def measure_widths(ob):
    """Bell-base and abacus widths across the flat faces (not the diagonals).

    Across-face is what matters: the capital sits on a round shaft and under a
    band whose radial position is measured face-on, so the corner-to-corner
    diagonal would over-report both by a factor of ~sqrt(2).
    """
    lo, hi = bounds(ob)
    verts = [v.co for v in ob.data.vertices]

    base = [v for v in verts if v.z <= lo.z + BASE_BAND]
    top = [v for v in verts if v.z >= hi.z - BASE_BAND]

    def across_face(sel):
        return max(2.0 * max(abs(v.x) for v in sel), 2.0 * max(abs(v.y) for v in sel))

    def diagonal(sel):
        return 2.0 * max(math.hypot(v.x, v.y) for v in sel)

    bell = across_face(base)
    abacus = across_face(top)
    log(f"bell base width  {bell:.5f}  (diagonal {diagonal(base):.5f})")
    log(f"abacus width     {abacus:.5f}  (diagonal {diagonal(top):.5f})")
    log(f"ratios: bell/height {bell:.4f}   abacus/height {abacus:.4f}   "
        f"abacus/bell {abacus / bell:.4f}")
    return bell, abacus


def setup_scene():
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

    def sun(energy, pitch, yaw):
        li = bpy.data.lights.new("sun", "SUN")
        li.energy = energy
        o = bpy.data.objects.new("sun", li)
        sc.collection.objects.link(o)
        o.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
        return o

    sun(2.6, 42.0, -35.0)
    sun(1.6, 42.0, 35.0)
    sun(0.8, 10.0, 180.0)
    return cam, clay


def aim(cam, yaw_deg, pitch_deg, zoom=1.0):
    """Camera on a sphere about (0, 0, 0.5) -- the unit-height capital's middle."""
    ctr = Vector((0.0, 0.0, 0.5))
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    dist = 4.0
    cam.data.ortho_scale = 1.45 * zoom
    cam.location = (ctr.x + dist * math.sin(yaw) * math.cos(pitch),
                    ctr.y - dist * math.cos(yaw) * math.cos(pitch),
                    ctr.z + dist * math.sin(pitch))
    cam.rotation_euler = (math.radians(90.0) - pitch, 0.0, yaw)


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    ob = import_donor(DONOR, name="CAPITAL_DONOR")
    weld_rel = donor_prep.weld(ob)
    donor_height = canonicalise(ob)
    bell, abacus = measure_widths(ob)
    canonical = ob.data.copy()

    cam, clay = setup_scene()
    ob.data.materials.clear()
    ob.data.materials.append(clay)
    donor_prep.shade_smooth(ob)

    def render(tag):
        for yaw, pitch, zoom, suffix in ((0, 4, 1.0, "face"),
                                         (45, 12, 1.0, "corner"),
                                         (0, -22, 0.85, "frombelow"),
                                         (0, 4, 0.40, "detail")):
            aim(cam, yaw, pitch, zoom)
            bpy.context.scene.render.filepath = os.path.join(OUT_RENDER, f"{tag}_{suffix}")
            bpy.ops.render.render(write_still=True)
        log(f"WROTE {tag}_(face|corner|frombelow|detail).png")

    results = {}
    ob.data.calc_loop_triangles()
    results["raw"] = {"tris": len(ob.data.loop_triangles), **donor_prep.integrity(ob.data)}
    render("00_raw")

    for target in SWEEP_TRIS:
        old = ob.data
        ob.data = canonical.copy()
        if old is not canonical:
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

    if SWEEP_ONLY:
        with open(os.path.join(OUT_RENDER, "sweep.json"), "w") as f:
            json.dump(results, f, indent=2)
        log("SWEEP_ONLY -- no master written")
        return

    # Rebuild from the canonical original: decimating an already-decimated mesh
    # is not the same operation as decimating the original once.
    old = ob.data
    ob.data = canonical.copy()
    bpy.data.meshes.remove(old)
    donor_prep.decimate(ob, CHOSEN_TRIS)
    donor_prep.shade_smooth(ob)
    ob.data.materials.clear()

    # Re-measure after decimation: the numbers the seating script uses must
    # describe the mesh that actually ships, not the one before the collapse.
    bell, abacus = measure_widths(ob)

    donor_prep.stamp_provenance(
        ob,
        source_asset=("Corinthian capital after the Temple of Vesta in Rome, "
                      "original work by the project owner "
                      "(donors/corinthian-capital-temple-of-vesta-in-rome.glb)"),
        derivation=(f"weld declined (donor not vertex-split); canonicalised to "
                    f"unit height with bell base on z=0 and plan centred; "
                    f"decimated to ~{CHOSEN_TRIS} tris; shade smooth. "
                    f"Donor height {donor_height:.5f} in its own units."),
        weld_rel_diag=weld_rel,
        frame="unit height, bell base on z=0, plan centred, abacus faces on +-X/+-Y",
        bell_base_width=bell,
        abacus_width=abacus,
        donor_height=donor_height,
    )
    final = donor_prep.report(ob, "MASTER")
    donor_prep.save_master(ob, OUT_BLEND, MASTER_NAME)

    with open(os.path.join(OUT_RENDER, "master_report.json"), "w") as f:
        json.dump({"master": MASTER_NAME, "blend": OUT_BLEND,
                   "chosen_tris": CHOSEN_TRIS, "weld_rel_diag": weld_rel,
                   "bell_base_width": bell, "abacus_width": abacus,
                   "donor_height": donor_height,
                   "sweep": results, "integrity": final}, f, indent=2)


if __name__ == "__main__":
    main()
