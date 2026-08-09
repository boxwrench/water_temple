# Building the Pulgas Water Temple — the pipeline, start to finish

A working guide to the workflow this project arrived at: **AI agent + headless
Blender + raw `.glb` donors + reference photography**. Written to be portable —
the temple supplies the worked examples, but the method transfers.

The shape of the whole thing:

```
reference photo ─┐
                 ├─► one coordinate system ─► element masters ─► seated module
raw .glb donor ──┘                                                     │
                                                                       ▼
        verified model ◄── structural swaps ◄── propagated ring ◄── wall fit
              │
              └─► repaired base ─► resolution tiers
```

Two currencies run in parallel the whole way: **renders** decide appearance,
**numeric audits** decide integrity. Neither substitutes for the other.

---

## 1. Fix one coordinate system first

Everything downstream is cheap if the frame is settled and expensive if it
isn't. The temple's is a cylinder:

```python
CY         = -0.5456366539001465   # colonnade centre in world Y
RMAP       = 0.300                 # mapping radius
LION_ANGLE = atan2(0.0756035098, 0.2408188273)   # where module 0 starts
MODULE     = radians(36.0)         # ten bays
PU         = RMAP * radians(18.0)  # half-bay, as arc length
```

Two rules that paid for themselves repeatedly:

- **`scripts/paths.py` is the only place paths and shared constants live.** Every
  script imports from it and inserts its own directory on `sys.path`, so any
  script runs from any working directory under
  `blender --background --python <script>`. This rule has a scar behind it: the
  project directory moved once, and every script carrying its own `ROOT`
  constant broke silently until each was found and fixed by hand.
- **A constant derived from geometry lives in exactly one module.** The drum's
  inner radius is derived from the capitals' inner radius; it sits in
  `paths.DRUM_INNER_R` and is imported by the three chain steps that need it.
  Scripts that *change* the source geometry print the new value to use:

  ```
  ==> TARGET_INNER_R for thicken_drum.py: 0.2023
  ```

---

## 2. Measure in the frame that means something

Having a coordinate system is not the same as measuring in it. Three times this
project produced numbers that were arithmetically correct and completely
meaningless, and each failure has the same shape: the measurement was taken in
the wrong frame, over the wrong subset, or of the wrong feature.

**The wrong frame.** The colonnade is centred on `(0, CY)`, not the world origin.
Radii taken from the world origin gave ten supposedly identical capitals a spread
of 0.2974 to 0.7944 — pure noise, entirely an artifact of measuring from the
wrong centre. Re-expressed in the colonnade's own polar frame they read 0.2477 to
0.2574, which is the real (and genuinely slightly irregular) layout.

**The wrong subset.** `Ten deep-fluted shaft overlays` is a single object holding
all ten shafts. Its overall radial extent, 0.2139 to 0.2915, is therefore the
colonnade *annulus* — not a column's width, which is what it looks like. A
column's actual diameter (0.0667 at the shaft top) only appears once you restrict
to one bay and re-express in that column's own frame:

```python
rad =  dx*cos(theta0) + dy*sin(theta0)   # outward along the column axis
tan = -dx*sin(theta0) + dy*cos(theta0)   # across the column
```

**The wrong feature.** A capital's bounding box is dominated by its square
abacus, but the thing that has to land on the shaft is the round bell base — a
thin band at the very bottom. Taking the "width" from the box would have been off
by the ratio between the two, and the diagonal of a square abacus over-reports by
another √2 on top of that.

**The wrong estimator.** A fourth trap, subtler than the other three: the mean
vertex position is *not* a centre. It is a centre weighted by mesh density, and
ornament meshes are never uniformly dense — a third of the capital's vertices are
in its abacus, so the vertex mean sits high and biased toward it. For a plan
centre, take the mean of the *extremes* (the bounding-box centre); for a circular
feature such as a bell base, the mean of its extremes really is its centre. Use
the vertex mean only when you actually want a centre of mass.

The practical form of all four: **profile the geometry in bands and print a
table, rather than trusting a single number.** Banding the capital by height is
what showed the bell flaring into the abacus; banding the shaft is what showed it
tapering from 0.0681 to 0.0667 toward the top. A single number cannot show you
that it is the wrong number — a profile can.

---

## 3. Getting geometry out of a photograph

Used for the anthemion plaque, where no donor existed — only a reference photo.
Four attempts failed before this method worked, and the failures are the useful
part.

**Check whether the target is even reachable before tuning toward it.** All four
early attempts built the ornament from lofted ridges whose cross-section tapers
to a line. The reference is carved as stacked near-flat planes with bullnose
edges. So "make the lobes broader" was never a parameter that could be turned up
— a tapered ridge *cannot* produce a fat rounded petal tip. It was a topology
limit wearing the costume of a tuning problem, and four rounds of tuning were
spent on it.

The tell is generic and worth watching for: **when successive parameter changes
all move the result in the same wrong direction, or produce no change at all in
the thing being asked for, stop tuning and ask what the construction is
incapable of.** An agent is especially prone to this failure, because adjusting a
constant and re-rendering always *looks* like progress.

**Sweep first, decide, then build.** `trace_anthemion.py` runs pure system Python
(numpy/scipy/PIL, no Blender) and emits a 3×3 contact sheet of edge maps across a
blur-σ × threshold grid. It is explicitly a *decision gate*: you look at the
sheet and judge whether the grooves resolve into clean connected contours before
any geometry is built on top of them.

**Read coordinates, don't estimate them.** `make_trace_guide.py` composites the
lightened photo, the edge map and the extracted silhouette under a labelled
normalised grid (half-width = 1.0, origin at the bounding-box centre), plus four
2× quadrant zooms. Tracing then means reading numbers off a grid rather than
eyeballing proportions.

**Pick the discriminator that matches the material, not the obvious one.**
Luminance thresholding (Otsu) amputated the plaque's lower third, which sits in
its own shadow and reads darker than the grey wall behind it. What actually
separates cast from wall here is **local texture**: the cast is pitted and
carries high local standard deviation everywhere, while the wall and its soft
drop shadow are smooth. Threshold local std at the 62nd percentile, keep the
largest component, fill holes. Brightness was the property that was easy to
measure; roughness was the property that differed.

**Exploit the shape's own structure.** The egg is star-convex about its centroid,
so the silhouette needs no marching-squares contour tracing at all: march outward
from the centroid along N angles and take the last mask pixel. That yields an
ordered, evenly-spaced contour directly, and — because `r(θ)` is now a periodic
1-D signal — it can be low-pass filtered to remove mask stair-stepping and folded
about the vertical axis to enforce symmetry. Recognising the right
parameterisation removed two whole processing stages.

**Record negative results with their cause, and a condition for retrying.**
Region segmentation into relief levels (flat-field correction, 1-D Lloyd
clustering, swept over k ∈ {4,5,6} × radius ∈ {40,80,140}) failed in all nine
parameterisations: the lower half collapses into one region every time. The
*cause* is what makes the record worth keeping — bullnose-rolled edges sweep the
full range of surface normals, so within-region brightness variation exceeds
between-region variation wherever elements are small relative to their own edge
rolls, which is precisely the opposite of what height-based clustering needs. The
script is kept, labelled, and marked **do not retry without a new signal**.
Without the cause written down, a later session re-runs the same sweep with a
different `k`.

**Verify after every region group, not at the end.** Thirteen regions were built
with an orthographic clay render and silhouette-difference image after each
group, so an error surfaces at region 5 instead of after all thirteen are stacked
on top of it.

**Do not let geometry force a deferred decision.** The rim moulding was built as
a *separate object* specifically because the keep-or-drop call was still open.
Where a decision is deliberately postponed, the construction has to keep both
branches reachable, or the postponement is fictional.

**Keep the finalize pass minimal.** `finalize_anthemion_master.py` does sizing,
orientation and triangle reduction — nothing else. Once a form is approved, the
finalize step must not quietly "improve" it.

Output: `trace/silhouette.json` → a master in the documented convention
(x horizontal, y depth with 0 at the back plane, z up, half-width 1.0).

One cost to note, because it comes due in §13: this construction — thirteen
regions solidified and joined, each region's patches meeting without ever being
merged — is exactly what left the anthemion master with 31,450 boundary edges.
A traced-and-lofted build produces cracks at every seam by default.

---

## 4. Judging a donor before building on it

**`inspect_donor.py <name-or-path>`** — works out which axis the relief faces and
renders orthographic views from every side. Read-only. Run it on anything new.

**`verify_new_lion.py`** — the deeper pass, for a donor that will be mirrored:

- **Fit the symmetry plane; don't assume it.** Search (yaw, roll, offset) for the
  plane that best maps the mesh onto itself, scored by KD-tree nearest-neighbour
  distance from reflected sample points. The lion sat **5° off-axis inside its own
  mesh** — residual 0.00807 at the fitted plane versus 0.01717 at the bounding-box
  centreline, better than 2:1.
- **Score only the sculpted front** (here the front 35% of depth). A flat mounting
  back is trivially symmetric and flattens the objective function.
- **Coarse-to-fine with a dense tree and a sparse query set.** The KD-tree is cheap
  at 40k points; the query set is what costs time — 1.5k coarse, 6k fine.
- **Report per-side residuals**, so "which half is better" is answered with a
  number as well as an image.
- **Light it symmetrically.** A mirror-symmetric key pair straddling the plane,
  plus a weak axial fill. A single off-axis key decides left-vs-right by shadow.
- **Judge from centre-line closeups**, not full-object views — mirroring amplifies
  whatever it copies.

---

## 5. The master recipe

`scripts/donor_prep.py` owns the shared hygiene, in this order:

```
import → measured weld → [shape-specific work] → decimate → provenance → clean save
```

**Import**: diff `bpy.data.objects` around the import, join multi-part meshes,
bake transforms into mesh data so everything afterwards is one honest frame.

**Weld — measured, not assumed.** glTF stores normals per *vertex*, so exporters
duplicate vertices along shading seams and the faces either side become
topologically disjoint. Whether a given donor is split depends on its exporter
and is invisible:

| donor | raw faces | raw boundary edges | after weld 1e-7×diag |
|---|---:|---:|---:|
| `lion.glb` | 1,486,552 | 36,974 | 200 |
| `leafscroll.glb` | 1,424,782 | 45,910 | 52 |
| `corinthian-capital…glb` | 2,424,926 | 381 | 465 |

So `weld()` trials each candidate threshold **plus the no-weld baseline**, scores
on (boundary + non-manifold), and keeps the winner — including "do nothing",
which is what it correctly chose for the capital.

Tolerances are a **fraction of the mesh's own bounding-box diagonal** (these three
donors span 1.18 to 3.14), and the tightest candidate wins wherever welding helps
at all, because true exporter duplicates are *exactly* coincident.

**Decimate after welding.** COLLAPSE decimation operates on connected topology.
Welded first, it is topology-preserving — the scroll swept 1.42M → 60k faces with
boundary edges pinned at 52 the whole way:

| budget | tris | boundary edges |
|---|---:|---:|
| welded raw | 1,424,730 | 52 |
| 400k | 400,000 | 52 |
| 200k | 200,000 | 52 |
| 60k | 59,998 | 52 |

**Sweep the detail budget and look at it.** Render candidates side by side under a
raking key — decimation damage shows in the shadow line long before it shows in
flat lighting. Rebuild the final master from the *original*, never from a
sweep entry: decimating an already-decimated mesh is a different operation.

Note that collapse decimation cannot be driven arbitrarily low — on undercut
ornament it hits a hard floor no ratio will pass. That does not matter at master
resolution, but it dominates the low LOD tiers; see §15.

**Stamp provenance** into the object: source asset, source URL, license, and a
`derivation` string with the actual parameters (weld threshold, symmetry yaw,
which half, decimation target). Months later that string is the only record.

**Save clean** — one master file, one master object. Appending from a file that
drags a stale scene along pulls that junk into the target.

---

## 6. Canonical frames

Each master is normalised so the seating code does no shape reasoning:

| element | convention |
|---|---|
| lion mask | front/snout −Y, flat back at +Y max, up +Z, width X |
| anthemion | x horizontal, y depth (0 at back plane), z up, half-width 1.0 |
| leaf scroll | **donor axes preserved** — its placement was already approved |
| capital | unit height, bell base on z = 0, plan centred, faces on ±X/±Y |

The scroll is the instructive one: when downstream placement is already approved
work, the master should change *density only* and leave the frame alone, so the
orientation function needs no edit at all.

Masters also carry the measurements the seating needs as custom properties — the
capital stamps `bell_base_width` and `abacus_width` in its unit-height frame, so
nothing re-measures the mesh later.

---

## 7. Seating an element on the cylinder

```python
def map_point(u, r, z):
    theta = LION_ANGLE + u / RMAP
    return Vector((r*cos(theta), CY + r*sin(theta), z))
```

Build the seating frame from `(tangent, −radial, up)` as columns — **determinant
+1**, a true rotation. Check it. Then place at `map_point(u, r, z)`.

Angular layout is architecturally fixed to the ten column axes (36° lion-to-lion,
18° lion-to-anthemion) and deliberately does **not** scale with element size —
`FRIEZE_SCALE` shrinks the ornaments in place and opens the gaps between them.
Elements seat bottom-down on a shared baseline, so the scale knob only moves the
ring's top edge, and the build reports headroom per element:

```
ANTHEMION_C  top z=0.3832   headroom to structure top (0.395) = +0.0118
```

**Quote a free fit in the element's own terms.** Most of the layout is locked to
the column axes, but the scroll's position inside its gap is a genuine choice.
It is expressed as a fraction of *the scroll's own length* — slide 5% toward the
anthemion — rather than as a fraction of the bay, because it describes something
about the scroll: how much of it slides out from behind the lion and under the
anthemion. A mirrored pair takes one symmetric number, not a left and a right.

**Make the fit measurable.** An `angular_report()` prints each element's angular
footprint and how much of each scroll its neighbours cover, so the judgement is
checkable instead of squinted at:

```
SCROLL_L: under LION_L 2.975 deg (22.3%), under ANTHEMION_C 0.967 deg (7.3%),
          clear 9.380 deg (70.4%)
```

That is also what settles how far is too far: at double the slide, the numbers
still look reasonable but the scroll stops overlapping the lion enough to close
the joint, and a bare patch of wall opens between them.

**Have the placement recorded by whatever performed it.** The seating call
stamps `u_center` and `r_target` onto each object, and the propagation step
reads them back rather than re-deriving them from the same constants. Once a
position depends on a runtime measurement, a second formula elsewhere will drift.

Prove one module before propagating it.

---

## 8. One module → ten

**Linked duplicates.** `ob.copy()` shares `.data`, so 40 frieze objects cost 4
mesh datablocks. This is what makes a 200k-face scroll affordable twenty times.

**Get the repeat unit right.** The reviewable module carried a lion at *each* end
so it could be judged in isolation — but the repeatable unit is one lion, two
scrolls, one anthemion, owning only the lion at its own start. The ring closes
because copy 9's "next" position is copy 0's own lion. Propagating the review
module as-is doubles a lion at every seam.

---

## 9. Making relief sit on a wall

Carved relief is not a flat-backed panel: its mass is spread through the radial
depth, and only a sliver of it actually reaches the wall. Four moves, in order:

1. **Thicken the wall** — push only the inner-surface vertex ring inward to the
   capitals' inner radius. The outer surface and the inset quotation text are
   untouched, so it is a pure thickening, not a resculpt.
2. **Bridge it into a continuous wall**, and carry the same inner radius up
   through the object above the drum so the masonry reads uniform to the top.
3. **Add hidden backing fillers.** Rather than shoving thin relief inward until it
   vanishes, add solid blocks bridging from inside the wall out to each element's
   real back. Fit them to the **angular silhouette** — slice into angular bins and
   take local z-min/z-max and back radius per bin — so they follow a tapering
   outline instead of a bounding box, and stay hidden. Verify with an explicit
   overhang metric that must stay ≤ 0:

   ```
   worst filler-above-element overhang: -0.00080 (must be <= 0)
   ```

   **A smoothed profile is not a fit — check which way the smoothing errs.** The
   first silhouette-fitted version took local z-min/z-max over a window ±1.6
   slice-widths wide, across only 20 slices. Taking a *maximum* over a
   neighbourhood is a dilation: wherever the outline is short next to something
   tall, the filler is built up to the tall height. Each filler grew past its own
   element, the elements already overlap in θ, and so all ten merged into a single
   raised band running the full 360° — a global artifact from a local smoothing
   parameter. The fix is the transferable part: **decouple the neighbourhood
   widths, because different quantities are conservative in opposite
   directions.** The z profile wants a tight window so it hugs the real outline;
   the back radius wants a *wide* one, because it takes the deepest nearby radius
   and a wide window there tucks the filler further in. Then inset z rather than
   outsetting it, so a filler can only ever sit inside its element's silhouette.

4. **Unify the material.** Put the new work on the building's own cast-stone
   material. An unmateralled object renders at Blender's default near-white and
   will look like a geometry defect against 0.305-grey neighbours.

### Authoring a running ornament band

For a repeating band on a cylinder — a braid, a bead-and-reel, a dentil run —
author the motif flat in **(θ, z)** and map it onto the cylinder only at the end.
Same move as the frieze seating, and it means no booleans anywhere.

Make each unit a **closed outline swept radially onto a copy of itself**: the
outline at `r_base`, the same outline at `r_base + relief`, and a quad band
joining them. It is watertight by construction rather than by repair. The well's
braid and cap course audit at 0 boundary edges, 0 non-manifold and 0 duplicates —
not because they were cleaned up, but because that construction cannot produce
them. 1,392 faces added **zero** new defects to the model's totals.

**Orientation can decide whether overlap is even possible.** The well's chevrons
overlap by 65% of their repeat and never intersect, because they point *along*
the band: a `>` presents a thin apex at mid-height and two open arms top and
bottom, so its neighbour's apex passes between the arms. The same motif rotated
to `^` is widest at its base and would collide at any overlap. When a motif has
to interlock, look at where its mass sits before choosing how to orient it.

**The character lives in two or three constants, so try them rather than argue
about them** (see step 11). One band read as a continuous zigzag ribbon, then as
a row of separate arrows, then as braid — changing nothing but the repeat count,
the overlap fraction, and the motif's rotation.

---

## 10. Swapping structural elements

**Inherit positions; don't regenerate them.** Each new capital reads its angle,
column-centre radius and seating height off the outgoing capital immediately
before that one is deleted. The measured colonnade is not regular — axis radii
0.2477–0.2574, bays 35.3°–37.1° — so an idealised 36° layout would visibly move
things. Inheriting makes "alignment survives the swap" true by construction.

Read a column axis from the **bell base** (a circle, so the mean of its extremes
is its centre), not the bounding box, which is dominated by the square abacus.

**Fit non-uniformly when the slot demands it.** The capital slot is bounded by the
shaft below and the architrave above, both fixed. It wants a bell-base-to-height
ratio of 0.8198; the donor's is 0.7197. So scale plan and height independently —
`k_z` fills the slot, `k_xy` matches the outgoing bell base. Result: capital top
at 0.17430 against an architrave underside of 0.17430, clearance 0.00000. Since
the only rotation is about Z, the non-uniform scale commutes with it and shears
nothing.

**Let data sharing choose the mechanism.** Narrowing the columns to 90% is one
visual operation with two implementations:

- ten capitals sharing **one mesh** → go through each object's world matrix
- ten shafts inside **one object** → go per-vertex, assigning each to its nearest
  column axis

For shared-mesh objects, compose in world space rather than multiplying
`ob.scale`, which would scale about the object's own origin:

```python
ob.matrix_world = T(axis) @ S(k, k, 1) @ T(axis).inverted() @ ob.matrix_world
```

That is origin-agnostic — it means "scale the world about this column's axis"
regardless of where the object's origin sits.

---

## 11. Sweep, measure, pick

The same move solved three problems that have nothing else in common, which is
what makes it worth naming rather than rediscovering:

| decision | candidates | what was measured |
|---|---|---|
| edge-detection for the photo trace | 3×3 blur-σ × threshold grid | do grooves resolve into connected contours |
| decimation budget | 4 budgets, raking key | boundary edges, and the shadow line |
| scroll placement | 3 slide distances | % of scroll under each neighbour |

When a choice is a judgement call, **don't reason about it — generate the
candidates, measure each, render each at a fixed camera, and pick.** It is nearly
always cheaper than arguing, and it converts taste into evidence.

Two habits make it pay:

- **Keep the rejected candidates.** They are what makes the chosen one
  defensible, and they show the failure mode. The scroll at double the slide
  looks fine in the table — 17.3% still under the lion — but the render shows a
  bare patch of wall opening at the joint. Neither the number nor the picture
  alone would have settled it.
- **Rebuild the final from the original, not from the winning candidate.** A
  sweep entry has usually been through an operation you are about to repeat, and
  decimating an already-decimated mesh is not the same operation as decimating
  the original once.

---

## 12. Verification

**`audit_mesh_quality.py <blend> [filter]`** — read-only, worst offenders first:
boundary edges, non-manifold edges, degenerate faces, zero-length edges,
duplicate verts, loose geometry, inverted-normal pairs, watertightness.

Print integrity at **every stage** of a build, not just the end. The
stage-by-stage log is what localises damage to a single operation.

**Compare at a fixed camera.** `render_capital_compare.py` and
`render_lion_compare.py` take the blend as an argument and supply their own
camera and lights, so any two files are directly comparable and the only
difference in the images is the thing that changed.

Expect non-manifold edges to *rise* when a weld succeeds — fusing a
three-sheet junction that split topology was hiding creates one edge with three
faces. Score on the sum: the lion traded 30,805 holes for 196 such edges.

**And never let the audit stand in for the render.** An integrity metric measures
whether a mesh is well-formed; it cannot tell you it is still the right shape.
§15 has the case that proves it — an operation that improved every number in this
list while destroying the building.

---

## 13. Knowing which fix is safe to make

Not every defect should be fixed, and the deciding question is not how bad it is
— it is **whether the fix can be proven to leave the approved shape alone.**

A weld merges coincident vertices and moves nothing. That is checkable, so check
it and say so:

```
bounds shift from the weld: 0.000e+00
```

With that assertion in hand, welding is safe to run on approved geometry. Re-running
a procedural build to fix its topology is not: it can change the form that was
signed off, and no amount of care makes that provable in advance.

### The worked example, and the mistake inside it

The anthemion plaque was the model's largest source of holes: 31,450 boundary
edges, ten copies of it in the ring. It was welded, and the weld recovered only
17%, down to 26,206.

**The wrong conclusion was drawn from that, and it stood in this guide for a
while.** The reasoning went: where the glTF donors collapsed by 99%+ because
their holes were duplicate-vertex splits, this one barely moved — so the
remaining boundaries must be *real* gaps that no weld can close, and closing them
would mean re-running the procedural loft, which puts an approved form at risk.
Leave it, document it, move on.

That is a well-formed argument from a measurement, and it is wrong. Re-run with a
wider candidate set, the same weld takes the anthemion to **1,246 boundary edges
— a 95% cure**, with the shape untouched.

The original sweep only reached 1e-6 × diagonal. **The sweep's bounds were
carrying an assumption, and the assumption was the thing being tested.** Those
bounds were inherited from the glTF donor work, where they are not merely
adequate but *correct*: exporter-duplicated vertices are exactly coincident, so
the tightest tolerance wins and a loose one starts fusing real geometry. Cracks
in a procedural loft are a different defect with a different physical scale —
patches that were never merged sit a real, small distance apart. They need a real
tolerance:

| defect | provenance | tolerance that works |
|---|---|---|
| shading-seam splits | glTF exporter | 1e-7 … 1e-6 × diagonal — tightest wins |
| unmerged patch seams | procedural loft | 1e-4 … 3e-4 × diagonal |

3e-4 of the diagonal is 0.03% of the object — orders of magnitude below any
feature these meshes carry, and safe by the same bounds-shift assertion as any
other weld.

Three things to carry out of this:

- **A negative result from a sweep is only as good as the sweep's range.** Before
  concluding "no parameter value works," state what range was tried and why those
  bounds. If the bounds came from a different problem, they are a hypothesis, not
  a setting.
- **Reuse the method, re-derive the constants.** The weld-and-score procedure
  transferred perfectly from donors to procedural geometry. Its candidate list
  did not. Constants tuned against one defect class are the part that silently
  fails to transfer.
- **Write down negative results in a form that can be falsified.** This one was
  recorded with its numbers and its reasoning, which is the only reason it could
  be caught and overturned later. Had it been recorded as "the anthemion can't be
  fixed," it would still be true today.

**Where this leaves the principle.** Unchanged, and better supported: a weld is
safe on approved geometry because it moves nothing and you can prove it; a
re-run of the procedural build is not, because it can change a form that was
signed off. What changed is only the finding — the cheap safe fix turned out to
work after all. A known, quantified defect is a fine place to stop; a
silently-unfixed one is not; and a *quantified* one is the only kind you can
later discover you were wrong about.

### Filling a hole and collapsing one are different operations — only one is provable

Closing the capital master's last ~76 small boundary loops (crack-thin gaps
between overlapping leaves, none over 0.018 × the model's own diagonal) looked
like a job for a fill operator. Three were tried, and all three are unsafe on
this mesh's tiny non-planar loops:

- `bmesh.ops.holes_fill` returns an empty face list on a verified non-degenerate
  loop (area 8.6e-6).
- `bmesh.ops.triangle_fill` reports success — a new `BMFace` appears in
  `res['geom']` — but the original boundary edges' `link_faces` count is
  unchanged afterward. Direct inspection showed why: it built the face from 0
  new verts and 0 new edges, meaning it silently reused *existing, unrelated*
  geometry elsewhere in the mesh rather than attaching to the loop it was given.
  Total mesh boundary count was unchanged before and after. It is not filling
  the requested hole; it is adding a stray duplicate face somewhere already
  manifold.
- `bmesh.ops.contextual_create` (the low-level op behind pressing `F`) returns
  nothing at all for the same loop — `{'faces': [], 'edges': []}`.

The fix was to stop trying to cover the hole and collapse it instead: weld the
loop's own vertices to each other, at a distance scoped to that loop's own
diagonal (`diag × 1.5`). This doesn't fill anything — it shrinks the hole to a
point — but it is provably safe the same way any weld is (§13's bounds-shift
argument), because the weld set is exactly the loop's own verts and nothing
outside that set can move. It closed 72 of 76 loops in one pass; the remainder
(open/branch loops, not closed cycles, so nothing to collapse to a single
point) needed the pooled-open-fragment weld already established for the big
seam. Boundary edges: 223 → 9 → 1 across the two passes, confirmed
shape-identical by render at every step.

**Scope the weld to only the defect's own vertices, never to the faces
touching it.** A second attempt at cleaning up leftover non-manifold edges
(87 of them, all bordering near-zero-area sliver faces) pulled in every vertex
of every face touching each bad edge, not just the edge's own two endpoints —
on the theory that the whole sliver should collapse together. One of those
sliver faces happened to share a vertex with ordinary full-sized geometry
elsewhere, which pulled that real geometry into the same cluster, ballooned
the computed weld distance, and fused unrelated parts of the mesh — boundary
edges spiked from 1 to 44. Rescoping to just the non-manifold edges' own
endpoints (nothing pulled in from attached faces) fixed it: boundary 1 → 11,
non-manifold 87 → 1. The lesson generalizes past this one bug: **the weld set
that is safe is the smallest one that contains the defect, not the smallest
one that seems topologically tidy.**

**The BMVert-reference-invalidation trap (§16's API notes) recurs in a new
shape every time it's forgotten.** It has now been hit three ways in this
project: creating a custom data layer after capturing element references
(fixed by creating the layer first); calling an op that adds geometry while
holding references to *unrelated* elements captured earlier (fixed by never
holding a reference across a mutating call — recompute fresh instead); and,
here, welding one cluster among several invalidating the still-unprocessed
clusters' vertex lists. The durable fix is the same shape every time: tag
elements with a custom data layer created before anything is captured, then
re-query `bm.verts`/`bm.edges` by tag value fresh before each mutating call,
rather than ever holding a Python element reference across one.

---

## 14. Repairing the whole model

Once the build is approved, one pass repairs every mesh in it — the same
weld-before-decimate rule the donors taught, applied to the finished building
rather than to one ornament. It does **no** decimation and changes no shape; it
exists so the tiers in §15 have something sound to decimate.

**Repair the mesh datablocks, not the objects.** The model is 419 objects sharing
356 unique meshes, and five instanced datablocks carry ~98% of all faces.
Repairing datablocks does the work once and it lands on every instance. Repairing
objects would either redo the same work ten times or, if the meshes were made
single-user first, multiply the model's memory by ten.

**The order is load-bearing, and was established by getting it wrong:**

```
weld  →  dissolve degenerate  →  delete loose  →  recalculate normals
```

- **Weld first**, so everything after it sees a connected surface. Recalculating
  normals before welding computes them across cracks.
- **Dissolve degenerate before deleting loose, not after.** Collapsing a
  zero-area face strands the verts and edges that bounded it — so cleaning loose
  geometry first removes some and then manufactures more. The first run of this
  script did exactly that and took the model **from 148 loose to 1,108**.
- **Weld per mesh, measured against a no-weld baseline**, exactly as
  `donor_prep.weld` does. Some meshes in a finished model are already stitched
  and blanket welding damages them.
- **Skip meshes below ~64 faces.** The repair cannot return more than it costs on
  tiny procedural pieces, which are clean anyway.

Whole model, before → after:

| metric | v6 model | repaired base |
|---|---:|---:|
| boundary edges | 274,523 | **21,720** |
| non-manifold edges | 6,086 | 2,780 |
| degenerate faces | 4,372 | **0** |
| loose geometry | 148 | **0** |
| inverted-normal pairs | 6,576 | 4,380 |
| faces | 8,458,017 | 8,419,289 |

Biggest movers: anthemion 26,206 → 1,246, inscription drum 1,243 → **0** boundary
and 3,752 → **0** degenerate, lion 246 → 99, scrolls 52 → 22.

---

## 15. Resolution tiers

For game and real-time use. One property of the model decides the entire strategy
and is worth checking for before starting on any other: almost all of the
geometry is a handful of shared datablocks.

**Instancing is where the leverage is.** Five instanced datablocks are ~98% of
the faces (capital 250k × 10, two scrolls 200k × 10 each, lion 100k × 10,
anthemion 80k × 10). The whole *building* — drum, columns, architrave, meander,
well — is 45,028 faces, 0.5%. So run an inventory reporting `faces × users` per
unique mesh **before** planning any reduction; that last column is what a budget
is actually spent on, and here it says the entire job is five meshes.

**Solve the ratio globally, not per mesh.** A tier's cost is dominated by a
handful of instanced meshes, so solve for the whole-model target:

```
target = fixed_faces + ratio × Σ(faces × users) over decimatable meshes
```

**Protect the small meshes.** Anything at or below ~2,000 faces is excluded and
counted as fixed. That is the building's own structure — 0.5% of the faces and
100% of the silhouette. Decimating it buys nothing measurable and costs the
shape. Hold this threshold fixed across tiers; see *Missing a target on purpose*
below for what happens when it is relaxed to make the numbers work.

**`modifier_apply` refuses multi-user data**, which is the one real API obstacle
here. Copy the mesh (the copy has a single user — a scratch object), decimate the
copy, then repoint all ten instances at the result. The obvious alternative,
making objects single-user first, decimates identical geometry ten times and
multiplies file size by ten.

**Decimate every tier from the base, never from the tier above it.** Error
compounds down a chain, and decimating an already-decimated mesh is a different
operation from decimating the original once.

### Collapse decimation has a floor, and welding makes it worse

The Corinthian capital will not go below ~24,000 faces at *any* ratio:

| approach | result |
|---|---:|
| ratio 0.10 | 24,980 |
| ratio 0.01 | 24,366 |
| ratio 0.01, three passes | 23,818 |
| weld 3e-4 then 0.01 | 23,962 |
| weld 1e-3 then 0.01 | 23,628 |
| weld 3e-3 then 0.01 | **42,739** (worse) |

The floor is intrinsic: COLLAPSE refuses any edge whose removal would create
non-manifold geometry, and deeply undercut acanthus has many touching leaves.
Heavier welding *raises* the floor by fusing more such junctions — the one case in
this project where more welding is actively counterproductive.

### The obvious escape from the floor, and why it was rejected

Voxel remesh sidesteps the floor completely: it discards the input topology and
rebuilds a clean manifold shell from a distance field, which then decimates
freely. It was implemented, measured, and **turned off**.

On every metric it won. Each tier landed within 1.14–1.29× of target — the first
time the low tiers were reachable at all — and lod1's boundary edges fell from
10,706 to **466**, with the remeshed meshes perfectly manifold.

Then someone looked at it. A distance-field rebuild suits organic blobs and ruins
everything this building is made of: the 0.02-thick architrave fragmented, the
fluted shafts shredded, the capitals melted. **Every number improved and the asset
was destroyed.**

This is the clearest case in the project of the two currencies in the preamble
coming apart, and it is worth stating as a rule: *an integrity metric measures
whether a mesh is well-formed, never whether it is still the right shape.* A
remesh scores well precisely because it throws away the topology carrying the
detail. Nothing in an audit can catch that — only a render can.

So the code is **kept and disabled** behind `REMESH_ENABLED = False`, with the
reason recorded at the flag. It is the right tool for a purely organic asset, and
a failure worth not rediscovering. If it is ever re-enabled for such an asset,
three traps are already handled in that code path:

- **Bisect the voxel size against the resulting face count; do not guess it.**
  Aim above target so a final collapse pass can land exactly.
- **The remesher refuses a voxel coarser than the mesh's own thickness** — a thin
  shell falls between samples and nothing is produced. Treat that failure as "too
  few faces" so the search moves to a finer voxel rather than aborting.
- **Voxel remesh discards material slots.** Re-append them, or the tier renders
  at Blender's default near-white and reads as a geometry fault (§9, and the
  appendix).

### Missing a target on purpose

With remesh off, the capital's floor propagates into the whole model: 24,366 × 10
= 243,660 is 80% of both low tiers. lod3 lands at **7.65×** its 40,000 target,
and lod4 cannot be solved at all — it comes out byte-for-byte identical to lod3,
25.5× its 12,000 target.

The floor also fails in a second way at the same time, which is easy to miss if
only the face count is checked: **at 24,366 the capital looks spiky**, because
collapse throws shard artefacts around the same non-manifold junctions it refuses
to collapse through. One root cause, two symptoms — one of them numeric and one
of them only visible in a render.

The tempting fix is to lower the protection threshold so the solver has more to
spend — and that was rejected too, for the same reason. Scaling `KEEP_FACES` down
per tier does let the solver reach the number, but it reaches it by decimating
the 45,028 faces of the building's own structure, which is 0.5% of the model and
100% of its silhouette. **A shredded architrave at 40,000 faces is worth less
than an intact one at 300,000.** The threshold stays fixed and the target stays
missed.

A budget is a proxy for what you actually want. When the only way to hit it is to
spend the thing the budget was protecting, miss it — and record that you missed
it deliberately, or the next session will "fix" it.

Both rejected escapes have the same shape: they hit the number by destroying the
silhouette, one globally (remesh) and one selectively (lowering the protection
threshold). That both were available and both were wrong is the argument for
treating the real fix as upstream — repair the capital master's own topology (124
non-manifold edges, 429 inverted-normal pairs), which should lift the floor and
remove the shard artefacts together, rather than routing around either.

### Follow-up: the upstream fix, worked — and it was only half right

The topology repair proposed just above was carried out (§13's self-collapse
technique): boundary edges 575 → 11, non-manifold 120 → 1, 74 loose verts / 7
loose edges → 0, shape confirmed identical by render at every step. It did
**not** lift the floor. Decimate still plateaus at 23,403 faces, flat from
ratio 0.05 down to 0.0001 — a fully-repaired mesh and a badly-defective one
hit the same wall. The floor's cause (§15 above) was never the non-manifold
edges themselves; it was the *geometric* complexity of the undercuts, which
topology repair does not remove.

**What did lift it: removing geometry that is never seen, not geometry that is
malformed.** The capital is a single zero-thickness shell whose deep undercuts
fold back on themselves — confirmed by bisecting a copy and rendering the cut
face, which showed the "interior" is the mirrored backside of the same
sculpted surface, not a separate redundant wall. A visibility pass — sample
~140 outward viewpoint directions on two spheres around the model (near and
far radius, for both grazing and near-parallel view angles), excluding the
cone beneath the capital that the column shaft physically occupies, and for
each face BVH-raycast from every unresolved viewpoint until *any one* sees it
unoccluded — found that 38.8% of the mesh (96,650 of 248,899 faces) is never
visible from any realistic outside angle. Removing them dropped the floor from
23,403 to **9,156**, more than doubling how far the mesh reduces, and a
14-angle before/after render comparison at the original resolution was
pixel-identical throughout. Two lessons:

- **A defect metric and a waste metric are different things, and each needs
  its own pass.** Non-manifold edges are a defect (the mesh is malformed).
  Permanently-occluded geometry is not a defect (the mesh is well-formed) — it
  is waste, and it does not show up in any integrity audit. Both capped the
  same decimate floor, but only one was fixable by repair.
- **The early-exit form of a visibility sweep is what makes it tractable.**
  Checking every face against every viewpoint is faces × viewpoints ray casts;
  resolving a face the moment *any* viewpoint sees it, and skipping it for all
  later viewpoints, means most of the mesh resolves in the first handful of
  viewpoints and only the genuinely hidden remainder pays for the full sweep.

**Two more reconstruction escapes were tried and rejected before the
visibility pass, both for the same reason as voxel remesh above: they scored
well and looked wrong.**

- **Solidify.** Complex mode (`NON_MANIFOLD`) produced catastrophic spikes —
  confirmed by eye, not caught by any metric. Simple mode (`EXTRUDE`) produced
  the same spikes for an identifiable, checkable reason: with Even Thickness
  on, the offset at a vertex is divided by the cosine of the local half-angle
  to hold wall thickness constant, and this mesh's undercuts fold back close
  enough to themselves that the angle approaches the singularity — measured
  as a **309×** bounding-box blowup with Even Thickness on, 1.01× with it off.
  Turning it off removed the spikes but not the underlying problem: even the
  clean version was "bubbly" — small self-intersecting bulges wherever the
  shell folds tightly, which offsetting a surface along its normal cannot
  avoid on geometry this convoluted, independent of any single parameter.
- **Mesh to Volume → Volume to Mesh.** The clearest case yet of the
  integrity-versus-shape gap: it reported a *perfect* result (0 boundary, 0
  non-manifold, bounding box within 1% of original) and the render was a
  field of disconnected, torn shards — worse than plain voxel remesh, which
  at least stays connected. A closed marching-cubes-style surface extraction
  cannot report a hole; it can still be visibly wrong.

Both failed for the same underlying reason as the capital's whole-mesh
decimate problem: this mesh's geometric complexity — thin, deeply undercut,
self-folding — defeats any method that reconstructs a new surface from a
field (distance, volume, or offset). The one thing that has worked on this
mesh, every time, is an operation that only ever *moves existing vertices a
small proven distance* (weld) or *removes faces already known to be
irrelevant* (visibility culling) — never one that rebuilds the surface.

**The floor being lower does not mean decimation itself is safe now.**
Collapse still produces visibly spiky, broken results on the interior-stripped
mesh at almost any real reduction ratio — still spiky at 76,123 faces, barely
a 2× reduction from the stripped base, not just down near the new floor. The
spike artefact and the hard floor turned out to be two symptoms of the same
undercut complexity, not one symptom that goes away once the other number
improves. The floor moving is necessary, not sufficient. Next candidate
approach, not yet built: decimate a *smooth* stand-in (coarse Voxel Remesh,
which tessellates evenly and has bounded local curvature by construction) down
to a genuinely low proxy, then bake the real surface detail onto it as a
normal map, rather than asking Collapse to simplify the organic surface
directly. This inverts the earlier voxel-remesh rejection rather than
contradicting it: remesh ruins the *asset*, but a remeshed shape is exactly
what a bake proxy is supposed to be — a smooth carrier for detail that lives
in a texture, not in triangles.

---

## 16. Project mechanics

**Never edit a source file in place.** Open, then *immediately* save-as the new
working file, then edit. The result is a chain of versioned checkpoints:

```
frieze-v1 → frieze-ring → thick-drum → v2 → v3 → v4 → v5 → v6
```

With no version control, this *is* the version control — and it makes "rebuild
the whole thing with a different donor and compare" cheap.

**Put the build's identity in the filename**, composed in one place:

```
Pulgas-Water-Temple-live-cornice-frieze-ring-v6-tripo2-s90-newcap90.blend
                                              │      │    └ base: new capitals, 90% columns
                                              │      └ FRIEZE_SCALE 0.90
                                              └ which lion master
```

No build can overwrite another, and variants sit side by side for comparison.

**Keep the losing option and label it.** Both the lion-half choice and the Leeds
fallback are one-line reversals because the rejected option was kept and
documented rather than deleted.

**Renders are outputs, not artifacts.** Every image in this project is
regenerable from a `.blend` that is still on disk, so `renders/` is disposable
and is not maintained. What is *not* regenerable is the number a render was used
to decide — so the numbers live in the docs, and the pixels do not need to be
kept. Keep a table mapping each kind of image to the one command that rebuilds
it. The corollary is that comparison scripts must carry their own camera and
lights (§12), or the images stop being regenerable in any meaningful sense.

**Say when a draft is a draft.** `integrate_lion_v1.py` states in its own
docstring that its scale and projection are estimated from a crude placeholder
and not yet confirmed against the user's judgement. Without that line, the next
session reads seated, plausible-looking geometry as approved geometry, and starts
protecting it.

---

## 17. Working with the agent

- **Ask for the measurement, not the opinion.** Nearly every decision here was
  settled by a number, and several contradicted a confident guess — including the
  "always weld" rule in §4, which measurement turned into "measure, then weld".
- **Write the plan down before implementing it**, with the *reason* for the
  sequencing. That reason is usually a dependency invisible in the code, and it
  is the first thing lost between sessions.
- **State next to a constant what it was derived from.** That comment is what lets
  a later session notice that changing X invalidates it.
- **Separate shared hygiene from shape-specific logic.** `donor_prep.py` handles
  any donor; symmetry fitting and half-mirroring stay in the lion's own script,
  because they would be nonsense on a radial element like a capital.
- **Put the reasoning in the module docstring.** With no version control, a
  script's docstring is the only place the *why* survives, and it is what the next
  session reads first. The docstrings here run to several hundred words and carry
  the measurements behind each decision — that is the knowledge base, and this
  guide is its distillation.
- **A docstring that contradicts its own code is worse than none.** Both are read
  as authoritative and only one is executed. When the code's ordering is
  load-bearing, state the reason inline at the line that depends on it, so the
  two cannot drift apart unnoticed.
- **Distinguish "this failed" from "this cannot work."** The first is a
  measurement, the second is a claim about all parameter values, and the second
  needs the range that was searched attached to it (§13). An agent will otherwise
  cite its own prior negative result as settled fact.
- **Re-derive constants when transferring a method to a new class of input.**
  The procedure usually transfers; the tuned numbers usually do not. This is the
  single most productive question to ask of any step being reused.

### Scripts versus a live connection

There is another way for an agent to drive Blender: an MCP addon
([`MCPBlender/blender-mcp`](https://github.com/MCPBlender/blender-mcp) and
similar) that attaches to a *running* Blender over a socket, exposing scene
inspection, object manipulation, viewport screenshots, asset-library search, and
an `execute_blender_code` tool that runs arbitrary Python in the session.

Worth knowing about, and worth being deliberate about, because the two modes are
good at opposite things:

| | headless script chain (this project) | live MCP session |
|---|---|---|
| reproducible | yes — rerun the chain | no — session state is not a record |
| reviewable before it runs | yes, it is a file | partly, code is emitted ad hoc |
| visual feedback loop | slow: render, then look | fast: screenshot the viewport |
| exploration | awkward | its natural strength |
| unattended multi-step builds | its natural strength | fragile, times out |

Everything in this guide depends on the left column. The versioned file chain
*is* the version control (§16); a constant printed for the next step only helps
if there is a next step to run; "rebuild the whole thing with a different donor
and compare" is only cheap because the build is a program. A live session
produces geometry with no reproducible provenance, which is the one thing this
project could not afford.

The reasonable division: **explore and diagnose live if you like, then write the
finding into a script and let the script be the record.** A viewport screenshot
is an excellent way to answer "what is going on here"; it is not an artifact, and
neither is the ad-hoc code that produced the state it shows.

Two notes if you do use one:

- Its own guidance converges on §3 and §12 from the other direction — screenshot
  before the change, screenshot after it, and check intermediate steps rather
  than only the end. That habit is apparently what anyone driving Blender through
  a model arrives at.
- But its verification story is **screenshots only**, with no integrity audit
  anywhere in it. That is exactly the half of the preamble's two currencies that
  a picture cannot supply — non-manifold edges, degenerate faces and inverted
  normals all render perfectly (§12). Run `audit_mesh_quality.py` against
  anything a live session produced before believing it.

---

## Result

| | before | after build | after repair (§14) |
|---|---:|---:|---:|
| model faces | 30.5M | 8.46M | **8.42M** |
| boundary edges | ~1.1M | 274,523 | **21,720** |
| degenerate faces | — | 4,372 | **0** |
| loose geometry | — | 148 | **0** |
| duplicate verts | ~157k | 51,515 | — |
| capitals | procedural, 6,080 f | Temple of Vesta master, 250k f | |
| scroll | raw donor ×20, 1.42M f each | master, 200k f | |

Plus four decimated tiers off the repaired base (§15), from 611k down to 306k
faces. The two lowest miss their targets, deliberately and on the record: the
capital's collapse floor sets them, and the two available ways around it both
cost the building's silhouette.

---

## Appendix — Blender API notes worth having on hand

Environment: Blender 5.2.0 LTS, `--background --python <script>`. The render
engine identifier is **`BLENDER_EEVEE`** (not `BLENDER_EEVEE_NEXT`).

- **Read bounds from `ob.data.vertices`, not `ob.bound_box`**, whenever you have
  transformed mesh *data*. `bound_box` is cached and reports pre-transform
  extents. Object-level transforms refresh it normally.
- **Set `rotation_mode = "XYZ"` immediately after appending an object.** Appended
  objects arrive in `QUATERNION` mode, where assigning `rotation_euler` does
  nothing at all.
- **Check `det == +1`** on any rotation matrix assembled from axis vectors.
  `(tangent, radial, up)` as columns is a reflection; `(tangent, −radial, up)` is
  the rotation.
- **Unwrap `atan2` before taking min/max.** It wraps at ±π, so an angular bounding
  box straddling the seam reports ~360° instead of ~0°. Unwrap about the circular
  mean: `(t − ctr + π) mod 2π − π`.
- **`bpy.context.view_layer.update()`** after changing transforms, before reading
  world-space positions back.
- **Capture a datablock's name before removing it** — touching it afterwards
  raises `ReferenceError: StructRNA has been removed`.
- **Assign materials to the mesh when objects share a datablock**, and to the
  object when they don't. A master arrives with no material and renders at
  Blender's default near-white, which looks like a geometry fault. Inherit the
  outgoing element's material the same way you inherit its position.
- **Import glTF by diffing `bpy.data.objects`** around the call. With a scene
  already loaded, "take the last mesh" grabs an unrelated object.
- **`modifier_apply` refuses multi-user mesh data outright.** Copy the datablock,
  apply on the single-user copy, repoint the instances (§15).
- **`voxel_remesh` discards material slots and raises `RuntimeError` on a voxel
  too coarse for the mesh's thickness.** Re-append materials; treat the exception
  as "zero faces" so a bisection search continues instead of aborting.
- **Snapshot the work list before a loop that adds or removes datablocks.**
  Iterating `bpy.data.meshes` live while the body creates and deletes meshes is
  unsafe. Build the list of `(mesh, objects)` tuples first, then iterate it.
- **Do modifier work on one reusable scratch object**, not on the real objects.
  Applying a modifier requires selection and an active object, and doing that to
  live objects risks disturbing their transforms.
