"""Live GUI viewer: Solidify (Complex, Fill Rim) on a duplicate of v5.

Numeric test (scratchpad/probe_solidify_remesh.py) already proved this closes
every remaining boundary loop (223 -> 0) and nearly all non-manifold edges
(90 -> 3) without touching the outward-facing carved surface at all -- offset
=-1 pushes the new shell material inward, and Fill Rim (nonmanifold_boundary
_mode='FLAT') caps the rim exactly at the old gap loops. This is a
comparison/inspection tool, not a repair step: nothing is saved here.

Run (GUI, not --background):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --python scripts/capital_solidify_live.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS                  # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v5.blend")


def log(*a):
    print("[cap-solidify-live]", *a)
    sys.stdout.flush()


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]
    ob.hide_set(True)
    ob.hide_render = True

    test_ob = bpy.data.objects.new("CAPITAL_SOLIDIFY_TEST", ob.data.copy())
    bpy.context.scene.collection.objects.link(test_ob)

    sol = test_ob.modifiers.new("Solidify", "SOLIDIFY")
    sol.solidify_mode = "EXTRUDE"
    sol.thickness = 0.03
    sol.offset = -1.0
    sol.use_even_offset = False  # was 309x bbox blowup at sharp creases -- this is the fix
    sol.use_thickness_angle_clamp = True
    sol.thickness_clamp = 1.0
    sol.use_rim = True
    sol.use_rim_only = False
    sol.use_quality_normals = True

    rem = test_ob.modifiers.new("Remesh", "REMESH")
    rem.mode = "VOXEL"
    rem.voxel_size = 0.005
    rem.adaptivity = 0.0
    rem.use_smooth_shade = True
    rem.show_viewport = False  # off by default -- Solidify alone already wins
    rem.show_render = False

    clay = bpy.data.materials.new("CLAY_TEST")
    clay.use_nodes = True
    clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.80
    test_ob.data.materials.append(clay)

    # Locate the 3 remaining non-manifold edges on the evaluated (Solidify-only)
    # result so they're easy to find in the viewport.
    deps = bpy.context.evaluated_depsgraph_get()
    eval_ob = test_ob.evaluated_get(deps)
    bm = bmesh.new()
    bm.from_object(eval_ob, deps)
    nm_edges = [e for e in bm.edges if len(e.link_faces) > 2]
    b_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    log(f"{len(nm_edges)} non-manifold, {len(b_edges)} boundary edges remain "
        f"on Solidify-only (EXTRUDE) result")
    bm.free()

    def frame_view():
        win = bpy.context.window
        if win is None or win.screen is None:
            return 0.2
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.shading.type = "SOLID"
                space.shading.light = "STUDIO"
                space.overlay.show_stats = True
                with bpy.context.temp_override(window=win, area=area, region=area.regions[-1]):
                    bpy.ops.object.select_all(action="DESELECT")
                    test_ob.select_set(True)
                    bpy.context.view_layer.objects.active = test_ob
                    bpy.ops.view3d.view_selected()
                break
        log("READY: CAPITAL_SOLIDIFY_TEST has Solidify (Complex/Fill Rim, live) "
            "and a disabled Remesh modifier below it (toggle its viewport-camera "
            "icon on to compare). Nothing saved.")
        return None

    bpy.app.timers.register(frame_view, first_interval=0.2)


if __name__ == "__main__":
    main()
