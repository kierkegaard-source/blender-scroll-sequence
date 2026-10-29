"""
Tablet sequence, base variant (Blender 5.2 / Cycles, OptiX)

Usage:
  blender -b --factory-startup -noaudio -P scene_tablet.py -- --frames 1,60,110 --samples 64 --out ./test
  blender -b --factory-startup -noaudio -P scene_tablet.py -- --anim --samples 128 --out ./frames

Scene: an olive green tablet floating over a cream background. The camera
orbits slowly while glowing particles leave the tablet surface and drift out.
All timing is LINEAR, which a scroll-scrubbed sequence needs for constant speed.
"""

import bpy
import math
import os
import random
import sys

# --------------------------------------------------------------------------
# Arguments
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
OUT = os.path.abspath(arg("--out", "./test"))
RES_X, RES_Y = (int(v) for v in arg("--res", "1920x1080").split("x"))
TEST_FRAMES = [int(f) for f in arg("--frames", "60").split(",")]
RENDER_ANIM = flag("--anim")

random.seed(7)

# --------------------------------------------------------------------------
# Palette: hex sRGB, converted to linear for the scene
# --------------------------------------------------------------------------
CREAM = "#F4EDE6"
CREAM_DEEP = "#E7DDD0"
OLIVE = "#404F1D"
OLIVE_DARK = "#2F3B15"
LIME = "#C9DE6E"
SAGE = "#A8B87A"


def srgb_to_linear(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, alpha)


def set_in(node, name, value):
    """Principled BSDF socket names change between versions, so set only if present."""
    if name in node.inputs:
        node.inputs[name].default_value = value
        return True
    return False


def iter_fcurves(action):
    """Blender 5.x removed Action.fcurves (slotted actions). Support both APIs."""
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for cb in getattr(strip, "channelbags", []):
                out.extend(cb.fcurves)
    return out


def linear_keys(obj):
    """Set every keyframe to LINEAR for scroll scrubbing."""
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    for fc in iter_fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


# --------------------------------------------------------------------------
# Clean scene
# --------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# make every new keyframe LINEAR from the start (for scroll scrubbing)
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

# --------------------------------------------------------------------------
# World: soft cream gradient in screen space (looks better than a flat color)
# --------------------------------------------------------------------------
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
wn = world.node_tree.nodes
wl = world.node_tree.links
wn.clear()

w_out = wn.new("ShaderNodeOutputWorld")
w_bg = wn.new("ShaderNodeBackground")
w_ramp = wn.new("ShaderNodeValToRGB")
w_grad = wn.new("ShaderNodeTexGradient")
w_map = wn.new("ShaderNodeMapping")
w_coord = wn.new("ShaderNodeTexCoord")

w_grad.gradient_type = "LINEAR"
w_map.inputs["Rotation"].default_value = (0, math.radians(90), 0)  # lighter at the top, deeper at the bottom
w_ramp.color_ramp.elements[0].position = 0.00
w_ramp.color_ramp.elements[0].color = srgb_to_linear(CREAM_DEEP)
w_ramp.color_ramp.elements[1].position = 0.62
w_ramp.color_ramp.elements[1].color = srgb_to_linear(CREAM)
# Strength MUST be 1.0: Background strength multiplies the color directly, and
# at 0.75 the cream background shifted to beige. Adjust brightness with the lights.
w_bg.inputs["Strength"].default_value = 1.0

wl.new(w_coord.outputs["Window"], w_map.inputs["Vector"])
wl.new(w_map.outputs["Vector"], w_grad.inputs["Vector"])
wl.new(w_grad.outputs["Fac"], w_ramp.inputs["Fac"])
wl.new(w_ramp.outputs["Color"], w_bg.inputs["Color"])
wl.new(w_bg.outputs["Background"], w_out.inputs["Surface"])

# --------------------------------------------------------------------------
# Tablet body
# --------------------------------------------------------------------------
bpy.ops.mesh.primitive_cylinder_add(vertices=160, radius=1.0, depth=0.34, location=(0, 0, 0))
tablet = bpy.context.active_object
tablet.name = "Tablet"

bev = tablet.modifiers.new("Bevel", "BEVEL")
bev.width = 0.085
bev.segments = 10
bev.limit_method = "ANGLE"
bev.angle_limit = math.radians(30)

sub = tablet.modifiers.new("Subsurf", "SUBSURF")
sub.levels = 1
sub.render_levels = 2

bpy.ops.object.shade_smooth()
try:
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
except Exception as e:
    print("shade_auto_smooth skipped:", e)

# Tablet material: reads as pressed mineral powder
mat = bpy.data.materials.new("Tablet_Mat")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
set_in(bsdf, "Base Color", srgb_to_linear(OLIVE))
set_in(bsdf, "Roughness", 0.62)
set_in(bsdf, "Metallic", 0.0)
set_in(bsdf, "IOR", 1.45)
set_in(bsdf, "Specular IOR Level", 0.35)

# very fine granular bump for a powder feel; it should not be visible as a pattern
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 900.0
noise.inputs["Detail"].default_value = 8.0
noise.inputs["Roughness"].default_value = 0.65
bump = nt.nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.09
bump.inputs["Distance"].default_value = 0.002
nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

# very narrow roughness variation so it does not form large blotches
rough_noise = nt.nodes.new("ShaderNodeTexNoise")
rough_noise.inputs["Scale"].default_value = 70.0
rough_ramp = nt.nodes.new("ShaderNodeValToRGB")
rough_ramp.color_ramp.elements[0].position = 0.35
rough_ramp.color_ramp.elements[0].color = (0.58, 0.58, 0.58, 1)
rough_ramp.color_ramp.elements[1].position = 0.70
rough_ramp.color_ramp.elements[1].color = (0.66, 0.66, 0.66, 1)
nt.links.new(rough_noise.outputs["Fac"], rough_ramp.inputs["Fac"])
nt.links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])

tablet.data.materials.append(mat)

# a flat horizontal disc looks dull, so tilt it and spin it slowly on its axis
TILT_X, TILT_Y = math.radians(-15), math.radians(7)
tablet.rotation_euler = (TILT_X, TILT_Y, 0)
tablet.keyframe_insert("rotation_euler", frame=FRAME_START)
tablet.rotation_euler = (TILT_X, TILT_Y, math.radians(52))
tablet.keyframe_insert("rotation_euler", frame=FRAME_END)
linear_keys(tablet)

# --------------------------------------------------------------------------
# Equator band: the plain disc looked like a bar of soap, a thin band helps
# --------------------------------------------------------------------------
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.972, minor_radius=0.032,
    major_segments=180, minor_segments=20, location=(0, 0, 0),
)
band = bpy.context.active_object
band.name = "Tablet_Band"
bpy.ops.object.shade_smooth()

mat_band = bpy.data.materials.new("Band_Mat")
mat_band.use_nodes = True
bb = mat_band.node_tree.nodes["Principled BSDF"]
set_in(bb, "Base Color", srgb_to_linear(OLIVE_DARK))
set_in(bb, "Roughness", 0.48)
set_in(bb, "Specular IOR Level", 0.45)
band.data.materials.append(mat_band)

band.parent = tablet  # spins with the tablet

# --------------------------------------------------------------------------
# Particles: linked duplicate icospheres, keyframed by hand for full control
# --------------------------------------------------------------------------
P_COUNT = 300
P_BIRTH = (28, 108)      # birth window (frames)
P_LIFE = (52, 78)        # lifetime (frames)

# particles are generated in the tablet's LOCAL space and parented to an empty
# with the same tilt, so their start points line up with the surface
p_root = bpy.data.objects.new("ParticleRoot", None)
p_root.rotation_euler = (TILT_X, TILT_Y, 0)
scene.collection.objects.link(p_root)

bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(0, 0, 40))
proto = bpy.context.active_object
proto.name = "P_proto"
bpy.ops.object.shade_smooth()
proto.hide_render = True

# two variants: glowing lime and matte sage
mat_glow = bpy.data.materials.new("P_Glow")
mat_glow.use_nodes = True
gb = mat_glow.node_tree.nodes["Principled BSDF"]
set_in(gb, "Base Color", srgb_to_linear(LIME))
set_in(gb, "Emission Color", srgb_to_linear(LIME))
# at emission 1.5 the particles turned yellow and looked like glitter
set_in(gb, "Emission Strength", 0.55)
set_in(gb, "Roughness", 0.4)

# NOTE: this variant used to be dark OLIVE, which looked like specks of dirt
# on the cream background. It was changed to sage and its share was reduced.
mat_dust = bpy.data.materials.new("P_Dust")
mat_dust.use_nodes = True
db = mat_dust.node_tree.nodes["Principled BSDF"]
set_in(db, "Base Color", srgb_to_linear(SAGE))
set_in(db, "Roughness", 0.7)

particles = bpy.data.collections.new("Particles")
scene.collection.children.link(particles)

R_TAB, H_TAB = 1.0, 0.17

for i in range(P_COUNT):
    # start: on the tablet surface (70% side wall, 30% top and bottom faces)
    th = random.uniform(0, math.tau)
    if random.random() < 0.7:
        r0 = R_TAB * random.uniform(0.96, 1.0)
        z0 = random.uniform(-H_TAB, H_TAB)
        n = (math.cos(th), math.sin(th), z0 * 1.5)
    else:
        r0 = R_TAB * random.uniform(0.15, 0.95)
        z0 = H_TAB * random.choice((1, -1))
        n = (math.cos(th) * 0.45, math.sin(th) * 0.45, 1.6 if z0 > 0 else -1.6)

    start = (r0 * math.cos(th), r0 * math.sin(th), z0)
    nl = math.sqrt(sum(c * c for c in n)) or 1.0
    n = [c / nl for c in n]

    dist = random.uniform(1.1, 3.2)
    swirl = random.uniform(-0.55, 0.55)
    end = (
        start[0] + n[0] * dist - math.sin(th) * swirl,
        start[1] + n[1] * dist + math.cos(th) * swirl,
        start[2] + n[2] * dist + random.uniform(-0.25, 0.45),
    )

    birth = random.randint(*P_BIRTH)
    death = birth + random.randint(*P_LIFE)
    size = random.uniform(0.007, 0.021)

    p = bpy.data.objects.new(f"P_{i:03d}", proto.data)
    particles.objects.link(p)
    p.parent = p_root

    # the mesh is shared, so the material is linked at OBJECT level
    # (the mesh needs a slot first for the object-level override to work)
    if not p.data.materials:
        p.data.materials.append(mat_dust)
    p.material_slots[0].link = "OBJECT"
    p.material_slots[0].material = mat_glow if random.random() < 0.88 else mat_dust

    # location
    p.location = start
    p.keyframe_insert("location", frame=birth)
    p.location = end
    p.keyframe_insert("location", frame=death)

    # scale: 0 at birth, grows, then fades out
    p.scale = (0, 0, 0)
    p.keyframe_insert("scale", frame=birth)
    p.scale = (size,) * 3
    p.keyframe_insert("scale", frame=birth + 7)
    p.scale = (size,) * 3
    p.keyframe_insert("scale", frame=death - 16)
    p.scale = (0, 0, 0)
    p.keyframe_insert("scale", frame=death)

    linear_keys(p)

# --------------------------------------------------------------------------
# Lights: three-point setup, all large area lights (soft product lighting)
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


# NOTE: a 900W key combined with the cream ambient washed the tablet out to
# light green. It is much lower now so the olive stays dark.
add_area("Key", (-3.4, -2.6, 4.2), (math.radians(38), 0, math.radians(-52)), (5, 4), 210,
         (1.0, 0.97, 0.92))
add_area("Fill", (4.2, -1.4, 1.2), (math.radians(78), 0, math.radians(64)), (6, 6), 45,
         (0.93, 0.96, 1.0))
add_area("Rim", (1.6, 4.6, 2.6), (math.radians(112), 0, math.radians(160)), (4, 3), 190,
         (1.0, 0.99, 0.95))

# --------------------------------------------------------------------------
# Camera: parented to an empty that rotates, for a clean orbit
# --------------------------------------------------------------------------
focus = bpy.data.objects.new("Focus", None)
focus.empty_display_size = 0.2
scene.collection.objects.link(focus)

orbit = bpy.data.objects.new("Orbit", None)
scene.collection.objects.link(orbit)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 85
cam_data.dof.use_dof = True
cam_data.dof.focus_object = focus
cam_data.dof.aperture_fstop = 1.6  # background particles were not blurring enough
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
cam.parent = orbit

trk = cam.constraints.new("TRACK_TO")
trk.target = focus
trk.track_axis = "TRACK_NEGATIVE_Z"
trk.up_axis = "UP_Y"

# dolly: from far to near. An earlier version overflowed the frame and the
# angle was too low, so the tablet read as an ellipse. Distance and height went up.
cam.location = (0, -7.4, 3.3)
cam.keyframe_insert("location", frame=FRAME_START)
cam.location = (0, -6.6, 2.4)
cam.keyframe_insert("location", frame=FRAME_END)
linear_keys(cam)

orbit.rotation_euler = (0, 0, math.radians(-24))
orbit.keyframe_insert("rotation_euler", frame=FRAME_START)
orbit.rotation_euler = (0, 0, math.radians(68))
orbit.keyframe_insert("rotation_euler", frame=FRAME_END)
linear_keys(orbit)

scene.camera = cam

# --------------------------------------------------------------------------
# Render settings
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
    print("OptiX denoiser not available, using the default:", e)

# NO motion blur in a scroll-scrubbed sequence: the user controls time
scene.render.use_motion_blur = False

# Avoids about 20 s of scene sync and kernel setup per frame. During an
# animation render the Cycles session stays alive between frames.
scene.render.use_persistent_data = True

scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.compression = 15
scene.render.film_transparent = False

# Standard view transform so the cream background matches its hex value
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0.0

scene.frame_start = FRAME_START
scene.frame_end = FRAME_END

# enable GPU devices
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
