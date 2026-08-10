"""First-pass integration of LEEDS_LION_MASK_MASTER into the one-section cornice.

Never touches the live file: opens it, immediately saves to a new working copy,
then does all edits there. Deletes the crude placeholder block at the lion slot
(measured empirically, see module-layout-report.json), appends the approved
Leeds mask, scales it to the slot's height, and seats it rigidly (no cylindrical
vertex remap -- the mask's angular footprint is ~3 degrees, curvature is
negligible at this radius) with its back plane flush with the backing and its
face projecting proud of the palmette/rinceaux surface, matching the reference
photo's high-relief antefix masks.

This is a first draft for review, not a final placement. Scale and projection
are estimated from the existing (crude) placeholder slot dimensions, not yet
confirmed against the user's proportion judgment.
"""


import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import math
import os
import json
import bmesh
from mathutils import Vector, Matrix

from paths import (ROOT, CORNICE_CLEAN as SOURCE_BLEND,  # noqa: E402,F401
                   CORNICE_WITH_LION as WORKING_BLEND,
                   LION_MASTER as MASK_BLEND, RENDERS)

OUT_DIR = RENDERS

CY = -0.5456366539001465
RMAP = 0.300
LION_ANGLE = math.atan2(0.0756035098, 0.2408188273)

# Measured from the current placeholder block (inspect_module_layout.py).
SLOT_Z_MIN, SLOT_Z_MAX = 0.31119999289512634, 0.3610000014305115
SLOT_R_BACK = 0.2921  # backing base radius, matches palmette/rinceaux mounting plane
SLOT_U_CENTER = 0.0047  # placeholder block's measured u-centroid, ~LION_ANGLE

# Mask master stats (finalize_lion_mask.py MASTER_REPORT).
MASK_BOUNDS_MIN = Vector((-0.10166, -0.12406, 0.13203))
MASK_BOUNDS_MAX = Vector((0.09303, 0.01999, 0.32275))


def map_point(u, r, z):
    theta = LION_ANGLE + u / RMAP
    return Vector((r * math.cos(theta), CY + r * math.sin(theta), z))


def main():
    bpy.ops.wm.open_mainfile(filepath=SOURCE_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=WORKING_BLEND)

    scene = bpy.context.scene
    anchor = bpy.data.objects["CORNICE_CLEAN_PREDONOR_MASTER_36DEG"]

    # --- Cut the placeholder block out of the anchor mesh ---
    bm = bmesh.new()
    bm.from_mesh(anchor.data)
    bm.faces.ensure_lookup_table()
    to_remove = []
    for f in bm.faces:
        c = f.calc_center_median()
        w = anchor.matrix_world @ c
        dx, dy = w.x, w.y - CY
        r = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)
        u = (theta - LION_ANGLE) * RMAP
        if -0.021 <= u <= 0.030 and w.z <= 0.362:
            to_remove.append(f)
    bmesh.ops.delete(bm, geom=to_remove, context='FACES')
    bm.to_mesh(anchor.data)
    bm.free()
    anchor.data.update()

    # --- Append the approved lion mask ---
    before_objs = set(bpy.data.objects.keys())
    with bpy.data.libraries.load(MASK_BLEND, link=False) as (data_from, data_to):
        data_to.objects = ['LEEDS_LION_MASK_MASTER']
    mask = bpy.data.objects['LEEDS_LION_MASK_MASTER']
    scene.collection.objects.link(mask)

    # --- Scale: fit the mask's height to the slot's height ---
    mask_height = MASK_BOUNDS_MAX.z - MASK_BOUNDS_MIN.z
    slot_height = SLOT_Z_MAX - SLOT_Z_MIN
    s = slot_height / mask_height

    # --- Rotation: local -Y (mask's outward/front) -> world radial-out at LION_ANGLE
    #     local +X (mask width) -> world tangent; local +Z -> world +Z ---
    radial = Vector((math.cos(LION_ANGLE), math.sin(LION_ANGLE), 0.0))
    tangent = Vector((-math.sin(LION_ANGLE), math.cos(LION_ANGLE), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    rot = Matrix((
        (tangent.x, -radial.x, up.x),
        (tangent.y, -radial.y, up.y),
        (tangent.z, -radial.z, up.z),
    ))

    mask.scale = (s, s, s)
    mask.rotation_mode = 'XYZ'
    mask.rotation_euler = rot.to_euler()

    # --- Position: back plane (local y = bounds_max.y) centered in x/z lands on
    #     the backing radius at the slot's z-center and u-center ---
    ref_local = Vector((
        (MASK_BOUNDS_MIN.x + MASK_BOUNDS_MAX.x) / 2.0,
        MASK_BOUNDS_MAX.y,
        (SLOT_Z_MIN + SLOT_Z_MAX) / 2.0 - (MASK_BOUNDS_MIN.z + MASK_BOUNDS_MAX.z) / 2.0
        + (MASK_BOUNDS_MIN.z + MASK_BOUNDS_MAX.z) / 2.0,
    ))
    # ref_local.z should just be the mesh's own z-center (mapped separately below)
    ref_local.z = (MASK_BOUNDS_MIN.z + MASK_BOUNDS_MAX.z) / 2.0

    desired_world = map_point(SLOT_U_CENTER, SLOT_R_BACK, (SLOT_Z_MIN + SLOT_Z_MAX) / 2.0)
    mask.location = desired_world - (rot @ Vector((s * ref_local.x, s * ref_local.y, s * ref_local.z)))

    mask["cornice_master_component"] = True
    mask.parent = None

    scene["cornice_working_phase"] = "LEEDS_LION_INTEGRATED_DRAFT_V1_AWAITING_REVIEW"
    bpy.ops.wm.save_as_mainfile(filepath=WORKING_BLEND)

    print(json.dumps({
        "saved": bpy.data.filepath,
        "scale": s,
        "mask_location": list(mask.location),
        "mask_dimensions": list(mask.dimensions),
    }, indent=2))


main()
