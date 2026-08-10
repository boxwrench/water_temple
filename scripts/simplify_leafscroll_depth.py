"""REJECTED APPROACH -- kept as a record, do not reuse without a new fix.

Tried to cut off the leafscroll's invisible back half and cap it flat.
orient_leafscroll() seats the scroll with its back plane at y=0, flush
against the cornice, and a front-facing raycast sweep confirmed the visible
surface never reaches deeper than raw-X -0.01106 while the mesh extends to
-0.11141 -- so the "2-sided" read was correct, roughly 40-45% of the mesh
is an invisible back hump.

But a single flat-plane cut through it does not work: this is organic,
deeply undulating acanthus relief (individual leaves and curls reach
different depths at different points), so the cross-section boundary at
ANY depth close enough to matter splits into 3-16 disconnected loops with
hundreds to thousands of edges -- confirmed by sweeping 11 cut depths and
counting boundary loops/edges directly. Both Blender's native bisect
use_fill and bmesh.ops.triangle_fill were tried on the resulting boundary;
both produced a visible starburst/fan artifact when rendered (large flat
facets radiating from concentrated vertices, not following the actual
leaf-shaped contour) -- the same failure SHAPE as Solidify on the capital,
from a different root cause (a genuinely complex, multiply-connected
boundary rather than a non-planar one). There is no cut depth that is both
simple to fill and saves meaningful geometry.

Superseded by scripts/strip_leafscroll_interior.py, which reuses the
capital's proven multi-viewpoint visibility raycast instead of a flat cut --
it removes only individually-invisible triangles and needs no cap at all.

Run:  blender --background --python scripts/simplify_leafscroll_depth.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import LEAFSCROLL_MASTER_OBJECT, MASTERS  # noqa: E402

IN_PATH = os.path.join(MASTERS, "leafscroll-master-v2.blend")
OUT_PATH = os.path.join(MASTERS, "leafscroll-master-v3.blend")

CUT_X = -0.012          # measured front-surface floor -0.01106, margin behind it
ORIGINAL_BACK_X = -0.11141


def log(*a):
    print("[leafscroll-depth]", *a)
    sys.stdout.flush()


def mesh_stats(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    s = {
        "verts": len(bm.verts), "faces": len(bm.faces),
        "boundary": sum(1 for e in bm.edges if len(e.link_faces) == 1),
        "nonmanifold": sum(1 for e in bm.edges if len(e.link_faces) > 2),
        "loose": (sum(1 for e in bm.edges if not e.link_faces)
                  + sum(1 for v in bm.verts if not v.link_edges)),
    }
    bm.free()
    return s


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[LEAFSCROLL_MASTER_OBJECT]
    log("before:", mesh_stats(ob.data))

    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")

    bpy.ops.mesh.bisect(
        plane_co=(CUT_X, 0.0, 0.0), plane_no=(1.0, 0.0, 0.0),
        use_fill=True, clear_inner=True, clear_outer=False,
        threshold=1e-5,
    )

    bpy.ops.object.mode_set(mode="OBJECT")

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lo_x = min(v.co.x for v in bm.verts)
    log(f"after bisect: raw-X min = {lo_x:.6f} (target ~{CUT_X})")

    # find the cap faces created by the fill: every vertex on the cut plane
    cap_faces = [f for f in bm.faces if all(abs(v.co.x - lo_x) < 1e-5 for v in f.verts)]
    log(f"cap faces found: {len(cap_faces)}")
    if not cap_faces:
        raise RuntimeError("no cap faces found at the cut plane -- bisect fill may have failed")

    extrude_result = bmesh.ops.extrude_face_region(bm, geom=cap_faces)
    new_verts = [g for g in extrude_result["geom"] if isinstance(g, bmesh.types.BMVert)]
    delta_x = ORIGINAL_BACK_X - lo_x
    bmesh.ops.translate(bm, verts=new_verts, vec=(delta_x, 0.0, 0.0))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges[:])

    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    log("after:", mesh_stats(ob.data))

    os.makedirs(MASTERS, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_PATH)
    log(f"SAVED {OUT_PATH}")


if __name__ == "__main__":
    main()
