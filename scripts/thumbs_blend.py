"""Render custom stills for thumbnails and social posts (EXR) with exact compositions.

blender -b --factory-startup -P thumbs_blend.py
"""
import bpy, math, os, sys
from mathutils import Vector

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world
import shots

OUT = os.path.join(ROOT, 'media', 'plates')
NIGHT = dict(shots.PROPS)
DAWN = dict(shots.PROPS, eye_gold=1.0, sky_pre=1.0, sky_dawn=1.0, eye_int=1.1, sky_glow=0.55, sky_bright=0.8, lights=0.2)


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    world.render_settings()
    world.world_shader()
    world.build_sea()
    world.build_cities()
    world.build_eye()
    world.build_cameras()
    bpy.context.scene.eevee.taa_render_samples = 64


def pose(rt, ap=1.0, bezel=0.0):
    """Pose the v2 orb rig (gimbals, voice ring, mood colors) exactly as it is at song time rt."""
    import rig
    sc = bpy.context.scene
    ob = bpy.data.objects
    rs = rig.rig_state(rt, bezel, 0.0)
    for p in world.RIG_PROPS:
        sc[p] = float(rs[p])
    cs = ap * rs['core_scale']
    ob['CoreGroup'].scale = (cs, cs, cs)
    ob['Voice'].scale = (ap, ap, ap)
    ob['ShellRot'].rotation_euler = [math.radians(x) for x in rs['shell_rot']]
    ob['G1'].rotation_euler = [math.radians(x) for x in rs['g1']]
    ob['G2'].rotation_euler = [math.radians(x) for x in rs['g2']]
    gs = ap * rs['g2_scale']
    ob['G2'].scale = (gs, gs, gs)
    ob['G3'].rotation_euler = [math.radians(x) for x in rs['g3']]
    ob['OrbitSpin'].rotation_euler = (0, 0, math.radians(rs['g3_spin']))
    sc.frame_set(int(round(rt * 24)) + 1)   # the voice ring reads the sung spectrum at this frame


def place(w, h, lens, cam_h, yh, ex, ey, er, R=40.0, yaw=0.0):
    """Return camera + eye world placement for a frame of w x h with sensor fit on the longer side (36 mm)."""
    if w >= h:
        th = 18.0 / lens
        tv = th * h / w
    else:
        tv = 18.0 / lens
        th = tv * w / h
    pitch = math.degrees(math.atan((2 * yh - 1) * tv))
    e = pitch + math.degrees(math.atan((1 - 2 * ey) * tv))
    az = yaw + math.degrees(math.atan((2 * ex - 1) * th))
    a = math.atan(er * 2 * tv)
    D = R / math.tan(a)
    d = shots.dir_vec(e, az)
    cam = (0.0, 0.0, cam_h)
    eye = (cam[0] + D * d[0], cam[1] + D * d[1], cam[2] + D * d[2])
    dd = shots.dir_vec(pitch, yaw)
    target = (cam[0] + dd[0] * 100, cam[1] + dd[1] * 100, cam[2] + dd[2] * 100)
    return cam, target, eye, R


def shoot(name, w, h, lens, cam_h, yh, ex, ey, er, props, rt=64.0, ap=1.0, bezel=0.0):
    sc = bpy.context.scene
    cam_obj = bpy.data.objects['Cam']
    cam_obj.data.sensor_fit = 'HORIZONTAL' if w >= h else 'VERTICAL'
    cam_obj.data.sensor_width = 36.0
    cam_obj.data.sensor_height = 36.0
    cam, target, eye, R = place(w, h, lens, cam_h, yh, ex, ey, er)
    for k in world.PROPS:
        sc[k] = float(props.get(k, shots.PROPS.get(k, 0.0)))
    root = bpy.data.objects['EyeRoot']
    root.location = eye
    s = R / 232.0
    root.scale = (s, s, s)
    q = (Vector(cam) - Vector(eye)).to_track_quat('Z', 'Y')
    root.rotation_euler = q.to_euler()
    dvec = (Vector(eye) - Vector(cam)).normalized()
    sc['eye_dir'] = [dvec.x, dvec.y, dvec.z]
    cam_obj.location = cam
    cam_obj.rotation_euler = world.look_at(cam, target)
    cam_obj.data.lens = lens
    sc.camera = cam_obj
    sc.render.resolution_x, sc.render.resolution_y = w, h
    pose(rt, ap, bezel)
    sc.render.filepath = os.path.join(OUT, name + '.exr')
    bpy.ops.render.render(write_still=True)
    print('THUMB_PLATE', name, flush=True)


JOBS = [
    # last field: the song moment whose orb rig (gimbal tilt, mood color, voice ring) the still borrows
    ('thumb_A', 1920, 1080, 50, 4, 0.76, 0.69, 0.44, 0.33, dict(NIGHT, eye_int=1.2, sky_glow=0.3), 64.5),
    ('thumb_B_night', 1920, 1080, 42, 2.5, 0.80, 0.5, 0.46, 0.42, dict(NIGHT, eye_int=1.15, sea_chop=1.2), 60.0),
    ('thumb_B_dawn', 1920, 1080, 42, 2.5, 0.80, 0.5, 0.46, 0.42, dict(DAWN, sea_chop=1.4), 203.0),
    ('thumb_C', 1920, 1080, 40, 2.0, 0.62, 0.64, 0.52, 0.27, dict(DAWN, sky_glow=0.9, eye_int=1.2, sea_chop=1.5), 200.0),
    # Shorts covers: eye and type kept inside the middle band (y .31-.69) that survives the ~3:2 crop on some surfaces
    ('cover_SH1', 1080, 1920, 40, 3.0, 0.55, 0.5, 0.41, 0.105, dict(NIGHT, eye_int=1.2), 60.0),
    ('cover_SH2', 1080, 1920, 50, 1.0, 0.53, 0.5, 0.44, 0.072, dict(NIGHT, eye_ember=1.0, eye_int=0.8, sea_chop=0.2, sea_rough=0.015, lights=0.55), 175.0),
    ('cover_SH3', 1080, 1920, 36, 2.0, 0.53, 0.5, 0.465, 0.10, dict(DAWN, sky_glow=1.0, eye_int=1.25, sea_chop=1.5), 203.0),
    ('square', 1080, 1080, 50, 4, 0.74, 0.5, 0.40, 0.22, dict(NIGHT, eye_int=1.1), 135.0),
    ('story', 1080, 1920, 36, 2.0, 0.55, 0.5, 0.40, 0.15, dict(DAWN, sky_glow=0.9, eye_int=1.2, sea_chop=1.5), 206.0),
    ('endscreen', 1920, 1080, 50, 2.5, 0.50, 0.5, 0.27, 0.16, dict(DAWN, sea_chop=0.3, sea_rough=0.02), 222.0),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None
    setup()
    for job in JOBS:
        if not only or job[0] in only:
            shoot(*job)
    print('THUMBS_DONE')


main()
