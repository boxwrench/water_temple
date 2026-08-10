"""Rough assembly test: lion + anthemion + leaf-scroll laid out flat.

Design: docs/superpowers/specs/2026-08-08-cornice-frieze-rough-assembly-design.md

Flat (non-cylindrical) strip -- curvature is negligible at this scale. Sequence
left to right: lion -> leaf-scroll -> anthemion -> leaf-scroll (mirrored) -> lion,
matching the alternation in reference/pulgas-cornice-photo.png. The leaf-scroll
donor is used raw (no finalize pass) with its blank-mass end tucked behind the
neighboring element. This is a proportion/fit check only -- never touches any
live temple file, writes a fresh isolated study file.

Run:  blender --background --python build_cornice_assembly_study.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
from mathutils import Vector

from paths import (ANTHEMION_MASTER, LION_MASTER, DONORS, TEMPLE_MODEL,
                    RENDERS)  # noqa: E402

LEAFSCROLL_DONOR = os.path.join(DONORS, "leafscroll.glb")
OUT_BLEND = os.path.join(TEMPLE_MODEL, "cornice-assembly-study.blend")
OUT_RENDER = os.path.join(RENDERS, "cornice-assembly-study")

TARGET_HEIGHT = 0.19               # leaf-scroll baseline height
# Ratios measured directly off reference/ChatGPT Image Aug 8, 2026, 06_47_52 AM.png
# (gridded proportion reference): anthemion ~233px, lion ~182px, scroll ~170-190px
# average, all pixel heights on the same photo -- NOT the 15%/200% figures used
# in the previous pass, which were verbal guesses and produced a wildly
# oversized anthemion.
LION_HEIGHT = TARGET_HEIGHT * 1.10        # lion ~10% taller than the leaf-scroll
ANTHEMION_HEIGHT = TARGET_HEIGHT * 1.35 * 1.2   # measured ratio, then a smaller +20%
                                                  # (the +50% pass read too big; pulled back)
ANTH_Y_FRONT = 0.02   # anthemion's back plane pushed slightly forward of the scroll's
GAP_OVERLAP = 0.22     # lion <-> scroll horizontal overlap fraction
ANTH_OVERLAP = 0.30    # scroll <-> anthemion horizontal overlap fraction

SHELF_THICKNESS = 0.045   # the projecting ledge the frieze elements sit on
SHELF_FRONT = 0.03        # how far the shelf's front face projects past y=0
SHELF_MARGIN = 0.05        # shelf extends this far past the row's outer elements


def log(*a):
    print("[assembly]", *a)
    sys.stdout.flush()


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


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


def import_leafscroll():
    bpy.ops.import_scene.gltf(filepath=LEAFSCROLL_DONOR)
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name not in
              {"ANTHEMION_PLAQUE_MASTER", "LEEDS_LION_MASK_MASTER"}]
    ob = meshes[-1]
    ob.rotation_mode = "XYZ"
    return ob


def orient_leafscroll(ob):
    """Donor axes (measured): x = relief depth/face dir, y = horizontal run
    (length), z = height. Rotate +90 about Z so length -> world X, face -> +Y,
    height stays Z. Then normalize height to TARGET_HEIGHT and put the back
    plane at y=0 like the other two masters. A final world-space x-flip
    reverses which end (spiral vs. the blank-mass end) sits toward the lion
    vs. the anthemion -- flipped per user direction, was spiral-to-lion,
    blank-to-anthemion; now spiral-to-anthemion, blank-to-lion.
    """
    ob.rotation_euler = (0, 0, math.radians(90.0))
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    size = hi - lo
    k = TARGET_HEIGHT / size.z
    ob.scale = (k, k, k)
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y, -lo.z)  # bottom (min z) to z=0
    apply_transforms(ob)

    ob.scale = (-1.0, 1.0, 1.0)
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    log(f"leafscroll normalised  size {(hi - lo).x:.4f} x {(hi - lo).y:.4f} x {(hi - lo).z:.4f}")
    return ob


def prep_lion(ob):
    # lion's front is local -Y (snout points -Y); rotate 180 about Z so the
    # snout faces world +Y, toward the camera, matching the other two elements.
    ob.rotation_euler = (0, 0, math.radians(180.0))
    apply_transforms(ob)

    lo, hi = world_bounds(ob)
    size = hi - lo
    k = LION_HEIGHT / size.z
    ob.scale = (k, k, k)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    # after the flip, back plane is now at min y (matches the anthemion convention)
    # bottom (min z) to z=0, so every element shares one baseline plane
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y, -lo.z)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    log(f"lion normalised  size {(hi - lo).x:.4f} x {(hi - lo).y:.4f} x {(hi - lo).z:.4f}")
    return ob


def prep_anthemion(ob):
    lo, hi = world_bounds(ob)
    size = hi - lo
    k = ANTHEMION_HEIGHT / size.z
    ob.scale = (k, k, k)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    # anthemion's front is local +Y, back plane already at y=0; push the whole
    # object forward by ANTH_Y_FRONT so it sits in front of the leaf-scroll.
    # bottom (min z) to z=0, so every element shares one baseline plane
    ob.location = (-(lo.x + hi.x) / 2.0, -lo.y + ANTH_Y_FRONT, -lo.z)
    apply_transforms(ob)
    lo, hi = world_bounds(ob)
    log(f"anthemion normalised  size {(hi - lo).x:.4f} x {(hi - lo).y:.4f} x {(hi - lo).z:.4f}")
    return ob


def place_row():
    """Build lion -> scroll -> anthemion -> scroll(mirrored) -> lion left to right,
    each element's world-space bounding box abutting (with GAP_OVERLAP pull-in)
    the next, all back planes flush at y = 0.
    """
    lion_l = prep_lion(append(LION_MASTER, "LEEDS_LION_MASK_MASTER", "LION_L"))
    scroll_l = orient_leafscroll(import_leafscroll())
    scroll_l.name = "SCROLL_L"
    anth = prep_anthemion(append(ANTHEMION_MASTER, "ANTHEMION_PLAQUE_MASTER", "ANTHEMION_C"))
    scroll_r = orient_leafscroll(import_leafscroll())
    scroll_r.name = "SCROLL_R"
    scroll_r.scale = (-1.0, 1.0, 1.0)  # mirror for the opposite-side pairing
    apply_transforms(scroll_r)
    lion_r = prep_lion(append(LION_MASTER, "LEEDS_LION_MASK_MASTER", "LION_R"))

    row = [lion_l, scroll_l, anth, scroll_r, lion_r]
    cursor = 0.0
    for i, ob in enumerate(row):
        lo, hi = world_bounds(ob)
        half_w = (hi.x - lo.x) / 2.0
        if i == 0:
            cursor = half_w
        else:
            prev_lo, prev_hi = world_bounds(row[i - 1])
            prev_half_w = (prev_hi.x - prev_lo.x) / 2.0
            overlap = ANTH_OVERLAP if "ANTHEMION" in (ob.name + row[i - 1].name) else GAP_OVERLAP
            step = (prev_half_w + half_w) * (1.0 - overlap)
            cursor += step
        ob.location.x += cursor - (world_bounds(ob)[0].x + world_bounds(ob)[1].x) / 2.0
        bpy.context.view_layer.update()
        lo, hi = world_bounds(ob)
        log(f"{ob.name:10s} centered at x={cursor:+.4f}  x-range {lo.x:+.4f}..{hi.x:+.4f}")

    for ob in row:
        ob["cornice_assembly_study"] = True
    return row


def build_shelf(x_lo, x_hi):
    """The projecting ledge every frieze element's baseline rests on
    (reference/pulgas-cornice-photo.png shows this plainly below the row).
    Simple flat slab for this rough pass -- no dentil/egg-and-dart detail yet.
    """
    shelf_back = -0.02
    width = (x_hi - x_lo) + 2 * SHELF_MARGIN
    depth = SHELF_FRONT - shelf_back
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = "SHELF"
    ob.scale = (width, depth, SHELF_THICKNESS)
    apply_transforms(ob)
    ob.location = ((x_lo + x_hi) / 2.0, (SHELF_FRONT + shelf_back) / 2.0, -SHELF_THICKNESS / 2.0)
    apply_transforms(ob)
    log(f"shelf  size {width:.4f} x {depth:.4f} x {SHELF_THICKNESS:.4f}")
    return ob


def setup_render(width_hint, height_hint):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 500
    sc.render.image_settings.file_format = "PNG"

    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.ortho_scale = width_hint * 1.08
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    key = bpy.data.lights.new("key", "SUN")
    key.energy = 3.8
    keyob = bpy.data.objects.new("key", key)
    sc.collection.objects.link(keyob)
    fill = bpy.data.lights.new("fill", "SUN")
    fill.energy = 1.1
    fillob = bpy.data.objects.new("fill", fill)
    sc.collection.objects.link(fillob)
    fillob.rotation_euler = (math.radians(32.0), 0.0, math.radians(145.0))
    return cam, keyob


def shot(cam, keyob, path, yaw_deg, pitch_deg, dist, key_yaw=-140.0, key_pitch=55.0,
         center=Vector((0.0, 0.0, 0.0))):
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    cam.location = center + Vector((
        -dist * math.sin(yaw) * math.cos(pitch),
        dist * math.cos(yaw) * math.cos(pitch),
        dist * math.sin(pitch)))
    cam.rotation_euler = (math.radians(90.0) - pitch, 0.0, yaw + math.pi)
    keyob.rotation_euler = (math.radians(key_pitch), 0.0, math.radians(key_yaw))
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("WROTE", os.path.basename(path))


def clay(ob):
    ob.data.materials.clear()
    m = bpy.data.materials.new(ob.name + "_CLAY")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.80
    ob.data.materials.append(m)


def main():
    os.makedirs(OUT_RENDER, exist_ok=True)
    clear()

    row = place_row()

    row_lo = Vector((1e9, 1e9, 1e9))
    row_hi = Vector((-1e9, -1e9, -1e9))
    for ob in row:
        blo, bhi = world_bounds(ob)
        row_lo.x, row_hi.x = min(row_lo.x, blo.x), max(row_hi.x, bhi.x)
    shelf = build_shelf(row_lo.x, row_hi.x)
    row.append(shelf)

    for ob in row:
        clay(ob)

    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for ob in row:
        blo, bhi = world_bounds(ob)
        lo.x, lo.y, lo.z = min(lo.x, blo.x), min(lo.y, blo.y), min(lo.z, blo.z)
        hi.x, hi.y, hi.z = max(hi.x, bhi.x), max(hi.y, bhi.y), max(hi.z, bhi.z)
    size = hi - lo
    center = Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, (lo.z + hi.z) / 2.0))
    log(f"row extents  size {size.x:.4f} x {size.y:.4f} x {size.z:.4f}  center {tuple(round(c, 4) for c in center)}")

    cam, keyob = setup_render(size.x, size.z)
    shot(cam, keyob, os.path.join(OUT_RENDER, "row-front.png"), 0, 0, size.x * 2.0, center=center)
    shot(cam, keyob, os.path.join(OUT_RENDER, "row-threequarter.png"), 22, 14, size.x * 2.0, center=center)

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    log("SAVED", OUT_BLEND)


main()
