import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import math
import os
import json
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from paths import ROOT, CORNICE_CLEAN as BLEND  # noqa: E402,F401
CY = -0.5456366539001465
RMAP = 0.300
MODULE_ANGLE = math.radians(36.0)
MODULE_ARC = RMAP * MODULE_ANGLE
LION_ANGLE = math.atan2(0.0756035098, 0.2408188273)

if bpy.data.filepath != BLEND:
    bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
main_scene = bpy.data.scenes.get("Scene") or scene
if bpy.context.window.scene != main_scene:
    bpy.context.window.scene = main_scene

working = bpy.data.collections.get("CORNICE_REFINED_WORKING")
source = bpy.data.collections.get("CORNICE_SOURCE_LION")
anchor = bpy.data.objects.get("CORNICE_REFINED_MASTER_36DEG")
if not working or not source or not anchor:
    raise RuntimeError("Phase 1 collections/anchor missing")

# Clear only previously generated working components, never protected geometry.
for obj in list(working.objects):
    if obj != anchor:
        data = obj.data if obj.type == 'MESH' else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0:
            bpy.data.meshes.remove(data)

stone = bpy.data.materials.get("Raised cast-stone ornament")
if stone is None:
    stone = bpy.data.materials.new("Raised cast-stone ornament")
    stone.diffuse_color = (0.305, 0.315, 0.320, 1)
    stone.roughness = 0.85

def create_mesh(name, verts, faces, material=stone, smooth=True):
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    working.objects.link(obj)
    if material:
        mesh.materials.append(material)
    if smooth:
        for p in mesh.polygons:
            p.use_smooth = True
    obj.parent = anchor
    obj.matrix_parent_inverse = anchor.matrix_world.inverted()
    return obj

def map_point(u, r, z):
    theta = LION_ANGLE + u / RMAP
    return (r * math.cos(theta), CY + r * math.sin(theta), z)

def deform_planar_object(obj):
    # Planar convention: X=tangential arc, Y=radius, Z=height.
    for v in obj.data.vertices:
        u, r, z = v.co.x, v.co.y, v.co.z
        v.co = map_point(u, r, z)
    obj.data.update()

def apply_modifier(obj, name):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=name)

def tri_count(obj):
    return sum(max(0, len(p.vertices)-2) for p in obj.data.polygons) if obj.type == 'MESH' else 0

# -----------------------------------------------------------------------------
# LION: scan-derived symmetrical relief from the approved crlnvl donor.
# -----------------------------------------------------------------------------
src = max((o for o in source.objects if o.type == 'MESH'), key=lambda o: len(o.data.polygons))
world_verts = [src.matrix_world @ v.co for v in src.data.vertices]
scan_normal = Vector((1.0,1.0,0.0)).normalized()
scan_tangent = Vector((-1.0,1.0,0.0)).normalized()
donor_t_center=-17.5
donor_half_width=4.8
donor_z_min,donor_z_max=9.8,21.2
depth_back_s,depth_front_s=2.0,-8.0
half_width=0.0235
target_z_min,target_z_max=0.3150,0.3595

# Retain actual donor triangles from the better-preserved increasing-tangent half.
# Plaque/cornice triangles are rejected by the rear-depth and vertical cuts.
dcoords=[]
for v in world_verts:
    dcoords.append((v.dot(scan_tangent)-donor_t_center,v.dot(scan_normal),v.z))
selected=[]
for p in src.data.polygons:
    cs=[dcoords[i] for i in p.vertices]
    cx=sum(c[0] for c in cs)/len(cs)
    if not (-0.16<=cx<=donor_half_width):
        continue
    def lion_oval(c):
        tx=max(0.0,c[0])
        return (-0.24<=c[0]<=donor_half_width and c[1]<=depth_back_s and
                (tx/donor_half_width)**2+((c[2]-15.5)/5.7)**2<=1.0)
    if not all(lion_oval(c) for c in cs):
        continue
    selected.append(tuple(p.vertices))
used=sorted(set(i for f in selected for i in f))
remap={old:i for i,old in enumerate(used)}
verts=[]
for old in used:
    tx,ds,dz=dcoords[old]
    # Clamp straddling centerline triangles onto the mirror plane for a watertight seam.
    u=max(0.0,tx)/donor_half_width*half_width
    z=target_z_min+(dz-donor_z_min)/(donor_z_max-donor_z_min)*(target_z_max-target_z_min)
    relief=max(0.0,min(1.0,(depth_back_s-ds)/(depth_back_s-depth_front_s)))
    r=0.2888+0.0262*(relief**0.88)
    verts.append((u,r,z))
faces=[tuple(remap[i] for i in f) for f in selected]

lion=create_mesh("CORNICE_LION_MASTER_CC_BY_4_0",verts,faces,smooth=True)
lion.parent=None
lion.matrix_world.identity()
mir=lion.modifiers.new("Architectural centerline symmetry","MIRROR")
mir.use_axis[0]=True; mir.use_clip=True; mir.use_mirror_merge=True; mir.merge_threshold=0.00025
apply_modifier(lion,mir.name)
# Preserve the tested donor surface exactly; its cropped perimeter is buried
# inside the continuous backing rather than exposed as a paper-thin edge.
for v in lion.data.vertices:
    v.co.x=max(-half_width,min(half_width,v.co.x))
    v.co.y=max(0.2875,min(0.3150,v.co.y))
    v.co.z=max(target_z_min,min(target_z_max,v.co.z))
# Normalize the cropped donor face to 80–85% of the ornament field height and
# the intended architectural mask width without changing radial relief.
max_u=max(abs(v.co.x) for v in lion.data.vertices)
min_z=min(v.co.z for v in lion.data.vertices); max_z=max(v.co.z for v in lion.data.vertices)
for v in lion.data.vertices:
    if max_u>1e-8: v.co.x*=0.0235/max_u
    if max_z-min_z>1e-8: v.co.z=0.3145+(v.co.z-min_z)/(max_z-min_z)*0.0450
deform_planar_object(lion)
lion.parent=anchor; lion.matrix_parent_inverse=anchor.matrix_world.inverted()
lion["source_asset_title"]="Lion Head"
lion["source_creator"]="crlnvl"
lion["source_url"]="https://sketchfab.com/3d-models/lion-head-e5fa840dc46b489dab96ac262897e588"
lion["source_license"]="CC BY 4.0"
lion["source_license_url"]="https://creativecommons.org/licenses/by/4.0/"
lion["donor_half_used"]="increasing plaque-tangent half from true diagonal frontal basis, centerline mirrored"
lion["adaptation"]="actual donor triangles cropped from wall/plaque; preserved half symmetrized; flattened to architectural relief; cropped perimeter deeply seated into backing"

# -----------------------------------------------------------------------------
# General solid leaf generator, used for anthemion and acanthus.
# -----------------------------------------------------------------------------
def solid_leaf(name, ub,zb,ut,zt,width,r_back,r_face,curve=0.0,segments=12,across=6,tip_bias=1.0):
    vs=[]; fs=[]; front_idx=[]; back_idx=[]
    du=ut-ub; dz=zt-zb; ln=max(1e-6,math.hypot(du,dz))
    pu=-dz/ln; pz=du/ln
    for j in range(segments+1):
        t=j/segments
        # Convex, pointed leaf body; compact at the base and sharpened at the crown.
        wf=(math.sin(math.pi*t)**0.72)*(0.72+0.28*t)
        uc=ub+du*t+curve*math.sin(math.pi*t)
        zc=zb+dz*t
        for k in range(across+1):
            s=2*k/across-1
            ww=max(0.00012,width*wf)
            u=uc+pu*ww*s; z=zc+pz*ww*s
            convex=max(0.0,1-s*s)
            rib=math.exp(-((s/0.24)**2))
            rr=r_back+(r_face-r_back)*(0.40+0.48*convex+0.12*rib)*math.sin(math.pi*(0.04+0.92*t))**0.35
            front_idx.append(len(vs)); vs.append(map_point(u,rr,z))
            back_idx.append(len(vs)); vs.append(map_point(u,r_back-0.0012,z))
    cols=across+1
    def F(j,k): return front_idx[j*cols+k]
    def B(j,k): return back_idx[j*cols+k]
    for j in range(segments):
        for k in range(across):
            fs += [(F(j,k),F(j,k+1),F(j+1,k+1)),(F(j,k),F(j+1,k+1),F(j+1,k))]
            fs += [(B(j,k),B(j+1,k+1),B(j,k+1)),(B(j,k),B(j+1,k),B(j+1,k+1))]
    for j in range(segments):
        for k in (0,across):
            if k==0: fs += [(F(j,k),F(j+1,k),B(j+1,k)),(F(j,k),B(j+1,k),B(j,k))]
            else: fs += [(F(j,k),B(j+1,k),F(j+1,k)),(F(j,k),B(j,k),B(j+1,k))]
    for k in range(across):
        fs += [(F(0,k),B(0,k+1),F(0,k+1)),(F(0,k),B(0,k),B(0,k+1))]
        fs += [(F(segments,k),F(segments,k+1),B(segments,k+1)),(F(segments,k),B(segments,k+1),B(segments,k))]
    return create_mesh(name,vs,fs,smooth=True)

def tube(name, points, radii, sides=8, smooth=True):
    vs=[]; fs=[]; n=len(points)
    for i,(u,r,z) in enumerate(points):
        if i==0: du=points[1][0]-u; dz=points[1][2]-z
        elif i==n-1: du=u-points[i-1][0]; dz=z-points[i-1][2]
        else: du=points[i+1][0]-points[i-1][0]; dz=points[i+1][2]-points[i-1][2]
        ln=max(1e-8,math.hypot(du,dz)); du/=ln; dz/=ln
        th=LION_ANGLE+u/RMAP
        radial=Vector((math.cos(th),math.sin(th),0))
        tangent=Vector((-math.sin(th),math.cos(th),0))
        vertical=Vector((0,0,1))
        side2=(-dz*tangent+du*vertical).normalized()
        center=Vector(map_point(u,r,z))
        rad=radii[i] if hasattr(radii,'__len__') else radii
        for s in range(sides):
            a=2*math.pi*s/sides
            vs.append(tuple(center+rad*(math.cos(a)*radial+math.sin(a)*side2)))
    for i in range(n-1):
        for s in range(sides):
            a=i*sides+s; b=i*sides+(s+1)%sides; c=(i+1)*sides+(s+1)%sides; d=(i+1)*sides+s
            fs += [(a,b,c),(a,c,d)]
    fs.append(tuple(range(sides-1,-1,-1)))
    fs.append(tuple((n-1)*sides+s for s in range(sides)))
    return create_mesh(name,vs,fs,smooth=smooth)

def bezier_points(p0,p1,p2,p3,n,r=0.298):
    out=[]
    for i in range(n):
        t=i/(n-1); q=1-t
        u=q**3*p0[0]+3*q*q*t*p1[0]+3*q*t*t*p2[0]+t**3*p3[0]
        z=q**3*p0[1]+3*q*q*t*p1[1]+3*q*t*t*p2[1]+t**3*p3[1]
        out.append((u,r,z))
    return out

# -----------------------------------------------------------------------------
# SEVEN-LOBED ANTHEMION, centered exactly 18 degrees from the lion.
# -----------------------------------------------------------------------------
PU=RMAP*math.radians(18.0)
pbz=0.3160
palmette=[]
specs=[
    (0.000,0.3605,0.0068,0.0000),
    (-0.008,0.3565,0.0065,-0.0010),(0.008,0.3565,0.0065,0.0010),
    (-0.017,0.3505,0.0062,-0.0018),(0.017,0.3505,0.0062,0.0018),
    (-0.027,0.3430,0.0058,-0.0025),(0.027,0.3430,0.0058,0.0025),
]
for idx,(off,ztip,w,cv) in enumerate(specs,1):
    palmette.append(solid_leaf(f"ANTHEMION seven-lobe leaf {idx:02d}",PU,pbz,PU+off,ztip,w,0.2955,0.3065,curve=cv,segments=12,across=6))

# Raised perimeter arch: deliberate half-oval frame around the fan.
arch=[]
for i in range(33):
    a=math.pi-math.pi*i/32
    u=PU+0.033*math.cos(a)
    z=pbz+0.002+0.044*math.sin(a)
    arch.append((u,0.3088,z))
tube("ANTHEMION raised perimeter arch",arch,[0.0017]*len(arch),sides=8)

# Compact leaf knot and restrained base volutes.
solid_leaf("ANTHEMION compact base leaf knot",PU,pbz-0.001,PU,pbz+0.011,0.008,0.296,0.308,segments=9,across=6)
for side in (-1,1):
    pts=[]
    center_u=PU+side*0.013
    for i in range(25):
        a=2.1*math.pi*i/24
        rad=0.010*(1-i/30)
        pts.append((center_u+side*rad*math.cos(a),0.303,pbz+0.003+rad*0.65*math.sin(a)))
    tube(f"ANTHEMION restrained base volute {'L' if side<0 else 'R'}",pts,[0.0018*(1-0.45*i/(len(pts)-1)) for i in range(len(pts))],sides=8)

# -----------------------------------------------------------------------------
# ACANTHUS RINCEAUX: two S-stems, counter-curls, overlapping leaves, one fruit cluster.
# -----------------------------------------------------------------------------
stem_specs=[
    ("left",(-PU,0.320),(-0.072,0.335),(-0.038,0.310),(-0.022,0.328)),
    ("right",(0.023,0.329),(0.045,0.310),(0.071,0.337),(PU,0.320)),
]
for sname,p0,p1,p2,p3 in stem_specs:
    pts=bezier_points(p0,p1,p2,p3,30,r=0.299)
    radii=[0.0032-(0.0015*i/(len(pts)-1)) for i in range(len(pts))]
    tube(f"RINCEAUX primary S-stem {sname}",pts,radii,sides=10)

# Principal volutes and smaller counter-curls.
for side,cu in [(-1,-0.050),(1,0.054)]:
    for kind,rad,nturn,z0 in [("principal",0.015,1.25,0.335),("counter",0.009,1.0,0.322)]:
        pts=[]
        for i in range(28):
            a=2*math.pi*nturn*i/27
            rr=rad*(1-0.58*i/27)
            pts.append((cu+side*rr*math.cos(a),0.301,z0+rr*0.65*math.sin(a)))
        tube(f"RINCEAUX {kind} volute {'L' if side<0 else 'R'}",pts,[0.0025*(1-0.5*i/27) for i in range(28)],sides=8)

# Three or four substantial leaves per side, deliberately varied.
leaf_specs=[
    (-0.079,0.320,-0.066,0.342,0.0075,-0.0020),
    (-0.062,0.329,-0.045,0.348,0.0070,0.0015),
    (-0.047,0.318,-0.033,0.335,0.0065,-0.0010),
    (-0.030,0.327,-0.018,0.348,0.0063,0.0012),
    (0.029,0.327,0.018,0.348,0.0063,-0.0012),
    (0.045,0.318,0.032,0.337,0.0066,0.0010),
    (0.061,0.330,0.047,0.349,0.0071,-0.0015),
    (0.078,0.320,0.066,0.342,0.0075,0.0020),
]
for idx,(ub,zb,ut,zt,w,cv) in enumerate(leaf_specs,1):
    solid_leaf(f"RINCEAUX overlapping acanthus leaf {idx:02d}",ub,zb,ut,zt,w,0.296,0.3055,curve=cv,segments=10,across=5)

# Side mane transitions: broad leaf forms overlap the donor relief edges.
for side in (-1,1):
    solid_leaf(f"LION mane-to-foliage transition {'L' if side<0 else 'R'}",side*0.020,0.318,side*0.032,0.348,0.0085,0.296,0.3075,curve=side*0.0015,segments=11,across=6)

# Restrained cluster of four berries, compact rather than necklace-like.
berry_centers=[(0.068,0.304,0.331),(0.073,0.306,0.334),(0.076,0.303,0.329),(0.071,0.305,0.327)]
for i,(u,r,z) in enumerate(berry_centers,1):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=0.0030,location=map_point(u,r,z))
    o=bpy.context.object; o.name=f"RINCEAUX compact berry cluster {i:02d}"
    for c in list(o.users_collection): c.objects.unlink(o)
    working.objects.link(o); o.data.materials.append(stone); o.parent=anchor; o.matrix_parent_inverse=anchor.matrix_world.inverted()
    # Slight ovoid scale, aligned radially enough for carved fruit.
    o.scale=(0.85,0.85,1.15)

# -----------------------------------------------------------------------------
# SHALLOW CONTINUOUS LEAF-AND-TONGUE MOLDING for exactly one 36-degree cell.
# -----------------------------------------------------------------------------
def annular_strip(name,u0,u1,r0,r1,z0,z1,segments=48):
    vs=[];fs=[]
    for i in range(segments+1):
        u=u0+(u1-u0)*i/segments
        vs += [map_point(u,r0,z0),map_point(u,r1,z0),map_point(u,r1,z1),map_point(u,r0,z1)]
    for i in range(segments):
        a=4*i; b=4*(i+1)
        fs += [(a+0,b+0,b+1),(a+0,b+1,a+1),(a+1,b+1,b+2),(a+1,b+2,a+2),
               (a+2,b+2,b+3),(a+2,b+3,a+3),(a+3,b+3,b+0),(a+3,b+0,a+0)]
    fs += [(0,1,2),(0,2,3),(4*segments,4*segments+2,4*segments+1),(4*segments,4*segments+3,4*segments+2)]
    return create_mesh(name,vs,fs,smooth=False)

u0,u1=-MODULE_ARC/2,MODULE_ARC/2
annular_strip("LEAF-AND-TONGUE narrow upper fillet",u0,u1,0.2945,0.2990,0.3153,0.3172,segments=64)
annular_strip("LEAF-AND-TONGUE small lower ridge",u0,u1,0.2938,0.2972,0.3105,0.3121,segments=64)
nt=20
for i in range(nt):
    u=u0+(i+0.5)*(u1-u0)/nt
    solid_leaf(f"LEAF-AND-TONGUE downward leaf {i+1:02d}",u,0.3160,u,0.3096,0.0020,0.2948,0.3002,segments=7,across=4)

# Record final component metadata and license modifications.
attr=bpy.data.texts.get("ORNAMENT_SOURCE_AND_LICENSE")
attr.clear()
attr.write(
    "Asset title: Lion Head\n"
    "Creator: crlnvl\n"
    "Original URL: https://sketchfab.com/3d-models/lion-head-e5fa840dc46b489dab96ac262897e588\n"
    "Exact license: Creative Commons Attribution 4.0 International (CC BY 4.0)\n"
    "License URL: https://creativecommons.org/licenses/by/4.0/\n"
    "Date acquired: 2026-08-05\n"
    "Modifications performed: Removed wall/plaque/background by direct triangle crop in the plaque's diagonal basis; selected the better-preserved increasing plaque-tangent half; centerline mirrored; flattened to approximately 35% relief depth; crop perimeter deeply seated into the continuous cornice backing; mapped to cylindrical cornice.\n"
    "Usage confirmation: Only lion-derived geometry was used from the donor. Palmette, rinceaux, fruit cluster, and leaf-and-tongue molding are newly modeled Blender geometry.\n"
)

components=[o for o in working.objects if o!=anchor]
for o in components:
    o["cornice_master_component"] = True
    o.hide_render=False; o.hide_set(False)

scene["cornice_working_phase"]="MANDATORY_SINGLE_MASTER_CHECKPOINT_BUILD"
scene["cornice_master_component_count"]=len(components)
scene["cornice_lion_triangles"]=tri_count(lion)
scene["cornice_master_triangles"]=sum(tri_count(o) for o in components)
scene["tripo_objects_remaining"]=sum(1 for o in bpy.data.objects if 'tripo' in o.name.lower())
bpy.ops.wm.save_as_mainfile(filepath=BLEND)

print(json.dumps({
    "saved":bpy.data.filepath,
    "lion_triangles":scene["cornice_lion_triangles"],
    "master_triangles":scene["cornice_master_triangles"],
    "component_count":len(components),
    "tripo_remaining":scene["tripo_objects_remaining"],
    "lion_bounds":[list(lion.dimensions),list(lion.location)],
    "objects":[o.name for o in components],
},indent=2))
