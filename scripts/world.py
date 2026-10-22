"""Builds the Hello, World scene in Blender 5.x from scratch and bakes the shot timeline.

Usage: blender -b --factory-startup -P world.py -- [build]
Writes: <root>/hello_world.blend, analysis/proj.json and analysis/cities.json
(<root> is HELLO_WORLD_ROOT if set, otherwise the folder above scripts/)
"""
import bpy, bmesh, math, json, os, sys, importlib
from mathutils import Vector, Matrix, Euler
from bpy_extras.object_utils import world_to_camera_view

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shots
importlib.reload(shots)

FPS = 24


# ------------------------------------------------------------------ helpers
def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def col(h, a=1.0):
    h = h.lstrip('#')
    return (s2l(int(h[0:2], 16) / 255), s2l(int(h[2:4], 16) / 255), s2l(int(h[4:6], 16) / 255), a)


def sock(node, ident, out=False):
    coll = node.outputs if out else node.inputs
    for s in coll:
        if s.identifier == ident:
            return s
    return coll[ident]


class NT:
    """Tiny node-tree builder."""

    def __init__(self, tree):
        self.t = tree
        self.t.nodes.clear()
        self.x = 0

    def n(self, kind, **props):
        node = self.t.nodes.new(kind)
        node.location = (self.x, 0)
        self.x += 200
        for k, v in props.items():
            if k.startswith('in_'):
                key = k[3:]
                s = sock(node, key) if key in [i.identifier for i in node.inputs] else node.inputs[key.replace('_', ' ')]
                s.default_value = v
            else:
                setattr(node, k, v)
        return node

    def link(self, a, b):
        self.t.links.new(a, b)

    def attr(self, name, kind='VIEW_LAYER'):
        a = self.n('ShaderNodeAttribute', attribute_type=kind, attribute_name=name)
        return sock(a, 'Fac', True) if 'Fac' in [o.identifier for o in a.outputs] else a.outputs['Factor']

    def attr_vec(self, name):
        a = self.n('ShaderNodeAttribute', attribute_type='VIEW_LAYER', attribute_name=name)
        return a.outputs['Vector']

    def math(self, op, a=None, b=None, c=None, clamp=False):
        m = self.n('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                self.link(v, m.inputs[i])
        return m.outputs[0]

    def mixc(self, fac, a, b):
        m = self.n('ShaderNodeMix', data_type='RGBA', blend_type='MIX')
        for ident, v in (('Factor_Float', fac), ('A_Color', a), ('B_Color', b)):
            s = sock(m, ident)
            if isinstance(v, (tuple, list)):
                s.default_value = v
            elif isinstance(v, (int, float)):
                s.default_value = v
            else:
                self.link(v, s)
        return sock(m, 'Result_Color', True)

    def ramp(self, inp, stops):
        r = self.n('ShaderNodeValToRGB')
        els = r.color_ramp.elements
        while len(els) > 1:
            els.remove(els[-1])
        els[0].position = stops[0][0]
        els[0].color = col(stops[0][1])
        for p, h in stops[1:]:
            e = els.new(p)
            e.color = col(h)
        r.color_ramp.interpolation = 'LINEAR'
        self.link(inp, r.inputs[0])
        return r.outputs['Color']

    def emission(self, color, strength):
        e = self.n('ShaderNodeEmission')
        for i, v in ((0, color), (1, strength)):
            if isinstance(v, (tuple, list, int, float)):
                e.inputs[i].default_value = v
            else:
                self.link(v, e.inputs[i])
        return e.outputs[0]

    def out_material(self, shader):
        o = self.n('ShaderNodeOutputMaterial')
        self.link(shader, o.inputs['Surface'])


def new_mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m, NT(m.node_tree)


def link_obj(obj, parent=None):
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


# ------------------------------------------------------------------ meshes (eye in "cover px" units, facing +Z)
def mesh_from(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    return me


def ring(name, r_in, r_out, seg=360, a0=0.0, a1=2 * math.pi, z=0.0):
    full = abs((a1 - a0) - 2 * math.pi) < 1e-6

    def b(bm):
        n = seg if full else seg + 1
        angs = [a0 + (a1 - a0) * i / seg for i in range(n)]
        inner = [bm.verts.new((r_in * math.cos(a), r_in * math.sin(a), z)) for a in angs]
        outer = [bm.verts.new((r_out * math.cos(a), r_out * math.sin(a), z)) for a in angs]
        m = n if full else n - 1
        for i in range(m):
            j = (i + 1) % n
            bm.faces.new((inner[i], inner[j], outer[j], outer[i]))
    return mesh_from(name, b)


def disc(name, r, seg=256, z=0.0, cx=0.0, cy=0.0):
    def b(bm):
        c = bm.verts.new((cx, cy, z))
        vs = [bm.verts.new((cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)]
        for i in range(seg):
            bm.faces.new((c, vs[i], vs[(i + 1) % seg]))
    return mesh_from(name, b)


def ticks(name, n, r0, r1, w):
    def b(bm):
        for k in range(n):
            a = 2 * math.pi * k / n
            ca, sa = math.cos(a), math.sin(a)
            px, py = -sa * w / 2, ca * w / 2
            v = [bm.verts.new((r0 * ca + px, r0 * sa + py, 0)), bm.verts.new((r1 * ca + px, r1 * sa + py, 0)),
                 bm.verts.new((r1 * ca - px, r1 * sa - py, 0)), bm.verts.new((r0 * ca - px, r0 * sa - py, 0))]
            bm.faces.new(v)
    return mesh_from(name, b)


def dots(name, n, r, rad, seg=12):
    def b(bm):
        for k in range(n):
            a = 2 * math.pi * k / n
            cx, cy = r * math.cos(a), r * math.sin(a)
            c = bm.verts.new((cx, cy, 0))
            vs = [bm.verts.new((cx + rad * math.cos(2 * math.pi * i / seg), cy + rad * math.sin(2 * math.pi * i / seg), 0)) for i in range(seg)]
            for i in range(seg):
                bm.faces.new((c, vs[i], vs[(i + 1) % seg]))
    return mesh_from(name, b)


# ------------------------------------------------------------------ materials
PAL = {
    'red': dict(stops=[(0, '#FFF7EA'), (0.10, '#FFE2AE'), (0.27, '#FF9C47'), (0.50, '#F23A2C'), (0.77, '#7C1016'), (1.0, '#25070A')],
                ring='#FF3B2F', amber='#F2A65A', mid='#FF5A3C', dots='#FF7A45'),
    'ember': dict(stops=[(0, '#FFB07A'), (0.20, '#E5532E'), (0.45, '#9A1E16'), (0.70, '#4A0C0C'), (0.88, '#2A0808'), (1.0, '#140505')],
                  ring='#B3261E', amber='#9A5A30', mid='#8A2A20', dots='#9A3A2A'),
    'gold': dict(stops=[(0, '#FFFFFF'), (0.15, '#FFF4D6'), (0.35, '#FFD98A'), (0.60, '#FFB04A'), (0.82, '#E0742E'), (1.0, '#7A3410')],
                 ring='#FFB347', amber='#FFE2A8', mid='#FFC46B', dots='#FFD08A'),
    # v2 moods
    # verse 1: cooler and more muted than the plain red, so the first chorus going white-hot really lands
    'cold': dict(stops=[(0, '#F6F4F6'), (0.10, '#E8CACC'), (0.27, '#DC5A60'), (0.50, '#B21C2C'), (0.77, '#460A16'), (1.0, '#120408')],
                 ring='#E84450', amber='#D8A8AC', mid='#E05058', dots='#EC7A80'),
    'amber': dict(stops=[(0, '#FFF8EC'), (0.10, '#FFE6B8'), (0.27, '#FFB860'), (0.50, '#F07A2A'), (0.77, '#7A3010'), (1.0, '#221008')],
                  ring='#FF9A3A', amber='#FFC98A', mid='#FFAA55', dots='#FFC070'),
    'crimson': dict(stops=[(0, '#FFF2F2'), (0.10, '#FFC0C4'), (0.27, '#FF4A5A'), (0.50, '#C80E2A'), (0.77, '#520614'), (1.0, '#160206')],
                    ring='#FF2440', amber='#FF8A90', mid='#FF3A4E', dots='#FF5A66'),
}
# order matters: later moods win when several are up at once
MOODS = (('eye_cold', 'cold'), ('eye_amber', 'amber'), ('eye_crimson', 'crimson'), ('eye_ember', 'ember'), ('eye_gold', 'gold'))


def palette_color(nt, key):
    c = col(PAL['red'][key])
    for prop, name in MOODS:
        c = nt.mixc(nt.attr(prop), c, col(PAL[name][key]))
    return c


def clip_out(nt, emission_shader, alpha):
    """Emission where alpha~1, see-through elsewhere (dithered clip keeps depth + reflections)."""
    tr = nt.n('ShaderNodeBsdfTransparent')
    mx = nt.n('ShaderNodeMixShader')
    if isinstance(alpha, (int, float)):
        mx.inputs[0].default_value = alpha
    else:
        nt.link(alpha, mx.inputs[0])
    nt.link(tr.outputs[0], mx.inputs[1])
    nt.link(emission_shader, mx.inputs[2])
    return mx.outputs[0]


def reveal_mask(nt, prop):
    """1 where the clockwise angle from 12 o'clock (object space) is below the prop value (draw-on)."""
    tc = nt.n('ShaderNodeTexCoord')
    sep = nt.n('ShaderNodeSeparateXYZ')
    nt.link(tc.outputs['Object'], sep.inputs[0])
    a = nt.math('ARCTAN2', sep.outputs['X'], sep.outputs['Y'])
    a = nt.math('FLOORED_MODULO', nt.math('DIVIDE', a, 2 * math.pi), 1.0)
    return nt.math('LESS_THAN', a, nt.math('MULTIPLY', nt.attr(prop), 1.0005))


def eye_part_material(name, key, strength, vis=None, reveal=None):
    m, nt = new_mat(name)
    c = palette_color(nt, key)
    s = nt.math('MULTIPLY', nt.attr('eye_int'), strength)
    s = nt.math('MULTIPLY', s, nt.attr('eye_rings'))
    alpha = 1.0
    if vis:
        v = nt.attr(vis)
        s = nt.math('MULTIPLY', s, v)
        alpha = nt.math('MINIMUM', nt.math('MULTIPLY', v, 12.0), 1.0)
    if reveal:
        r = reveal_mask(nt, reveal)
        alpha = r if isinstance(alpha, float) else nt.math('MULTIPLY', alpha, r)
    em = nt.emission(c, s)
    nt.out_material(em if isinstance(alpha, float) else clip_out(nt, em, alpha))
    return m


def frame_value(nt, scale=1.0):
    v = nt.n('ShaderNodeValue')
    v.outputs[0].default_value = 0.0
    fc = v.outputs[0].driver_add('default_value')
    fc.driver.type = 'SCRIPTED'
    fc.driver.expression = 'frame * %r' % scale
    return v.outputs[0]


def core_material():
    """The orb itself: a real sphere whose glow is laid out by viewing angle, so from the front it reads exactly
    like the old flat iris, but it stays round from any side. A slow 4D noise keeps the core alive."""
    m, nt = new_mat('Core')
    geo = nt.n('ShaderNodeNewGeometry')
    dp = nt.n('ShaderNodeVectorMath', operation='DOT_PRODUCT')
    nt.link(geo.outputs['Normal'], dp.inputs[0])
    nt.link(geo.outputs['Incoming'], dp.inputs[1])
    f = nt.math('ABSOLUTE', dp.outputs['Value'])
    t = nt.math('SQRT', nt.math('MAXIMUM', nt.math('SUBTRACT', 1.0, nt.math('MULTIPLY', f, f)), 0.0))
    tc = nt.n('ShaderNodeTexCoord')
    nz = nt.n('ShaderNodeTexNoise', noise_dimensions='4D')
    nz.inputs['Scale'].default_value = 0.02
    nz.inputs['Detail'].default_value = 3.0
    nt.link(tc.outputs['Object'], nz.inputs['Vector'])
    nt.link(frame_value(nt, 0.006), nz.inputs['W'])
    t = nt.math('MULTIPLY_ADD', nt.math('SUBTRACT', nz.outputs['Factor'], 0.5), 0.10, t)
    t = nt.math('MINIMUM', nt.math('MAXIMUM', t, 0.0), 1.0)
    c = nt.ramp(t, PAL['red']['stops'])
    for prop, name in MOODS:
        c = nt.mixc(nt.attr(prop), c, nt.ramp(t, PAL[name]['stops']))
    heat = nt.attr('eye_heat')
    inv = nt.math('SUBTRACT', 1.0, t)
    expo = nt.math('MULTIPLY_ADD', heat, -1.4, 3.0)
    core = nt.math('POWER', inv, expo)
    gain = nt.math('MULTIPLY_ADD', heat, 7.0, 9.0)
    s = nt.math('MULTIPLY_ADD', core, gain, 1.1)
    # white-hot center when the heat is up
    c = nt.mixc(nt.math('MULTIPLY', heat, nt.math('POWER', inv, 6.0)), c, (1.0, 0.98, 0.95, 1.0))
    s = nt.math('MULTIPLY', s, nt.attr('eye_int'))
    s = nt.math('MULTIPLY', s, nt.attr('eye_core'))
    nt.out_material(nt.emission(c, s))
    return m


def shell_material():
    """A faint glass globe around the core: lat/long lines that brighten toward the silhouette."""
    m, nt = new_mat('Shell')
    tc = nt.n('ShaderNodeTexCoord')
    sep = nt.n('ShaderNodeSeparateXYZ')
    nt.link(tc.outputs['Object'], sep.inputs[0])
    lon = nt.math('DIVIDE', nt.math('ARCTAN2', sep.outputs['Y'], sep.outputs['X']), 2 * math.pi)
    g1 = nt.math('FRACT', nt.math('MULTIPLY', lon, 18.0))
    l1 = nt.math('LESS_THAN', nt.math('ABSOLUTE', nt.math('SUBTRACT', g1, 0.5)), 0.035)
    lat = nt.math('ARCSINE', nt.math('MINIMUM', nt.math('MAXIMUM', nt.math('DIVIDE', sep.outputs['Z'], 146.0), -1.0), 1.0))
    g2 = nt.math('FRACT', nt.math('MULTIPLY', lat, 9.0 / math.pi))
    l2 = nt.math('LESS_THAN', nt.math('ABSOLUTE', nt.math('SUBTRACT', g2, 0.5)), 0.035)
    lines = nt.math('MAXIMUM', l1, l2)
    geo = nt.n('ShaderNodeNewGeometry')
    dp = nt.n('ShaderNodeVectorMath', operation='DOT_PRODUCT')
    nt.link(geo.outputs['Normal'], dp.inputs[0])
    nt.link(geo.outputs['Incoming'], dp.inputs[1])
    fr = nt.math('POWER', nt.math('SUBTRACT', 1.0, nt.math('ABSOLUTE', dp.outputs['Value'])), 1.6)
    vis = nt.attr('shell_vis')
    s = nt.math('MULTIPLY', nt.math('MULTIPLY_ADD', fr, 2.4, 0.5), nt.math('MULTIPLY', vis, nt.attr('eye_int')))
    em = nt.emission(palette_color(nt, 'mid'), nt.math('MULTIPLY', s, 1.2))
    # lines live on the glass toward the silhouette and fade out over the face, so the core glow stays clean
    edge = nt.n('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
    edge.inputs['From Min'].default_value = 0.10
    edge.inputs['From Max'].default_value = 0.50
    nt.link(fr, edge.inputs['Value'])
    alpha = nt.math('MULTIPLY', lines, nt.math('MINIMUM', nt.math('MULTIPLY', vis, 12.0), 1.0))
    alpha = nt.math('MULTIPLY', alpha, edge.outputs['Result'])
    nt.out_material(clip_out(nt, em, alpha))
    return m


def voice_material(nframes, bars=60):
    """The voice ring: the old dotted ring, but each dot stretches into a bar with the sung spectrum
    (lows at 6 o'clock, highs at 12, mirrored left/right). Reads analysis/rig_spec.png, one row per frame."""
    m, nt = new_mat('M_Voice')
    tc = nt.n('ShaderNodeTexCoord')
    sep = nt.n('ShaderNodeSeparateXYZ')
    nt.link(tc.outputs['Object'], sep.inputs[0])
    ln = nt.n('ShaderNodeVectorMath', operation='LENGTH')
    nt.link(tc.outputs['Object'], ln.inputs[0])
    r = ln.outputs['Value']
    ang = nt.math('ARCTAN2', sep.outputs['X'], nt.math('MULTIPLY', sep.outputs['Y'], -1.0))
    a = nt.math('DIVIDE', nt.math('ABSOLUTE', ang), math.pi)
    k = nt.math('FLOOR', nt.math('MULTIPLY', a, float(bars)))
    ac = nt.math('DIVIDE', nt.math('ADD', k, 0.5), float(bars))
    frc = nt.math('FRACT', nt.math('MULTIPLY', a, float(bars)))
    barm = nt.math('MULTIPLY', nt.math('GREATER_THAN', frc, 0.24), nt.math('LESS_THAN', frc, 0.76))
    u = nt.math('MULTIPLY_ADD', ac, 39.0 / 40.0, 0.5 / 40.0)
    v = nt.math('SUBTRACT', 1.0, nt.math('DIVIDE', nt.math('SUBTRACT', frame_value(nt), 0.5), float(nframes)))
    cmb = nt.n('ShaderNodeCombineXYZ')
    nt.link(u, cmb.inputs[0])
    nt.link(v, cmb.inputs[1])
    tex = nt.n('ShaderNodeTexImage', interpolation='Linear', extension='EXTEND')
    img = bpy.data.images.load(os.path.join(ROOT, 'analysis', 'rig_spec.png'))
    img.colorspace_settings.name = 'Non-Color'
    tex.image = img
    nt.link(cmb.outputs[0], tex.inputs['Vector'])
    amp = nt.math('MULTIPLY', nt.math('ADD', tex.outputs['Color'], 0.0), nt.attr('voice_gain'))
    rlen = nt.math('MULTIPLY_ADD', amp, 40.0, 157.0)
    radm = nt.math('MULTIPLY', nt.math('GREATER_THAN', r, 152.6), nt.math('LESS_THAN', r, rlen))
    mask = nt.math('MULTIPLY', nt.math('MULTIPLY', barm, radm), reveal_mask(nt, 'boot3'))
    # bars brighten with level and fade toward their tips
    tip = nt.math('SUBTRACT', 1.0, nt.math('MULTIPLY', nt.math('DIVIDE', nt.math('SUBTRACT', r, 152.6),
                                                                      nt.math('ADD', nt.math('SUBTRACT', rlen, 152.6), 0.01)), 0.55))
    s = nt.math('MULTIPLY', nt.math('MULTIPLY_ADD', amp, 2.6, 1.7), tip)
    s = nt.math('MULTIPLY', s, nt.attr('eye_int'))
    em = nt.emission(palette_color(nt, 'dots'), s)
    nt.out_material(clip_out(nt, em, mask))
    return m


def wave_material():
    """A ring of light that rolls across the water from under the orb on the beat."""
    m, nt = new_mat('M_Wave')
    tc = nt.n('ShaderNodeTexCoord')
    ln = nt.n('ShaderNodeVectorMath', operation='LENGTH')
    nt.link(tc.outputs['Object'], ln.inputs[0])
    r = ln.outputs['Value']
    # band width is ~3 m in the world (wave_in = 1 - 3/r, keyed per frame), not a fixed share of the radius,
    # so a wave near the camera stays a line of light instead of a wide bar
    win = nt.attr('wave_in', 'OBJECT')
    peak = nt.math('MULTIPLY_ADD', win, 0.15, 0.85)
    rise = nt.n('ShaderNodeMapRange', clamp=True)
    nt.link(win, rise.inputs['From Min'])
    nt.link(peak, rise.inputs['From Max'])
    nt.link(r, rise.inputs['Value'])
    fall = nt.n('ShaderNodeMapRange', clamp=True)
    fall.inputs['From Min'].default_value = 1.0
    nt.link(peak, fall.inputs['From Max'])
    nt.link(r, fall.inputs['Value'])
    prof = nt.math('MULTIPLY', nt.math('POWER', rise.outputs['Result'], 2.0), fall.outputs['Result'])
    wa = nt.attr('wave_a', 'OBJECT')
    s = nt.math('MULTIPLY', nt.math('MULTIPLY', prof, wa), nt.attr('eye_int'))
    em = nt.emission(palette_color(nt, 'ring'), nt.math('MULTIPLY', s, 9.0))
    alpha = nt.math('MULTIPLY', nt.math('GREATER_THAN', prof, 0.02), nt.math('GREATER_THAN', wa, 0.002))
    nt.out_material(clip_out(nt, em, alpha))
    return m


def iris_material():
    m, nt = new_mat('Iris')
    tc = nt.n('ShaderNodeTexCoord')
    ln = nt.n('ShaderNodeVectorMath', operation='LENGTH')
    nt.link(tc.outputs['Object'], ln.inputs[0])
    t = nt.math('DIVIDE', ln.outputs['Value'], 132.0, clamp=True)
    r_red = nt.ramp(t, PAL['red']['stops'])
    r_emb = nt.ramp(t, PAL['ember']['stops'])
    r_gold = nt.ramp(t, PAL['gold']['stops'])
    c = nt.mixc(nt.attr('eye_ember'), r_red, r_emb)
    c = nt.mixc(nt.attr('eye_gold'), c, r_gold)
    inv = nt.math('SUBTRACT', 1.0, t)
    core = nt.math('POWER', inv, 3.0)
    s = nt.math('MULTIPLY_ADD', core, 9.0, 1.1)
    s = nt.math('MULTIPLY', s, nt.attr('eye_int'))
    s = nt.math('MULTIPLY', s, nt.attr('eye_core'))
    nt.out_material(nt.emission(c, s))
    return m


def white_material(name, strength):
    m, nt = new_mat(name)
    s = nt.math('MULTIPLY', nt.attr('eye_int'), strength)
    s = nt.math('MULTIPLY', s, nt.attr('eye_rings'))
    nt.out_material(nt.emission((1, 1, 1, 1), s))
    return m


def sea_material():
    m, nt = new_mat('Sea')
    tc = nt.n('ShaderNodeTexCoord')
    t_drv = nt.n('ShaderNodeValue')
    t_drv.outputs[0].default_value = 0.0
    fc = t_drv.outputs[0].driver_add('default_value')
    fc.driver.type = 'SCRIPTED'
    fc.driver.expression = 'frame / 24.0'
    # long horizontal ripples: compress along Y so normals vary toward the camera
    mp = nt.n('ShaderNodeMapping', vector_type='POINT')
    mp.inputs['Scale'].default_value = (0.22, 1.0, 1.0)
    nt.link(tc.outputs['Object'], mp.inputs['Vector'])
    w1 = nt.math('MULTIPLY', t_drv.outputs[0], 0.35)
    n1 = nt.n('ShaderNodeTexNoise', noise_dimensions='4D')
    n1.inputs['Scale'].default_value = 0.55
    n1.inputs['Detail'].default_value = 6.0
    n1.inputs['Roughness'].default_value = 0.62
    nt.link(mp.outputs['Vector'], n1.inputs['Vector'])
    nt.link(w1, n1.inputs['W'])
    n2 = nt.n('ShaderNodeTexNoise', noise_dimensions='4D')
    n2.inputs['Scale'].default_value = 2.6
    n2.inputs['Detail'].default_value = 3.0
    nt.link(mp.outputs['Vector'], n2.inputs['Vector'])
    w2 = nt.math('MULTIPLY', t_drv.outputs[0], 0.8)
    nt.link(w2, n2.inputs['W'])
    h = nt.math('MULTIPLY_ADD', n2.outputs['Factor'], 0.35, nt.math('MULTIPLY', n1.outputs['Factor'], 1.0))
    bump = nt.n('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.5
    bump.inputs['Distance'].default_value = 0.35
    nt.link(nt.math('MULTIPLY', h, nt.attr('sea_chop')), bump.inputs['Height'])
    # scanlines: thin bright bands across the water, perspective-spaced for free
    sep = nt.n('ShaderNodeSeparateXYZ')
    nt.link(tc.outputs['Object'], sep.inputs[0])
    yy = nt.math('DIVIDE', sep.outputs['Y'], 3.0)
    fr = nt.math('FRACT', yy)
    band = nt.math('LESS_THAN', fr, 0.08)
    cam = nt.n('ShaderNodeVectorMath', operation='LENGTH')
    nt.link(tc.outputs['Camera'], cam.inputs[0])
    fade = nt.math('DIVIDE', 60.0, nt.math('ADD', cam.outputs['Value'], 60.0))
    lines = nt.math('MULTIPLY', nt.math('MULTIPLY', band, fade), nt.attr('sea_lines'))
    bs = nt.n('ShaderNodeBsdfPrincipled')
    bs.inputs['Base Color'].default_value = col('#06070A')
    bs.inputs['Roughness'].default_value = 0.06
    bs.inputs['IOR'].default_value = 1.33
    nt.link(bump.outputs['Normal'], bs.inputs['Normal'])
    bs.inputs['Emission Color'].default_value = col('#FFE6C8')
    nt.link(nt.math('MULTIPLY', lines, 0.012), bs.inputs['Emission Strength'])
    nt.link(nt.attr('sea_rough'), bs.inputs['Roughness'])
    nt.out_material(bs.outputs['BSDF'])
    return m


def lights_material():
    m, nt = new_mat('CityLights')
    br = nt.n('ShaderNodeAttribute', attribute_type='GEOMETRY', attribute_name='bright')
    wm = nt.n('ShaderNodeAttribute', attribute_type='GEOMETRY', attribute_name='warm')
    c = nt.mixc(wm.outputs['Factor'], col('#BFD4FF'), col('#FFD9A8'))
    c = nt.mixc(nt.attr('fire'), c, col('#FF5A1F'))
    s = nt.math('MULTIPLY', br.outputs['Factor'], 13.0)
    s = nt.math('MULTIPLY', s, nt.attr('lights'))
    # the breakdown takes lights one at a time: each goes out as lights_taken passes its seed
    sd = nt.n('ShaderNodeAttribute', attribute_type='GEOMETRY', attribute_name='seed')
    on = nt.math('DIVIDE', nt.math('SUBTRACT', sd.outputs['Factor'], nt.attr('lights_taken')), 0.006)
    on = nt.math('MINIMUM', nt.math('MAXIMUM', on, 0.0), 1.0)
    s = nt.math('MULTIPLY', s, on)
    s = nt.math('MULTIPLY', s, nt.math('ADD', 1.0, nt.math('MULTIPLY', nt.attr('fire'), 1.5)))
    # a taken light is gone, not a black square against the sky
    nt.out_material(clip_out(nt, nt.emission(c, s), on))
    return m


def lone_material():
    m, nt = new_mat('LoneLight')
    s = nt.math('MULTIPLY', nt.attr('lone'), 260.0)
    nt.out_material(nt.emission(col('#FFE6B8'), s))
    return m


def world_shader():
    w = bpy.data.worlds.new('Sky')
    bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = NT(w.node_tree)
    tc = nt.n('ShaderNodeTexCoord')
    sep = nt.n('ShaderNodeSeparateXYZ')
    nt.link(tc.outputs['Generated'], sep.inputs[0])
    z = sep.outputs['Z']
    t = nt.n('ShaderNodeMapRange', clamp=True)
    t.inputs['From Min'].default_value = 0.0
    t.inputs['From Max'].default_value = 0.42
    nt.link(z, t.inputs['Value'])
    tz = t.outputs['Result']
    night = nt.ramp(tz, [(0, '#120D13'), (0.18, '#08080C'), (1, '#040406')])
    pre = nt.ramp(tz, [(0, '#4A2A3E'), (0.12, '#221B38'), (0.45, '#0A0E24'), (1, '#05060E')])
    dawn = nt.ramp(tz, [(0, '#FFB566'), (0.10, '#D8746A'), (0.30, '#7A4470'), (0.60, '#2E2A60'), (1, '#121640')])
    c = nt.mixc(nt.attr('sky_pre'), night, pre)
    c = nt.mixc(nt.attr('sky_dawn'), c, dawn)
    # glow around the eye/sun direction
    dot = nt.n('ShaderNodeVectorMath', operation='DOT_PRODUCT')
    nt.link(tc.outputs['Generated'], dot.inputs[0])
    nt.link(nt.attr_vec('eye_dir'), dot.inputs[1])
    g = nt.math('POWER', nt.math('MAXIMUM', dot.outputs['Value'], 0.0), 60.0)
    g2 = nt.math('POWER', nt.math('MAXIMUM', dot.outputs['Value'], 0.0), 8.0)
    gl = nt.math('MULTIPLY_ADD', g2, 0.07, nt.math('MULTIPLY', g, 0.6))
    gcol = col('#FF4A2A')
    for prop, hexc in (('eye_cold', '#B02434'), ('eye_amber', '#FF9A3A'), ('eye_crimson', '#E8163A'),
                       ('eye_ember', '#E04A2A'), ('eye_gold', '#FFC46B')):
        gcol = nt.mixc(nt.attr(prop), gcol, col(hexc))
    glow = nt.n('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
    sock(glow, 'Factor_Float').default_value = 1.0
    nt.link(gcol, sock(glow, 'A_Color'))
    gv = nt.math('MULTIPLY', gl, nt.attr('sky_glow'))
    comb = nt.n('ShaderNodeCombineXYZ')
    for i in range(3):
        nt.link(gv, comb.inputs[i])
    nt.link(comb.outputs[0], sock(glow, 'B_Color'))
    add = nt.n('ShaderNodeMix', data_type='RGBA', blend_type='ADD')
    sock(add, 'Factor_Float').default_value = 1.0
    nt.link(c, sock(add, 'A_Color'))
    nt.link(sock(glow, 'Result_Color', True), sock(add, 'B_Color'))
    # fire band at the horizon
    nz = nt.n('ShaderNodeTexNoise', noise_dimensions='3D')
    nz.inputs['Scale'].default_value = 7.0
    nz.inputs['Detail'].default_value = 4.0
    nt.link(tc.outputs['Generated'], nz.inputs['Vector'])
    fb = nt.math('EXPONENT', nt.math('MULTIPLY', nt.math('MAXIMUM', z, 0.0), -38.0))
    fb = nt.math('MULTIPLY', fb, nt.math('POWER', nz.outputs['Factor'], 2.0))
    fb = nt.math('MULTIPLY', fb, nt.math('MULTIPLY', nt.attr('fire'), 6.0))
    fcomb = nt.n('ShaderNodeMix', data_type='RGBA', blend_type='ADD')
    nt.link(fb, sock(fcomb, 'Factor_Float'))
    nt.link(sock(add, 'Result_Color', True), sock(fcomb, 'A_Color'))
    sock(fcomb, 'B_Color').default_value = col('#FF4A1F')
    bg = nt.n('ShaderNodeBackground')
    nt.link(sock(fcomb, 'Result_Color', True), bg.inputs['Color'])
    nt.link(nt.attr('sky_bright'), bg.inputs['Strength'])
    out = nt.n('ShaderNodeOutputWorld')
    nt.link(bg.outputs[0], out.inputs['Surface'])


# ------------------------------------------------------------------ scene objects
def sphere(name, r, seg=96, rings=48):
    def b(bm):
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
        for f in bm.faces:
            f.smooth = True
    return mesh_from(name, b)


def beads(name, n, r, rad):
    def b(bm):
        for k in range(n):
            a = 2 * math.pi * k / n
            m = Matrix.Translation((r * math.cos(a), r * math.sin(a), 0))
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=rad, matrix=m)
        for f in bm.faces:
            f.smooth = True
    return mesh_from(name, b)


def build_eye():
    """v2 orb. EyeRoot faces the camera. Inside it:
      CoreGroup  - the sphere core, rim, glint (+ a slowly turning glass shell)
      G1         - outer ring + ticks (gimbal: leaves the face plane with the music)
      G2         - mid ring (second gimbal, opposite sense)
      G3 > Orbit - a steeply inclined orbit ring with three beads (appears when the rig opens up)
      Voice      - the spectrum ring (stays in the face plane so it always reads)"""
    root = link_obj(bpy.data.objects.new('EyeRoot', None))
    coreg = link_obj(bpy.data.objects.new('CoreGroup', None), root)
    shellr = link_obj(bpy.data.objects.new('ShellRot', None), coreg)
    g1 = link_obj(bpy.data.objects.new('G1', None), root)
    g2 = link_obj(bpy.data.objects.new('G2', None), root)
    g3 = link_obj(bpy.data.objects.new('G3', None), root)
    orbit = link_obj(bpy.data.objects.new('OrbitSpin', None), g3)
    for o in (g1, g2):
        o.rotation_mode = 'ZYX'      # spin about the ring's own normal first, then tilt
    g3.rotation_mode = 'XYZ'         # incline, then precess about the face normal
    n = int(math.ceil(shots.DURATION * FPS))
    mats = {
        'outer': eye_part_material('M_Outer', 'amber', 2.4, vis='g1_vis', reveal='boot1'),
        'ticks': eye_part_material('M_Ticks', 'amber', 1.5, vis='g1_vis', reveal='boot1'),
        'major': eye_part_material('M_Major', 'amber', 2.8, vis='g1_vis', reveal='boot1'),
        'micro': eye_part_material('M_Micro', 'amber', 0.9, vis='g1_vis', reveal='boot1'),
        'mid': eye_part_material('M_Mid', 'mid', 1.6, reveal='boot2'),
        'orbit': eye_part_material('M_Orbit', 'ring', 2.2, vis='g3_vis'),
        'bead': eye_part_material('M_Bead', 'amber', 6.0, vis='g3_vis'),
        'rim': eye_part_material('M_Rim', 'ring', 4.0),
        'core': core_material(),
        'shell': shell_material(),
        'voice': voice_material(n),
        'hi': white_material('M_Highlight', 5.0),
        'arc': white_material('M_Arc', 0.9),
    }
    parts = [
        ('Outer', ring('Outer', 231.0, 233.0), 'outer', g1),
        ('OuterInner', ring('OuterInner', 222.4, 223.0), 'micro', g1),
        ('TicksMinor', ticks('TicksMinor', 120, 208, 218, 1.5), 'ticks', g1),
        ('TicksMicro', ticks('TicksMicro', 360, 224.5, 228.5, 0.7), 'micro', g1),
        ('TicksMajor', ticks('TicksMajor', 12, 200, 218, 2.4), 'major', g1),
        ('Mid', ring('Mid', 175.3, 176.7), 'mid', g2),
        ('MidDash', ring('MidDash', 181.5, 182.3, 360, math.radians(-20), math.radians(70)), 'mid', g2),
        ('Orbit', ring('Orbit', 203.8, 205.2), 'orbit', orbit),
        ('Beads', beads('Beads', 3, 204.5, 4.2), 'bead', orbit),
        ('Voice', ring('Voice', 150.0, 200.0, 720), 'voice', root),
        ('Core', sphere('Core', 132.0), 'core', coreg),
        ('Shell', sphere('Shell', 146.0, 72, 36), 'shell', shellr),
        ('Rim', ring('Rim', 130.8, 133.2, 360, z=0.2), 'rim', coreg),
        ('Highlight', disc('Highlight', 6.0, 32, z=133.0, cx=-48, cy=42), 'hi', coreg),
        ('Arc', ring('Arc', 116.5, 119.5, 64, math.radians(115), math.radians(160), z=133.0), 'arc', coreg),
    ]
    for name, me, mk, parent in parts:
        me.materials.append(mats[mk])
        link_obj(bpy.data.objects.new(name, me), parent)
    return root


def build_waves():
    m = wave_material()
    for i in range(4):
        me = ring('Wave%d' % i, 0.955, 1.0, 1024)
        me.materials.append(m)
        o = link_obj(bpy.data.objects.new('Wave%d' % i, me))
        o['wave_a'] = 0.0
        o['wave_in'] = 0.955
        o.location = (0, 0, 0.06)
        o.scale = (0.001, 0.001, 1)


def build_sea():
    me = bpy.data.meshes.new('Sea')
    bm = bmesh.new()
    s = 6000.0
    v = [bm.verts.new((-s, -400, 0)), bm.verts.new((s, -400, 0)), bm.verts.new((s, s, 0)), bm.verts.new((-s, s, 0))]
    bm.faces.new(v)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(sea_material())
    return link_obj(bpy.data.objects.new('Sea', me))


def build_cities(seed=11, n=1600):
    import random
    rnd = random.Random(seed)
    me = bpy.data.meshes.new('Cities')
    bm = bmesh.new()
    lay_b = bm.faces.layers.float.new('bright')
    lay_w = bm.faces.layers.float.new('warm')
    lay_s = bm.faces.layers.float.new('seed')
    rs = random.Random(99)   # separate stream so the city layout is unchanged
    clusters = [(rnd.uniform(-62, 62), rnd.uniform(1.5, 7.0), rnd.uniform(900, 1700)) for _ in range(26)]
    for i in range(n):
        if rnd.random() < 0.75:
            ca, cw, cd = rnd.choice(clusters)
            az = rnd.gauss(ca, cw)
            dist = cd + rnd.gauss(0, 60)
        else:
            az = rnd.uniform(-70, 70)
            dist = rnd.uniform(850, 1900)
        a = math.radians(az)
        x, y = dist * math.sin(a), dist * math.cos(a)
        z = abs(rnd.gauss(0, 2.2)) + 0.4
        if rnd.random() < 0.07:
            z += rnd.uniform(6, 28)
        size = rnd.uniform(0.9, 1.8) * dist / 1200.0
        nx, ny = -math.sin(a), -math.cos(a)
        px, py = -ny * size / 2, nx * size / 2
        vs = [bm.verts.new((x - px, y - py, z - size / 2)), bm.verts.new((x + px, y + py, z - size / 2)),
              bm.verts.new((x + px, y + py, z + size / 2)), bm.verts.new((x - px, y - py, z + size / 2))]
        f = bm.faces.new(vs)
        f[lay_b] = rnd.uniform(0.15, 1.0) ** 2
        f[lay_w] = 0.0 if rnd.random() < 0.12 else 1.0
        # order of being taken: lights straight ahead of the orb first, spreading out to the edges
        f[lay_s] = 0.012 + 0.982 * (0.72 * rs.random() + 0.28 * min(1.0, abs(az) / 70.0))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(lights_material())
    obj = link_obj(bpy.data.objects.new('Cities', me))
    # lone light, apart from the others
    me2 = disc('Lone', 1.4, 16)
    me2.materials.append(lone_material())
    lone = link_obj(bpy.data.objects.new('LoneLight', me2))
    a = math.radians(shots.LONE_AZ)
    lone.location = (1300 * math.sin(a), 1300 * math.cos(a), 2.2)
    lone.rotation_euler = (math.radians(90), 0, -a)
    return obj


def build_cameras():
    cams = {}
    for name, w, h in (('Cam', 1920, 1080), ('CamV', 1080, 1920)):
        cd = bpy.data.cameras.new(name)
        cd.clip_start = 0.1
        cd.clip_end = 8000
        cd.sensor_fit = 'HORIZONTAL' if w >= h else 'VERTICAL'
        cd.sensor_width = 36.0
        cd.sensor_height = 36.0
        cams[name] = link_obj(bpy.data.objects.new(name, cd))
    return cams


def render_settings():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    ee = sc.eevee
    ee.taa_render_samples = 32
    ee.use_raytracing = True
    try:
        ee.ray_tracing_method = 'SCREEN'
    except Exception:
        pass
    ee.use_shadows = False
    try:
        ee.use_fast_gi = False
    except Exception:
        pass
    sc.render.fps = FPS
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    im = sc.render.image_settings
    im.file_format = 'OPEN_EXR'
    im.color_depth = '16'
    im.exr_codec = 'DWAA'
    im.color_mode = 'RGB'
    try:
        sc.view_settings.view_transform = 'Standard'
    except Exception:
        pass


# ------------------------------------------------------------------ baking
PROPS = ['eye_gold', 'eye_ember', 'eye_int', 'eye_core', 'eye_rings', 'sky_pre', 'sky_dawn', 'sky_glow', 'sky_bright',
         'lights', 'fire', 'lone', 'sea_chop', 'sea_rough', 'sea_lines']
RIG_PROPS = ['eye_cold', 'eye_heat', 'eye_amber', 'eye_crimson', 'voice_gain', 'g1_vis', 'g3_vis', 'shell_vis',
             'boot1', 'boot2', 'boot3', 'lights_taken']


def look_at(cam_loc, target, roll=0.0):
    d = Vector(target) - Vector(cam_loc)
    q = d.to_track_quat('-Z', 'Y')
    e = q.to_euler()
    if roll:
        e.rotate_axis('Z', math.radians(roll))
    return e


def key(obj, path, frame):
    obj.keyframe_insert(data_path=path, frame=frame)


def bake(frames):
    import rig
    sc = bpy.context.scene
    ob = bpy.data.objects
    root = ob['EyeRoot']
    coreg, shellr, voice = ob['CoreGroup'], ob['ShellRot'], ob['Voice']
    g1, g2, g3, orbit = ob['G1'], ob['G2'], ob['G3'], ob['OrbitSpin']
    waves = [ob['Wave%d' % i] for i in range(4)]
    cams = {'Cam': ob['Cam'], 'CamV': ob['CamV']}
    all_props = PROPS + RIG_PROPS
    for p in all_props:
        sc[p] = 0.0
    sc['eye_dir'] = [0.0, 1.0, 0.0]
    for f in frames:
        t = (f - 1) / FPS
        st = shots.state(t)
        rs = rig.rig_state(t, st['bezel_rot'], st['iris_rot'])
        for p in PROPS:
            v = float(st[p])
            if p == 'eye_int':
                v *= rs['int_boost']      # the collapsing orb stays a bright point
            elif p == 'sky_glow':
                v *= rs['sky_glow_k']
            sc[p] = v
            sc.keyframe_insert(data_path='["%s"]' % p, frame=f)
        for p in RIG_PROPS:
            sc[p] = float(rs[p])
            sc.keyframe_insert(data_path='["%s"]' % p, frame=f)
        root.location = st['eye_loc']
        s = st['eye_R'] / 232.0
        root.scale = (s, s, s)
        key(root, 'location', f)
        key(root, 'scale', f)
        a = st['ap']
        cs = a * rs['core_scale']
        coreg.scale = (cs, cs, cs)
        key(coreg, 'scale', f)
        rk = rs['ring_scale']
        vs = a * rk
        voice.scale = (vs, vs, vs)
        key(voice, 'scale', f)
        shellr.rotation_euler = [math.radians(x) for x in rs['shell_rot']]
        key(shellr, 'rotation_euler', f)
        g1.rotation_euler = [math.radians(x) for x in rs['g1']]
        g1.scale = (rk, rk, rk)
        key(g1, 'rotation_euler', f)
        key(g1, 'scale', f)
        g2.rotation_euler = [math.radians(x) for x in rs['g2']]
        gs = a * rs['g2_scale'] * rk
        g2.scale = (gs, gs, gs)
        key(g2, 'rotation_euler', f)
        key(g2, 'scale', f)
        g3.rotation_euler = [math.radians(x) for x in rs['g3']]
        g3.scale = (rk, rk, rk)
        key(g3, 'rotation_euler', f)
        key(g3, 'scale', f)
        orbit.rotation_euler = (0, 0, math.radians(rs['g3_spin']))
        key(orbit, 'rotation_euler', f)
        # shockwaves: centered under the orb, rolling out past the camera
        cl = st['cam']['loc']
        el = st['eye_loc']
        dcam = math.hypot(el[0] - cl[0], el[1] - cl[1])
        rmax = 1.15 * dcam + 20.0
        for w, (u, alpha) in zip(waves, rs['waves']):
            win = 0.955
            if alpha > 0.002:
                rr = rmax * (1 - (1 - u) ** 2.2) + 0.5
                w.location = (el[0], el[1], 0.06)
                w.scale = (rr, rr, 1.0)
                w_abs = min(18.0, max(1.5, 0.025 * (dcam - rr)))   # thinner as its front nears the camera
                win = 1.0 - min(0.045, max(0.003, w_abs / rr))
                # it rolls toward the camera and dies out just before it would pass underneath
                alpha *= min(1.0, max(0.0, (dcam - 6.0 - rr) / max(15.0, 0.12 * dcam)))
            else:
                w.scale = (0.001, 0.001, 1.0)
            w['wave_a'] = float(alpha)
            w['wave_in'] = float(win)
            key(w, 'location', f)
            key(w, 'scale', f)
            w.keyframe_insert(data_path='["wave_a"]', frame=f)
            w.keyframe_insert(data_path='["wave_in"]', frame=f)
        for name, cst in (('Cam', st['cam']), ('CamV', st['camv'])):
            c = cams[name]
            c.location = cst['loc']
            c.rotation_euler = look_at(cst['loc'], cst['target'], cst.get('roll', 0.0))
            c.data.lens = cst['lens']
            key(c, 'location', f)
            key(c, 'rotation_euler', f)
            c.data.keyframe_insert(data_path='lens', frame=f)
        # eye faces the 16:9 camera (both cameras sit close together)
        cl = Vector(st['cam']['loc'])
        el = Vector(st['eye_loc'])
        q = (cl - el).to_track_quat('Z', 'Y')
        root.rotation_mode = 'XYZ'
        root.rotation_euler = q.to_euler()
        key(root, 'rotation_euler', f)
        d = (el - cl).normalized()
        sc['eye_dir'] = [d.x, d.y, d.z]
        sc.keyframe_insert(data_path='["eye_dir"]', frame=f)
    for a in [sc.animation_data, root.animation_data] + [o.animation_data for o in (coreg, shellr, voice, g1, g2, g3, orbit)] + \
             [w.animation_data for w in waves] + \
             [c.animation_data for c in cams.values()] + [c.data.animation_data for c in cams.values()]:
        if a and a.action:
            for fc in iter_fcurves(a.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'


def iter_fcurves(action):
    fcs = getattr(action, 'fcurves', None)
    if fcs is not None:
        try:
            for fc in fcs:
                yield fc
            return
        except TypeError:
            pass
    for layer in getattr(action, 'layers', []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    yield fc


def export_projection(frames, out_json):
    """Per frame and camera: the orb's screen position/size, horizon and reflection lines (for overlays), plus the
    camera's world matrix and lens so the compositor can project any 3D point (city lights, particles)."""
    sc = bpy.context.scene
    res = {}
    for cname, (w, h) in (('Cam', (1920, 1080)), ('CamV', (1080, 1920))):
        cam = bpy.data.objects[cname]
        sc.render.resolution_x, sc.render.resolution_y = w, h
        rows = []
        mats = []
        for f in frames:
            sc.frame_set(f)
            root = bpy.data.objects['EyeRoot']
            c = root.matrix_world.translation
            R = root.scale[0] * 232.0
            mw = cam.matrix_world
            right = Vector((mw[0][0], mw[1][0], mw[2][0]))
            fwd = -Vector((mw[0][2], mw[1][2], mw[2][2]))
            p0 = world_to_camera_view(sc, cam, c)
            p1 = world_to_camera_view(sc, cam, c + right * R)
            flat = Vector((fwd.x, fwd.y, 0)).normalized()
            hz = world_to_camera_view(sc, cam, Vector((cam.location.x, cam.location.y, 0)) + flat * 6000)
            refl = world_to_camera_view(sc, cam, Vector((c.x, c.y, -c.z)))
            rows.append([round(p0.x, 5), round(1 - p0.y, 5), round(abs(p1.x - p0.x) * w / h, 5), round(1 - hz.y, 5),
                         round(1 - refl.y, 5), round(p0.z, 2)])
            m = cam.matrix_world
            mats.append([round(m[i][j], 6) for i in range(3) for j in range(4)] + [round(cam.data.lens, 4)])
        res[cname] = rows
        res[cname + 'Mat'] = mats
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    with open(out_json, 'w') as fh:
        json.dump({'fields': ['x', 'y', 'r_h', 'horizon_y', 'refl_y', 'depth'], 'first_frame': frames[0],
                   'frames': list(frames), **res}, fh)


def render_tests(frames, which):
    import gpu
    sc = bpy.context.scene
    os.makedirs(os.path.join(ROOT, 'analysis', 'test'), exist_ok=True)
    for cname in which:
        sc.camera = bpy.data.objects[cname]
        sc.render.resolution_x, sc.render.resolution_y = (1920, 1080) if cname == 'Cam' else (1080, 1920)
        for f in frames:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(ROOT, 'analysis', 'test', '%s_%05d.exr' % (cname, f))
            import time
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            try:
                gi = gpu.platform.renderer_get()
            except Exception as e:
                gi = str(e)[:40]
            print('TEST_RENDERED', cname, f, round(time.time() - t0, 2), 's', gi, flush=True)


def export_cities(obj, out_json):
    """City light centers (world space) + brightness/warmth, so the compositor can wire threads to real lights."""
    me = obj.data
    lb = me.attributes.get('bright')
    lw = me.attributes.get('warm')
    ls = me.attributes.get('seed')
    pts = []
    for i, p in enumerate(me.polygons):
        c = obj.matrix_world @ p.center
        pts.append([round(c.x, 3), round(c.y, 3), round(c.z, 3), round(lb.data[i].value, 4) if lb else 1.0,
                    round(lw.data[i].value, 1) if lw else 1.0, round(ls.data[i].value, 5) if ls else 1.0])
    with open(out_json, 'w') as fh:
        json.dump(pts, fh)


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    bpy.ops.wm.read_factory_settings(use_empty=True)
    render_settings()
    world_shader()
    build_sea()
    export_cities(build_cities(), os.path.join(ROOT, 'analysis', 'cities.json'))
    build_eye()
    build_waves()
    cams = build_cameras()
    sc = bpy.context.scene
    sc.camera = cams['Cam']
    n = int(math.ceil(shots.DURATION * FPS))
    sc.frame_start, sc.frame_end = 1, n
    if args and args[0] == 'test':
        frames = [int(x) for x in args[1].split(',')]
        bake(frames)
        export_projection(frames, os.path.join(ROOT, 'analysis', 'proj_test.json'))
        render_tests(frames, args[2].split(',') if len(args) > 2 else ['Cam'])
        print('TEST_DONE')
        return
    frames = list(range(1, n + 1))
    bake(frames)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, 'hello_world.blend'))
    export_projection(frames, os.path.join(ROOT, 'analysis', 'proj.json'))
    print('WORLD_DONE frames', n)


if __name__ == '__main__':
    main()
