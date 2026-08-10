"""Build a new lion mask master from donors/lion.glb, mirrored from one half.

Replaces LEEDS_LION_MASK_MASTER as the frieze's lion. The donor is a Tripo mesh
whose head is *posed* 5 degrees off-axis inside the mesh as well as sculpted
slightly asymmetrically (see verify_new_lion.py for the measurement). Mirroring
across the bounding-box centreline would therefore produce a twisted mask, so
this script re-derives the true mirror plane, rotates the mesh onto it, and only
then cuts and mirrors.

Half choice: the user's-left half (world -Y when viewed head-on), chosen by the
user. Note for the record that the rendered comparison in
renders/lion-new-symmetry/ read the other way -- the right half is the crisper
sculpt -- so if the frieze reads soft in the muzzle later, HALF_KEEP is the knob.

Output conventions are copied from LEEDS_LION_MASK_MASTER so the master is a
drop-in for prep_lion() in integrate_cornice_frieze_v1.py:

    front (snout) -> -Y      back (flat mounting plane) -> +Y max
    up            -> +Z      width                     -> X
    shade smooth, provenance in custom properties

Shared donor hygiene (import, measured weld, decimate, provenance, clean
single-object save) lives in donor_prep.py. What stays here is the part that is
only correct for a symmetric wall relief: fitting the mirror plane, cutting one
half away, and mirroring it back. A radial 3D element such as the Corinthian
capital must not be put through that.

The weld runs immediately after import, before the bisect and above all before
the decimate. Doing it the other way round -- which is how the first two masters
were built -- tears the donor's glTF shading seams open into real gaps; see
donor_prep.py's docstring for the measurements.

Read-only with respect to donors/. Writes masters/Tripo-lion-mask-master-v2.blend
(a clean file containing only the master, unlike the Leeds one which carries a
whole stale temple along with it) plus preview renders.

Run:  blender --background --python scripts/build_tripo_lion_master.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json                                                     # noqa: E402
import math                                                     # noqa: E402

import bmesh                                                    # noqa: E402
import bpy                                                      # noqa: E402
from mathutils import Matrix, Vector                            # noqa: E402

import donor_prep                                               # noqa: E402
from donor_prep import bounds, import_donor                     # noqa: E402
from paths import DONORS, MASTERS, RENDERS                      # noqa: E402
from verify_new_lion import (canonical_transform,                # noqa: E402
                             find_symmetry_plane)

DONOR = os.path.join(DONORS, "lion.glb")

# -v2 rather than overwriting the original: deleting or destroying a
# masters/*.blend needs explicit approval, and keeping both side by side is what
# makes the weld fix reviewable (same object name, so swapping is a one-line
# change in paths.py -- see LION_MASTER_TRIPO there).
OUT_BLEND = os.path.join(MASTERS, "Tripo-lion-mask-master-v2.blend")
OUT_RENDER = os.path.join(RENDERS, "tripo-lion-master-v2")
MASTER_NAME = "TRIPO_LION_MASK_MASTER"

# -1 keeps the viewer's-left half (world -Y), +1 the viewer's-right half.
HALF_KEEP = -1

# Leeds master, for convention and proportion comparison.
LEEDS_SIZE = Vector((0.19469, 0.14405, 0.19072))   # width x depth x height
LEEDS_BACK_Y = 0.01999
LEEDS_BOTTOM_Z = 0.13203

# The donor carries ~1.49M tris; ten copies of that in the ring is pointless
# weight. Leeds sits at 60k. This one gets more, because the extra surface
# detail is the entire reason for the swap.
TARGET_TRIS = 100000

# Seam treatment: the mirror weld leaves a faint ridge down the forehead
# centreline. Smooth only vertices within this fraction of the width of y = 0.
SEAM_BAND = 0.004
SEAM_ITERS = 3


def log(*a):
    print("[lion-master]", *a)
    sys.stdout.flush()


def apply_modifier(ob, name):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=name)


def mirror_half(ob):  # noqa: D401 -- shape-specific: only valid for a symmetric relief
    """Cut away one side of y = 0 and mirror the survivor back across it."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.bisect_plane(
        bm,
        geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
        plane_co=Vector((0.0, 0.0, 0.0)),
        plane_no=Vector((0.0, 1.0, 0.0)),
        clear_outer=(HALF_KEEP < 0),
        clear_inner=(HALF_KEEP > 0),
    )
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    m = ob.modifiers.new("MIRROR", "MIRROR")
    m.use_axis = (False, True, False)
    m.use_mirror_merge = True
    m.merge_threshold = 1e-4
    apply_modifier(ob, "MIRROR")
    ob.data.calc_loop_triangles()
    log(f"mirrored: {len(ob.data.vertices)} verts, {len(ob.data.loop_triangles)} tris")


def smooth_seam(ob, width):
    """Relax the weld ridge without touching the rest of the sculpt.

    Restricted to a narrow band either side of y = 0 -- a global smooth would
    cost exactly the crispness the new donor was chosen for.
    """
    band = SEAM_BAND * width
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    seam = [v for v in bm.verts if abs(v.co.y) <= band]
    for _ in range(SEAM_ITERS):
        bmesh.ops.smooth_vert(bm, verts=seam, factor=0.5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    log(f"smoothed {len(seam)} seam verts within +-{band:.5f} of y=0")


def to_master_frame(ob):
    """Canonical frame (front +X, width Y, up Z) -> master frame (front -Y,
    width X, up Z). That is a -90 degree rotation about Z: (x, y, z) -> (y, -x, z),
    determinant +1, so it rotates rather than mirrors.
    """
    ob.data.transform(Matrix.Rotation(math.radians(-90.0), 4, "Z"))
    ob.data.update()


def normalise_to_leeds_placement(ob):
    """Match the Leeds master's overall height and its origin-relative seating.

    Only the height and the aspect ratio actually reach the frieze --
    prep_lion() re-scales by height and re-centres -- but keeping the same
    placement means a side-by-side diff of the two masters is meaningful.
    x is centred on 0 here rather than copying Leeds' small leftover offset,
    since this mask is symmetric by construction.
    """
    lo, hi = bounds(ob)
    size = hi - lo
    k = LEEDS_SIZE.z / size.z
    ob.data.transform(Matrix.Scale(k, 4))
    ob.data.update()

    lo, hi = bounds(ob)
    ob.data.transform(Matrix.Translation(Vector((
        -(lo.x + hi.x) / 2.0,
        LEEDS_BACK_Y - hi.y,
        LEEDS_BOTTOM_Z - lo.z,
    ))))
    ob.data.update()
    return bounds(ob)


def setup_render(size, ctr):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 900
    sc.render.resolution_y = 900
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(size) * 1.12
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

    # Front is -Y now, so a head-on camera sits on -Y and the symmetric key
    # pair straddles the x = 0 plane.
    sun(2.2, 55.0, -30.0)
    sun(2.2, 55.0, 30.0)
    sun(0.9, 12.0, 0.0)
    return cam


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    ob = import_donor(DONOR, name="LION_DONOR")

    # Weld FIRST -- before the bisect, the mirror and above all the decimate.
    # The donor is glTF vertex-split (36,974 boundary edges out of nothing but
    # shading seams); decimating that topology collapses each side of every
    # seam independently and tears the zero-width cracks open into real gaps.
    # See donor_prep's module docstring for the measurements.
    weld_rel = donor_prep.weld(ob)

    lo, hi = bounds(ob)
    sym = find_symmetry_plane(ob, lo, hi)
    log(f"mirror plane: yaw={sym['yaw_deg']:.2f} deg roll={sym['roll_deg']:.2f} deg "
        f"residual={sym['residual']:.5f} (naive {sym['naive_residual']:.5f})")

    ob.data.transform(canonical_transform(sym))
    ob.data.update()

    mirror_half(ob)
    donor_prep.report(ob, "mirrored")
    lo, hi = bounds(ob)
    smooth_seam(ob, (hi - lo).y)
    donor_prep.decimate(ob, TARGET_TRIS)
    to_master_frame(ob)
    lo, hi = normalise_to_leeds_placement(ob)
    size = hi - lo

    ob.rotation_mode = "XYZ"
    donor_prep.shade_smooth(ob)

    # Provenance confirmed by the project owner: every file in donors/ is their
    # own work, this lion included. No third-party license applies to it, unlike
    # the Leeds mask it replaces (CC BY 4.0). donor_prep supplies those license
    # defaults; only the lion-specific fields are named here.
    donor_prep.stamp_provenance(
        ob,
        source_asset="Lion mask, original work by the project owner (donors/lion.glb)",
        derivation=(
            f"welded at {weld_rel:.0e}*diag, symmetry plane fitted "
            f"(yaw {sym['yaw_deg']:.2f} deg), mesh rotated onto it, "
            f"{'left' if HALF_KEEP < 0 else 'right'} half kept and mirrored, "
            f"seam relaxed, decimated to ~{TARGET_TRIS} tris, shade smooth"),
        mirror_half="viewer-left (-Y)" if HALF_KEEP < 0 else "viewer-right (+Y)",
        weld_rel_diag=weld_rel,
    )
    tris = ob["triangle_count"]
    final = donor_prep.report(ob, "MASTER")

    log(f"master size  w {size.x:.5f}  d {size.y:.5f}  h {size.z:.5f}   ({tris} tris)")
    log(f"leeds  size  w {LEEDS_SIZE.x:.5f}  d {LEEDS_SIZE.y:.5f}  h {LEEDS_SIZE.z:.5f}")
    log(f"aspect  new w/h {size.x / size.z:.4f}  d/h {size.y / size.z:.4f}")
    log(f"aspect  leeds w/h {LEEDS_SIZE.x / LEEDS_SIZE.z:.4f}  "
        f"d/h {LEEDS_SIZE.y / LEEDS_SIZE.z:.4f}")

    ctr = (lo + hi) / 2.0
    cam = setup_render(size, ctr)
    dist = max(size) * 3.0

    def shot(name, yaw_deg, pitch_deg):
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        # Camera sits at ctr - dist * view_direction, where the direction for
        # euler (90-pitch, 0, yaw) is (-sin yaw cos pitch, cos yaw cos pitch,
        # -sin pitch). Getting the x sign wrong points the camera away from the
        # subject at any non-zero yaw and renders an empty frame.
        cam.location = (ctr.x + dist * math.sin(yaw) * math.cos(pitch),
                        ctr.y - dist * math.cos(yaw) * math.cos(pitch),
                        ctr.z + dist * math.sin(pitch))
        cam.rotation_euler = (math.radians(90.0) - pitch, 0.0, yaw)
        bpy.context.scene.render.filepath = os.path.join(OUT_RENDER, name)
        bpy.ops.render.render(write_still=True)
        log("WROTE", name)

    shot("master_front.png", 0, 0)
    shot("master_threequarter.png", 34, 16)
    shot("master_frombelow.png", 0, -28)
    shot("master_profile.png", 90, 0)

    # Renders are done, so the camera and lights can go: save_master strips the
    # file down to the master object alone.
    donor_prep.save_master(ob, OUT_BLEND, MASTER_NAME)

    with open(os.path.join(OUT_RENDER, "master_report.json"), "w") as f:
        json.dump({
            "master": MASTER_NAME,
            "blend": OUT_BLEND,
            "half_kept": ob["mirror_half"],
            "symmetry": sym,
            "weld_rel_diag": weld_rel,
            "size": [size.x, size.y, size.z],
            "leeds_size": [LEEDS_SIZE.x, LEEDS_SIZE.y, LEEDS_SIZE.z],
            "triangles": tris,
            "integrity": final,
        }, f, indent=2)


if __name__ == "__main__":
    main()
