"""Real cylindrical integration: lion + anthemion + leaf-scroll + existing
shelf molding, seated on the actual temple cornice for one 36-degree module.

Supersedes the flat rough-assembly test (build_cornice_assembly_study.py,
approved proportions/orientation) and the old v1 lion-only integration.
Also removes the superseded egg-block ANTHEMION/RINCEAUX procedural objects
that were still sitting in cornice-with-lion.blend -- but KEEPS the
LEAF-AND-TONGUE molding objects there, which are the shelf's decorative
band the user asked to reuse rather than rebuild.

Never touches cornice-with-lion.blend: opens it, immediately saves to a new
file, and does all edits there.

Architecturally fixed (do not vary by tuning): lion-to-lion spacing 36 deg,
lion-to-anthemion offset 18 deg, both lions and the anthemion sit at those
exact angles so the repeat stays aligned with the ten column axes. Only the
leaf-scroll's placement within each 18-degree gap is a tunable fit choice.

The lion master is loaded through LION_MASTER (masters/Leeds-lion-mask-
master.blend) via a plain append-and-normalize step with no assumptions
baked in beyond its own bounding box -- swapping in a replacement lion
master later is a one-line path change, nothing else in this script
depends on this particular mesh.

Run:  blender --background --python integrate_cornice_frieze_v1.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
from mathutils import Vector, Matrix

from paths import (ANTHEMION_MASTER, LION_MASTER, LION_MASTER_OBJECT,
                    LION_MASTER_LEEDS_OBJECT, LEAFSCROLL_MASTER,
                    LEAFSCROLL_MASTER_OBJECT, DONORS, TEMPLE_MODEL,
                    CHAIN_BASE, RENDERS, FRIEZE_SCALE, ANTHEMION_SCALE,
                    chain_blend, chain_render)  # noqa: E402

LEAFSCROLL_DONOR = os.path.join(DONORS, "leafscroll.glb")

# Output names carry the active lion master's tag (see paths.chain_blend), so
# building with a different lion cannot silently overwrite the checkpoint built
# with the other one.
OUT_BLEND = chain_blend("frieze-v1")
OUT_RENDER = chain_render("cornice-frieze-v1")

# --- fixed architectural constants (from integrate_lion_v1.py / build_refined_cornice_master.py) ---
CY = -0.5456366539001465
RMAP = 0.300
LION_ANGLE = math.atan2(0.0756035098, 0.2408188273)
MODULE_ARC = RMAP * math.radians(36.0)
PU = RMAP * math.radians(18.0)   # anthemion offset from the lion, arc-length
SLOT_R_BACK = 0.2921             # backing radius, matches the existing molding/lion seating
Z_BASELINE = 0.3172              # top of the existing LEAF-AND-TONGUE upper fillet -- the
                                  # shelf surface every element's bottom now shares

# --- real-world target sizes, anchored to the already-seated lion's real height
#     (grounded in the measured placeholder slot, not a free parameter), then the
#     proportions tuned against the gridded reference photo ---
#
# The internal ratios below are the approved proportions and should not be
# touched. FRIEZE_SCALE / ANTHEMION_SCALE (in paths.py) resize the whole set
# without disturbing those ratios; see the note there for why the angular layout
# does not scale with them.
LION_HEIGHT_REAL = 0.0498 * FRIEZE_SCALE
SCROLL_HEIGHT_REAL = LION_HEIGHT_REAL / 1.10
ANTHEMION_HEIGHT_REAL = SCROLL_HEIGHT_REAL * 1.35 * 1.2 * ANTHEMION_SCALE
ANTH_Y_FRONT_REAL = 0.105 * SCROLL_HEIGHT_REAL   # same fraction as the flat study

# The structure's actual top -- the surface the ring's top edge must stay clear
# of. Used only to report headroom, nothing is clamped to it.
STRUCTURE_Z_TOP = 0.395

# How far each scroll SLIDES toward the anthemion, as a fraction of the scroll's
# own length. The two scrolls are mirror images seated either side of the
# anthemion, so this is one symmetric number, not a left and a right -- the pair
# moves as one about the anthemion.
#
# Quoted against the scroll's own length rather than against the 18-degree gap
# because it describes something about the scroll (how much of it slides out of
# the lion and under the anthemion) rather than about the bay. The anthemion is
# seated at a larger radius than the scroll, so it genuinely sits proud and the
# scroll passes behind it.
#
# Measured at 0.00 the scroll sits 27.3% behind the lion and only 2.2% under the
# anthemion; angular_report() prints those percentages on every build.
#
# This is the one placement in the frieze that is a free fit choice rather than
# architecture -- the lion and anthemion angles are locked to the column axes.
SCROLL_TUCK_FRAC = 0.05

# The approved starting placement it slides from: the scroll centred in its
# 18-degree gap, then offset by this fraction of PU toward the lion.
SCROLL_GAP_OFFSET_FRAC = -0.15


def log(*a):
    print("[frieze-v1]", *a)
    sys.stdout.flush()


def world_bounds(ob):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for c in ob.bound_box:
        w = ob.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return lo, hi


def apply_transforms(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.select_set(False)


def append(blend_path, obj_name, new_name):
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = [obj_name]
    ob = bpy.data.objects[obj_name]
    if ob.name != new_name:
        ob.name = new_name
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_mode = "XYZ"
    return ob


_scroll_source = []


def import_leafscroll():
    """A fresh, independently-editable copy of the leaf-scroll master.

    Was a raw re-import of donors/leafscroll.glb on every call, which meant the
    finished ring carried twenty copies of 1,424,782 faces -- about 93% of the
    whole model -- and twenty copies of the donor's 45,910 glTF split-seam holes.
    Now it appends masters/leafscroll-master.blend once (welded, then decimated
    to ~200k, 52 boundary edges) and copies it thereafter.

    The master deliberately preserves the donor's own axes, so orient_leafscroll()
    below is unchanged and the approved placement is untouched. The only thing
    that differs is mesh density.

    Each call returns a copy with its own mesh datablock, because the callers
    edit the geometry independently (SCROLL_R gets mirrored). Linked duplicates
    would make that edit apply to both.
    """
    if not _scroll_source:
        _scroll_source.append(
            append(LEAFSCROLL_MASTER, LEAFSCROLL_MASTER_OBJECT, "SCROLL_SOURCE"))
        _scroll_source[0].hide_render = True

    src = _scroll_source[0]
    ob = src.copy()
    ob.data = src.data.copy()
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_mode = "XYZ"
    ob.hide_render = False
    return ob


def orient_leafscroll(ob):
    """Same recipe as the flat study: length -> world X, face -> +Y, height -> Z,
    normalized to SCROLL_HEIGHT_REAL, back plane at y=0, bottom at z=0, then the
    approved flip so the spiral end faces the anthemion and the blank-mass end
    faces the lion.
    """
    ob.rotation_euler = (0, 0, math.radians(90.0))
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    k = SCROLL_HEIGHT_REAL / (hi.z - lo.z)
    ob.scale = (k, k, k)
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y, -lo.z)
    apply_transforms(ob)

    ob.scale = (-1.0, 1.0, 1.0)
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    log(f"leafscroll normalised  size {(hi - lo).x:.4f} x {(hi - lo).y:.4f} x {(hi - lo).z:.4f}")
    return ob


def prep_lion(ob):
    ob.rotation_euler = (0, 0, math.radians(180.0))  # snout -Y -> +Y, faces camera/viewer
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    k = LION_HEIGHT_REAL / (hi.z - lo.z)
    ob.scale = (k, k, k)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y, -lo.z)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    log(f"lion normalised  size {(hi - lo).x:.4f} x {(hi - lo).y:.4f} x {(hi - lo).z:.4f}")
    return ob


def prep_anthemion(ob):
    lo, hi = world_bounds(ob)
    k = ANTHEMION_HEIGHT_REAL / (hi.z - lo.z)
    ob.scale = (k, k, k)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y, -lo.z)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    log(f"anthemion normalised  size {(hi - lo).x:.4f} x {(hi - lo).y:.4f} x {(hi - lo).z:.4f}")
    return ob


def map_point(u, r, z):
    theta = LION_ANGLE + u / RMAP
    return Vector((r * math.cos(theta), CY + r * math.sin(theta), z))


def seat_rigid(ob, u_center, r_target, z_target=Z_BASELINE):
    """Rigidly rotate+place an already-normalized object (local origin = its
    own bottom/back/center anchor point) onto the cylinder at arc-length
    u_center, radius r_target, height z_target. Same recipe as
    integrate_lion_v1.py's lion seating, generalized to any prepared element.
    """
    theta = LION_ANGLE + u_center / RMAP
    radial = Vector((math.cos(theta), math.sin(theta), 0.0))
    tangent = Vector((-math.sin(theta), math.cos(theta), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    # (tangent, radial, up) as columns is a LEFT-handed frame (det -1, a
    # reflection, not a rotation) -- confirmed the hard way: it silently
    # mirrors geometry instead of rotating it, which happened to be hard to
    # spot on the near-symmetric lion but was obvious as a backwards-facing
    # anthemion. (tangent, -radial, up) is the proper rotation (det +1),
    # exactly integrate_lion_v1.py's matrix -- it expects local -Y as front.
    # Every element here (lion post-flip, anthemion, scroll) is normalized to
    # local +Y = front instead, so compose one extra 180-about-Z to match.
    rot_proper = Matrix((
        (tangent.x, -radial.x, up.x),
        (tangent.y, -radial.y, up.y),
        (tangent.z, -radial.z, up.z),
    ))
    rot = rot_proper @ Matrix.Rotation(math.pi, 3, 'Z')
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = rot.to_euler()
    ob.location = map_point(u_center, r_target, z_target)
    ob["cornice_master_component"] = True
    # Record the arc position actually used. propagate_cornice_frieze_ring.py
    # reads this back off the object rather than re-deriving it from the same
    # constants, so the placement has exactly one source: the seating call.
    ob["u_center"] = u_center
    ob["r_target"] = r_target
    bpy.context.view_layer.update()


def remove_superseded_egg_block():
    """Delete the old egg-block ANTHEMION/RINCEAUX objects and the old v1 lion
    placement -- all superseded by this pass. Keep LEAF-AND-TONGUE (the shelf's
    decorative molding, reused as-is) and everything else untouched.
    """
    doomed_prefixes = ("ANTHEMION ", "RINCEAUX ", "LION mane")
    # The source file always carries the old Leeds placement, and may carry a
    # previous run's lion of whichever master is current -- clear both.
    doomed_names = {LION_MASTER_LEEDS_OBJECT, LION_MASTER_OBJECT}
    removed = []
    for ob in list(bpy.data.objects):
        if ob.name.startswith(doomed_prefixes) or ob.name in doomed_names:
            removed.append(ob.name)
            data = ob.data if ob.type == "MESH" else None
            bpy.data.objects.remove(ob, do_unlink=True)
            if data and data.users == 0:
                bpy.data.meshes.remove(data)
    log(f"removed {len(removed)} superseded objects")


def clay(ob):
    ob.data.materials.clear()
    m = bpy.data.materials.new(ob.name + "_CLAY")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.80
    ob.data.materials.append(m)


def setup_render(center, dist):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1400
    sc.render.resolution_y = 900
    sc.render.image_settings.file_format = "PNG"

    for w_ in list(bpy.data.worlds):
        pass
    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    cam_data = bpy.data.cameras.new("FRIEZE_CAM")
    cam = bpy.data.objects.new("FRIEZE_CAM", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    key = bpy.data.lights.new("FRIEZE_KEY", "SUN")
    key.energy = 3.5
    keyob = bpy.data.objects.new("FRIEZE_KEY", key)
    sc.collection.objects.link(keyob)
    fill = bpy.data.lights.new("FRIEZE_FILL", "SUN")
    fill.energy = 1.0
    fillob = bpy.data.objects.new("FRIEZE_FILL", fill)
    sc.collection.objects.link(fillob)
    fillob.rotation_euler = (math.radians(35.0), 0.0, math.radians(150.0))
    return cam, keyob, fillob


def shot(cam, keyob, path, yaw_deg, pitch_deg, dist, center, key_yaw=-150.0, key_pitch=45.0):
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    cam.data.type = "PERSP"
    cam.data.lens = 50
    cam.location = center + Vector((
        -dist * math.sin(yaw) * math.cos(pitch),
        dist * math.cos(yaw) * math.cos(pitch),
        dist * math.sin(pitch)))
    direction = (center - cam.location).normalized()
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    keyob.rotation_euler = (math.radians(key_pitch), 0.0, math.radians(key_yaw))
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("WROTE", os.path.basename(path))


def angular_report(objs):
    """Angular footprint of each seated element, and how much of each scroll is
    hidden behind its neighbours.

    This is what turns the scroll placement into a checkable number instead of a
    squint at a render: it says exactly how many degrees of scroll are under the
    anthemion, how many under the lion, and how many read clear.
    """
    spans = {}
    for ob in objs:
        ths = [math.atan2((ob.matrix_world @ v.co).y - CY,
                          (ob.matrix_world @ v.co).x) for v in ob.data.vertices]
        # Unwrap about the circular mean before min/max -- atan2 wraps at +-pi
        # and an element straddling the seam would report a ~360 degree span.
        mx = sum(math.cos(t) for t in ths) / len(ths)
        my = sum(math.sin(t) for t in ths) / len(ths)
        ctr = math.atan2(my, mx)
        unw = [(t - ctr + math.pi) % (2 * math.pi) - math.pi for t in ths]
        spans[ob.name] = (math.degrees(ctr + min(unw)), math.degrees(ctr + max(unw)))

    log("angular footprints (deg about the colonnade axis):")
    for name, (a, b) in sorted(spans.items(), key=lambda kv: kv[1][0]):
        log(f"   {name:12s} {a:8.3f} .. {b:8.3f}   width {b - a:6.3f}")

    def overlap(a, b):
        return max(0.0, min(spans[a][1], spans[b][1]) - max(spans[a][0], spans[b][0]))

    for scroll, lion in (("SCROLL_L", "LION_L"), ("SCROLL_R", "LION_R")):
        if not {scroll, lion, "ANTHEMION_C"} <= spans.keys():
            continue
        w = spans[scroll][1] - spans[scroll][0]
        o_l, o_a = overlap(scroll, lion), overlap(scroll, "ANTHEMION_C")
        log(f"   {scroll}: under {lion} {o_l:.3f} deg ({o_l / w * 100:4.1f}%), "
            f"under ANTHEMION_C {o_a:.3f} deg ({o_a / w * 100:4.1f}%), "
            f"clear {w - o_l - o_a:.3f} deg ({(w - o_l - o_a) / w * 100:4.1f}%)")
    return spans


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)

    # CHAIN_BASE, not CORNICE_WITH_LION: the capital swap runs upstream of the
    # chain and produces its own base file. See paths.CHAIN_BASE.
    bpy.ops.wm.open_mainfile(filepath=CHAIN_BASE)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    remove_superseded_egg_block()

    lion_l = prep_lion(append(LION_MASTER, LION_MASTER_OBJECT, "LION_L"))
    seat_rigid(lion_l, 0.0, SLOT_R_BACK)

    lion_r = prep_lion(append(LION_MASTER, LION_MASTER_OBJECT, "LION_R"))
    seat_rigid(lion_r, MODULE_ARC, SLOT_R_BACK)

    anth = prep_anthemion(append(ANTHEMION_MASTER, "ANTHEMION_PLAQUE_MASTER", "ANTHEMION_C"))
    seat_rigid(anth, PU, SLOT_R_BACK + ANTH_Y_FRONT_REAL)

    scroll_l = orient_leafscroll(import_leafscroll())
    scroll_l.name = "SCROLL_L"

    scroll_r = orient_leafscroll(import_leafscroll())
    scroll_r.name = "SCROLL_R"
    scroll_r.scale = (-1.0, 1.0, 1.0)
    apply_transforms(scroll_r)

    # Both scrolls slide the same distance toward the anthemion. They are mirror
    # images of each other, so "left" and "right" is the wrong frame -- the pair
    # is symmetric about the anthemion and moves as one. The scroll's own local
    # x is tangential once seated, so its x extent IS its arc length and the
    # slide can be quoted as a fraction of it.
    slo, shi = world_bounds(scroll_l)
    scroll_len = (shi - slo).x
    tuck = SCROLL_TUCK_FRAC * scroll_len
    base = PU / 2.0 + SCROLL_GAP_OFFSET_FRAC * PU
    log(f"scroll length {scroll_len:.5f}; tuck {SCROLL_TUCK_FRAC:.3f} of it "
        f"= {tuck:.5f} toward the anthemion, from base offset {base:.5f}")

    seat_rigid(scroll_l, base + tuck, SLOT_R_BACK)
    seat_rigid(scroll_r, MODULE_ARC - base - tuck, SLOT_R_BACK)

    # The appended scroll source was only a template to copy from; leaving it in
    # the file would ship an unplaced 200k-face object into the whole chain.
    for src in _scroll_source:
        data = src.data
        bpy.data.objects.remove(src, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    _scroll_source.clear()

    new_row = [lion_l, lion_r, anth, scroll_l, scroll_r]
    for ob in new_row:
        clay(ob)

    angular_report(new_row)

    for u, name in [(0.0, "LION_L"), (PU, "ANTHEMION_C"), (MODULE_ARC, "LION_R")]:
        log(f"{name:12s} fixed at u={u:.4f}  theta={math.degrees(LION_ANGLE + u / RMAP):.3f} deg")

    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for ob in new_row:
        blo, bhi = world_bounds(ob)
        for i in range(3):
            lo[i] = min(lo[i], blo[i])
            hi[i] = max(hi[i], bhi[i])
    center = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, (lo.z + hi.z) / 2.0))
    span = (hi - lo).length
    log(f"module extents  size {tuple(round(c,4) for c in (hi-lo))}  center {tuple(round(c,4) for c in center)}")

    # Headroom is what the scale knobs are actually for: the ring is seated
    # bottom-down on Z_BASELINE, so the only thing that can crowd the structure's
    # top is the tallest element's height. Report per element, tallest first.
    log(f"scale  FRIEZE_SCALE={FRIEZE_SCALE:.3f}  ANTHEMION_SCALE={ANTHEMION_SCALE:.3f}")
    tops = sorted(((world_bounds(ob)[1].z, ob.name) for ob in new_row), reverse=True)
    for top_z, name in tops:
        log(f"   {name:12s} top z={top_z:.4f}   headroom to structure top "
            f"({STRUCTURE_Z_TOP}) = {STRUCTURE_Z_TOP - top_z:+.4f}")

    cam, keyob, fillob = setup_render(center, span)
    shot(cam, keyob, os.path.join(OUT_RENDER, "module-front.png"), 0, 8, span * 1.6, center)
    shot(cam, keyob, os.path.join(OUT_RENDER, "module-threequarter.png"), 35, 18, span * 1.7, center)
    shot(cam, keyob, os.path.join(OUT_RENDER, "module-frombelow.png"), 10, -20, span * 1.6, center)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


if __name__ == "__main__":
    main()
