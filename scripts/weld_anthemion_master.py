"""Weld the anthemion plaque master.

The last element still carrying split topology. It is not a glTF donor -- it was
built procedurally from a traced profile (trace_anthemion.py ->
finalize_anthemion_master.py) -- but it has the same defect for a different
reason: the build lofted and joined separate surface patches without ever
merging the coincident vertices where they met. Measured on the shipped master:
31,450 boundary edges and 10,514 duplicate vertices on 80,000 faces, and ten
copies of it go into the ring.

This does NOT re-run the procedural build. A weld merges coincident vertices and
moves nothing, so the shape is preserved exactly -- which is the point, because
the anthemion's proportions are approved work and re-deriving them would put
that at risk to fix a topology problem.

Writes masters/anthemion-plaque-master-v2.blend with the same object name, so
switching is a one-line change in paths.py.

Run:  blender --background --python scripts/weld_anthemion_master.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy                                                        # noqa: E402

import donor_prep                                                 # noqa: E402
from donor_prep import bounds                                     # noqa: E402
from paths import ANTHEMION_MASTER_V2, MASTERS  # noqa: E402

# The pre-weld master this read from was deleted once -v2 superseded it, so this
# script is spent and kept only as the record of how -v2 was made.
SOURCE = os.path.join(MASTERS, "anthemion-plaque-master.blend")

MASTER_OBJECT = "ANTHEMION_PLAQUE_MASTER"


def log(*a):
    print("[anthemion-weld]", *a)
    sys.stdout.flush()


def main():
    if not os.path.exists(SOURCE):
        raise SystemExit(
            f"{SOURCE} no longer exists -- it was deleted once "
            f"anthemion-plaque-master-v2.blend superseded it. This script is a "
            f"record of how -v2 was made, not a step that can be re-run.")
    bpy.ops.wm.open_mainfile(filepath=SOURCE)

    ob = bpy.data.objects.get(MASTER_OBJECT)
    if ob is None:
        cands = [o for o in bpy.data.objects if o.type == "MESH"]
        raise SystemExit(f"{MASTER_OBJECT!r} not found; meshes present: "
                         f"{[o.name for o in cands]}")

    lo, hi = bounds(ob)
    before = donor_prep.report(ob, "before weld")
    donor_prep.weld(ob)
    after = donor_prep.report(ob, "after weld")

    lo2, hi2 = bounds(ob)
    moved = max(abs(lo2[i] - lo[i]) for i in range(3) if True)
    moved = max(moved, max(abs(hi2[i] - hi[i]) for i in range(3)))
    log(f"bounds shift from the weld: {moved:.3e} (should be 0 -- a weld merges "
        f"coincident vertices, it does not move geometry)")
    log(f"boundary {before['boundary']} -> {after['boundary']}, "
        f"faces {before['faces']} -> {after['faces']}")

    ob["derivation"] = (str(ob.get("derivation", "")) +
                        " | welded (merge by distance) to close the split topology "
                        "left by the procedural build; geometry unmoved")
    donor_prep.save_master(ob, ANTHEMION_MASTER_V2, MASTER_OBJECT)


if __name__ == "__main__":
    main()
