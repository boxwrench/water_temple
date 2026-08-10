"""Build the leafscroll's LOD1/LOD2/LOD3 resolution tiers.

Unlike the capital, straight Collapse decimation degrades this mesh
gracefully -- confirmed by rendering (not just checking face counts,
per the capital's LOD1 lesson) at ratios 0.5/0.25/0.1/0.05: no
starburst/shattering at any of them, just increasingly visible but
coherent faceting. That is very likely because this is a shallow relief
carving with a consistent front-facing normal direction, unlike the
capital's deep undercut/folded-back acanthus geometry -- Collapse
struggles specifically with undercuts, not organic detail in general.

Three tiers, decimating LEAFSCROLL_MASTER (v3, interior-stripped) directly:
  LOD1  ratio 0.25  ~38k faces  -- negligible quality loss
  LOD2  ratio 0.10  ~15k faces  -- visible faceting, still reads correctly
  LOD3  ratio 0.05  ~7.6k faces -- heavy faceting, for far/background use

Run:  blender --background --python scripts/build_leafscroll_lods.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import LEAFSCROLL_MASTER, LEAFSCROLL_MASTER_OBJECT, MASTERS  # noqa: E402

TIERS = [
    ("lod1", 0.25, os.path.join(MASTERS, "leafscroll-master-lod1.blend")),
    ("lod2", 0.10, os.path.join(MASTERS, "leafscroll-master-lod2.blend")),
    ("lod3", 0.05, os.path.join(MASTERS, "leafscroll-master-lod3.blend")),
]


def log(*a):
    print("[scroll-lod]", *a)
    sys.stdout.flush()


def build_tier(tag, ratio, out_path):
    bpy.ops.wm.open_mainfile(filepath=LEAFSCROLL_MASTER)
    ob = bpy.data.objects[LEAFSCROLL_MASTER_OBJECT]
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

    me_new = bpy.data.meshes.new(LEAFSCROLL_MASTER_OBJECT)
    bm.to_mesh(me_new)
    bm.free()

    ob.modifiers.clear()
    ob.data = me_new
    ob.name = LEAFSCROLL_MASTER_OBJECT

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
