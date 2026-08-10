"""Open v5 in a live GUI window with a Voxel Remesh modifier on a duplicate,
so the voxel size can be dragged and watched update in real time instead of
scripting camera renders per iteration.

This is a comparison tool, not a repair step: it does NOT save anything.
Original v5 object is kept (hidden) for reference; the remesh test copy is
what's visible. Pick a voxel size in the Modifier panel, note it down, and
that value gets baked into a real repair script afterward.

Run (GUI, not --background):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --python scripts/capital_voxel_live.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh                                                      # noqa: E402
import bpy                                                        # noqa: E402

from paths import CAPITAL_MASTER_OBJECT, MASTERS                  # noqa: E402

IN_PATH = os.path.join(MASTERS, "corinthian-capital-master-v5.blend")


def log(*a):
    print("[cap-voxel-live]", *a)
    sys.stdout.flush()


def remaining_gap_stats(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    by_vert = {}
    for e in boundary_edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen = set()
    diags = []
    for e0 in boundary_edges:
        if e0.index in seen:
            continue
        cv = set()
        stack = [e0]
        seen.add(e0.index)
        while stack:
            e = stack.pop()
            for v in e.verts:
                cv.add(v)
                for e2 in by_vert.get(v, []):
                    if e2.index not in seen:
                        seen.add(e2.index)
                        stack.append(e2)
        pts = [v.co for v in cv]
        lo2, hi2 = pts[0].copy(), pts[0].copy()
        for p in pts[1:]:
            for i in range(3):
                lo2[i] = min(lo2[i], p[i])
                hi2[i] = max(hi2[i], p[i])
        diags.append((hi2 - lo2).length)
    bm.free()
    diags.sort(reverse=True)
    return diags


def main():
    bpy.ops.wm.open_mainfile(filepath=IN_PATH)
    ob = bpy.data.objects[CAPITAL_MASTER_OBJECT]

    lo = [1e18] * 3
    hi = [-1e18] * 3
    for v in ob.data.vertices:
        for i in range(3):
            lo[i] = min(lo[i], v.co[i])
            hi[i] = max(hi[i], v.co[i])
    diag = sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5

    diags = remaining_gap_stats(ob.data)
    log(f"capital diagonal: {diag:.4f}")
    log(f"{len(diags)} boundary loops remain; largest diagonals: "
        f"{[round(x, 5) for x in diags[:10]]}")

    start_voxel = 0.03  # ~1.5% of diag -- bridges most measured gaps (up to
    # ~0.043, 2.2% of diag) while still finer than the leaf-carving scale.
    # Push it up toward ~0.05 if gaps remain visible; pull down toward ~0.015
    # if acanthus vein detail looks blobby.
    log(f"starting voxel size: {start_voxel} (drag it live in the Modifier panel)")

    # Duplicate so the original stays untouched and hidden for reference.
    test_me = ob.data.copy()
    test_ob = bpy.data.objects.new("CAPITAL_VOXEL_TEST", test_me)
    bpy.context.scene.collection.objects.link(test_ob)
    ob.hide_set(True)
    ob.hide_render = True

    mod = test_ob.modifiers.new("VoxelRemesh", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = start_voxel
    mod.adaptivity = 0.0
    mod.use_smooth_shade = True
    mod.show_viewport = True

    clay = bpy.data.materials.new("CLAY_TEST")
    clay.use_nodes = True
    clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.83, 0.78, 1)
    clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.80
    test_me.materials.append(clay)

    def frame_view():
        # bpy.context.window is still None if this runs during initial script
        # execution (--python at load time is too early); deferring via a
        # timer runs it after the UI has actually finished initializing.
        win = bpy.context.window
        if win is None or win.screen is None:
            return 0.2  # try again shortly
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
        log("READY: modifier is live on CAPITAL_VOXEL_TEST -- drag Voxel Size in "
            "the Modifier Properties panel and watch it update. Nothing has been "
            "saved. Report back a value that closes the gaps without mushing the "
            "leaf detail.")
        return None

    bpy.app.timers.register(frame_view, first_interval=0.2)


if __name__ == "__main__":
    main()
