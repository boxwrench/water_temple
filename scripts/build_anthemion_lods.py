"""Build the anthemion's LOD1/LOD2/LOD3 resolution tiers.

Unlike the leafscroll and lion, the anthemion needed neither a repair pass
nor visibility culling first (see scripts/inspect_anthemion.py):
  - 0 non-manifold, 0 duplicate, 0 loose, 0 degenerate already -- the 26,206
    boundary edges (1192 separate loops, largest 756 edges) are real open-
    shell topology from the procedural build, not sliver-defect artifacts
    (those cluster in pairs of 2-3 verts; these don't).
  - A raw-Y depth histogram and side-on render confirmed the mesh has no
    invisible back mass to strip: the back cap already sits flush at
    y~=0.0000 (lo.y = -0.0001) with the whole 0.67 of local-Y depth being the
    front relief itself. prep_anthemion() applies no rotation before
    seating, so raw +Y is already the front axis (see
    integrate_cornice_frieze_v1.py).

So this goes straight from ANTHEMION_MASTER (v2, welded) to decimate ratio
testing. The leafscroll/lion's .25/.1/.05 ratios were tried first and
rendered -- .10 was already heavily faceted/crystalline and .05 collapsed
into an unrecognizable crumpled mass. The anthemion is the deepest, sharpest
relief of the four masters (many thin, close-set undercut petals packed
tightly together), so it hits the "undercut depth predicts decimate
viability" pattern (PIPELINE-GUIDE.md SS15) harder than the lion did. A
gentler set -- .5/.25/.15 -- was rendered instead and stays clean through
moderate faceting at every tier with nothing broken; user-approved 2026-08-09.

Run:  blender --background --python scripts/build_anthemion_lods.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import ANTHEMION_MASTER, MASTERS  # noqa: E402

OBJ_NAME = "ANTHEMION_PLAQUE_MASTER"

TIERS = [
    ("lod1", 0.50, os.path.join(MASTERS, "anthemion-plaque-master-lod1.blend")),
    ("lod2", 0.25, os.path.join(MASTERS, "anthemion-plaque-master-lod2.blend")),
    ("lod3", 0.15, os.path.join(MASTERS, "anthemion-plaque-master-lod3.blend")),
]


def log(*a):
    print("[anthemion-lod]", *a)
    sys.stdout.flush()


def build_tier(tag, ratio, out_path):
    bpy.ops.wm.open_mainfile(filepath=ANTHEMION_MASTER)
    ob = bpy.data.objects[OBJ_NAME]
    faces_before = len(ob.data.polygons)

    dec = ob.modifiers.new("Dec", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = ratio

    deps = bpy.context.evaluated_depsgraph_get()
    eval_ob = ob.evaluated_get(deps)
    bm = bmesh.new()
    bm.from_object(eval_ob, deps)
    faces_after = len(bm.faces)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)

    me_new = bpy.data.meshes.new(OBJ_NAME)
    bm.to_mesh(me_new)
    bm.free()

    ob.modifiers.clear()
    ob.data = me_new
    ob.name = OBJ_NAME

    log(f"{tag}: ratio {ratio} -> {faces_before} -> {faces_after} faces "
        f"(boundary {boundary}, non-manifold {nonmanifold})")

    for other in list(bpy.data.objects):
        if other is not ob:
            bpy.data.objects.remove(other, do_unlink=True)

    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_path)
    log(f"SAVED {out_path}")


def main():
    for tag, ratio, out_path in TIERS:
        build_tier(tag, ratio, out_path)


if __name__ == "__main__":
    main()
