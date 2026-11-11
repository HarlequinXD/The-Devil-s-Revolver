"""Mode 7 ground (8bpp affine tiles + 128x128 map), sky layer and HUD font."""
import math
import random
import zlib
import numpy as np
from PIL import Image
from common import (CFile, rgb15, snap15, pack4bpp_tile, FONT5x7, GROUND_COLORS, SKY_BANKS, HUD_BANK, HORIZON)
import gen_town as town

T = 128  # map is 128x128 tiles


def C(*c):
    return np.array(c, dtype=np.float32)


ASPHALT = C(78, 78, 90)
WALK = C(206, 192, 188)
GRASS = C(84, 150, 74)
SAND = C(238, 216, 170)
WET = C(198, 172, 132)
SHALLOW = C(62, 196, 202)
DEEP = C(26, 98, 164)
LOT = C(216, 180, 174)


def noise_tile(rng, base, amp=9):
    t = np.zeros((8, 8, 3), np.float32) + base
    t += (rng.standard_normal((8, 8, 1)) * amp)
    t += rng.standard_normal((8, 8, 3)) * 2
    return t


def specks(rng, t, n, col, amp=0):
    for _ in range(n):
        x, y = rng.integers(0, 8, 2)
        t[y, x] = col + rng.standard_normal(3) * amp


def p_asphalt(rng):
    t = noise_tile(rng, ASPHALT, 5)
    specks(rng, t, rng.integers(2, 5), ASPHALT * 0.8)
    specks(rng, t, rng.integers(1, 4), ASPHALT * 1.25)
    return t


def p_yellow(rng, vertical):
    t = p_asphalt(rng)
    for i in range(8):
        for k in (2, 5):
            c = C(236, 196, 70) + rng.standard_normal(3) * 6
            if vertical:
                t[i, k] = c
            else:
                t[k, i] = c
    return t


def p_crosswalk(rng, vertical):
    t = p_asphalt(rng)
    for y in range(8):
        for x in range(8):
            if ((x if vertical else y) % 4) < 2:
                t[y, x] = C(232, 232, 236) + rng.standard_normal(3) * 5
    return t


def p_walk(rng):
    t = noise_tile(rng, WALK, 4)
    specks(rng, t, rng.integers(1, 4), WALK * 0.9)
    t[7, :] = WALK * 0.82          # slab joints
    t[:, 7] = WALK * 0.82
    return t


def p_curb(rng, mask):
    t = p_walk(rng)
    for i in range(8):
        if mask & 1: t[0, i] = C(112, 106, 104); t[1, i] = C(236, 232, 226)
        if mask & 2: t[i, 7] = C(112, 106, 104); t[i, 6] = C(236, 232, 226)
        if mask & 4: t[7, i] = C(112, 106, 104); t[6, i] = C(236, 232, 226)
        if mask & 8: t[i, 0] = C(112, 106, 104); t[i, 1] = C(236, 232, 226)
    return t


def p_lot(rng):
    t = noise_tile(rng, LOT, 4)
    for _ in range(6):
        x, y = rng.integers(0, 8, 2)
        t[y, x] = rng.choice([C(250, 236, 226), C(170, 140, 140), C(140, 190, 180)])
    return t


def p_grass(rng):
    t = noise_tile(rng, GRASS, 10)
    specks(rng, t, rng.integers(2, 5), GRASS * 0.75)
    specks(rng, t, rng.integers(1, 3), C(130, 190, 96))
    return t


def p_path(rng):
    t = noise_tile(rng, C(226, 210, 178), 5)
    specks(rng, t, 3, C(200, 182, 150))
    return t


def p_sand(rng, base=SAND):
    t = noise_tile(rng, base, 6)
    specks(rng, t, rng.integers(2, 5), base * 0.9)
    specks(rng, t, rng.integers(0, 3), np.minimum(base * 1.06, 255))
    return t


def p_wet(rng):
    t = p_sand(rng, WET)
    for x in range(8):
        if rng.random() < 0.3:
            t[rng.integers(0, 8), x] = C(220, 214, 200)
    return t


def p_surf(rng):
    t = noise_tile(rng, C(120, 214, 214), 6)
    for y in range(8):
        edge = 3 + int(2 * math.sin(y * 1.3 + rng.random() * 2))
        for x in range(8):
            if x <= edge:
                t[y, x] = C(244, 248, 246) - rng.random() * 18
            elif x == edge + 1:
                t[y, x] = C(180, 232, 230)
    return t


def p_water(rng, base, amp=5):
    t = noise_tile(rng, base, amp)
    for _ in range(rng.integers(1, 3)):          # little wave glints
        x, y = rng.integers(0, 6), rng.integers(0, 8)
        t[y, x:x + 3] = np.minimum(base * 1.35 + 30, 255)
    return t


def p_seawall(rng):
    t = noise_tile(rng, C(176, 172, 168), 5)
    t[:, 0] = C(222, 220, 214)
    t[:, 7] = C(110, 106, 104)
    return t


def p_boards(rng, vertical):
    t = np.zeros((8, 8, 3), np.float32)
    cols = [C(176, 136, 94), C(192, 152, 106), C(160, 122, 84)]
    for k in range(2):
        c = cols[rng.integers(0, 3)]
        for i in range(8):
            for j in range(4):
                v = c + rng.standard_normal(3) * 4
                if vertical:
                    t[i, k * 4 + j] = v
                else:
                    t[k * 4 + j, i] = v
        for i in range(8):
            if vertical:
                t[i, k * 4 + 3] = C(110, 80, 56)
            else:
                t[k * 4 + 3, i] = C(110, 80, 56)
    return t


def edge_blend(rng, t, mask, other):
    o = other(rng)
    for y in range(8):
        for x in range(8):
            d = 9
            if mask & 1: d = min(d, y)
            if mask & 2: d = min(d, 7 - x)
            if mask & 4: d = min(d, 7 - y)
            if mask & 8: d = min(d, x)
            if d < 1.5 + rng.random() * 1.8:
                t[y, x] = o[y, x]
    return t


def shadowed(t):
    return t * np.array([0.58, 0.56, 0.74], np.float32)


VARIANTS = {'asphalt': 10, 'yel_v': 2, 'yel_h': 2, 'cw_v': 2, 'cw_h': 2, 'walk': 6, 'lot': 4, 'grass': 8,
            'path': 3, 'sand': 10, 'wet': 4, 'surf': 4, 'shallow': 6, 'deep': 8, 'seawall': 2, 'board_h': 3,
            'grassedge': 3}


def paint(kind, rng):
    if kind.endswith('_sh'):
        return shadowed(paint(kind[:-3], rng))
    if kind.startswith('curb_'):
        return p_curb(rng, int(kind.split('_')[1]))
    return {
        'asphalt': lambda: p_asphalt(rng), 'yel_v': lambda: p_yellow(rng, True), 'yel_h': lambda: p_yellow(rng, False),
        'cw_v': lambda: p_crosswalk(rng, True), 'cw_h': lambda: p_crosswalk(rng, False), 'walk': lambda: p_walk(rng),
        'lot': lambda: p_lot(rng), 'grass': lambda: p_grass(rng), 'path': lambda: p_path(rng),
        'sand': lambda: p_sand(rng), 'wet': lambda: p_wet(rng), 'surf': lambda: p_surf(rng),
        'shallow': lambda: p_water(rng, SHALLOW), 'deep': lambda: p_water(rng, DEEP, 4),
        'seawall': lambda: p_seawall(rng), 'board_h': lambda: p_boards(rng, False),
        'grassedge': lambda: edge_blend(rng, p_grass(rng), 2, p_sand),
    }[kind]()


def nvariants(kind):
    if kind.endswith('_sh'):
        return max(2, VARIANTS.get(kind[:-3], 2) // 3)
    return VARIANTS.get(kind, 1 if kind.startswith('curb_') else 2)


def build_terrain_grid():
    W = [['deep'] * T for _ in range(T)]
    X0, X1, Y0, Y1 = town.LAND_X0, town.LAND_X1, town.LAND_Y0, town.LAND_Y1
    road = lambda k: k in ('asphalt', 'yel_v', 'yel_h', 'cw_v', 'cw_h')
    for y in range(Y0, Y1 + 1):
        for x in range(X0, X1 + 1):
            if x <= town.CITY_X1:
                W[y][x] = 'lot'
            elif x <= town.PARK_X1:
                W[y][x] = 'grass'
            elif x < town.WET_X0:
                W[y][x] = 'sand'
            else:
                W[y][x] = 'wet'
    # sidewalks round every block, then the roads over them
    for y in range(Y0, Y1 + 1):
        for x in range(X0, town.CITY_X1 + 1):
            near_ave = any(a - 2 <= x < a + town.ROAD_W + 2 for a in town.AVENUES)
            near_st = any(s - 2 <= y < s + town.ROAD_W + 2 for s in town.STREETS)
            if near_ave or near_st or x < X0 + 3 or y < Y0 + 3 or y > Y1 - 3:
                W[y][x] = 'walk'
    for a in town.AVENUES:
        for y in range(Y0 + 1, Y1):
            for x in range(a, a + town.ROAD_W):
                W[y][x] = 'asphalt'
    for s in town.STREETS:
        for y in range(s, s + town.ROAD_W):
            for x in range(X0 + 1, town.CITY_X1 - 1):
                W[y][x] = 'asphalt'
    in_st = lambda y: any(s <= y < s + town.ROAD_W for s in town.STREETS)
    in_ave = lambda x: any(a <= x < a + town.ROAD_W for a in town.AVENUES)
    for a in town.AVENUES:
        for y in range(Y0 + 1, Y1):
            if in_st(y):
                continue
            if any(s - 2 <= y < s or s + town.ROAD_W <= y < s + town.ROAD_W + 2 for s in town.STREETS):
                for x in range(a, a + town.ROAD_W):
                    W[y][x] = 'cw_v'
            else:
                W[y][a + 2] = 'yel_v'
    for s in town.STREETS:
        for x in range(X0 + 1, town.CITY_X1 - 1):
            if in_ave(x):
                continue
            if any(a - 2 <= x < a or a + town.ROAD_W <= x < a + town.ROAD_W + 2 for a in town.AVENUES):
                for y in range(s, s + town.ROAD_W):
                    W[y][x] = 'cw_h'
            else:
                W[s + 2][x] = 'yel_h'
    # seawall along the bay and the north / south channels (city + park part)
    for y in range(Y0, Y1 + 1):
        W[y][X0] = 'seawall'
    for x in range(X0, town.PARK_X1 + 1):
        W[Y0][x] = 'seawall'; W[Y1][x] = 'seawall'
    # palm park: a winding path; boardwalks down to the sea
    for y in range(Y0 + 1, Y1):
        px = 79 + int(round(1.6 * math.sin(y / 6.0)))
        W[y][px] = 'path'
        W[y][town.PARK_X1] = 'grassedge'
    for r in town.BOARDWALK_ROWS:
        for x in range(town.PARK_X0, town.WET_X0 - 2):
            W[r][x] = 'board_h'
    # the beach's north / south tips run into wet sand
    for x in range(town.BEACH_X0, X1 + 1):
        W[Y0][x] = 'wet'; W[Y1][x] = 'wet'
    # water: surf against the beach, shallow near any shore, deep beyond
    land = [[W[y][x] != 'deep' for x in range(T)] for y in range(T)]
    for y in range(T):
        for x in range(T):
            if land[y][x]:
                continue
            best = 9
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    if land[(y + dy) % T][(x + dx) % T]:
                        best = min(best, max(abs(dx), abs(dy)))
            if best == 1 and x > X1 and Y0 < y < Y1:
                W[y][x] = 'surf'
            elif best <= 4:
                W[y][x] = 'shallow'
    # curbs where a sidewalk meets the road
    for y in range(T):
        for x in range(T):
            if W[y][x] == 'walk':
                m = 0
                if road(W[(y - 1) % T][x]): m |= 1
                if road(W[y][(x + 1) % T]): m |= 2
                if road(W[(y + 1) % T][x]): m |= 4
                if road(W[y][(x - 1) % T]): m |= 8
                if m:
                    W[y][x] = 'curb_%d' % m
    # building shadows (late sun low in the west -> shadows fall east)
    shadow = [[False] * T for _ in range(T)]
    for b in town.BUILDINGS:
        x0, y0, x1, y1 = town.footprint(b)
        h = town.MESHES[town.MESH_ID[b[0]]].height
        sx, sy = int(h * 0.55), -int(h * 0.2)
        for ty in range((y0 + sy) // 8, (y1 + sy) // 8 + 1):
            for tx in range(x0 // 8, (x1 + sx) // 8 + 1):
                if 0 <= tx < T and 0 <= ty < T:
                    shadow[ty][tx] = True
    for y in range(T):
        for x in range(T):
            k = W[y][x]
            if shadow[y][x] and k not in ('deep', 'shallow', 'surf', 'seawall', 'wet', 'grassedge'):
                W[y][x] = k + '_sh'
    return W


LAST_KIND = None


def build_ground():
    global LAST_KIND
    kind = build_terrain_grid()
    LAST_KIND = kind
    tiles = {}            # key -> (index, image)
    order = []
    rngs = {}
    tmap = np.zeros((T, T), np.int32)
    for y in range(T):
        for x in range(T):
            k = kind[y][x]
            nvar = nvariants(k)
            var = (x * 7349 + y * 1931 + (x * y) % 17) % nvar
            key = (k, var)
            if key not in tiles:
                seed = zlib.crc32(('%s/%d' % (k, var)).encode())
                img = paint(k, np.random.default_rng(seed))
                tiles[key] = len(order)
                order.append(np.clip(img, 0, 255))
            tmap[y, x] = tiles[key]
    n = len(order)
    assert n <= 256, n
    strip = np.concatenate(order, axis=1).astype(np.uint8)    # 8 x (8n) x 3
    im = Image.fromarray(strip, 'RGB')
    q = im.quantize(colors=GROUND_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = q.getpalette()[:GROUND_COLORS * 3]
    idx = np.array(q, dtype=np.int32) + 1                       # colours 1..191
    tiledata = []
    for i in range(n):
        tiledata += list(idx[:, i * 8:(i + 1) * 8].flatten())
    palette = [0] + [rgb15(pal[i * 3:i * 3 + 3]) for i in range(GROUND_COLORS)]
    # a preview of the whole map for the README / debugging
    preview = np.zeros((T * 8, T * 8, 3), np.uint8)
    for y in range(T):
        for x in range(T):
            t = idx[:, tmap[y, x] * 8:(tmap[y, x] + 1) * 8]
            preview[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = np.array(pal, np.uint8).reshape(-1, 3)[t - 1]
    return tiledata, list(tmap.flatten()), palette, n, preview


# ------------------------------------------------------------------ sky
SKY_W, SKY_H = 256, 64


def sky_image():
    """1980s Miami sunset: violet -> magenta -> orange, a striped sun, skyline and palm silhouettes"""
    img = np.zeros((SKY_H, SKY_W, 3), np.float32)
    stops = [(0.0, (44, 22, 96)), (0.35, (120, 40, 140)), (0.62, (226, 82, 132)), (0.82, (255, 150, 104)),
             (1.0, (255, 214, 168))]
    for y in range(SKY_H):
        t = y / (SKY_H - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                img[y, :] = np.array(c0) + (np.array(c1) - np.array(c0)) * k
    hor = np.array(stops[-1][1], np.float32)
    # thin streaks of cloud lit from below
    for (cx, cy, L) in ((30, 12, 50), (110, 20, 36), (160, 8, 44), (226, 24, 40), (80, 32, 30)):
        for x in range(-L // 2, L // 2):
            w = math.cos(x / L * math.pi) ** 2
            xx = (cx + x) % SKY_W
            img[cy, xx] = img[cy, xx] * (1 - w * 0.6) + np.array([255, 170, 200.]) * w * 0.6
            img[cy + 1, xx] = img[cy + 1, xx] * (1 - w * 0.4) + np.array([150, 60, 130.]) * w * 0.4
    # big striped sun sitting on the horizon
    sx, sy, R = 196, 44, 15
    for y in range(SKY_H):
        for x in range(SKY_W):
            d = math.hypot(x - sx, y - sy)
            if d < R:
                k = (y - (sy - R)) / (2 * R)
                c = np.array([255, 236, 120.]) * (1 - k) + np.array([255, 70, 140.]) * k
                gap = y > sy - 4 and (y - sy) % 4 in (0,) if y < sy + 6 else (y - sy) % 3 == 0
                if not gap:
                    img[y, x] = c
            elif d < R + 10:
                a = (1 - (d - R) / 10) ** 2 * 0.5
                img[y, x] = img[y, x] * (1 - a) + np.array([255, 190, 140.]) * a
    # downtown skyline far away (periodic so the panorama wraps)
    r = random.Random(1986)
    sky_h = [SKY_H] * SKY_W
    x = 0
    while x < SKY_W:
        w = r.randint(4, 11)
        if r.random() < 0.7 and not (150 < x < 240):
            top = SKY_H - r.randint(5, 20)
            for i in range(w):
                sky_h[(x + i) % SKY_W] = min(sky_h[(x + i) % SKY_W], top)
            if r.random() < 0.3:
                sky_h[(x + w // 2) % SKY_W] = top - r.randint(3, 6)
        x += w + r.randint(0, 3)
    win = np.array([255, 220, 120.])
    for x in range(SKY_W):
        for y in range(sky_h[x], SKY_H):
            img[y, x] = np.array([70, 34, 96.]) * 0.75 + img[y, x] * 0.25
            if (y + x * 3) % 7 == 0 and y < SKY_H - 3 and r.random() < 0.35:
                img[y, x] = win * 0.7 + img[y, x] * 0.3
    # palm silhouettes in front
    for px in (12, 58, 101, 140, 236):
        base, top = SKY_H - 1, SKY_H - 22 - r.randint(0, 6)
        for y in range(top, base):
            xx = px + int((base - y) * 0.15)
            img[y, xx % SKY_W] = [40, 16, 50]
        cx = px + int((base - top) * 0.15)
        for ang in range(0, 360, 40):
            for k in range(1, 9):
                fx = cx + int(k * math.cos(math.radians(ang)))
                fy = top + int(k * 0.5 * math.sin(math.radians(ang)) + (k * k) / 14)
                if 0 <= fy < SKY_H:
                    img[fy, fx % SKY_W] = [40, 16, 50]
    img[SKY_H - 2:, :] = hor
    return np.clip(img, 0, 255)


BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 - 0.5


def build_sky():
    img = sky_image()
    bands = [(0, 24, SKY_BANKS[0]), (24, 48, SKY_BANKS[1]), (48, 64, SKY_BANKS[2])]
    tiles, tmap = [], {}
    sky_map = [[0] * 32 for _ in range(8)]
    palettes = {}
    for (y0, y1, bank) in bands:
        reg = img[y0:y1].copy()
        for y in range(reg.shape[0]):
            for x in range(reg.shape[1]):
                reg[y, x] += BAYER[y % 4, x % 4] * 10
        q = Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8), 'RGB').quantize(
            colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        pal = q.getpalette()[:45]
        palettes[bank] = [0] + [rgb15(pal[i * 3:i * 3 + 3]) for i in range(15)]
        ind = np.array(q) + 1
        for ty in range((y1 - y0) // 8):
            for tx in range(32):
                t = ind[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                key = (bank, t.tobytes())
                if key not in tmap:
                    tmap[key] = len(tiles)
                    tiles.append(pack4bpp_tile(t))
                sky_map[y0 // 8 + ty][tx] = tmap[key] | (bank << 12)
    return tiles, sky_map, palettes, img


# ------------------------------------------------------------------ HUD font
HUD_PAL = ['#000000', '#140c08', '#fff6e0', '#f2c040', '#d0402a', '#3a2416', '#7a5232', '#b07c48',
           '#e0b070', '#9aa0a8', '#5c6066', '#ffffff', '#8ad060', '#000000', '#000000', '#000000']
FONT_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$:!.,'-/?*"


def glyph_tile(ch, ink):
    g = FONT5x7[ch]
    t = [[0] * 8 for _ in range(8)]
    for y, row in enumerate(g):
        for x, b in enumerate(row):
            if b == '1':
                for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):
                    xx, yy = x + 1 + dx, y + dy
                    if 0 <= xx < 8 and 0 <= yy < 8 and t[yy][xx] == 0:
                        t[yy][xx] = 1
    for y, row in enumerate(g):
        for x, b in enumerate(row):
            if b == '1':
                t[y][x + 1] = ink
    return t


def build_font():
    tiles = []
    for ink in (2, 3):  # white set, gold set
        for ch in FONT_CHARS:
            tiles.append(pack4bpp_tile(glyph_tile(ch, ink)))
    # icons: bullet, spent bullet, panel, panel edge
    bullet = ["........", "..33....", ".3883...", ".3883...", ".3883...", ".3883...", ".7777...", ".7777..."]
    spent = ["........", "........", "........", "........", "........", "........", ".aaaa...", ".aaaa..."]
    for pat in (bullet, spent):
        t = [[0] * 8 for _ in range(8)]
        for y, row in enumerate(pat):
            for x, c in enumerate(row):
                if c != '.':
                    t[y][x] = int(c, 16)
        tiles.append(pack4bpp_tile(t))
    from common import hexrgb
    pal = [rgb15(hexrgb(c)) for c in HUD_PAL]
    return tiles, pal
