"""
Tablet sequence, hinged lid variant (Blender 5.2 / Cycles, OptiX)

Usage:
  blender -b --factory-startup -noaudio -P scene_tablet_hinge.py -- --frames 1,55,90,140 --samples 48 --res 1280x720 --out test
  blender -b --factory-startup -noaudio -P scene_tablet_hinge.py -- --anim --samples 64 --res 1920x1080 --out frames_hinge

Timeline (frames):
  1-38    closed tablet, camera orbiting
  38-78   top half swings open on a hinge at the far edge, the cut face opens
  44-120  particles rise out of the granular interior
  78-144  orbit continues, particles drift apart

The tablet is built as one piece and cut in two with a boolean. The cut faces
inherit the cutter cube's material (the interior): material_mode='TRANSFER'.
"""

import bpy
import math
import os
import random
import sys

# --------------------------------------------------------------------------
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def flag(name):
    return name in argv


FRAME_START = int(arg("--start", 1))
FRAME_END = int(arg("--end", 144))
SAMPLES = int(arg("--samples", 64))
OUT = os.path.abspath(arg("--out", "./test_split"))
RES_X, RES_Y = (int(v) for v in arg("--res", "1920x1080").split("x"))
TEST_FRAMES = [int(f) for f in arg("--frames", "90").split(",")]
RENDER_ANIM = flag("--anim")

random.seed(11)

# --------------------------------------------------------------------------
CREAM = "#F4EDE6"
CREAM_DEEP = "#E7DDD0"
OLIVE = "#404F1D"
OLIVE_DARK = "#2F3B15"
INTERIOR = "#5A6636"   # cut face matrix
LIME = "#C9DE6E"       # granules
SAGE = "#A8B87A"

# timing
SPLIT_IN, SPLIT_OUT = 38, 78

# HINGE variant: the top half opens from its edge, not from its center.
#
# The hinge must be on the FAR edge (+Y). On the near edge the lid tips toward
# the camera and hides the bottom half's cut face. On the far edge it swings up
# and BACK, and both cut faces stay visible.
HINGE_Y = 0.97         # hinge axis position along the radius
# -58 was tried: the lid turned almost face-on and read as a flat disc.
# At -42 the cut face reads and the shell's top surface still shows its volume.
HINGE_ANGLE = math.radians(-42)   # negative = the near edge lifts
HINGE_LIFT = 0.10      # raise the hinge slightly so the contact seam is hidden


def srgb_to_linear(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, alpha)


def set_in(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value
        return True
    return False


def apply_mods(obj):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def smooth(obj, angle=35):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth()
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle))
    except Exception as e:
        print("shade_auto_smooth skipped:", e)


# --------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

# --------------------------------------------------------------------------
# World
# --------------------------------------------------------------------------
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
wn, wl = world.node_tree.nodes, world.node_tree.links
wn.clear()

w_out = wn.new("ShaderNodeOutputWorld")
w_bg = wn.new("ShaderNodeBackground")
w_ramp = wn.new("ShaderNodeValToRGB")
w_grad = wn.new("ShaderNodeTexGradient")
w_map = wn.new("ShaderNodeMapping")
w_coord = wn.new("ShaderNodeTexCoord")

w_map.inputs["Rotation"].default_value = (0, math.radians(90), 0)
w_ramp.color_ramp.elements[0].position = 0.00
w_ramp.color_ramp.elements[0].color = srgb_to_linear(CREAM_DEEP)
w_ramp.color_ramp.elements[1].position = 0.62
w_ramp.color_ramp.elements[1].color = srgb_to_linear(CREAM)
w_bg.inputs["Strength"].default_value = 1.0

wl.new(w_coord.outputs["Window"], w_map.inputs["Vector"])
wl.new(w_map.outputs["Vector"], w_grad.inputs["Vector"])
wl.new(w_grad.outputs["Fac"], w_ramp.inputs["Fac"])
wl.new(w_ramp.outputs["Color"], w_bg.inputs["Color"])
wl.new(w_bg.outputs["Background"], w_out.inputs["Surface"])

# --------------------------------------------------------------------------
# Shell material
# --------------------------------------------------------------------------
mat_shell = bpy.data.materials.new("Shell")
mat_shell.use_nodes = True
nt = mat_shell.node_tree
bsdf = nt.nodes["Principled BSDF"]
set_in(bsdf, "Base Color", srgb_to_linear(OLIVE))
set_in(bsdf, "Roughness", 0.62)
set_in(bsdf, "Specular IOR Level", 0.35)

n1 = nt.nodes.new("ShaderNodeTexNoise")
n1.inputs["Scale"].default_value = 900.0
n1.inputs["Detail"].default_value = 8.0
bmp = nt.nodes.new("ShaderNodeBump")
bmp.inputs["Strength"].default_value = 0.09
bmp.inputs["Distance"].default_value = 0.002
nt.links.new(n1.outputs["Fac"], bmp.inputs["Height"])
nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])

# --------------------------------------------------------------------------
# Cut face (interior) material: lime granules in an olive matrix
# --------------------------------------------------------------------------
mat_core = bpy.data.materials.new("Core")
mat_core.use_nodes = True
ct = mat_core.node_tree
cb = ct.nodes["Principled BSDF"]
set_in(cb, "Roughness", 0.82)
set_in(cb, "Specular IOR Level", 0.2)

vor = ct.nodes.new("ShaderNodeTexVoronoi")
vor.feature = "F1"
vor.inputs["Scale"].default_value = 52.0

# hard-edged granules, so CONSTANT interpolation
gran = ct.nodes.new("ShaderNodeValToRGB")
gran.color_ramp.interpolation = "CONSTANT"
gran.color_ramp.elements[0].position = 0.0
gran.color_ramp.elements[0].color = srgb_to_linear(LIME)
gran.color_ramp.elements[1].position = 0.16
gran.color_ramp.elements[1].color = srgb_to_linear(INTERIOR)
ct.links.new(vor.outputs["Distance"], gran.inputs["Fac"])

# a second Voronoi breaks up granule size so they are not all the same
vor2 = ct.nodes.new("ShaderNodeTexVoronoi")
vor2.inputs["Scale"].default_value = 130.0
mix = ct.nodes.new("ShaderNodeMixRGB")
mix.blend_type = "MULTIPLY"
mix.inputs["Fac"].default_value = 0.35
ct.links.new(gran.outputs["Color"], mix.inputs["Color1"])
ct.links.new(vor2.outputs["Distance"], mix.inputs["Color2"])
ct.links.new(mix.outputs["Color"], cb.inputs["Base Color"])

# rough cut face, like pressed powder
cbump = ct.nodes.new("ShaderNodeBump")
cbump.inputs["Strength"].default_value = 0.45
cbump.inputs["Distance"].default_value = 0.01
ct.links.new(vor.outputs["Distance"], cbump.inputs["Height"])
ct.links.new(cbump.outputs["Normal"], cb.inputs["Normal"])

# --------------------------------------------------------------------------
# Tablet body: built as one piece, then cut in two
# --------------------------------------------------------------------------
bpy.ops.mesh.primitive_cylinder_add(vertices=192, radius=1.0, depth=0.34, location=(0, 0, 0))
base = bpy.context.active_object
base.name = "Tablet_base"

bev = base.modifiers.new("Bevel", "BEVEL")
bev.width = 0.085
bev.segments = 12
bev.limit_method = "ANGLE"
bev.angle_limit = math.radians(30)
apply_mods(base)                      # must be applied BEFORE the cut
base.data.materials.append(mat_shell)

# cutter cubes: their material is transferred to the cut face
def make_cutter(name, z):
    bpy.ops.mesh.primitive_cube_add(size=8, location=(0, 0, z))
    c = bpy.context.active_object
    c.name = name
    c.data.materials.append(mat_core)
    c.hide_render = True
    return c


cut_lo = make_cutter("Cut_lower", -4.0)   # removes z<0, keeps the TOP half
cut_hi = make_cutter("Cut_upper", 4.0)    # removes z>0, keeps the BOTTOM half


def make_half(name, cutter):
    obj = base.copy()
    obj.data = base.data.copy()
    obj.name = name
    scene.collection.objects.link(obj)
    b = obj.modifiers.new("Cut", "BOOLEAN")
    b.operation = "DIFFERENCE"
    b.object = cutter
    try:
        b.solver = "EXACT"
    except Exception:
        pass
    try:
        b.material_mode = "TRANSFER"   # cut face takes the cutter's material
    except Exception as e:
        print("could not set material_mode:", e)
    apply_mods(obj)                    # the halves will move, so bake the boolean
    smooth(obj)
    return obj


top = make_half("Half_top", cut_lo)
bottom = make_half("Half_bottom", cut_hi)

# the base mesh and cutters are no longer needed
for o in (base, cut_lo, cut_hi):
    bpy.data.objects.remove(o, do_unlink=True)

# --------------------------------------------------------------------------
# Equator band: just below the cut line, belongs to the bottom half
# --------------------------------------------------------------------------
# major+minor must be SLIGHTLY larger than the shell radius (1.0). At exactly
# 1.0 the band sinks into the surface and disappears in the closed frames.
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.970, minor_radius=0.034,
    major_segments=180, minor_segments=20, location=(0, 0, -0.075),
)
band = bpy.context.active_object
band.name = "Band"
bpy.ops.object.shade_smooth()

mat_band = bpy.data.materials.new("Band_Mat")
mat_band.use_nodes = True
bb = mat_band.node_tree.nodes["Principled BSDF"]
set_in(bb, "Base Color", srgb_to_linear(OLIVE_DARK))
set_in(bb, "Roughness", 0.48)
band.data.materials.append(mat_band)

# --------------------------------------------------------------------------
# Assembly: tilt and slow spin. The halves separate in its LOCAL space.
# --------------------------------------------------------------------------
TILT_X, TILT_Y = math.radians(-15), math.radians(7)

asm = bpy.data.objects.new("Assembly", None)
scene.collection.objects.link(asm)
asm.rotation_euler = (TILT_X, TILT_Y, 0)
asm.keyframe_insert("rotation_euler", frame=FRAME_START)
asm.rotation_euler = (TILT_X, TILT_Y, math.radians(52))
asm.keyframe_insert("rotation_euler", frame=FRAME_END)

bottom.parent = asm
band.parent = bottom      # parent the band to the BOTTOM half, or it floats when the half drops

# --- hinge ---
# An empty is placed on the far edge and the top half is parented to it, so
# the rotation happens around that axis instead of the center. The half's
# local offset cancels the hinge offset so it starts in place.
hinge = bpy.data.objects.new("Hinge", None)
hinge.empty_display_size = 0.3
scene.collection.objects.link(hinge)
hinge.parent = asm
hinge.location = (0, HINGE_Y, 0)

top.parent = hinge
top.location = (0, -HINGE_Y, 0)
top.rotation_euler = (0, 0, 0)

hinge.rotation_euler = (0, 0, 0)
hinge.keyframe_insert("rotation_euler", frame=SPLIT_IN)
hinge.keyframe_insert("location", frame=SPLIT_IN)
hinge.rotation_euler = (HINGE_ANGLE, 0, 0)
hinge.location = (0, HINGE_Y, HINGE_LIFT)
hinge.keyframe_insert("rotation_euler", frame=SPLIT_OUT)
hinge.keyframe_insert("location", frame=SPLIT_OUT)

# bottom half: drops very slightly, which makes the separation read better
bottom.location = (0, 0, 0)
bottom.keyframe_insert("location", frame=SPLIT_IN)
bottom.location = (0, 0, -0.12)
bottom.keyframe_insert("location", frame=SPLIT_OUT)

# --------------------------------------------------------------------------
# Particles: these now come out of the CUT FACE
# --------------------------------------------------------------------------
P_COUNT = 300
P_BIRTH = (44, 120)
P_LIFE = (50, 76)

p_root = bpy.data.objects.new("ParticleRoot", None)
p_root.rotation_euler = (TILT_X, TILT_Y, 0)
scene.collection.objects.link(p_root)

bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(0, 0, 40))
proto = bpy.context.active_object
proto.name = "P_proto"
bpy.ops.object.shade_smooth()
proto.hide_render = True

mat_glow = bpy.data.materials.new("P_Glow")
mat_glow.use_nodes = True
gb = mat_glow.node_tree.nodes["Principled BSDF"]
set_in(gb, "Base Color", srgb_to_linear(LIME))
set_in(gb, "Emission Color", srgb_to_linear(LIME))
set_in(gb, "Emission Strength", 0.55)
set_in(gb, "Roughness", 0.4)

mat_dust = bpy.data.materials.new("P_Dust")
mat_dust.use_nodes = True
db = mat_dust.node_tree.nodes["Principled BSDF"]
set_in(db, "Base Color", srgb_to_linear(SAGE))
set_in(db, "Roughness", 0.7)

particles = bpy.data.collections.new("Particles")
scene.collection.children.link(particles)

for i in range(P_COUNT):
    th = random.uniform(0, math.tau)
    r0 = 0.88 * math.sqrt(random.random())          # uniform distribution over the disc
    z0 = random.uniform(0.0, 0.12)
    start = (r0 * math.cos(th), r0 * math.sin(th), z0)

    # up and outward; particles near the center rise more steeply
    up = 1.15 - 0.55 * (r0 / 0.88)
    n = (math.cos(th) * 0.75, math.sin(th) * 0.75, up)
    nl = math.sqrt(sum(c * c for c in n)) or 1.0
    n = [c / nl for c in n]

    dist = random.uniform(0.9, 2.8)
    swirl = random.uniform(-0.5, 0.5)
    end = (
        start[0] + n[0] * dist - math.sin(th) * swirl,
        start[1] + n[1] * dist + math.cos(th) * swirl,
        start[2] + n[2] * dist + random.uniform(-0.1, 0.4),
    )

    birth = random.randint(*P_BIRTH)
    death = birth + random.randint(*P_LIFE)
    size = random.uniform(0.007, 0.021)

    p = bpy.data.objects.new(f"P_{i:03d}", proto.data)
    particles.objects.link(p)
    p.parent = p_root
    if not p.data.materials:
        p.data.materials.append(mat_dust)
    p.material_slots[0].link = "OBJECT"
    p.material_slots[0].material = mat_glow if random.random() < 0.88 else mat_dust

    p.location = start
    p.keyframe_insert("location", frame=birth)
    p.location = end
    p.keyframe_insert("location", frame=death)

    p.scale = (0, 0, 0)
    p.keyframe_insert("scale", frame=birth)
    p.scale = (size,) * 3
    p.keyframe_insert("scale", frame=birth + 7)
    p.scale = (size,) * 3
    p.keyframe_insert("scale", frame=death - 16)
    p.scale = (0, 0, 0)
    p.keyframe_insert("scale", frame=death)

# --------------------------------------------------------------------------
# Lights
# --------------------------------------------------------------------------
def add_area(name, loc, rot, size, energy, color=(1, 1, 1)):
    d = bpy.data.lights.new(name, "AREA")
    d.shape = "RECTANGLE"
    d.size, d.size_y = size
    d.energy = energy
    d.color = color
    o = bpy.data.objects.new(name, d)
    o.location, o.rotation_euler = loc, rot
    scene.collection.objects.link(o)
    return o


add_area("Key", (-3.4, -2.6, 4.2), (math.radians(38), 0, math.radians(-52)), (5, 4), 210,
         (1.0, 0.97, 0.92))
add_area("Fill", (4.2, -1.4, 1.2), (math.radians(78), 0, math.radians(64)), (6, 6), 45,
         (0.93, 0.96, 1.0))
add_area("Rim", (1.6, 4.6, 2.6), (math.radians(112), 0, math.radians(160)), (4, 3), 190,
         (1.0, 0.99, 0.95))
# extra fill that lights the interior once the cut opens
add_area("CoreFill", (-1.2, -3.4, 2.0), (math.radians(62), 0, math.radians(-20)), (3, 2), 70,
         (1.0, 0.98, 0.90))

# --------------------------------------------------------------------------
# Camera: stays high so the inside of the cut is visible
# --------------------------------------------------------------------------
focus = bpy.data.objects.new("Focus", None)
scene.collection.objects.link(focus)
# the focus point rises into the gap as the halves separate
focus.location = (0, 0, 0.15)
focus.keyframe_insert("location", frame=FRAME_START)
focus.location = (0, 0, 0.65)   # the hinged lid swings higher, so focus goes higher
focus.keyframe_insert("location", frame=SPLIT_OUT)
focus.keyframe_insert("location", frame=FRAME_END)

orbit = bpy.data.objects.new("Orbit", None)
scene.collection.objects.link(orbit)

cam_data = bpy.data.cameras.new("Cam")
# at 85mm the opened composition did not fit vertically; 70mm leaves enough room
cam_data.lens = 70
cam_data.dof.use_dof = True
cam_data.dof.focus_object = focus
cam_data.dof.aperture_fstop = 2.0
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
cam.parent = orbit

trk = cam.constraints.new("TRACK_TO")
trk.target = focus
trk.track_axis = "TRACK_NEGATIVE_Z"
trk.up_axis = "UP_Y"

# The composition grows taller as it opens, so the camera pulls BACK instead
# of moving in. An earlier version moved in and the top half left the frame.
cam.location = (0, -7.2, 3.2)
cam.keyframe_insert("location", frame=FRAME_START)
cam.location = (0, -11.0, 4.6)
cam.keyframe_insert("location", frame=SPLIT_OUT)
cam.location = (0, -10.5, 4.4)
cam.keyframe_insert("location", frame=FRAME_END)

orbit.rotation_euler = (0, 0, math.radians(-24))
orbit.keyframe_insert("rotation_euler", frame=FRAME_START)
orbit.rotation_euler = (0, 0, math.radians(62))
orbit.keyframe_insert("rotation_euler", frame=FRAME_END)

scene.camera = cam

# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
scene.render.engine = "CYCLES"
scene.cycles.device = "GPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.01
scene.cycles.use_denoising = True
try:
    scene.cycles.denoiser = "OPTIX"
except Exception as e:
    print("OptiX denoiser not available:", e)

scene.render.use_motion_blur = False
scene.render.use_persistent_data = True   # avoids about 20 s of scene sync per frame

scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False

scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"

scene.frame_start = FRAME_START
scene.frame_end = FRAME_END

prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
try:
    prefs.refresh_devices()
except Exception:
    pass
for d in prefs.devices:
    d.use = d.type in ("OPTIX", "CUDA")

os.makedirs(OUT, exist_ok=True)

if RENDER_ANIM:
    scene.render.filepath = os.path.join(OUT, "frame_")
    print(f">>> ANIM {FRAME_START}-{FRAME_END} @ {SAMPLES} spp -> {OUT}")
    bpy.ops.render.render(animation=True)
else:
    for f in TEST_FRAMES:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(OUT, f"test_{f:04d}.png")
        print(f">>> TEST frame {f} @ {SAMPLES} spp")
        bpy.ops.render.render(write_still=True)

print(">>> DONE")
