"""Miami Beach, 1986: art-deco building textures (palette-indexed), low-poly meshes and the city layout."""
import random
import math
from common import FONT5x7, hexrgb

# OBJ palette bank used by every building (15 colours + transparent)
TOWN_PAL = ['#000000', '#1a1426', '#3c3f66', '#5f86b4', '#a9dcef', '#f6f2e8', '#d6cdc2', '#f7b5c9',
            '#d688a3', '#a7e8cf', '#73bba1', '#fde59a', '#d2ae62', '#ff3fa8', '#40f0ff', '#b9a6e6']
#           0 clear    1 ink      2 navy     3 glass    4 glass hi 5 white    6 white sh 7 pink
#           8 pink sh  9 mint     10 mint sh 11 yellow  12 yell sh 13 neon pk 14 neon cy 15 lavender
# shading ramp: colour -> one step darker (used for faces turned from the sun)
DARKER = [0, 1, 1, 2, 3, 6, 15, 8, 2, 10, 2, 12, 8, 8, 3, 2]


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

# stucco colours: (base, shade)
COLOURS = {'white': (5, 6), 'pink': (7, 8), 'mint': (9, 10), 'yellow': (11, 12), 'lav': (15, 6)}


def add_tex(name, t):
    TEX_ID[name] = len(TEXTURES)
    TEXTURES.append((name, t))


def stucco(t, base, shade, rnd, x0=0, y0=0, w=None, h=None):
    w = w or t.w; h = h or t.h
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            t.set(x, y, shade if rnd.random() < 0.07 else base)


def deco_window(t, x, y, w, h, base, shade):
    """window with a white frame, glass with a glint, and a shading 'eyebrow' ledge"""
    t.rect(x - 2, y - 3, w + 4, 1, 5)          # eyebrow ledge
    t.rect(x - 2, y - 2, w + 4, 1, shade)      # its shadow
    t.rect(x - 1, y - 1, w + 2, h + 2, 5)
    t.rect(x, y, w, h, 3)
    t.rect(x, y, w, 1, 2)
    for i in range(min(w, h) - 1):
        t.set(x + 1 + i, y + h - 2 - i, 4)
    t.rect(x + w // 2, y, 1, h, 5)


def build_textures():
    r = random.Random(1986)
    for cname, (b, s) in COLOURS.items():
        t = Tex(32, 32); stucco(t, b, s, r); add_tex('st_' + cname, t)
        t = Tex(32, 32); stucco(t, b, s, r)
        deco_window(t, 9, 9, 14, 13, b, s)
        t.rect(0, 30, 32, 1, s)                 # floor line
        add_tex('sw_' + cname, t)
    # vertical fins with a neon tube up the middle (8 texels wide, repeats)
    for nm, neon in (('fin_pink', 13), ('fin_cyan', 14)):
        t = Tex(32, 32); stucco(t, 5, 6, r)
        for x in range(0, 32, 8):
            t.rect(x + 3, 0, 2, 32, neon); t.rect(x + 2, 0, 1, 32, 6); t.rect(x + 5, 0, 1, 32, 6)
        add_tex(nm, t)
    # condo tower: glass bands and white balconies
    t = Tex(32, 32)
    for y in range(32):
        for x in range(32):
            t.set(x, y, 3 if (x + y) % 11 else 4)
    for y in (0, 16):
        t.rect(0, y, 32, 3, 5); t.rect(0, y + 3, 32, 1, 6)
        for x in range(0, 32, 4):
            t.set(x, y + 1, 6)
    t.rect(15, 0, 2, 32, 6)
    add_tex('condo', t)
    # lifeguard hut stripes
    t = Tex(32, 32)
    bands = (7, 11, 9, 14, 15, 13, 5, 7)
    for x in range(32):
        for y in range(32):
            t.set(x, y, bands[(x // 4) % 8])
    t.rect(0, 0, 32, 2, 5); t.rect(0, 30, 32, 2, 6)
    t.rect(10, 9, 12, 9, 1); t.rect(11, 10, 10, 7, 3)
    add_tex('hut', t)
    t = Tex(32, 32); stucco(t, 5, 6, r); add_tex('post', t)

    # ---- facades (64x64, stretched over a whole front wall)
    def facade(name, colour, neon, sign_text, floors=3, style='windows'):
        b, s = COLOURS[colour]
        f = Tex(64, 64)
        stucco(f, b, s, r)
        # stepped "ziggurat" parapet: cut the skyline out of the top rows
        for y in range(10):
            half = 12 + (y // 3) * 7 if y < 9 else 40
            for x in range(64):
                if abs(x - 31.5) > half:
                    f.set(x, y, 0)
        for y in range(10):                    # trim along the steps
            half = 12 + (y // 3) * 7
            if y % 3 == 0 and y < 9:
                for x in range(64):
                    if abs(x - 31.5) <= half and f.p[y][x]:
                        f.set(x, y, 5)
        f.rect(0, 10, 64, 1, neon)              # neon cornice
        f.rect(6, 12, 52, 10, 1)                # sign board
        text(f, sign_text, 32, 13, neon)
        top, bot = 25, 50
        fh = (bot - top) // floors
        for k in range(floors):
            wy = top + k * fh + 3
            if style == 'windows':
                for wx in (5, 25, 45):
                    deco_window(f, wx, wy, 14, fh - 5, b, s)
            elif style == 'porthole':
                for wx in (10, 54):
                    deco_window(f, wx - 6, wy, 12, fh - 5, b, s)
                for a in range(0, 360, 8):
                    f.set(32 + int(4.5 * math.cos(math.radians(a))), wy + (fh - 5) // 2 + int(4.5 * math.sin(math.radians(a))), 5)
                f.rect(29, wy + (fh - 5) // 2 - 2, 7, 5, 3)
            else:  # glass-block centre strip
                for wx in (5, 45):
                    deco_window(f, wx, wy, 14, fh - 5, b, s)
                for yy in range(wy - 2, wy + fh - 2):
                    for xx in range(24, 40):
                        f.set(xx, yy, 4 if (xx // 3 + yy // 3) % 2 else 3)
            f.rect(0, top + (k + 1) * fh - 1, 64, 1, s)
        # ground floor: striped awning over a glass shopfront
        for x in range(64):
            f.set(x, 50, 1)
            for y in range(51, 54):
                f.set(x, y, neon if (x // 4) % 2 else 5)
        f.rect(0, 54, 64, 1, 1)
        f.rect(2, 55, 60, 9, 3)
        for x in range(4, 62, 9):
            f.rect(x, 55, 1, 9, 5)
        f.rect(27, 55, 10, 9, 1); f.rect(28, 56, 8, 8, 2)
        for i in range(5):
            f.set(5 + i, 62 - i, 4); f.set(44 + i, 62 - i, 4)
        add_tex(name, f)

    facade('fac_palms', 'pink', 14, 'PALMS')
    facade('fac_coral', 'mint', 13, 'CORAL', style='porthole')
    facade('fac_breeze', 'yellow', 13, 'SEABREEZE', style='glass')
    facade('fac_tropic', 'lav', 14, 'TROPICS')
    facade('fac_neptune', 'white', 14, 'NEPTUNE', style='glass')
    facade('fac_surf', 'pink', 14, 'SURF', floors=2, style='porthole')
    facade('fac_cafe', 'mint', 13, 'CAFE', floors=2)
    facade('fac_dunes', 'white', 13, 'DUNES', style='windows')
    facade('fac_regal', 'yellow', 14, 'REGAL', floors=2, style='glass')
    facade('fac_aqua', 'lav', 13, 'AQUA', floors=2, style='porthole')


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

    def box(self, w, d, hw, front_tex, side='siding', back=None, front_h=None, stretch_front=True, parapet=None):
        x0, x1, z0, z1 = -w / 2, w / 2, -d / 2, d / 2
        fh = front_h or hw
        self.wall(x0, z1, x1, z1, 0, fh, front_tex, stretch=stretch_front, flags=2 if fh > hw else 0)
        self.wall(x1, z1, x1, z0, 0, hw, side)
        self.wall(x1, z0, x0, z0, 0, hw, back or side)
        self.wall(x0, z0, x0, z1, 0, hw, side)
        if fh > hw:  # back of the false front, seen from behind
            self.wall(x1, z1 - 1, x0, z1 - 1, hw, fh, parapet or side)

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


def deco(name, w, d, h, fac, colour, fin=None, parapet=8):
    m = Mesh(name)
    m.box(w, d, h, fac, side='sw_' + colour, front_h=h + parapet, parapet='st_' + colour)
    if fin:
        zf, zb = d / 2 + 3, d / 2
        top = h + parapet + 10
        m.wall(-4, zf, 4, zf, int(h * 0.3), top, fin)
        m.wall(4, zf, 4, zb, int(h * 0.3), top, fin)
        m.wall(-4, zb, -4, zf, int(h * 0.3), top, fin)
        m.wall(4, zb, -4, zb, h + parapet, top, fin)
    add_mesh(m)


def build_meshes():
    # name, width, depth, height, facade, side colour, fin
    deco('palms', 56, 44, 44, 'fac_palms', 'pink', 'fin_cyan')
    deco('coral', 48, 40, 44, 'fac_coral', 'mint')
    deco('breeze', 60, 44, 50, 'fac_breeze', 'yellow', 'fin_pink')
    deco('tropic', 52, 40, 44, 'fac_tropic', 'lav', 'fin_cyan')
    deco('neptune', 56, 44, 50, 'fac_neptune', 'white', 'fin_pink')
    deco('surf', 44, 36, 32, 'fac_surf', 'pink')
    deco('cafe', 40, 36, 30, 'fac_cafe', 'mint')
    deco('dunes', 52, 40, 44, 'fac_dunes', 'white', 'fin_cyan')
    deco('regal', 44, 36, 32, 'fac_regal', 'yellow')
    deco('aqua', 44, 36, 32, 'fac_aqua', 'lav', 'fin_pink')
    m = Mesh('condo'); m.box(44, 44, 96, 'condo', side='condo', stretch_front=False); add_mesh(m)
    # lifeguard hut on stilts
    m = Mesh('lifeguard')
    for (lx, lz) in ((-6, -5), (6, -5), (6, 5), (-6, 5)):
        m.wall(lx - 1, lz, lx + 1, lz, 0, 12, 'post', flags=1)
        m.wall(lx, lz - 1, lx, lz + 1, 0, 12, 'post', flags=1)
    w, d = 16, 12
    x0, x1, z0, z1 = -w / 2, w / 2, -d / 2, d / 2
    m.wall(x0, z1, x1, z1, 12, 24, 'hut', stretch=True)
    m.wall(x1, z1, x1, z0, 12, 24, 'hut')
    m.wall(x1, z0, x0, z0, 12, 24, 'hut')
    m.wall(x0, z0, x0, z1, 12, 24, 'hut')
    m.gable_x(w, d, 24, 30, roof='st_pink', gable='st_pink', o=2)
    add_mesh(m)


# ------------------------------------------------------------------ layout (all in 8-unit ground tiles)
# columns, west to east: bay | seawall | West Ave | block A | Washington | block B | Collins
#                        | block C (hotels) | Ocean Drive | palm park | beach | surf | ocean
ROAD_W = 5
AVENUES = [9, 28, 47, 69]            # first tile column of each N-S avenue
STREETS = [8, 38, 68, 98]            # first tile row of each E-W street
LAND_X0, LAND_X1 = 6, 98             # land columns (inclusive)
LAND_Y0, LAND_Y1 = 5, 105            # land rows (inclusive)
CITY_X1 = 75                         # last city column (Ocean Drive's east sidewalk)
PARK_X0, PARK_X1 = 76, 83
BEACH_X0, WET_X0 = 84, 97
BOARDWALK_ROWS = (24, 54, 84)   # wooden paths across the park and sand
BLOCKS_X = [(16, 25), (35, 44), (54, 66)]
BLOCKS_Y = [(15, 35), (45, 65), (75, 95)]

BUILDINGS = []   # (mesh, x, y, rot)  rot 1 faces west (-x), rot 3 faces east (+x)


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


def mesh_width(name):
    m = MESHES[MESH_ID[name]]
    xs = [w[0] for w in m.walls if not (w[11] & 1)] + [w[2] for w in m.walls if not (w[11] & 1)]
    return max(xs) - min(xs)


def mesh_depth(name):
    m = MESHES[MESH_ID[name]]
    zs = [w[1] for w in m.walls if not (w[11] & 1) and abs(w[1]) <= 30] + [w[3] for w in m.walls if not (w[11] & 1) and abs(w[3]) <= 30]
    return max(zs) - min(zs)


def build_layout():
    rnd = random.Random(86)
    hotels = ['palms', 'coral', 'breeze', 'tropic', 'neptune', 'dunes']
    small = ['surf', 'cafe', 'regal', 'aqua', 'coral', 'tropic']

    def row(x_front, facing_east, y0, y1, kinds):
        """fill a block edge with buildings whose fronts sit on x_front"""
        y = y0 + rnd.randint(2, 8)
        while True:
            name = rnd.choice(kinds)
            w = mesh_width(name)
            if y + w > y1 - 2:
                break
            d = mesh_depth(name)
            cx = x_front - d / 2 if facing_east else x_front + d / 2
            BUILDINGS.append((name, cx, y + w / 2, 3 if facing_east else 1))
            y += w + rnd.randint(4, 14)

    for bi, (bx0, bx1) in enumerate(BLOCKS_X):
        for (by0, by1) in BLOCKS_Y:
            X0, X1 = bx0 * 8, (bx1 + 1) * 8
            Y0, Y1 = by0 * 8, (by1 + 1) * 8
            if bi == 1 and by0 == 45:
                BUILDINGS.append(('condo', X0 + 40, Y0 + 60, 1))
                row(X1, True, Y0 + 110, Y1, small)
                continue
            if bi == 0 and by0 == 75:
                BUILDINGS.append(('condo', X0 + 40, Y0 + 110, 3))
                row(X0, False, Y0, Y0 + 80, small)
                continue
            row(X0, False, Y0, Y1, small if bi < 2 else hotels)
            row(X1, True, Y0, Y1, hotels if bi == 2 else small)
    # lifeguard huts on the sand, facing the sea
    for y in (150, 360, 570, 770):
        BUILDINGS.append(('lifeguard', 742, y, 3))


def town_palette():
    return [hexrgb(c) for c in TOWN_PAL]
