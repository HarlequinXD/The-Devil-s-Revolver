#!/usr/bin/env python3
"""Generate every asset for The Devil's Revolver as C source in src/assets/.

usage: python3 tools/gen_assets.py [--preview]
Requires numpy and Pillow (only needed when regenerating assets; the generated
C files are committed so the ROM builds without Python).
"""
import math
import os
import random
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CFile, OUT, ROOT, rgb15, hexrgb, sprite_to_4bpp, HORIZON, FOCAL, CAM_H, WORLD,
                    SKY_BANKS, HUD_BANK)
import gen_town as town
import gen_ground as ground
import gen_sprites as spr

PREVIEW = '--preview' in sys.argv


def main():
    os.makedirs(OUT, exist_ok=True)
    decls = []

    # ---------------------------------------------------------- tables
    cf = CFile('tables')
    cf.array('s16', 'lut_sin', [int(round(math.sin(i * 2 * math.pi / 512) * 4096)) for i in range(512)])
    cf.array('u32', 'lut_recip', [0xFFFFFFFF] + [65536 * 256 // i for i in range(1, 4096)], per_line=8)
    # OBJ affine scale levels: level i shows a sprite at SCALE_LEVEL[i]/256
    levels = [2.0 * (0.04 / 2.0) ** (i / 30.0) for i in range(31)]
    cf.array('u16', 'scale_level_pa', [int(round(256 / s)) for s in levels])
    lut = []
    for q in range(1024):  # scale in 1/256 -> nearest level
        s = max(q, 1) / 256.0
        lut.append(min(range(31), key=lambda i: abs(math.log(levels[i] / s))))
    cf.array('u8', 'scale_to_level', lut)
    cf.array('u16', 'lut_atan', [int(round(math.atan(i / 256.0) / (2 * math.pi) * 65536)) for i in range(257)])
    cf.array('u16', 'scale_level_q8', [int(round(s * 256)) for s in levels])
    decls += cf.write()

    # ---------------------------------------------------------- town layout first (ground needs it)
    town.build_textures()
    town.build_meshes()
    town.build_layout()

    # ---------------------------------------------------------- ground
    tiles, tmap, gpal, ntiles, preview = ground.build_ground()
    cf = CFile('ground')
    cf.array('u8', 'ground_tiles', tiles, per_line=32)
    cf.array('u8', 'ground_map', tmap, per_line=32)
    decls += cf.write()
    if PREVIEW:
        Image.fromarray(preview).save(os.path.join(ROOT, 'docs', 'map_preview.png'))

    # ---------------------------------------------------------- sky + HUD font + BG palette
    sky_tiles, sky_map, sky_pals, sky_img = ground.build_sky()
    font_tiles, hud_pal = ground.build_font()
    bgpal = list(gpal) + [0] * (256 - len(gpal))
    for bank, p in sky_pals.items():
        bgpal[bank * 16:bank * 16 + 16] = p
    bgpal[HUD_BANK * 16:HUD_BANK * 16 + 16] = hud_pal
    bgpal[0] = rgb15((238, 226, 205))  # backdrop = horizon haze
    full_map = []
    for y in range(32):
        for x in range(64):
            full_map.append(sky_map[y][x % 32] if y < 8 else sky_map[7][x % 32])
    cf = CFile('sky')
    cf.array('u8', 'sky_tiles', [b for t in sky_tiles for b in t], per_line=32)
    cf.array('u16', 'sky_map', full_map)
    cf.array('u8', 'font_tiles', [b for t in font_tiles for b in t], per_line=32)
    cf.array('u16', 'bg_palette', bgpal)
    decls += cf.write()

    # ---------------------------------------------------------- town textures + meshes
    cf = CFile('town')
    for name, t in town.TEXTURES:
        cf.array('u8', 'tex_' + name, t.flat(), per_line=32)
    lines = ['const TexDef town_tex[%d] = {' % len(town.TEXTURES)]
    for name, t in town.TEXTURES:
        lines.append('  {tex_%s, %d, %d, {0,0}},' % (name, int(math.log2(t.w)), int(math.log2(t.h))))
    lines.append('};\n')
    cf.raw('\n'.join(lines), 'extern const TexDef town_tex[%d];' % len(town.TEXTURES))
    cf.array('u8', 'town_shade', [c for lvl in town.shade_luts() for c in lvl])
    for m in town.MESHES:
        L = ['const MWall mw_%s[%d] = {' % (m.name, max(1, len(m.walls)))]
        for w in m.walls:
            v = [int(round(a)) for a in w[:10]]
            L.append('  {%s, %d, %d, {0,0}},' % (','.join(map(str, v)), w[10], w[11]))
        L.append('};')
        L.append('const MPoly mp_%s[%d] = {' % (m.name, max(1, len(m.polys))))
        for (verts, uvs, tex, flags) in m.polys:
            n = len(verts)
            vv = verts + [verts[-1]] * (4 - n)
            uu = uvs + [uvs[-1]] * (4 - n)
            L.append('  {{%s},{%s},{%s},{%s},{%s}, %d, %d, %d, 0},' % (
                ','.join(str(int(round(p[0]))) for p in vv), ','.join(str(int(round(p[1]))) for p in vv),
                ','.join(str(int(round(p[2]))) for p in vv), ','.join(str(u) for u, _ in uu),
                ','.join(str(v) for _, v in uu), n, tex, flags))
        if not m.polys:
            L.append('  {{0},{0},{0},{0},{0},0,0,0,0},')
        L.append('};\n')
        cf.raw('\n'.join(L))
    L = ['const Mesh town_mesh[%d] = {' % len(town.MESHES)]
    for m in town.MESHES:
        L.append('  {mw_%s, mp_%s, %d, %d, %d, %d},' % (m.name, m.name, len(m.walls), len(m.polys), m.radius, m.height))
    L.append('};\n')
    cf.raw('\n'.join(L), 'extern const Mesh town_mesh[%d];' % len(town.MESHES))
    L = ['const BuildingDef town_buildings[%d] = {' % len(town.BUILDINGS)]
    for b in town.BUILDINGS:
        x0, y0, x1, y1 = town.footprint(b)
        L.append('  {%d, %d, %d, %d, %d, %d, %d, %d},  /* %s */' % (
            town.MESH_ID[b[0]], b[3], int(b[1]), int(b[2]), x0, y0, x1, y1, b[0]))
    L.append('};\n')
    cf.raw('\n'.join(L), 'extern const BuildingDef town_buildings[%d];' % len(town.BUILDINGS))
    decls += cf.write()

    # ---------------------------------------------------------- sprites
    cf = CFile('sprites')
    cow = spr.character_frames(False, 64)
    cf.array('u8', 'spr_cowboy', [b for f in cow for b in sprite_to_4bpp(f)], per_line=32)
    out = spr.character_frames(True, 32)
    cf.array('u8', 'spr_outlaw', [b for f in out for b in sprite_to_4bpp(f)], per_line=32)
    tips = []
    for wide, outlaw in ((64, False), (32, True)):
        for d in range(8):
            J = spr.skeleton(0.0, 'shoot')
            dv = J['wrR'] - J['elR']; dv = dv / np.linalg.norm(dv)
            tip = J['wrR'] + np.array([0, 1.5, 0]) + dv * 7.5
            R = spr.rot_x(spr.PITCH) @ spr.rot_y(d * math.pi / 4)
            v = R @ tip
            tips += [int(round(wide / 2 + v[0])), int(round(62 - v[1]))]
    cf.array('s8', 'gun_tips', tips)
    cf.array('u8', 'spr_outlaw_dead', sprite_to_4bpp(spr.dead_frame(True)), per_line=32)
    bills = [  # name, image, palette bank, art px per world unit, collision radius
        ('saguaro', spr.saguaro(), 2, 1.25, 4), ('joshua', spr.joshua(), 2, 1.6, 3),
        ('deadtree', spr.dead_tree(), 2, 1.6, 3), ('bush', spr.bush(), 2, 2.0, 0),
        ('rock', spr.rock(1), 3, 2.0, 6), ('rock2', spr.rock(5), 3, 2.6, 4),
        ('barrel', spr.barrel(), 3, 2.6, 4), ('skull', spr.skull(), 3, 3.0, 0),
        ('tumble0', spr.tumbleweed(0), 3, 3.0, 0), ('tumble1', spr.tumbleweed(1), 3, 3.0, 0)]
    L = ['const BillDef bill_defs[%d] = {' % len(bills)]
    for name, img, pal, k, rad in bills:
        h, w = img.shape
        cf.array('u8', 'bill_' + name, sprite_to_4bpp(img), per_line=32)
        shape, size = obj_shape(w, h)
        L.append('  {bill_%s, %d, %d, %d, %d, %d, %d, %d, %d, 0},' % (name, w * h // 2, w, h, shape, size, pal,
                                                                  int(round(k * 16)), rad))
    L.append('};\n')
    cf.raw('\n'.join(L), 'extern const BillDef bill_defs[%d];' % len(bills))
    cf.array('u8', 'fx_flash', sprite_to_4bpp(spr.fx_flash()), per_line=32)
    cf.array('u8', 'fx_dust', [b for f in range(3) for b in sprite_to_4bpp(spr.fx_dust(f))], per_line=32)
    cf.array('u8', 'fx_shadow', sprite_to_4bpp(spr.fx_shadow()), per_line=32)
    cf.array('u8', 'fx_spark', sprite_to_4bpp(spr.fx_spark()), per_line=32)
    objpal = [0] * 256
    for bank, pal in ((0, spr.COWBOY_PAL), (1, spr.OUTLAW_PAL), (2, spr.PLANT_PAL), (3, spr.PROP_PAL),
                      (4, spr.FX_PAL), (5, town.TOWN_PAL)):
        objpal[bank * 16:bank * 16 + 16] = spr.pal15(pal)
    cf.array('u16', 'obj_palette', objpal)
    decls += cf.write()

    # ---------------------------------------------------------- world placement
    rnd = random.Random(1885)
    boxes = [town.footprint(b) for b in town.BUILDINGS]

    def blocked(x, y, margin):
        for (x0, y0, x1, y1) in boxes:
            if x0 - margin < x < x1 + margin and y0 - margin < y < y1 + margin:
                return True
        if town.STREET_X0 - 24 < x < town.STREET_X1 + 24 and y > town.STREET_Y0 - 40:
            return True
        if town.CROSS_X0 - 10 < x < town.CROSS_X1 + 10 and town.CROSS_Y0 - 20 < y < town.CROSS_Y1 + 20:
            return True
        if 820 < y < 870:
            return True
        return False
    places = []
    weights = [(0, 26), (1, 8), (2, 7), (3, 30), (4, 12), (5, 10), (7, 3)]
    tot = sum(w for _, w in weights)
    tries = 0
    while len(places) < 230 and tries < 20000:
        tries += 1
        x, y = rnd.uniform(16, WORLD - 16), rnd.uniform(16, WORLD - 16)
        in_town = 300 < x < 740 and 160 < y < 780
        if blocked(x, y, 18) or (in_town and rnd.random() < 0.85):
            continue
        r = rnd.uniform(0, tot)
        for t, w in weights:
            r -= w
            if r <= 0:
                break
        if any((px - x) ** 2 + (py - y) ** 2 < 18 ** 2 for px, py, _ in places):
            continue
        places.append((int(x), int(y), t))
    # barrels beside the buildings on the boardwalk edges
    for b in town.BUILDINGS[:12]:
        if rnd.random() < 0.6:
            x0, y0, x1, y1 = town.footprint(b)
            x = 472 if b[3] == 3 else 552
            places.append((x, int(y0 + rnd.uniform(4, 12)), 6))
    places.sort(key=lambda p: (p[1] // 128) * 8 + p[0] // 128)
    starts = [0] * 65
    for p in places:
        starts[(p[1] // 128) * 8 + p[0] // 128 + 1] += 1
    for i in range(64):
        starts[i + 1] += starts[i]
    cf = CFile('world')
    cf.array('u16', 'bill_cell_start', starts)
    cf.raw('const BillPlace world_bills[%d] = {\n%s\n};\n' % (
        len(places), '\n'.join('  {%d, %d, %d, 0},' % p for p in places)),
        'extern const BillPlace world_bills[%d];' % len(places))
    spawns = [(512, 330), (500, 420), (520, 640), (420, 512), (610, 512), (530, 700), (700, 512), (512, 240)]
    cf.raw('const s16 npc_spawns[%d][2] = {\n%s\n};\n' % (len(spawns), '\n'.join('  {%d, %d},' % s for s in spawns)),
           'extern const s16 npc_spawns[%d][2];' % len(spawns))
    decls += cf.write()

    # ---------------------------------------------------------- header
    consts = {
        'N_GROUND_TILES': ntiles, 'N_SKY_TILES': len(sky_tiles), 'N_FONT_TILES': len(font_tiles),
        'N_TOWN_TEX': len(town.TEXTURES), 'N_MESHES': len(town.MESHES), 'N_BUILDINGS': len(town.BUILDINGS),
        'N_BILL_DEFS': len(bills), 'N_WORLD_BILLS': len(places), 'N_NPC_SPAWNS': len(spawns),
        'N_SCALE_LEVELS': 31, 'CHAR_FRAMES': spr.N_FRAMES, 'COWBOY_FRAMES': spr.N_FRAMES_COWBOY,
        'GEN_HORIZON': HORIZON, 'GEN_FOCAL': FOCAL, 'GEN_CAM_H': CAM_H,
    }
    with open(os.path.join(OUT, 'assets.h'), 'w') as f:
        f.write(HEADER)
        for k, v in consts.items():
            f.write('#define %s %d\n' % (k, v))
        f.write('#define FONT_CHARS "%s"\n\n' % ground.FONT_CHARS.replace('\\', '\\\\'))
        for name in ('saguaro', 'joshua', 'deadtree', 'bush', 'rock', 'rock2', 'barrel', 'skull', 'tumble0', 'tumble1'):
            f.write('#define BILL_%s %d\n' % (name.upper(), [b[0] for b in bills].index(name)))
        f.write('\n' + '\n'.join(decls) + '\n\n#endif\n')
    print('ground tiles %d, sky tiles %d, font tiles %d, textures %d, meshes %d, buildings %d, billboards %d'
          % (ntiles, len(sky_tiles), len(font_tiles), len(town.TEXTURES), len(town.MESHES), len(town.BUILDINGS), len(places)))


def obj_shape(w, h):
    table = {(8, 8): (0, 0), (16, 16): (0, 1), (32, 32): (0, 2), (64, 64): (0, 3),
             (16, 8): (1, 0), (32, 8): (1, 1), (32, 16): (1, 2), (64, 32): (1, 3),
             (8, 16): (2, 0), (8, 32): (2, 1), (16, 32): (2, 2), (32, 64): (2, 3)}
    return table[(w, h)]


HEADER = r'''/* Generated by tools/gen_assets.py - do not edit. */
#ifndef ASSETS_H
#define ASSETS_H
#include <stdint.h>

typedef uint8_t u8;   typedef int8_t s8;
typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;

/* vertical wall quad of a building: floor edge (x0,z0)->(x1,z1), heights y0..y1,
   texture coords in 1/16 texel (u along the wall, v from top to bottom) */
typedef struct { s16 x0, z0, x1, z1, y0, y1, u0, u1, v0, v1; u8 tex, flags, pad[2]; } MWall;
/* general polygon (roof slopes, gables): up to 4 verts, clockwise seen from outside */
typedef struct { s16 x[4], y[4], z[4], u[4], v[4]; u8 n, tex, flags, pad; } MPoly;
typedef struct { const MWall *walls; const MPoly *polys; u8 nwalls, npolys; s16 radius, height; } Mesh;
typedef struct { const u8 *pix; u8 wshift, hshift, pad[2]; } TexDef;
typedef struct { u8 mesh, rot; s16 x, y; s16 bx0, by0, bx1, by1; } BuildingDef;
typedef struct { const u8 *tiles; u16 bytes; u8 w, h, shape, size, pal, k16, radius, pad; } BillDef;
typedef struct { s16 x, y; u8 type, pad; } BillPlace;

#define WALL_DOUBLE 1

'''

if __name__ == '__main__':
    main()
