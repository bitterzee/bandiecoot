"""Builds every Kamar furniture item in Blender and exports them to one GLB.

Each floor item is modeled in its own frame: X = across its front (u), -Y = toward the front (v),
Z = up, with the corner (u=0, v=0, z=0) at the origin. Sizes match KM3 in index.html (1 unit ~ 25 cm).
Wall items (w_*) use X = across the wall, Z = up from their bottom edge, -Y = out from the wall.
Material names carry the colour for the app: c_<hex> plain, g_<hex>_<glow> glowing.
"""
import bpy, math, sys

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else '/tmp/kamar.glb'

bpy.ops.wm.read_factory_settings(use_empty=True)
MATS = {}
RES = 1.8  # mesh resolution multiplier for round parts
PARTS = []


def mat(col, glow=0):
    col = col.lstrip('#').lower()
    if len(col) == 3:
        col = ''.join(ch * 2 for ch in col)
    name = f'g_{col}_{glow}' if glow else f'c_{col}'
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    rgb = tuple(int(col[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb)
    b.inputs['Base Color'].default_value = (*lin, 1)
    b.inputs['Roughness'].default_value = .6
    if glow:
        b.inputs['Emission Color'].default_value = (*lin, 1)
        b.inputs['Emission Strength'].default_value = glow
    MATS[name] = m
    return m


def _fin(o, col, glow, bev, smooth=False):
    o.data.materials.append(mat(col, glow))
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bev:
        # rounded edges with hardened normals: flat faces stay crisp, the bevels shade smoothly
        for p in o.data.polygons:
            p.use_smooth = True
        md = o.modifiers.new('bev', 'BEVEL')
        md.width = bev
        md.segments = 5 if bev >= .08 else 4 if bev >= .03 else 2
        md.limit_method = 'ANGLE'
        md.harden_normals = True
        with bpy.context.temp_override(object=o, active_object=o):
            bpy.ops.object.modifier_apply(modifier=md.name)
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
    o.select_set(False)
    PARTS.append(o)
    return o


def box(u0, u1, v0, v1, z0, z1, col, bev=.05, glow=0, rot=(0, 0, 0)):
    w, d, h = abs(u1 - u0), abs(v1 - v0), abs(z1 - z0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=((u0 + u1) / 2, -(v0 + v1) / 2, (z0 + z1) / 2), rotation=rot)
    o = bpy.context.object
    o.scale = (w, d, h)
    bev = min(bev, w * .3, d * .3, h * .3) if bev else 0
    return _fin(o, col, glow, bev if bev > .004 else 0)


def cyl(u, v, z0, z1, r, col, r2=None, seg=28, glow=0, axis='Z', bev=.02, h=0):
    depth = abs(z1 - z0)
    if axis == 'Z':
        loc, rot = (u, -v, (z0 + z1) / 2), (0, 0, 0)
    elif axis == 'Y':  # z0..z1 measured along v (toward the front)
        loc, rot = (u, -(v + (z0 + z1) / 2), h), (math.pi / 2, 0, 0)
    else:  # along u
        loc, rot = ((z0 + z1) / 2, -v, u), (0, math.pi / 2, 0)
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=max(12, int(seg * RES)), radius=r, depth=depth, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=max(12, int(seg * RES)), radius1=r, radius2=r2, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o = _fin(o, col, glow, min(bev, r * .3, depth * .3) if bev else 0)
    for p in o.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    return o


def sph(u, v, z, r, col, sc=(1, 1, 1), glow=0, rot=(0, 0, 0), seg=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=int(seg * RES), ring_count=int(seg * RES) // 2, radius=r, location=(u, -v, z), rotation=rot)
    o = bpy.context.object
    o.scale = sc
    return _fin(o, col, glow, 0, smooth=True)


def tor(u, v, z, R, r, col, rot=(0, 0, 0), glow=0, arc=None):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=int(36 * RES), minor_segments=int(10 * RES), location=(u, -v, z), rotation=rot)
    return _fin(bpy.context.object, col, glow, 0, smooth=True)



def rod(p0, p1, r, col, seg=16, glow=0):
    """Cylinder between two (u, v, z) points."""
    from mathutils import Vector
    a = Vector((p0[0], -p0[1], p0[2])); b = Vector((p1[0], -p1[1], p1[2]))
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=max(12, int(seg * RES)), radius=r, depth=d.length, location=(a + b) / 2)
    o = bpy.context.object
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    o = _fin(o, col, glow, 0)
    for p in o.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    return o


def slab(pts, v0, v1, col, bev=.03, ox=0, oz=0, sc=1, glow=0, samples=10):
    """Closed Catmull-Rom outline in the (u, z) plane, extruded from v0 to v1 toward the front."""
    import bmesh
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for k in range(samples):
            t = k / samples
            t2, t3 = t * t, t * t * t
            out.append(tuple(.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    me = bpy.data.meshes.new('slab')
    bm = bmesh.new()
    back = [bm.verts.new((ox + x * sc, -v0, oz + z * sc)) for x, z in out]
    front = [bm.verts.new((ox + x * sc, -v1, oz + z * sc)) for x, z in out]
    bm.faces.new(back[::-1])
    bm.faces.new(front)
    m = len(out)
    for i in range(m):
        bm.faces.new((back[i], back[(i + 1) % m], front[(i + 1) % m], front[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new('slab', me)
    bpy.context.collection.objects.link(o)
    for p in o.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    md = None
    if bev:
        md = o.modifiers.new('bev', 'BEVEL'); md.width = bev; md.segments = 4; md.limit_method = 'ANGLE'; md.angle_limit = math.radians(40); md.harden_normals = True
        with bpy.context.temp_override(object=o, active_object=o):
            bpy.ops.object.modifier_apply(modifier=md.name)
    o.data.materials.append(mat(col, glow))
    PARTS.append(o)
    return o


def finish(name):
    """Join the parts made since the last finish into one object named name, origin at the item corner."""
    global PARTS
    if not PARTS:
        return
    bpy.ops.object.select_all(action='DESELECT')
    for o in PARTS:
        o.select_set(True)
    bpy.context.view_layer.objects.active = PARTS[0]
    if len(PARTS) > 1:
        bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    o.data.name = name
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    o.select_set(False)
    PARTS = []


WOOD, WOOD_D, WOOD_L = '#8b5a2b', '#5a3a22', '#b07a44'
BOOKS = ['#d23b2b', '#2f5fa8', '#e2c44c', '#2f8f45', '#f4f0e2', '#8a4fb3', '#e08a2e', '#1d1d1d', '#2f9e9a']

# ---------------- floor furniture ----------------
# kasur [4.2, 8, 3]: wooden bed, headboard against the wall
box(0, 4.2, 0, .35, 0, 3, WOOD_D, .1)
box(.15, 4.05, .05, .3, 2.1, 2.7, WOOD, .06)
box(0, 4.2, .35, 8, .35, 1, '#6b4a2b', .06)
for u in (.1, 3.8):
    box(u, u + .3, 7.6, 7.95, 0, .4, WOOD_D, .04)
box(0, 4.2, 7.7, 8, 0, 1.55, WOOD_D, .08)
box(.15, 4.05, .4, 7.7, 1, 1.7, '#f1ede4', .18)
box(.55, 3.65, .65, 2.1, 1.65, 2.25, '#ffffff', .24)
box(.08, 4.12, 3.1, 7.72, 1.45, 1.95, '#2f6db0', .16)
box(.07, 4.13, 4.1, 4.55, 1.5, 1.97, '#e2c44c', .1)
box(.07, 4.13, 5.6, 6.05, 1.5, 1.97, '#e2c44c', .1)
box(.3, 1.4, 6.2, 7, 1.95, 2.05, '#e08a2e', .03, rot=(0, 0, .3))  # a comic on the blanket
finish('kasur')

# meja [5, 2.4, 3]: study desk with a drawer block
for u, v in ((.12, .12), (4.6, .12), (.12, 2.0), (4.6, 2.0)):
    box(u, u + .28, v, v + .28, 0, 2.75, WOOD_D, .04)
box(0, 5, 0, 2.4, 2.72, 3, WOOD_L, .05)
box(3, 4.85, .15, 2.3, 1.15, 2.72, WOOD, .05)
for z in (1.3, 2.0):
    box(3.08, 4.77, 2.3, 2.36, z, z + .6, '#9c6a38', .03)
    box(3.75, 4.1, 2.36, 2.44, z + .25, z + .35, '#e2c44c', .02)
box(.5, 2.9, .3, .5, 2.2, 2.72, WOOD, .03)  # back rail
finish('meja')

# kursi [1.8, 1.8, 3.6]: chair, backrest at the front so whoever sits faces the desk behind it
for u, v in ((.2, .2), (1.6, .2), (.2, 1.6), (1.6, 1.6)):
    cyl(u, v, 0, 1.55, .09, '#3a3a3a', seg=12)
box(0, 1.8, 0, 1.8, 1.5, 1.85, '#2e3274', .14)
box(.1, 1.7, 1.52, 1.8, 1.85, 3.55, '#2e3274', .13)
box(.25, 1.55, 1.47, 1.53, 2.2, 3.3, '#3c43a0', .05)
finish('kursi')

# lemari [3, 2, 8]: wardrobe
box(0, 3, 0, 2, 0, 7.85, '#9a6a3e', .06)
box(-.06, 3.06, -.02, 2.08, 7.8, 8, '#7a5230', .05)
box(.08, 1.46, 2, 2.08, .3, 7.65, '#a8743f', .04)
box(1.54, 2.92, 2, 2.08, .3, 7.65, '#a8743f', .04)
box(.3, 1.24, 2.08, 2.11, 4.6, 7.2, '#b9d8e8', .01)
for u in (1.3, 1.65):
    cyl(u, 2.13, 3.6, 4.3, .05, '#e2c44c', seg=10)
box(.1, 2.9, 2, 2.08, .05, .28, '#7a5230', .03)
finish('lemari')

# rakbuku [3, 1.2, 6]: bookshelf full of books
box(0, .15, 0, 1.2, 0, 6, '#6b4a2b', .03)
box(2.85, 3, 0, 1.2, 0, 6, '#6b4a2b', .03)
box(0, 3, 0, .08, 0, 6, '#3a2a1a', 0)
for z in (0, 1.95, 3.9, 5.85):
    box(.1, 2.9, 0, 1.2, z, z + .15, '#6b4a2b', .03)
k = 0
for zb in (.15, 2.1, 4.05):
    u = .2
    while u < 2.7:
        t = .12 + (k * 7 % 4) * .03
        h = 1.15 + (k * 5 % 5) * .12
        lean = .12 if k % 11 == 6 else 0
        box(u, u + t, .15, 1.05, zb, zb + h, BOOKS[k % len(BOOKS)], .015, rot=(0, lean, 0))
        u += t + .015
        k += 1
finish('rakbuku')

# tv [2.2, 2, 2]: CRT TV with a curved screen
box(0, 2.2, 1.05, 2, 0, 2, '#3a3a3a', .14)
box(.3, 1.9, .15, 1.1, .2, 1.8, '#2e2e2e', .25)
box(.14, 1.66, 1.96, 2.02, .18, 1.8, '#1f1f1f', .05)
box(.24, 1.56, 1.96, 2.05, .27, 1.72, '#5a8fb8', .2, glow=.9)  # rounded-rectangle CRT glass
for z in (1.3, 1.0, .7):
    cyl(1.93, 2.0, 0, .06, .07, '#c8302a' if z == 1.3 else '#111', axis='Y', seg=12)
    PARTS[-1].location.z = z
cyl(1.1, 1.5, 2, 2.12, .18, '#2a2a2a', seg=24)
for a in (-.45, .45):
    rod((1.1, 1.5, 2.1), (1.1 + math.sin(a) * 1.0, 1.4, 2.1 + math.cos(a) * 1.0), .02, '#9a9aa8')
    sph(1.1 + math.sin(a) * 1.0, 1.4, 2.1 + math.cos(a) * 1.0, .04, '#9a9aa8')
finish('tv')

# komputer [2.6, 2.8, 2.6]: beige CRT monitor + keyboard + mouse
box(.75, 1.85, .7, 1.8, 0, .12, '#cfc9b8', .05)
cyl(1.3, 1.25, .1, .45, .25, '#cfc9b8', seg=16)
box(.55, 2.05, .1, .9, .55, 2.1, '#d8d2c0', .2)
box(.3, 2.3, .8, 2.2, .4, 2.35, '#e6e1d2', .12)
box(.45, 2.15, 2.2, 2.24, .55, 2.2, '#c9c3b2', .03)
box(.55, 2.05, 2.22, 2.27, .65, 2.1, '#1d3a5a', .04, glow=.35)
for z, w in ((1.8, .9), (1.6, 1.3), (1.4, .6), (1.2, 1.1)):
    box(.65, .65 + w, 2.27, 2.29, z, z + .07, '#7fd17f', 0, glow=1.2)
box(.2, 2.4, 2.35, 2.78, 0, .14, '#e6e1d2', .04)
for i in range(10):
    for j in range(3):
        box(.3 + i * .2, .45 + i * .2, 2.42 + j * .11, 2.5 + j * .11, .14, .19, '#cfc9b8', .012)
sph(2.52, 2.58, .07, .1, '#e6e1d2', sc=(1, 1.4, .6))
finish('komputer')

# compo [2.8, 1, 1.2]: boombox / tape compo
box(0, 2.8, 0, 1, 0, 1.2, '#2a2a2a', .1)
for u in (.45, 2.35):
    cyl(u, 1, -.04, .06, .38, '#555', axis='Y', seg=28, h=.6)
    cyl(u, 1, .0, .1, .26, '#111', axis='Y', seg=24, h=.6)
box(.95, 1.85, 1, 1.05, .45, .95, '#9fb4c8', .02)
box(1.05, 1.75, 1.04, 1.07, .55, .85, '#2a2a2a', .01)
for i in range(5):
    box(.95 + i * .19, 1.08 + i * .19, .95, 1.04, .15, .3, '#e2c44c' if i == 2 else '#bbb', .02)
box(.3, 2.5, .4, .6, 1.2, 1.55, '#3a3a3a', .06)
box(.45, 2.35, .4, .6, 1.2, 1.4, '#2a2a2a', 0)
finish('compo')

# konsol [1.3, 1.6, .35]: grey console + controller with cable
box(0, 1.3, 0, 1, 0, .3, '#a6a6b4', .06)
cyl(.45, .45, .28, .34, .28, '#8a8a98', seg=24)
box(.85, 1.15, .75, .95, .3, .32, '#6a6a78', .01)
cyl(1.05, .98, 0, .06, .04, '#c8302a', axis='Y', seg=10, h=.16)
box(.25, .95, 1.2, 1.45, 0, .12, '#9a9aa8', .05)
sph(.27, 1.42, .07, .13, '#9a9aa8', sc=(1, 1.3, .6))
sph(.93, 1.42, .07, .13, '#9a9aa8', sc=(1, 1.3, .6))
for du, col in ((.75, '#2f8f45'), (.83, '#d23b2b'), (.79, '#2f5fa8')):
    cyl(du, 1.28, .12, .15, .03, col, seg=8)
box(.58, .62, 1.0, 1.2, .02, .05, '#333', 0)
finish('konsol')

# kaset [1, .7, .5]: stack of cassette tapes
for i, col in enumerate(('#d23b2b', '#2f5fa8', '#e2c44c')):
    box(0 + i * .03, 1, 0, .7, i * .16, i * .16 + .14, '#1d1d1d', .02, rot=(0, 0, (i - 1) * .12))
    box(.1 + i * .03, .9, .68, .72, i * .16 + .03, i * .16 + .11, col, .005, rot=(0, 0, (i - 1) * .12))
finish('kaset')

# gitar [1.2, .5, 4.6]: offset double-cutaway electric guitar on an A-frame stand
BODY = [(0, 0), (.33, .03), (.5, .18), (.55, .42), (.43, .63), (.41, .78), (.49, .96), (.52, 1.16), (.43, 1.26), (.31, 1.14), (.17, 1.0), (.07, 1.02),
        (-.07, 1.02), (-.17, 1.05), (-.31, 1.23), (-.44, 1.3), (-.5, 1.13), (-.42, .93), (-.4, .76), (-.5, .55), (-.55, .3), (-.43, .08), (-.2, 0)]
slab(BODY, .14, .36, '#c8452f', bev=.05, ox=.6, oz=.35)
GUARD = [(.05, .1), (.3, .2), (.38, .45), (.3, .62), (.3, .8), (.36, .98), (.18, .98), (.07, .9), (-.07, .9), (-.2, 1.0), (-.33, 1.06), (-.3, .8), (-.32, .55), (-.24, .25)]
slab(GUARD, .36, .375, '#f4f0e2', bev=.008, ox=.6, oz=.35)
for z in (.82, 1.02, 1.2):
    box(.47, .73, .37, .395, z, z + .07, '#f8f4ea', .015)
    for k in range(6):
        cyl(.5 + k * .042, .39, 0, .012, .01, '#9a9a9a', axis='Y', seg=8, h=z + .035, bev=0)
box(.46, .74, .36, .4, .58, .7, '#c9c9c9', .02)                              # bridge
for k, z in enumerate((.62, .48, .4)):
    cyl(.92 - k * .03, .37, 0, .06, .045, '#e6e6e6', axis='Y', seg=16, h=z + .2)  # knobs
box(.52, .68, .17, .34, 1.32, 4.0, '#6b3e1e', .025)                           # neck
box(.53, .67, .34, .37, 1.4, 4.0, '#2a1a10', .01)                             # fretboard
for i in range(20):
    z = 1.45 + (4.0 - 1.45) * (1 - .94 ** i) / (1 - .94 ** 20)
    box(.53, .67, .365, .375, z, z + .012, '#d8d8d8', 0)
for z in (2.0, 2.45, 2.9, 3.3):
    cyl(.6, .375, 0, .006, .018, '#f4f0e2', axis='Y', seg=10, h=z, bev=0)
HEAD = [(-.08, 0), (.08, 0), (.12, .2), (.2, .38), (.16, .48), (.0, .46), (-.1, .3)]
slab(HEAD, .2, .32, '#c8452f', bev=.02, ox=.6, oz=3.98)
for k in range(6):
    cyl(.73 + (k % 2) * .0, .28, 0, .12, .025, '#d0d0d0', axis='Y', seg=10, h=4.04 + k * .065, bev=0)
    PARTS[-1].location.x = .7 + k * .012
for x0, x1 in ((.15, .55), (1.05, .65)):                                      # A-frame stand
    rod((x0, .1, 0), (x1, .25, 1.0), .03, '#2a2a2a')
    rod((x0, .45, 0), (x1, .25, 1.0), .03, '#2a2a2a')
rod((.3, .25, .3), (.9, .25, .3), .035, '#2a2a2a')
rod((.6, .1, 1.3), (.6, .1, 3.3), .025, '#2a2a2a')
finish('gitar')

# drum [1.4, 1.4, 1.6]: snare on a stand with sticks
for a in (0, 2.1, 4.2):
    cyl(.7 + math.cos(a) * .45, .7 + math.sin(a) * .45, 0, .9, .035, '#888', seg=8)
cyl(.7, .7, .6, 1.0, .05, '#aaa', seg=10)
cyl(.7, .7, 1.0, 1.45, .6, '#f4f0e2', seg=32)
cyl(.7, .7, 1.43, 1.5, .62, '#bbbbbb', seg=32, bev=.01)
cyl(.7, .7, .98, 1.04, .62, '#bbbbbb', seg=32, bev=.01)
cyl(.7, .7, 1.5, 1.51, .58, '#ece6d6', seg=32, bev=0)
for i in range(8):
    a = i / 8 * math.tau
    box(.7 + math.cos(a) * .6 - .03, .7 + math.cos(a) * .6 + .03, .7 + math.sin(a) * .6 - .03, .7 + math.sin(a) * .6 + .03, 1.05, 1.42, '#999', .01)
box(.2, 1.3, .9, .97, 1.52, 1.58, '#e6c27a', .02, rot=(0, 0, .2))
box(.25, 1.35, 1.05, 1.12, 1.52, 1.58, '#e6c27a', .02, rot=(0, 0, -.15))
finish('drum')

# ampli [1.6, 1, 1.7]: guitar amp
box(0, 1.6, 0, 1, 0, 1.7, '#1d1d1d', .08)
box(.1, 1.5, .96, 1.02, .1, 1.3, '#3a3a3a', .03)
for i in range(6):
    box(.12, 1.48, 1.02, 1.04, .18 + i * .18, .24 + i * .18, '#2a2a2a', 0)
box(.1, 1.5, .96, 1.02, 1.36, 1.62, '#c9b27a', .02)
for u in (.3, .55, .8, 1.05, 1.3):
    cyl(u, 1.02, 0, .08, .05, '#111', axis='Y', seg=12)
    PARTS[-1].location.z = 1.49
box(.5, 1.1, .4, .6, 1.7, 1.82, '#111', .04)
finish('ampli')

# kipas [1.2, 1.2, 4.2]: standing fan facing front
cyl(.6, .6, 0, .2, .45, '#5a6a7a', r2=.35, seg=24)
cyl(.6, .6, .2, 3.2, .06, '#9aa6b0', seg=12)
sph(.6, .45, 3.5, .22, '#7a8690', sc=(1, 1.3, 1))
tor(.6, .85, 3.5, .7, .04, '#c9d2da', rot=(math.pi / 2, 0, 0))
tor(.6, .85, 3.5, .45, .025, '#c9d2da', rot=(math.pi / 2, 0, 0))
for i in range(3):
    a = i / 3 * math.tau
    sph(.6 + math.cos(a) * .32, .8, 3.5 + math.sin(a) * .32, .3, '#7fb4d8', sc=(1, .12, .5), rot=(0, -a, 0))
for i in range(8):
    a = i / 8 * math.pi
    box(.57, .63, .84, .86, 2.8, 4.2, '#c9d2da', 0, rot=(0, a, 0))
    PARTS[-1].location = (.6, -.85, 3.5)
cyl(.6, .9, 0, .08, .1, '#5a6a7a', axis='Y', seg=16)
PARTS[-1].location.z = 3.5
finish('kipas')

# tanaman [1, 1, 3]: potted plant
cyl(.5, .5, 0, .85, .32, '#b0563a', r2=.42, seg=20)
cyl(.5, .5, .78, .9, .45, '#8a3f2a', seg=20)
cyl(.5, .5, .86, .88, .4, '#3a2a1a', seg=20, bev=0)
for i in range(9):
    a = i / 9 * math.tau
    tilt = .35 + (i % 3) * .2
    sph(.5 + math.cos(a) * .3, .5 + math.sin(a) * .3, 1.6 + (i % 3) * .4, .5, ['#2f8f45', '#3aa055', '#46b062'][i % 3], sc=(.22, .07, 1), rot=(math.sin(a) * tilt, -math.cos(a) * tilt, a))
finish('tanaman')

# bola [.7, .7, .7]: basketball
sph(.35, .35, .35, .35, '#e07a2e')
tor(.35, .35, .35, .35, .012, '#2a1408', rot=(0, 0, 0))
tor(.35, .35, .35, .35, .012, '#2a1408', rot=(math.pi / 2, 0, 0))
tor(.35, .35, .35, .35, .012, '#2a1408', rot=(0, math.pi / 2, 0))
finish('bola')

# karpet [6, 4, .05]: rug
box(0, 6, 0, 4, 0, .04, '#b3243a', .02)
box(.3, 5.7, .3, 3.7, .04, .05, '#d9822b', 0)
box(.6, 5.4, .6, 3.4, .05, .06, '#b3243a', 0)
for i in range(6):
    box(.9 + i * .8, 1.3 + i * .8, 1.8, 2.2, .06, .07, '#f1e3a4', 0)
for i in range(16):
    box(.1 + i * .37, .14 + i * .37, -.12, 0, 0, .02, '#f1e3a4', 0)
    box(.1 + i * .37, .14 + i * .37, 4, 4.12, 0, .02, '#f1e3a4', 0)
finish('karpet')

# lampu [1, 1, 2.2]: anglepoise desk lamp
cyl(.5, .45, 0, .1, .36, '#1f5f3a', seg=32, bev=.03)
cyl(.5, .45, .1, .16, .12, '#2a2a2a', seg=20)
B0, E, H = (.5, .45, .16), (.5, .2, 1.25), (.5, .72, 1.8)
for du in (-.05, .05):
    rod((B0[0] + du, B0[1], B0[2]), (E[0] + du, E[1], E[2]), .022, '#2f7a4a')
    rod((E[0] + du, E[1], E[2]), (H[0] + du, H[1], H[2]), .022, '#2f7a4a')
rod((.42, .32, .7), (.42, .28, 1.0), .008, '#bbbbbb')                       # spring
for p in (B0, E, H):
    cyl(p[0], p[1], 0, .14, .055, '#2a2a2a', axis='X', seg=16) if False else sph(p[0], p[1], p[2], .06, '#2a2a2a')
cyl(.5, .85, 1.5, 1.92, .36, '#1f5f3a', r2=.13, seg=32, bev=.02)
PARTS[-1].rotation_euler = (-.75, 0, 0)
PARTS[-1].location = (.5, -.88, 1.7)
sph(.5, .95, 1.58, .12, '#fff3c4', glow=4)
finish('lampu')

# lava [.6, .6, 2.2]: lava lamp
cyl(.3, .3, 0, .55, .28, '#7a7a8a', r2=.14, seg=24)
cyl(.3, .3, .55, 1.8, .14, '#e0408a', r2=.22, seg=24, glow=1.2)
cyl(.3, .3, 1.8, 2.2, .22, '#7a7a8a', r2=.08, seg=24)
for z, r in ((.85, .1), (1.2, .08), (1.55, .11)):
    sph(.3, .3, z, r, '#ffb347', sc=(1, 1, 1.3), glow=1.5)
finish('lava')

# keyboard [4.5, 1.3, 2.6]: synth keyboard on an X stand
for u in (.6, 3.75):
    box(u, u + .12, .55, .7, 0, 2.2, '#333', .03, rot=(.45, 0, 0))
    PARTS[-1].location = (u + .06, -.65, 1.1)
    box(u, u + .12, .55, .7, 0, 2.2, '#333', .03, rot=(-.45, 0, 0))
    PARTS[-1].location = (u + .06, -.65, 1.1)
box(0, 4.5, 0, 1.3, 2.05, 2.4, '#2a2a2a', .08)
box(.15, 4.35, .55, 1.28, 2.38, 2.46, '#f4f0e2', .02)
for i in range(29):
    if i % 7 in (2, 6):
        continue
    box(.25 + i * .143, .35 + i * .143, .55, .9, 2.46, 2.53, '#111', .01)
box(.2, 1.4, .1, .45, 2.4, 2.45, '#5a8fb8', .01, glow=.6)
for u in (1.7, 1.9, 2.1, 2.3):
    cyl(u, .25, 2.4, 2.48, .05, '#888', seg=10)
finish('keyboard')

# majalah [1.6, 1.2, .3]: magazine stack
for i, col in enumerate(('#d23b2b', '#f4f0e2', '#2f5fa8')):
    box(0, 1.5, 0, 1.1, i * .1, i * .1 + .09, col, .01, rot=(0, 0, (i - 1) * .08))
box(.3, 1.0, .3, .6, .3, .31, '#e2c44c', 0, rot=(0, 0, .08))
finish('majalah')

# kardus [2.6, 1.8, .4]: game cases scattered on the floor
for (u, v, w, d, col, r) in ((0, 0, .9, .6, '#2f8f45', .2), (1.1, .2, .7, .6, '#e08a2e', -.3), (.3, 1.0, .8, .6, '#8a4fb3', .5), (1.8, 1.0, .7, .7, '#d23b2b', -.1)):
    box(u, u + w, v, v + d, 0, .14, '#1d1d1d', .02, rot=(0, 0, r))
    box(u + .05, u + w - .05, v + .05, v + d - .05, .14, .16, col, 0, rot=(0, 0, r))
cyl(2.2, .4, 0, .02, .28, '#d8dde3', seg=28, bev=0)
finish('kardus')

# speaker [.8, .8, 1.4]
box(0, .8, 0, .8, 0, 1.4, '#1d1d1d', .06)
for z, r in ((.45, .28), (1.05, .16)):
    cyl(.4, .8, -.02, .04, r, '#444', axis='Y', seg=24)
    PARTS[-1].location.z = z
    cyl(.4, .8, .0, .05, r * .45, '#222', axis='Y', seg=16)
    PARTS[-1].location.z = z
finish('speaker')

# ---------------- new 90s floor items ----------------
# vcr [1.6, 1.2, .4]: video player with a tape on top
box(0, 1.6, 0, 1.1, 0, .32, '#2a2a2e', .04)
box(.15, .95, 1.1, 1.12, .14, .24, '#111', .01)
box(1.05, 1.45, 1.1, 1.13, .15, .25, '#0f2a16', .01)
box(1.1, 1.4, 1.13, 1.14, .18, .22, '#3cff7a', 0, glow=1.5)
box(.2, 1.1, .2, .8, .32, .5, '#1d1d1d', .03, rot=(0, 0, .15))
box(.3, 1.0, .78, .8, .36, .46, '#f4f0e2', 0, rot=(0, 0, .15))
finish('vcr')

# stik [.6, .4, .15]: game controller
box(.12, .48, .05, .3, 0, .1, '#9a9aa8', .04)
sph(.12, .25, .06, .11, '#9a9aa8', sc=(1, 1.4, .6))
sph(.48, .25, .06, .11, '#9a9aa8', sc=(1, 1.4, .6))
for du, dv, col in ((.42, .12, '#2f8f45'), (.48, .17, '#d23b2b'), (.36, .17, '#2f5fa8'), (.42, .22, '#e2c44c')):
    cyl(du, dv, .09, .12, .025, col, seg=8, bev=0)
box(.14, .2, .14, .2, .09, .12, '#555', 0)
box(.1, .24, .17, .19, .09, .12, '#555', 0)
finish('stik')

# topi [.7, .8, .35]: baseball cap
sph(.35, .3, .02, .3, '#d23b2b', sc=(1, 1, .9))
box(.12, .58, .45, .8, .02, .05, '#d23b2b', .02)
sph(.35, .3, .29, .04, '#d23b2b')
box(.25, .45, .02, .2, .2, .23, '#f4f0e2', 0, rot=(.6, 0, 0))
finish('topi')

# sepatu [1.2, .5, .45]: pair of sneakers
for v in (0, .26):
    box(0, 1.1, v, v + .22, 0, .1, '#f4f0e2', .04)
    box(.05, .8, v + .01, v + .21, .1, .38, '#2f5fa8', .08)
    sph(.85, v + .11, .14, .17, '#2f5fa8', sc=(1.2, .65, .6))
    box(.15, .55, v + .02, v + .2, .38, .45, '#f4f0e2', .03)
    box(.3, .7, v + .21, v + .23, .15, .3, '#d23b2b', .01)
finish('sepatu')

# kaleng [.3, .3, .45]: soda can
cyl(.15, .15, 0, .45, .14, '#d23b2b', seg=24, bev=.03)
cyl(.15, .15, .44, .46, .12, '#c9c9c9', seg=24, bev=0)
box(.04, .26, .02, .28, .18, .26, '#f4f0e2', 0)
PARTS[-1].scale = (1, 1, 1)
finish('kaleng')

# pizza [1.5, 1.5, .15]: pizza box with a slice on top
box(0, 1.5, 0, 1.5, 0, .14, '#d9b98a', .02)
box(.3, 1.2, .3, 1.2, .14, .15, '#c8302a', 0)
box(.55, .95, .5, .9, .15, .16, '#f4f0e2', 0)
sph(.5, 1.1, .18, .32, '#f1c060', sc=(1, .55, .08), rot=(0, 0, .5))
finish('pizza')

# skate [.9, .3, 3]: skateboard leaning on the wall
box(.15, .75, .05, .17, 0, 3, '#2a2a2a', .05, rot=(-.18, 0, 0))
PARTS[-1].location = (.45, -.25, 1.48)
box(.2, .7, .17, .19, .6, 2.4, '#f4f0e2', 0, rot=(-.18, 0, 0))
PARTS[-1].location = (.45, -.36, 1.5)
for z in (.6, 2.3):
    for u in (.2, .7):
        cyl(u, .35 - z * .18 * .6, 0, .1, .08, '#e2c44c', axis='Y', seg=14)
        PARTS[-1].location.z = z
finish('skate')

# kerucut [.9, .9, 1.7]: traffic cone
box(0, .9, 0, .9, 0, .12, '#e05a1e', .04)
cyl(.45, .45, .12, 1.7, .36, '#e8681e', r2=.05, seg=28, bev=0)
for z, r in ((.55, .27), (1.0, .2)):
    cyl(.45, .45, z, z + .2, r + .015, '#f4f0e2', r2=r - .01, seg=28, bev=0)
finish('kerucut')

# globe [.8, .8, 1.2]: desk globe
cyl(.4, .4, 0, .1, .3, '#5a3a22', seg=24)
cyl(.4, .4, .1, .35, .04, '#c9a24a', seg=10)
tor(.4, .4, .75, .42, .025, '#c9a24a', rot=(0, .4, 0))
sph(.4, .4, .75, .37, '#3c7fc8', rot=(0, .4, 0))
for (a, b, s) in ((.4, .5, .16), (2.2, .2, .12), (3.6, -.3, .14), (5.0, .8, .09)):
    sph(.4 + math.cos(a) * math.cos(b) * .33, .4 + math.sin(a) * math.cos(b) * .33, .75 + math.sin(b) * .33, s, '#4aa055', sc=(1, 1, .45), rot=(0, math.pi / 2 - b, a))
finish('globe')

# boneka [.9, .8, 1.1]: teddy bear sitting, facing front
B = '#9a6a3e'
sph(.45, .4, .35, .32, B, sc=(1, .9, 1.05))
sph(.45, .45, .8, .24, B)
for u in (.27, .63):
    sph(u, .42, .98, .08, B)
    sph(u, .48, .98, .045, '#e8c9a0')
sph(.45, .64, .76, .09, '#e8c9a0', sc=(1, .8, .8))
sph(.45, .72, .79, .03, '#1d1d1d')
for u in (.37, .53):
    sph(u, .66, .86, .025, '#1d1d1d')
for u in (.16, .74):
    sph(u, .5, .42, .1, B, sc=(1, 1, 1.6), rot=(0, (.6 if u < .4 else -.6), 0))
for u in (.28, .62):
    sph(u, .65, .1, .11, B, sc=(1, 1.6, .9))
    sph(u, .82, .1, .06, '#e8c9a0', sc=(1, .4, 1))
box(.33, .57, .58, .62, .54, .62, '#d23b2b', .01)
finish('boneka')

# ---------------- wall items (X across, Z up from the bottom, -Y out of the wall) ----------------
# w_neon [3 x 2]: neon "ROCK" sign with a tube border
bpy.ops.object.text_add(location=(.25, -.12, .55))
t = bpy.context.object
t.data.body = 'ROCK'
t.data.size = .95
t.data.extrude = 0
t.data.bevel_depth = .035
t.data.fill_mode = 'NONE'
t.data.align_x = 'LEFT'
t.rotation_euler = (math.pi / 2, 0, 0)
bpy.ops.object.convert(target='MESH')
t = bpy.context.object
dims = t.dimensions
t.scale = (2.5 / max(dims.x, .01), 1, 1)
t.data.materials.append(mat('#ff4fa0', 3))
for p in t.data.polygons:
    p.use_smooth = True
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
PARTS.append(t)
bpy.ops.curve.primitive_bezier_circle_add(radius=1, location=(1.5, -.12, 1))
c = bpy.context.object
c.scale = (1.42, 1, .9)
c.rotation_euler = (math.pi / 2, 0, 0)
c.data.bevel_depth = .035
bpy.ops.object.convert(target='MESH')
c = bpy.context.object
c.data.materials.append(mat('#3c8cff', 3))
for p in c.data.polygons:
    p.use_smooth = True
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
PARTS.append(c)
box(.2, 2.8, 0, .06, .15, 1.85, '#1d1d1d', .02)
for u in (.6, 2.4):
    cyl(u, .03, 1.85, 1.95, .03, '#888', seg=8)
finish('w_neon')

# w_ring [2 x 3]: basketball hoop with a net
box(0, 2, 0, .1, 1.2, 3, '#f4f0e2', .04)
for (u0, u1, z0, z1) in ((.6, 1.4, 1.5, 1.56), (.6, 1.4, 2.1, 2.16), (.6, .66, 1.5, 2.16), (1.34, 1.4, 1.5, 2.16)):
    box(u0, u1, .1, .12, z0, z1, '#d23b2b', 0)
box(.85, 1.15, .1, .45, 1.42, 1.5, '#e07a2e', .01)
tor(1, .75, 1.48, .34, .025, '#e07a2e')
bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=.34, radius2=.22, depth=.55, location=(1, -.75, 1.2), rotation=(math.pi, 0, 0))
n = bpy.context.object
w = n.modifiers.new('net', 'WIREFRAME')
w.thickness = .02
n.data.materials.append(mat('#f4f0e2'))
with bpy.context.temp_override(object=n, active_object=n):
    bpy.ops.object.modifier_apply(modifier=w.name)
PARTS.append(n)
finish('w_ring')

# w_kerai [4 x 4]: window with half-open blinds
box(0, 4, 0, .2, 0, 4, '#e6e1d2', .03)
box(.2, 3.8, .15, .17, .2, 3.8, '#9fc4e8', 0, glow=.8)
for i in range(16):
    z = .35 + i * .215
    box(.2, 3.8, .22, .26, z, z + .16, '#cfcfd6', .01, rot=(.7, 0, 0))
    PARTS[-1].location = (2, -.24, z + .08)
box(.1, 3.9, 0, .32, 3.8, 4, '#cfcfd6', .03)
cyl(3.6, .3, .4, 3.8, .012, '#888', seg=6)
finish('w_kerai')


# w_jendela [4 x 3]: wooden window, four glass panes, curtains on a rod
box(0, 4, 0, .22, 0, 3, '#e6e1d2', .03)
box(.2, 3.8, .12, .16, .2, 2.8, '#a9d3f0', 0, glow=.8)
box(1.94, 2.06, .14, .3, .2, 2.8, '#e6e1d2', .02)
box(.2, 3.8, .14, .3, 1.44, 1.56, '#e6e1d2', .02)
box(-.15, 4.15, 0, .55, -.1, .05, '#d8d2c0', .03)
cyl(2, .55, -.3, 4.3, .04, '#5a3a22', axis='Y', seg=10)
PARTS[-1].rotation_euler = (0, math.pi / 2, 0)
PARTS[-1].location = (2, -.55, 3.15)
for side in (0, 1):
    for i in range(4):
        u = (-.25 + i * .22) if side == 0 else (4.25 - i * .22)
        cyl(u, .5, -.2, 3.1, .14, '#c8452f', seg=12)
        PARTS[-1].scale = (1, .55, 1)
        bpy.ops.object.select_all(action='DESELECT')
    box(-.35 if side == 0 else 3.5, .5 if side == 0 else 4.35, .35, .62, 1.1, 1.25, '#e2c44c', .03)
finish('w_jendela')

# w_rakvcd [6 x 2]: wooden wall cabinet packed with VCD jewel cases (spines out)
WOODV = '#7a4f2c'
box(0, 6, 0, .08, 0, 2, '#5e3b20', .01)                       # back panel
for u0 in (0, 5.88):
    box(u0, u0 + .12, 0, .72, 0, 2, WOODV, .02)               # sides
for z in (0, .96, 1.9):
    box(0, 6, 0, .74, z, z + .1, WOODV, .02)                  # bottom, middle, top shelves
box(-.05, 6.05, 0, .78, 1.96, 2.04, '#6a4426', .02)            # top lip
box(2.96, 3.04, .08, .72, .1, .96, WOODV, .01)                # centre divider, lower row
SPINES = ['#d23b2b', '#2f5fa8', '#e2c44c', '#2f8f45', '#f4f0e2', '#8a4fb3', '#e08a2e', '#1d1d1d', '#2f9e9a', '#c2185b', '#5d4037', '#90a4ae']
k = 0
for zb in (.1, 1.06):
    u = .16
    end = 5.84
    while u < end - .05:
        if zb == .1 and 2.9 < u < 3.1:
            u = 3.08
        if k % 23 == 11 and u + .7 < end:                       # a little stack lying flat
            for j in range(4):
                box(u + .02, u + .62, .12, .66, zb + j * .045, zb + j * .045 + .04, SPINES[(k + j) % 12], .005)
            u += .7
            k += 1
            continue
        if k % 29 == 17 and u + .34 < end:                      # gap with one case leaning
            box(u + .05, u + .09, .12, .66, zb, zb + .56, SPINES[k % 12], .004, rot=(0, -.35, 0))
            PARTS[-1].location = (u + .18, -.39, zb + .27)
            u += .34
            k += 1
            continue
        col = SPINES[(k * 7) % 12]
        box(u, u + .045, .12, .64, zb, zb + .56, '#d9dde2', .004)          # clear case
        box(u - .001, u + .046, .6, .645, zb + .02, zb + .54, col, 0)       # printed spine
        box(u - .002, u + .047, .63, .65, zb + .3, zb + .44, '#f4f0e2', 0)  # title strip
        box(u - .002, u + .047, .63, .65, zb + .07, zb + .1, '#1d1d1d' if col != '#1d1d1d' else '#e2c44c', 0)
        u += .047 + (.01 if k % 9 else .03)
        k += 1
# a disc out of its case, leaning on the front of the lower shelf
cyl(1.4, .78, 0, .02, .27, '#cfd8e3', axis='Y', seg=32, h=.38, bev=0)
PARTS[-1].rotation_euler = (math.pi / 2 - .25, 0, 0)
cyl(1.4, .8, 0, .02, .05, '#8a96a3', axis='Y', seg=16, h=.38, bev=0)
PARTS[-1].rotation_euler = (math.pi / 2 - .25, 0, 0)
finish('w_rakvcd')

# w_rakdinding [3 x 1]: wall cassette rack, six columns of tapes lying flat, spines out
CASW = .43
box(0, 3, 0, .06, 0, 1, '#5e3b20', .01)
for i in range(7):
    u = .03 + i * (CASW + .05)
    box(u, u + .05, 0, .5, 0, 1, '#8b5a2b', .015)              # dividers
box(0, 3, 0, .52, 0, .06, '#8b5a2b', .015)
box(0, 3, 0, .52, .94, 1, '#8b5a2b', .015)
JC = ['#d23b2b', '#2f5fa8', '#e2c44c', '#2f8f45', '#f4f0e2', '#8a4fb3', '#e08a2e', '#1d1d1d', '#2f9e9a', '#c2185b', '#ff8a65', '#6d8b3a']
k = 0
for col in range(6):
    u0 = .08 + col * (CASW + .05)
    rows = 11 - (col * 3 % 4)                                   # some columns not full
    for r in range(rows):
        z = .06 + r * .078
        out = .06 if (k % 17 == 5) else 0                       # one tape pulled out a bit
        box(u0 + .005, u0 + CASW - .005, .06, .46 + out, z, z + .072, '#cfd4da', .006)   # clear case
        c = JC[(k * 5) % 12]
        box(u0 + .01, u0 + CASW - .01, .44 + out, .465 + out, z + .006, z + .066, c, 0)  # J-card spine
        box(u0 + .06, u0 + CASW * .72, .46 + out, .468 + out, z + .022, z + .05, '#f8f4ea', 0)  # handwritten label
        box(u0 + CASW * .78, u0 + CASW - .04, .46 + out, .468 + out, z + .022, z + .05, '#1d1d1d' if c != '#1d1d1d' else '#f8f4ea', 0)
        k += 1
# a loose tape on top showing its reels
box(.5, 1.0, .1, .42, 1.0, 1.06, '#2a2a2a', .01)
box(.56, .94, .4, .43, 1.06, 1.065, '#f4f0e2', 0)
for uu in (.63, .87):
    cyl(uu, .26, 1.06, 1.07, .045, '#f4f0e2', seg=12, bev=0)
finish('w_rakdinding')

# w_jam [1 x 1]: round wall clock
cyl(.5, 0, 0, .14, .48, '#c8302a', axis='Y', seg=36, h=.5)
cyl(.5, .14, 0, .02, .41, '#f8f4ea', axis='Y', seg=36, h=.5, bev=0)
for i in range(12):
    a = i / 12 * math.tau
    L = .09 if i % 3 == 0 else .05
    box(.5 + math.sin(a) * .33 - .012, .5 + math.sin(a) * .33 + .012, .16, .18, .5 + math.cos(a) * .33 - L / 2, .5 + math.cos(a) * .33 + L / 2, '#1d1d1d', 0, rot=(0, a, 0))
    PARTS[-1].location = (.5 + math.sin(a) * .33, -.17, .5 + math.cos(a) * .33)
box(.485, .515, .17, .19, .5, .74, '#1d1d1d', 0, rot=(0, .9, 0))
PARTS[-1].location = (.5 + math.sin(.9) * .12, -.18, .5 + math.cos(.9) * .12)
box(.49, .51, .18, .2, .5, .84, '#1d1d1d', 0, rot=(0, 2.6, 0))
PARTS[-1].location = (.5 + math.sin(2.6) * .17, -.19, .5 + math.cos(2.6) * .17)
cyl(.5, .2, 0, .03, .035, '#c8302a', axis='Y', seg=12, h=.5, bev=0)
finish('w_jam')

bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_apply=True, export_yup=True,
                          export_materials='EXPORT', export_normals=True, export_texcoords=False,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7, export_draco_position_quantization=12, export_draco_normal_quantization=8)
print('EXPORTED', OUT, len(bpy.data.objects), 'objects')
