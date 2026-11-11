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


SAND = C(205, 168, 112)
SAND2 = C(184, 144, 96)
ROAD = C(152, 113, 77)


def noise_tile(rng, base, amp=9):
    t = np.zeros((8, 8, 3), np.float32) + base
    t += (rng.standard_normal((8, 8, 1)) * amp)
    t += rng.standard_normal((8, 8, 3)) * 2
    return t


def specks(rng, t, n, col, amp=0):
    for _ in range(n):
        x, y = rng.integers(0, 8, 2)
        t[y, x] = col + rng.standard_normal(3) * amp


def p_sand(rng, base=SAND):
    t = noise_tile(rng, base, 7)
    specks(rng, t, rng.integers(1, 4), base * 0.84)
    specks(rng, t, rng.integers(0, 3), np.minimum(base * 1.1, 255))
    return t


def p_cracked(rng):
    t = noise_tile(rng, C(198, 162, 112), 5)
    x, y = rng.integers(0, 8, 2)
    for _ in range(9):
        t[y % 8, x % 8] = C(142, 106, 72)
        if rng.random() < 0.5:
            x += rng.choice((-1, 1))
        else:
            y += rng.choice((-1, 1))
    return t


def p_scrub(rng):
    t = p_sand(rng)
    cx, cy = rng.integers(1, 7, 2)
    for _ in range(rng.integers(4, 8)):
        x = int(np.clip(cx + rng.integers(-2, 3), 0, 7)); y = int(np.clip(cy + rng.integers(-1, 2), 0, 7))
        t[y, x] = rng.choice([C(118, 116, 58), C(92, 96, 46), C(140, 132, 70)])
    return t


def p_rocky(rng):
    t = p_sand(rng, SAND2)
    for _ in range(rng.integers(2, 4)):
        x, y = rng.integers(0, 7, 2)
        g = rng.integers(120, 160)
        t[y, x] = C(g, g - 8, g - 18); t[y, x + 1] = C(g - 25, g - 32, g - 40)
        if y < 7:
            t[y + 1, x] = C(g - 40, g - 45, g - 50)
    return t


def p_creek(rng):
    t = noise_tile(rng, C(168, 150, 126), 6)
    for _ in range(9):
        x, y = rng.integers(0, 8, 2)
        g = rng.integers(110, 190)
        t[y, x] = C(g, g - 6, g - 14)
    return t


def p_road(rng):
    t = noise_tile(rng, ROAD, 6)
    specks(rng, t, rng.integers(2, 5), ROAD * 0.82)
    specks(rng, t, rng.integers(1, 3), ROAD * 1.12)
    return t


def p_rut(rng, vertical):
    t = p_road(rng)
    for i in range(8):
        for k, f in ((3, 0.78), (4, 0.72)):
            if vertical:
                t[i, k] *= f
            else:
                t[k, i] *= f
    return t


def p_boards(rng, vertical):
    t = np.zeros((8, 8, 3), np.float32)
    cols = [C(132, 88, 52), C(150, 104, 62), C(118, 78, 46)]
    for k in range(2):
        c = cols[rng.integers(0, 3)]
        for i in range(8):
            for j in range(4):
                v = c + rng.standard_normal(3) * 4 + (rng.random() < 0.15) * -18
                if vertical:
                    t[i, k * 4 + j] = v
                else:
                    t[k * 4 + j, i] = v
        for i in range(8):
            if vertical:
                t[i, k * 4 + 3] = C(62, 40, 26)
            else:
                t[k * 4 + 3, i] = C(62, 40, 26)
    return t


def p_rail(rng, part):
    t = noise_tile(rng, C(124, 114, 104), 10)          # gravel ballast
    sleeper_rows = {'a': range(1, 8), 'm': range(0, 8), 'c': range(0, 3)}[part]
    for y in sleeper_rows:
        for x in range(0, 4):
            t[y, x] = C(92, 64, 42) + rng.standard_normal(3) * 4
    rail_row = {'a': 4, 'm': 7, 'c': None}[part]
    if rail_row is not None:
        t[rail_row, :] = C(72, 70, 74)
        t[rail_row - 1, :] = C(178, 176, 182)
    return t


def p_bones(rng):
    t = p_sand(rng)
    for (x, y) in ((1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (2, 2), (2, 4), (5, 2), (5, 4)):
        t[y, x] = C(232, 224, 205)
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
    return t * np.array([0.6, 0.6, 0.72], np.float32)


VARIANTS = {'sand': 16, 'sand2': 8, 'cracked': 6, 'scrub': 8, 'rocky': 6, 'creek': 8, 'road': 10,
            'rut_v': 4, 'rut_h': 4, 'board_v': 4, 'board_h': 4, 'rail_a': 2, 'rail_m': 2, 'rail_c': 2,
            'bones': 2, 'sand_sh': 6, 'road_sh': 6, 'board_v_sh': 2, 'board_h_sh': 2}


def paint(kind, rng):
    if kind.startswith('roadedge'):
        mask = int(kind.split('_')[1])
        return edge_blend(rng, p_road(rng), mask, p_sand)
    return {
        'sand': lambda: p_sand(rng), 'sand2': lambda: p_sand(rng, SAND2), 'cracked': lambda: p_cracked(rng),
        'scrub': lambda: p_scrub(rng), 'rocky': lambda: p_rocky(rng), 'creek': lambda: p_creek(rng),
        'road': lambda: p_road(rng), 'rut_v': lambda: p_rut(rng, True), 'rut_h': lambda: p_rut(rng, False),
        'board_v': lambda: p_boards(rng, True), 'board_h': lambda: p_boards(rng, False),
        'rail_a': lambda: p_rail(rng, 'a'), 'rail_m': lambda: p_rail(rng, 'm'), 'rail_c': lambda: p_rail(rng, 'c'),
        'bones': lambda: p_bones(rng),
        'sand_sh': lambda: shadowed(p_sand(rng)), 'road_sh': lambda: shadowed(p_road(rng)),
        'board_v_sh': lambda: shadowed(p_boards(rng, True)), 'board_h_sh': lambda: shadowed(p_boards(rng, False)),
    }[kind]()


def value_noise(seed, cells, size=T):
    rng = np.random.default_rng(seed)
    g = rng.random((cells + 1, cells + 1))
    g[-1, :] = g[0, :]; g[:, -1] = g[:, 0]
    out = np.zeros((size, size))
    for y in range(size):
        for x in range(size):
            fx, fy = x / size * cells, y / size * cells
            ix, iy = int(fx), int(fy)
            tx, ty = fx - ix, fy - iy
            tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
            a = g[iy, ix] * (1 - tx) + g[iy, ix + 1] * tx
            b = g[iy + 1, ix] * (1 - tx) + g[iy + 1, ix + 1] * tx
            out[y, x] = a * (1 - ty) + b * ty
    return out


def build_terrain_grid():
    kind = [['sand'] * T for _ in range(T)]
    n1 = value_noise(3, 8)
    n2 = value_noise(11, 16)
    rng = random.Random(5)
    for y in range(T):
        for x in range(T):
            v, w = n1[y, x], n2[y, x]
            k = 'sand'
            if v < 0.28: k = 'sand2'
            elif v > 0.78: k = 'cracked'
            if w > 0.72: k = 'scrub'
            elif w < 0.18: k = 'rocky'
            if k == 'sand' and rng.random() < 0.004: k = 'bones'
            kind[y][x] = k
    # dry creek in the west
    for y in range(T):
        cx = 22 + 5 * math.sin(y / 11.0) + 2 * math.sin(y / 4.3)
        for x in range(T):
            if abs(x - cx) < 1.6:
                kind[y][x] = 'creek'
    road = [[False] * T for _ in range(T)]

    def road_rect(x0, y0, x1, y1):
        for y in range(max(0, y0 // 8), min(T, (y1 + 7) // 8)):
            for x in range(max(0, x0 // 8), min(T, (x1 + 7) // 8)):
                road[y][x] = True
    road_rect(town.STREET_X0, town.STREET_Y0, town.STREET_X1, town.STREET_Y1)
    road_rect(town.CROSS_X0, town.CROSS_Y0, town.CROSS_X1, town.CROSS_Y1)
    road_rect(448, 168, 576, 200)               # church plaza
    road_rect(560, 770, 690, 832)               # depot yard
    road_rect(330, 560, 420, 640)               # corral yard
    # winding trails out of town (west / east / north)
    for x in range(0, town.CROSS_X0 // 8 + 1):
        yc = 63 + 4 * math.sin(x / 6.0)
        for y in range(int(yc) - 1, int(yc) + 2):
            road[y % T][x] = True
    for x in range(town.CROSS_X1 // 8, T):
        yc = 63 + 5 * math.sin(x / 7.0 + 1)
        for y in range(int(yc) - 1, int(yc) + 2):
            road[y % T][x] = True
    for y in range(0, 22):
        xc = 64 + 6 * math.sin(y / 5.0)
        for x in range(int(xc) - 1, int(xc) + 2):
            road[y][x % T] = True
    for y in range(T):
        for x in range(T):
            if road[y][x]:
                kind[y][x] = 'road'
    # wheel ruts down the main street and along the cross street
    for y in range(town.STREET_Y0 // 8 + 1, T):
        for x in (62, 65):
            if road[y][x] and not (town.CROSS_Y0 // 8 <= y < (town.CROSS_Y1 + 7) // 8):
                kind[y][x] = 'rut_v'
    for x in range(town.CROSS_X0 // 8 + 1, town.CROSS_X1 // 8):
        for y in (62, 65):
            if not (60 <= x <= 67):
                kind[y][x] = 'rut_h'
    # boardwalks in front of the buildings
    boards = set()
    for (y0, y1) in ((296, 488), (536, 728)):
        for y in range(y0 // 8, y1 // 8):
            for x in (58, 59, 68, 69):
                kind[y][x] = 'board_v'; boards.add((x, y))
    for x in range(568 // 8, 680 // 8):         # depot platform
        for y in (102, 103):
            kind[y][x] = 'board_h'; boards.add((x, y))
    # railway (rails run east-west)
    for x in range(T):
        kind[104][x] = 'rail_a'; kind[105][x] = 'rail_m'; kind[106][x] = 'rail_c'
    # soft road edges where road meets open desert
    def is_paved(x, y):
        k = kind[y % T][x % T]
        return k.startswith('road') or k.startswith('rut') or k.startswith('board') or k.startswith('rail')
    for y in range(T):
        for x in range(T):
            if kind[y][x] == 'road':
                m = 0
                if not is_paved(x, y - 1): m |= 1
                if not is_paved(x + 1, y): m |= 2
                if not is_paved(x, y + 1): m |= 4
                if not is_paved(x - 1, y): m |= 8
                if m:
                    kind[y][x] = 'roadedge_%d' % m
    # building shadows (afternoon sun from the west-south-west -> shadows fall east-north-east)
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
            if shadow[y][x]:
                k = kind[y][x]
                if k in ('road', 'rut_v', 'rut_h') or k.startswith('roadedge'):
                    kind[y][x] = 'road_sh'
                elif k in ('board_v', 'board_h'):
                    kind[y][x] = k + '_sh'
                elif k in ('sand', 'sand2', 'scrub', 'cracked', 'rocky', 'bones'):
                    kind[y][x] = 'sand_sh'
    return kind


def build_ground():
    kind = build_terrain_grid()
    tiles = {}            # key -> (index, image)
    order = []
    rngs = {}
    tmap = np.zeros((T, T), np.int32)
    for y in range(T):
        for x in range(T):
            k = kind[y][x]
            nvar = VARIANTS.get(k, 2)
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
    img = np.zeros((SKY_H, SKY_W, 3), np.float32)
    top, mid, hor = np.array([46, 86, 156.]), np.array([118, 158, 204.]), np.array([240, 226, 200.])
    for y in range(SKY_H):
        t = y / (SKY_H - 1)
        c = top + (mid - top) * min(1, t / 0.55) if t < 0.55 else mid + (hor - mid) * ((t - 0.55) / 0.45) ** 0.8
        img[y, :] = c
    rng = np.random.default_rng(4)
    # wispy clouds
    for (cx, cy, L) in ((40, 14, 46), (120, 9, 30), (150, 24, 54), (220, 16, 36), (90, 30, 40)):
        for x in range(-L // 2, L // 2):
            w = math.cos(x / L * math.pi) ** 2
            for dy in (-1, 0, 1):
                xx = (cx + x) % SKY_W
                yy = cy + dy + int(2 * math.sin(x / 9))
                a = w * (0.55 if dy == 0 else 0.25)
                img[yy, xx] = img[yy, xx] * (1 - a) + np.array([248, 240, 228.]) * a
    # the afternoon sun low in the west
    sx, sy = 196, 26
    for y in range(SKY_H):
        for x in range(SKY_W):
            d = math.hypot(x - sx, (y - sy) * 1.1)
            if d < 6:
                img[y, x] = [255, 250, 222]
            elif d < 18:
                a = (1 - (d - 6) / 12) ** 2 * 0.6
                img[y, x] = img[y, x] * (1 - a) + np.array([255, 236, 170.]) * a
    # two layers of mesas / buttes (periodic so the sky wraps)
    def profile(seed, base, amp):
        r = random.Random(seed)
        h = [base] * SKY_W
        x = 0
        while x < SKY_W:
            w = r.randint(14, 46)
            if r.random() < 0.6:
                top = base - r.randint(int(amp * 0.4), amp)
                slope = r.randint(2, 5)
                for i in range(w):
                    e = min(i, w - 1 - i)
                    hh = base - min(base - top, e * (base - top) // slope + 1)
                    h[(x + i) % SKY_W] = min(h[(x + i) % SKY_W], hh)
            x += w + r.randint(4, 24)
        return h
    far = profile(9, 58, 14)
    near = profile(21, 63, 11)
    for x in range(SKY_W):
        for y in range(far[x], SKY_H):
            a = 0.55 + 0.25 * (y - far[x]) / 12
            img[y, x] = np.array([168, 128, 132.]) * (1 - min(a, 0.8)) + hor * min(a, 0.8) * 0.2 + np.array([168, 128, 132.]) * min(a, 0.8) * 0.8
            img[y, x] = img[y, x] * 0.8 + hor * 0.2
        for y in range(near[x], SKY_H):
            k = (y - near[x]) / 8
            c = np.array([150, 96, 70.]) if y - near[x] > 0 else np.array([186, 120, 84.])
            img[y, x] = c * (1 - min(1, k) * 0.5) + hor * min(1, k) * 0.5
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
