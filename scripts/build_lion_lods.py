"""Build the lion's LOD1/LOD2/LOD3 resolution tiers.

Same ratios as the leafscroll (scripts/build_leafscroll_lods.py), chosen
after rendering each candidate rather than trusting face counts alone: 0.5
and 0.25 read as essentially full detail, 0.1 shows visible but coherent
faceting, and 0.05 is the roughest usable tier (some spiky triangles in the
mane curls, rougher than the leafscroll's equivalent tier but not broken).

  LOD1  ratio 0.25  ~24.8k faces  -- negligible quality loss
  LOD2  ratio 0.10  ~9.9k faces   -- visible faceting, still reads correctly
  LOD3  ratio 0.05  ~5.0k faces   -- rough (mane curls get spiky), far/background use

Run:  blender --background --python scripts/build_lion_lods.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import LION_MASTER, LION_MASTER_OBJECT, MASTERS  # noqa: E402

TIERS = [
    ("lod1", 0.25, os.path.join(MASTERS, "Tripo-lion-mask-master-lod1.blend")),
    ("lod2", 0.10, os.path.join(MASTERS, "Tripo-lion-mask-master-lod2.blend")),
    ("lod3", 0.05, os.path.join(MASTERS, "Tripo-lion-mask-master-lod3.blend")),
]


def log(*a):
    print("[lion-lod]", *a)
    sys.stdout.flush()


def build_tier(tag, ratio, out_path):
    bpy.ops.wm.open_mainfile(filepath=LION_MASTER)
    ob = bpy.data.objects[LION_MASTER_OBJECT]
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

    me_new = bpy.data.meshes.new(LION_MASTER_OBJECT)
    bm.to_mesh(me_new)
    bm.free()

    ob.modifiers.clear()
    ob.data = me_new
    ob.name = LION_MASTER_OBJECT

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
