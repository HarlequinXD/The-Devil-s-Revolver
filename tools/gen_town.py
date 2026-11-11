"""Town: building textures (palette-indexed), low-poly meshes and world layout."""
import random
import math
from common import FONT5x7, hexrgb

# OBJ palette bank used by every building (15 colours + transparent)
TOWN_PAL = ['#000000', '#1a1210', '#3b2618', '#5e3d22', '#85593a', '#a87a4f', '#c9a06b',
            '#6f655a', '#a39684', '#ddd0b0', '#b98a5e', '#7e3424', '#b4523a', '#2a3138',
            '#6f8c9c', '#efe5c8']
# shading ramp: colour -> one step darker (used for faces turned from the sun)
DARKER = [0, 1, 1, 2, 3, 4, 5, 2, 7, 10, 4, 2, 11, 1, 13, 9]


def shade_luts():
    l0 = list(range(16))
    l1 = [DARKER[i] for i in range(16)]
    l2 = [DARKER[DARKER[i]] for i in range(16)]
    return [l0, l1, l2]


# ------------------------------------------------------------------ painters
class Tex:
    def __init__(self, w, h, fill=0):
        self.w, self.h = w, h
        self.p = [[fill] * w for _ in range(h)]

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.p[y][x] = c

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, c)

    def frame(self, x, y, w, h, c):
        for xx in range(x, x + w):
            self.set(xx, y, c)
            self.set(xx, y + h - 1, c)
        for yy in range(y, y + h):
            self.set(x, yy, c)
            self.set(x + w - 1, yy, c)

    def flat(self):
        return [c for row in self.p for c in row]


def planks_h(t, x0, y0, w, h, rnd, ramp=(3, 4, 5), gap=2, ph=4, nails=True):
    y = y0
    while y < y0 + h:
        col = rnd.choice(ramp)
        for yy in range(y, min(y + ph, y0 + h)):
            for xx in range(x0, x0 + w):
                c = col
                r = rnd.random()
                if r < 0.10:
                    c = ramp[max(0, ramp.index(col) - 1)]
                elif r < 0.14:
                    c = ramp[min(len(ramp) - 1, ramp.index(col) + 1)]
                t.set(xx, yy, c)
        for xx in range(x0, x0 + w):
            t.set(xx, min(y + ph - 1, y0 + h - 1), gap)
        if nails:
            for xx in range(x0 + 3, x0 + w, 16):
                t.set(xx, y + 1, 1)
        y += ph


def planks_v(t, x0, y0, w, h, rnd, ramp=(3, 4, 5), gap=2, pw=4):
    x = x0
    while x < x0 + w:
        col = rnd.choice(ramp)
        for xx in range(x, min(x + pw, x0 + w)):
            for yy in range(y0, y0 + h):
                c = col
                r = rnd.random()
                if r < 0.10:
                    c = ramp[max(0, ramp.index(col) - 1)]
                elif r < 0.14:
                    c = ramp[min(len(ramp) - 1, ramp.index(col) + 1)]
                t.set(xx, yy, c)
        for yy in range(y0, y0 + h):
            t.set(min(x + pw - 1, x0 + w - 1), yy, gap)
        x += pw


def window(t, x, y, w, h, frame=6, glass=13, hi=14, mull=5, shade=True):
    t.rect(x - 1, y - 1, w + 2, h + 2, 1)
    t.rect(x, y, w, h, frame)
    t.rect(x + 1, y + 1, w - 2, h - 2, glass)
    for i in range(min(w, h) - 3):
        t.set(x + 2 + i, y + h - 3 - i, hi)
    t.rect(x + w // 2, y + 1, 1, h - 2, mull)
    t.rect(x + 1, y + h // 2, w - 2, 1, mull)
    if shade:  # sill
        t.rect(x - 1, y + h, w + 2, 1, 6)


def door(t, x, y, w, h, rnd, ramp=(2, 3, 4)):
    t.rect(x - 1, y - 1, w + 2, h + 1, 1)
    planks_v(t, x, y, w, h, rnd, ramp=ramp, gap=1, pw=3)
    t.set(x + w - 3, y + h // 2, 6)
    t.set(x + w - 3, y + h // 2 + 1, 6)


def text(t, s, cx, y, col, scale=1):
    width = len(s) * 6 * scale - scale
    x = cx - width // 2
    for ch in s:
        g = FONT5x7.get(ch, FONT5x7[' '])
        for gy, row in enumerate(g):
            for gx, bit in enumerate(row):
                if bit == '1':
                    t.rect(x + gx * scale, y + gy * scale, scale, scale, col)
        x += 6 * scale


def sign(t, s, x, y, w, h, board=15, ink=11, edge=1):
    t.rect(x, y, w, h, edge)
    t.rect(x + 1, y + 1, w - 2, h - 2, board)
    text(t, s, x + w // 2, y + (h - 7) // 2, ink)


# ------------------------------------------------------------------ textures
TEXTURES = []      # list of (name, Tex)
TEX_ID = {}


def add_tex(name, t):
    TEX_ID[name] = len(TEXTURES)
    TEXTURES.append((name, t))


def build_textures():
    r = random.Random(7)
    t = Tex(32, 32); planks_h(t, 0, 0, 32, 32, r); add_tex('siding', t)
    t = Tex(32, 32); planks_h(t, 0, 0, 32, 32, r, ramp=(7, 8, 8), gap=7 if False else 2); add_tex('weathered', t)
    t = Tex(32, 32); planks_v(t, 0, 0, 32, 32, r); add_tex('boards', t)
    t = Tex(32, 32); planks_h(t, 0, 0, 32, 32, r)
    window(t, 10, 8, 12, 14); add_tex('side_window', t)
    t = Tex(32, 32); planks_h(t, 0, 0, 32, 32, r, ramp=(9, 9, 15), gap=8, nails=False); add_tex('whitewash', t)
    # adobe stucco
    t = Tex(32, 32)
    for y in range(32):
        for x in range(32):
            v = r.random()
            t.set(x, y, 10 if v < 0.72 else (9 if v < 0.9 else 4))
    for _ in range(4):
        x, y = r.randrange(32), r.randrange(32)
        for i in range(r.randrange(4, 9)):
            t.set(x, y, 4); x += r.choice((-1, 0, 1)); y += 1
    add_tex('adobe', t)
    # brick
    t = Tex(32, 32, 1)
    for row in range(8):
        off = 4 if row % 2 else 0
        for bx in range(-1, 5):
            c = r.choice((11, 12, 12, 11, 10))
            t.rect(bx * 8 + off + 1, row * 4 + 1, 7, 3, c)
    add_tex('brick', t)
    # shingles
    t = Tex(32, 32, 1)
    for row in range(8):
        off = (row % 2) * 3
        for bx in range(-1, 7):
            c = r.choice((2, 3, 3, 7))
            t.rect(bx * 6 + off, row * 4, 5, 3, c)
            t.set(bx * 6 + off, row * 4 + 2, 1)
    add_tex('shingle', t)
    # corrugated tin
    t = Tex(32, 32)
    for y in range(32):
        for x in range(32):
            c = (8, 8, 7, 7)[x % 4]
            if r.random() < 0.06:
                c = 10  # rust spots
            t.set(x, y, c)
    add_tex('tin', t)
    # water tank staves with iron hoops
    t = Tex(32, 32)
    planks_v(t, 0, 0, 32, 32, r, ramp=(3, 4, 4), gap=2, pw=4)
    for y in (4, 15, 27):
        t.rect(0, y, 32, 2, 1)
        t.rect(0, y, 32, 1, 7)
    add_tex('tank', t)

    # ---- facades (64x64, stretched over a whole front wall)
    def facade_base(ramp=(3, 4, 5)):
        f = Tex(64, 64)
        planks_h(f, 0, 0, 64, 64, r, ramp=ramp)
        return f

    f = facade_base()
    f.rect(0, 0, 64, 3, 2); f.rect(0, 20, 64, 2, 2)         # trim
    sign(f, 'SALOON', 6, 5, 52, 13, board=15, ink=12)
    window(f, 5, 31, 13, 15); window(f, 46, 31, 13, 15)
    f.rect(23, 29, 18, 35, 1); f.rect(24, 30, 16, 34, 13)  # dark doorway
    for dx in (24, 32):                                      # batwing doors
        planks_v(f, dx, 38, 8, 14, r, ramp=(5, 6, 6), gap=4, pw=2)
        f.rect(dx, 38, 8, 1, 2)
    add_tex('fac_saloon', f)

    f = facade_base((4, 5, 6))
    f.rect(0, 0, 64, 2, 2)
    sign(f, 'STORE', 8, 5, 48, 12, board=2, ink=15, edge=1)
    window(f, 3, 26, 21, 24, frame=5); window(f, 40, 26, 21, 24, frame=5)
    door(f, 27, 30, 10, 34, r)
    add_tex('fac_store', f)

    f = Tex(64, 64)
    bt = TEXTURES[TEX_ID['brick']][1]
    for y in range(64):
        for x in range(64):
            f.set(x, y, bt.p[y % 32][x % 32])
    f.rect(0, 0, 64, 4, 9); f.rect(0, 4, 64, 1, 1)
    sign(f, 'BANK', 14, 7, 36, 13, board=9, ink=11)
    for wx in (6, 46):
        window(f, wx, 30, 12, 18, frame=9)
        f.rect(wx, 27, 12, 3, 9)
    f.rect(23, 26, 18, 38, 9)
    door(f, 26, 30, 12, 34, r, ramp=(2, 2, 3))
    add_tex('fac_bank', f)

    f = facade_base((7, 8, 8))
    f.rect(0, 0, 64, 2, 1)
    sign(f, 'SHERIFF', 8, 5, 48, 12, board=2, ink=15)
    window(f, 6, 28, 14, 16)
    for bx in range(8, 20, 3):
        f.rect(bx, 28, 1, 16, 1)
    f.rect(40, 30, 1, 1, 1)
    door(f, 34, 28, 14, 36, r)
    # star badge
    for (x, y) in ((27, 30), (26, 31), (27, 31), (28, 31), (25, 32), (26, 32), (27, 32), (28, 32), (29, 32),
                   (26, 33), (27, 33), (28, 33), (26, 34), (28, 34)):
        f.set(x, y, 6)
    add_tex('fac_sheriff', f)

    f = facade_base((10, 10, 9))
    f.rect(0, 0, 64, 2, 2)
    sign(f, 'HOTEL', 10, 4, 44, 11, board=15, ink=2)
    for wx in (5, 26, 47):
        window(f, wx, 19, 11, 12)
    f.rect(0, 35, 64, 2, 4)
    window(f, 5, 41, 12, 13); window(f, 47, 41, 12, 13)
    door(f, 26, 40, 12, 24, r)
    add_tex('fac_hotel', f)

    f = facade_base()
    window(f, 8, 22, 14, 16)
    door(f, 38, 24, 12, 40, r)
    add_tex('fac_house', f)

    f = facade_base((7, 8, 8))
    window(f, 40, 24, 14, 14, frame=8)
    door(f, 10, 26, 12, 38, r, ramp=(7, 8, 8))
    add_tex('fac_shack', f)

    f = Tex(64, 64)
    planks_h(f, 0, 0, 64, 64, r, ramp=(9, 9, 15), gap=8, nails=False)
    f.rect(20, 26, 24, 38, 1)
    door(f, 21, 27, 11, 37, r, ramp=(2, 3, 3)); door(f, 32, 27, 11, 37, r, ramp=(2, 3, 3))
    for a in range(0, 360, 6):   # round window
        x = 32 + int(7 * math.cos(math.radians(a))); y = 12 + int(7 * math.sin(math.radians(a)))
        f.set(x, y, 1)
    f.rect(27, 8, 11, 9, 13); f.rect(32, 6, 1, 13, 6); f.rect(26, 12, 13, 1, 6)
    add_tex('fac_church', f)

    f = facade_base((11, 12, 12))
    f.rect(0, 0, 64, 3, 9)
    sign(f, 'DEPOT', 12, 5, 40, 12, board=9, ink=11)
    window(f, 5, 26, 12, 16, frame=9); window(f, 47, 26, 12, 16, frame=9)
    door(f, 25, 26, 14, 38, r)
    add_tex('fac_depot', f)

    f = facade_base((4, 5, 5))
    sign(f, 'BARBER', 7, 5, 50, 12, board=15, ink=12)
    window(f, 6, 26, 18, 20)
    door(f, 36, 26, 12, 38, r)
    for y in range(26, 50):  # striped pole
        f.set(56, y, 12 if (y // 3) % 2 else 15); f.set(57, y, 12 if (y // 3) % 2 else 15)
    add_tex('fac_barber', f)


# ------------------------------------------------------------------ meshes
Q = 16  # texel coordinates are stored in 1/16 texel


class Mesh:
    def __init__(self, name):
        self.name = name
        self.walls = []
        self.polys = []
        self.radius = 0

    def wall(self, x0, z0, x1, z1, y0, y1, tex, stretch=False, flags=0, dens=1.0):
        tw, th = TEXTURES[TEX_ID[tex]][1].w, TEXTURES[TEX_ID[tex]][1].h
        L = math.hypot(x1 - x0, z1 - z0)
        if stretch:
            u0, u1, v0, v1 = 0, tw * Q, 0, th * Q
        else:
            u0, u1 = 0, int(L * dens * Q)
            v0, v1 = 0, int((y1 - y0) * dens * Q)
        self.walls.append((x0, z0, x1, z1, y0, y1, u0, u1, v0, v1, TEX_ID[tex], flags))

    def poly(self, verts, uvs, tex, flags=0):
        self.polys.append((verts, [(int(u * Q), int(v * Q)) for u, v in uvs], TEX_ID[tex], flags))

    def box(self, w, d, hw, front_tex, side='siding', back=None, front_h=None, stretch_front=True):
        x0, x1, z0, z1 = -w / 2, w / 2, -d / 2, d / 2
        fh = front_h or hw
        self.wall(x0, z1, x1, z1, 0, fh, front_tex, stretch=stretch_front)
        self.wall(x1, z1, x1, z0, 0, hw, side)
        self.wall(x1, z0, x0, z0, 0, hw, back or side)
        self.wall(x0, z0, x0, z1, 0, hw, side)
        if fh > hw:  # back of the false front, seen from behind
            self.wall(x1, z1 - 1, x0, z1 - 1, hw, fh, 'boards')

    def porch(self, w, d, h_wall=22, h_front=17, depth=13):
        zf = d / 2 + depth
        self.poly([(-w / 2, h_front, zf), (-w / 2, h_wall, d / 2), (w / 2, h_wall, d / 2), (w / 2, h_front, zf)],
                  [(0, depth * 1.2), (0, 0), (w, 0), (w, depth * 1.2)], 'tin', flags=1)
        for px in (-w / 2 + 2, 0, w / 2 - 2):
            self.wall(px - 1, zf - 1, px + 1, zf - 1, 0, h_front, 'boards', flags=1, dens=1)

    def gable_z(self, w, d, hw, hr, roof='shingle', gable='siding', o=3):
        """ridge runs front-to-back; slopes face +x / -x"""
        L = math.hypot(w / 2 + o, hr - hw)
        ef, eb = d / 2 + o, -d / 2 - o
        self.poly([(w / 2 + o, hw - 1, ef), (0, hr, ef), (0, hr, eb), (w / 2 + o, hw - 1, eb)],
                  [(0, L), (0, 0), (d + 2 * o, 0), (d + 2 * o, L)], roof)
        self.poly([(-w / 2 - o, hw - 1, eb), (0, hr, eb), (0, hr, ef), (-w / 2 - o, hw - 1, ef)],
                  [(0, L), (0, 0), (d + 2 * o, 0), (d + 2 * o, L)], roof)
        self.poly([(-w / 2, hw, d / 2), (0, hr, d / 2), (w / 2, hw, d / 2)],
                  [(0, hr - hw), (w / 2, 0), (w, hr - hw)], gable)
        self.poly([(w / 2, hw, -d / 2), (0, hr, -d / 2), (-w / 2, hw, -d / 2)],
                  [(0, hr - hw), (w / 2, 0), (w, hr - hw)], gable)

    def gable_x(self, w, d, hw, hr, roof='shingle', gable='siding', o=3):
        """ridge runs left-right; slopes face front (+z) and back (-z)"""
        L = math.hypot(d / 2 + o, hr - hw)
        xl, xr = -w / 2 - o, w / 2 + o
        self.poly([(xl, hw - 1, d / 2 + o), (xl, hr, 0), (xr, hr, 0), (xr, hw - 1, d / 2 + o)],
                  [(0, L), (0, 0), (w + 2 * o, 0), (w + 2 * o, L)], roof)
        self.poly([(xr, hw - 1, -d / 2 - o), (xr, hr, 0), (xl, hr, 0), (xl, hw - 1, -d / 2 - o)],
                  [(0, L), (0, 0), (w + 2 * o, 0), (w + 2 * o, L)], roof)
        self.poly([(w / 2, hw, d / 2), (w / 2, hr, 0), (w / 2, hw, -d / 2)],
                  [(0, hr - hw), (d / 2, 0), (d, hr - hw)], gable)
        self.poly([(-w / 2, hw, -d / 2), (-w / 2, hr, 0), (-w / 2, hw, d / 2)],
                  [(0, hr - hw), (d / 2, 0), (d, hr - hw)], gable)

    def finish(self):
        pts = [(w[0], w[2]) for w in self.walls] + [(w[1], w[3]) for w in self.walls]
        for p in self.polys:
            pts += [(v[0], v[2]) for v in p[0]]
        self.radius = int(max(math.hypot(x, z) for x, z in pts)) + 2
        hy = [w[5] for w in self.walls] + [v[1] for p in self.polys for v in p[0]]
        self.height = int(max(hy))
        return self


MESHES = []
MESH_ID = {}


def add_mesh(m):
    MESH_ID[m.name] = len(MESHES)
    MESHES.append(m.finish())


def build_meshes():
    m = Mesh('saloon'); m.box(56, 60, 30, 'fac_saloon', side='side_window', front_h=44); m.porch(56, 60); add_mesh(m)
    m = Mesh('store'); m.box(48, 56, 26, 'fac_store', side='siding', front_h=38); m.porch(48, 56, 20, 16); add_mesh(m)
    m = Mesh('bank'); m.box(44, 52, 32, 'fac_bank', side='brick', front_h=36); add_mesh(m)
    m = Mesh('sheriff'); m.box(40, 48, 26, 'fac_sheriff', side='weathered', front_h=34); add_mesh(m)
    m = Mesh('hotel'); m.box(56, 56, 40, 'fac_hotel', side='side_window', front_h=48); m.porch(56, 56, 22, 17); add_mesh(m)
    m = Mesh('barber'); m.box(40, 44, 26, 'fac_barber', side='siding', front_h=34); add_mesh(m)
    m = Mesh('house'); m.box(40, 40, 24, 'fac_house', side='side_window'); m.gable_x(40, 40, 24, 38); add_mesh(m)
    m = Mesh('shack'); m.box(34, 34, 22, 'fac_shack', side='weathered'); m.gable_x(34, 34, 22, 33, roof='tin', gable='weathered'); add_mesh(m)
    m = Mesh('church'); m.box(40, 64, 28, 'fac_church', side='whitewash')
    m.gable_z(40, 64, 28, 46, gable='whitewash')
    # steeple: a box on the front with a pyramid cap
    s = 7; zc = 32 - s
    m.wall(-s, zc + s, s, zc + s, 46, 64, 'whitewash'); m.wall(s, zc + s, s, zc - s, 46, 64, 'whitewash')
    m.wall(s, zc - s, -s, zc - s, 46, 64, 'whitewash'); m.wall(-s, zc - s, -s, zc + s, 46, 64, 'whitewash')
    ap = (0, 82, zc)
    corners = [(-s - 1, zc + s + 1), (s + 1, zc + s + 1), (s + 1, zc - s - 1), (-s - 1, zc - s - 1)]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        m.poly([(a[0], 64, a[1]), ap, (b[0], 64, b[1])], [(0, 20), (8, 0), (16, 20)], 'shingle')
    add_mesh(m)
    m = Mesh('depot'); m.box(72, 36, 26, 'fac_depot', side='siding'); m.gable_x(72, 36, 26, 38, roof='shingle')
    m.porch(72, 36, 22, 17, 12); add_mesh(m)
    # water tower
    m = Mesh('watertower')
    for (lx, lz) in ((-11, -11), (11, -11), (11, 11), (-11, 11)):
        m.wall(lx - 1.5, lz, lx + 1.5, lz, 0, 36, 'boards', flags=1)
        m.wall(lx, lz - 1.5, lx, lz + 1.5, 0, 36, 'boards', flags=1)
    R = 15; n = 8
    pts = [(R * math.sin(2 * math.pi * (i - 0.5) / n), R * math.cos(2 * math.pi * (i - 0.5) / n)) for i in range(n)]
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        m.wall(a[0], a[1], b[0], b[1], 36, 58, 'tank', dens=1.4)
    ap = (0, 72, 0)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        m.poly([(a[0] * 1.15, 58, a[1] * 1.15), ap, (b[0] * 1.15, 58, b[1] * 1.15)], [(0, 18), (6, 0), (12, 18)], 'shingle')
    add_mesh(m)


# ------------------------------------------------------------------ layout
STREET_X0, STREET_X1 = 480, 544      # main street
STREET_Y0, STREET_Y1 = 190, 1024
CROSS_Y0, CROSS_Y1 = 488, 536        # cross street
CROSS_X0, CROSS_X1 = 250, 800
RAIL_Y = 848                         # rail line centre
WEST_FRONT, EAST_FRONT = 464, 560    # building fronts (boardwalks between)

BUILDINGS = []   # (mesh, x, y, rot)


def local_to_world(b, lx, lz):
    mesh, bx, by, rot = b
    if rot == 0:
        return bx + lx, by + lz
    if rot == 1:
        return bx - lz, by + lx
    if rot == 2:
        return bx - lx, by - lz
    return bx + lz, by - lx


def footprint(b):
    m = MESHES[MESH_ID[b[0]]]
    xs, ys = [], []
    for w in m.walls:
        for (lx, lz) in ((w[0], w[1]), (w[2], w[3])):
            wx, wy = local_to_world(b, lx, lz)
            xs.append(wx); ys.append(wy)
    return int(min(xs)), int(min(ys)), int(max(xs)) + 1, int(max(ys)) + 1


def build_layout():
    def west(mesh, y):
        d = mesh_depth(mesh)
        BUILDINGS.append((mesh, WEST_FRONT - d / 2, y, 3))

    def east(mesh, y):
        d = mesh_depth(mesh)
        BUILDINGS.append((mesh, EAST_FRONT + d / 2, y, 1))

    west('saloon', 452); west('store', 388); west('house', 326)
    west('hotel', 572); west('barber', 636); west('shack', 694)
    east('bank', 452); east('sheriff', 388); east('house', 326)
    east('store', 572); east('house', 636); east('shack', 694)
    BUILDINGS.append(('church', 512, 140, 0))
    BUILDINGS.append(('depot', 620, 808, 0))
    BUILDINGS.append(('watertower', 700, 790, 0))
    BUILDINGS.append(('shack', 372, 600, 0))
    BUILDINGS.append(('house', 668, 300, 1))


def mesh_depth(name):
    m = MESHES[MESH_ID[name]]
    zs = [w[1] for w in m.walls if not w[11]] + [w[3] for w in m.walls if not w[11]]
    return max(zs) - min(zs)


def town_palette():
    return [hexrgb(c) for c in TOWN_PAL]
