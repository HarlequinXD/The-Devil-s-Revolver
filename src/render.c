/* Software renderer for the textured 3D buildings + the Mode 7 scanline table.
 *
 * Compiled as ARM code and placed in IWRAM (32-bit bus, no wait states).
 * Each building is drawn into a small 8bpp canvas (at 1x or 2x pixel size)
 * and then packed into 4bpp OBJ tiles, so the hardware composites it over
 * the Mode 7 ground like any other sprite.
 *
 * Walls are vertical and the camera never pitches, so every screen column of
 * a wall has constant depth: walls are drawn column by column with exact
 * perspective-correct texturing (Wolfenstein style). Roof slopes and gables
 * use an affine triangle filler.
 */
#include "game.h"

#define CSTRIDE 128
#define CROWS 80
static u8 canvas[CSTRIDE * CROWS] ALIGN4;
static u8 shade_iw[48] ALIGN4;      /* shading LUT copied to IWRAM */
static const u8 *tex_pix[N_TOWN_TEX];
static u8 tex_ewram[52 * 1024] EWRAM_BSS ALIGN4;
static int shade_ready;

typedef long long s64;

#ifdef PLATFORM_NATIVE
#define IWRAM_FN
#else
#define IWRAM_FN __attribute__((section(".iwram")))
#endif

/* ARM assembly inner loop (fill.s): textured, transparent, shaded column */
#ifdef PLATFORM_GBA
void col_fill(u8 *dst, const u8 *col, u32 vv, u32 vstp, u32 n, const u8 *shade, u32 sh, u32 mask);
void pack_row(u32 *out, const u8 *src, u32 ntiles);  /* ntiles 8x8 tiles -> 4bpp */
void canvas_clear_row(u8 *dst, u32 bytes);          /* bytes multiple of 32 */
#else
/* portable C versions of the ARM assembly loops in fill.s */
static void col_fill(u8 *dst, const u8 *col, u32 vv, u32 vstp, u32 n, const u8 *shade, u32 sh, u32 mask) {
    if (shade) for (; n; n--, dst += 128, vv += vstp) *dst = shade[col[(vv >> sh) & mask]];
    else for (; n; n--, dst += 128, vv += vstp) *dst = col[(vv >> sh) & mask];
}
static void pack_row(u32 *out, const u8 *src, u32 ntiles) {
    for (u32 t = 0; t < ntiles; t++, src += 8)
        for (int r = 0; r < 8; r++) {
            const u8 *s = src + r * 128;
            u32 v = 0;
            for (int k = 0; k < 8; k++) v |= (u32)(s[k] & 15) << (k * 4);
            *out++ = v;
        }
}
static void canvas_clear_row(u8 *dst, u32 bytes) { memset(dst, 0, bytes); }
#endif

INLINE s32 mul64sh(s32 a, s32 b, int sh) { return (s32)(((s64)a * b) >> sh); }

/* 2^28 / x for x >= 1 using the reciprocal table (about 11 bits of precision) */
INLINE s32 recip28(s32 x) {
    u32 v = (u32)x; int sh = 0;
    while (v >= 4096) { v >>= 1; sh++; }
    if (!v) v = 1;
    return (s32)((lut_recip[v] << 4) >> sh);
}

/* sun comes from the west-south-west in the afternoon */
#define SUN_X (-3700)
#define SUN_Y (1500)

typedef struct { s32 key; u8 kind, idx, shade, flip; } Face;


typedef struct {
    s32 Xa, Za, Xb, Zb, ua, ub;          /* cam space Q8, u Q4 */
    s32 iza, izb, sxa16, sxb16;          /* 2^20/Z and screen x (Q4) */
    const MWall *w;
    u8 shade;
    s16 occ_top, occ_bot;                /* rows this wall surely covers (for occlusion) */
} WallJob;

typedef struct {
    s32 x[4], y[4];                      /* canvas coords Q4 */
    s32 u[4], v[4];                      /* texels Q4 */
    s32 z;
    const MPoly *p;
    u8 shade;
} PolyJob;

static WallJob wjobs[40];
static u8 occ_top[SCREEN_W + 2], occ_bot[SCREEN_W + 2];   /* see occ_add() */
static PolyJob pjobs[24] EWRAM_BSS;

static int cv_sx0, cv_sy0, cv_s, cv_w, cv_h;
static int prep_nw, prep_np, prep_s, prep_nx, prep_ny, prep_ow, prep_oh;
static s32 prep_bx0, prep_by0;

/* ------------------------------------------------------------- wall columns */
IWRAM_FN static void draw_wall(const WallJob *j) {
    const MWall *w = j->w;
    s32 sxa16 = j->sxa16, sxb16 = j->sxb16;
    s32 span = sxb16 - sxa16;
    if (span <= 0) return;
    int s = cv_s, sh = 4 + (s - 1);
    s32 base16 = cv_sx0 * 16 + 8 * s;                         /* centre of column 0 */
    s32 c0 = (sxa16 - base16 + (16 * s - 1)) >> sh;
    if (c0 < 0) c0 = 0;
    s32 c1 = (sxb16 - base16 + (16 * s - 1)) >> sh;           /* exclusive */
    if (c1 > cv_w) c1 = cv_w;
    if (c0 >= c1) return;                                     /* nothing on this canvas */
    s32 iza = j->iza, izb = j->izb;                           /* 2^20 / Z */
    s32 uza = j->ua * iza, uzb = j->ub * izb;
    s32 rspan = recip28(span);                                /* no divisions per wall */
    s32 diz16 = mul64sh((izb - iza) << 8, rspan, 28);         /* iz<<8 per 1/16 px */
    s32 duz16 = mul64sh(uzb - uza, rspan, 28);
    s32 f0 = base16 + (c0 << sh) - sxa16;
    s32 iz8 = (iza << 8) + diz16 * f0;
    s32 uz = uza + duz16 * f0;
    s32 dizc = diz16 << sh, duzc = duz16 << sh;
    const TexDef *td = &town_tex[w->tex];
    const u8 *pix = tex_pix[w->tex];
    int ws = td->wshift, wm = (1 << td->wshift) - 1, hm = (1 << td->hshift) - 1;
    const u8 *shade = shade_iw + j->shade * 16;
    s32 hy1 = (CAM_H - w->y1) * FOCAL, hy0 = (CAM_H - w->y0) * FOCAL;
    /* texels per screen pixel = Kw * Z (no per-column division) */
    s32 Kw = mul64sh((w->v1 - w->v0) << 16, recip28((w->y1 - w->y0) * FOCAL), 28);
    s32 rowbase16 = cv_sy0 * 16 + 8 * s;
    /* wall top/bottom are linear in 1/Z, hence in screen x: step them exactly.
       u and the texel step need Z: computed every 8 columns, lerped between. */
    s32 top_fx = (s32)(((s64)hy1 * iz8) >> 16), dtop = (s32)(((s64)hy1 * dizc) >> 16);
    s32 bot_fx = (s32)(((s64)hy0 * iz8) >> 16), dbot = (s32)(((s64)hy0 * dizc) >> 16);
    u32 vshift = 12 - td->hshift, fsh = 32 - td->hshift - ws, fmask = hm << ws;
    const u8 *fshade = j->shade ? shade : 0;
    s32 u = 0, du = 0, vst = 0, dvst = 0;
    int left = 0;
    for (s32 c = c0; c < c1; c++, iz8 += dizc, uz += duzc, top_fx += dtop, bot_fx += dbot) {
        if (!left) {                                           /* new block of up to 8 columns */
            int len = c1 - c; if (len > 8) len = 8;
            s32 izA = iz8 >> 8, izB = (iz8 + dizc * len) >> 8;
            if (izA <= 0) izA = 1;
            if (izB <= 0) izB = 1;
            s32 ZA = recip28(izA), ZB = recip28(izB);            /* Z * 256 */
            s32 uA = mul64sh(uz, ZA, 28), uB = mul64sh(uz + duzc * len, ZB, 28);
            s32 vA = mul64sh(Kw, ZA, 8), vB = mul64sh(Kw, ZB, 8);
            s32 rl = (s32)lut_recip[len];                      /* 2^24 / len */
            u = uA << 8; du = mul64sh((uB - uA) << 8, rl, 24);
            vst = vA; dvst = mul64sh(vB - vA, rl, 24);
            left = len;
        }
        left--;
        s32 top16 = HORIZON * 16 + (top_fx >> 8);
        s32 bot16 = HORIZON * 16 + (bot_fx >> 8);
        s32 uc = u >> 8, vstep = vst;
        u += du; vst += dvst;
        if (bot16 <= top16) continue;
        s32 r0 = (top16 - rowbase16 + (16 * s - 1)) >> sh;
        if (r0 < 0) r0 = 0;
        s32 r1 = (bot16 - rowbase16 + (16 * s - 1)) >> sh;
        if (r1 > cv_h) r1 = cv_h;
        if (r0 >= r1) continue;
        {   /* skip the part of the column already hidden by a nearer building */
            s32 sx = cv_sx0 + c * s;
            if (sx >= 0 && sx < SCREEN_W) {
                s32 ot = occ_top[sx], ob = occ_bot[sx];
                if (s == 2) { if (occ_top[sx + 1] > ot) ot = occ_top[sx + 1]; if (occ_bot[sx + 1] < ob) ob = occ_bot[sx + 1]; }
                if (ot != 255 && ob > ot) {
                    s32 y0 = cv_sy0 + r0 * s, y1 = cv_sy0 + r1 * s;
                    if (ot <= y0 && ob > y0) { s32 n = (ob - cv_sy0) >> (s - 1); if (n > r0) r0 = n; }
                    if (ob >= y1 && ot < y1) { s32 n = (ot - cv_sy0 + s - 1) >> (s - 1); if (n < r1) r1 = n; }
                    if (r0 >= r1) continue;
                }
            }
        }
        s32 v = (w->v0 << 16) + mul64sh(vstep, rowbase16 + (r0 << sh) - top16, 4);
        const u8 *col = pix + ((uc >> 4) & wm);
        u8 *dst = canvas + r0 * CSTRIDE + c;
        u32 vv = (u32)v << vshift, vstp = (u32)(vstep << (s - 1)) << vshift;
        col_fill(dst, col, vv, vstp, r1 - r0, fshade, fsh, fmask);
    }
}

/* ------------------------------------------------------------- affine triangles */
typedef struct { s32 x, u, v, dx, du, dv; s32 y0, y1; } Edge;

IWRAM_FN static int edge_init(Edge *e, const PolyJob *p, int a, int b) {
    s32 ay = p->y[a], by = p->y[b];
    s32 dy = by - ay;
    if (dy <= 0) return 0;
    if (dy > 4095) dy = 4095;
    s32 inv = (s32)lut_recip[dy];
    e->dx = mul64sh(p->x[b] - p->x[a], inv, 8);
    e->du = mul64sh(p->u[b] - p->u[a], inv, 8);
    e->dv = mul64sh(p->v[b] - p->v[a], inv, 8);
    s32 r0 = (ay - 8 + 15) >> 4;           /* first row whose centre >= ay */
    s32 pre = (r0 * 16 + 8) - ay;
    e->x = (p->x[a] << 12) + ((e->dx * pre) >> 4);
    e->u = (p->u[a] << 12) + ((e->du * pre) >> 4);
    e->v = (p->v[a] << 12) + ((e->dv * pre) >> 4);
    e->y0 = r0;
    e->y1 = (by - 8 + 15) >> 4;            /* exclusive */
    return 1;
}

static inline __attribute__((always_inline)) void span(s32 row, const Edge *l, const Edge *r, const u8 *pix, int ws, int wm, int hm, const u8 *shade) {
    if (row < 0 || row >= cv_h) return;
    s32 xl = l->x, xr = r->x;
    if (xr <= xl) return;
    s32 wq = (xr - xl) >> 12;
    if (wq <= 0) wq = 1;
    if (wq > 4095) wq = 4095;
    s32 inv = (s32)lut_recip[wq];
    s32 du = mul64sh(r->u - l->u, inv, 20);
    s32 dv = mul64sh(r->v - l->v, inv, 20);
    s32 c0 = (xl - 0x8000 + 0xFFFF) >> 16;
    s32 c1 = (xr - 0x8000 + 0xFFFF) >> 16;
    if (c0 < 0) c0 = 0;
    if (c1 > cv_w) c1 = cv_w;
    if (c0 >= c1) return;
    s32 pre = (c0 << 16) + 0x8000 - xl;
    s32 u = l->u + mul64sh(du, pre, 16);
    s32 v = l->v + mul64sh(dv, pre, 16);
    u8 *dst = canvas + row * CSTRIDE + c0;
    for (s32 c = c0; c < c1; c++, u += du, v += dv) {
        u32 t = pix[((((v >> 16) & hm)) << ws) | ((u >> 16) & wm)];
        if (t) *dst = shade[t];
        dst++;
    }
}

IWRAM_FN static void draw_tri(const PolyJob *p, int i0, int i1, int i2) {
    int idx[3] = {i0, i1, i2};
    /* sort by y */
    if (p->y[idx[0]] > p->y[idx[1]]) { int t = idx[0]; idx[0] = idx[1]; idx[1] = t; }
    if (p->y[idx[1]] > p->y[idx[2]]) { int t = idx[1]; idx[1] = idx[2]; idx[2] = t; }
    if (p->y[idx[0]] > p->y[idx[1]]) { int t = idx[0]; idx[0] = idx[1]; idx[1] = t; }
    {   /* whole triangle off the canvas? */
        s32 mnx = p->x[i0], mxx = mnx;
        if (p->x[i1] < mnx) mnx = p->x[i1];
        if (p->x[i1] > mxx) mxx = p->x[i1];
        if (p->x[i2] < mnx) mnx = p->x[i2];
        if (p->x[i2] > mxx) mxx = p->x[i2];
        if (mxx < 0 || mnx >= cv_w * 16 || p->y[idx[2]] < 0 || p->y[idx[0]] >= cv_h * 16) return;
    }
    Edge lng, s1, s2;
    if (!edge_init(&lng, p, idx[0], idx[2])) return;
    int h1 = edge_init(&s1, p, idx[0], idx[1]);
    int h2 = edge_init(&s2, p, idx[1], idx[2]);
    const TexDef *td = &town_tex[p->p->tex];
    int ws = td->wshift, wm = (1 << td->wshift) - 1, hm = (1 << td->hshift) - 1;
    const u8 *shade = shade_iw + p->shade * 16;
    /* is the long edge on the left? compare x at the middle vertex height */
    s32 ym = p->y[idx[1]];
    s32 dy = p->y[idx[2]] - p->y[idx[0]];
    s32 xl_at_m = p->x[idx[0]] + ((p->x[idx[2]] - p->x[idx[0]]) * (ym - p->y[idx[0]])) / (dy ? dy : 1);
    int long_left = xl_at_m < p->x[idx[1]];
    for (int part = 0; part < 2; part++) {
        Edge *sh = part ? &s2 : &s1;
        if (!(part ? h2 : h1)) continue;
        s32 rs = sh->y0, re = sh->y1;
        if (re > cv_h) re = cv_h;
        if (re > lng.y1) re = lng.y1;
        if (rs < 0) {                          /* skip rows above the canvas in one step */
            s32 k = -rs;
            sh->x += sh->dx * k; sh->u += sh->du * k; sh->v += sh->dv * k;
            rs = 0;
        }
        if (lng.y0 < rs) {
            s32 k = rs - lng.y0;
            lng.x += lng.dx * k; lng.u += lng.du * k; lng.v += lng.dv * k; lng.y0 = rs;
        }
        for (s32 row = rs; row < re; row++) {
            if (long_left) span(row, &lng, sh, tex_pix[p->p->tex], ws, wm, hm, shade);
            else span(row, sh, &lng, tex_pix[p->p->tex], ws, wm, hm, shade);
            sh->x += sh->dx; sh->u += sh->du; sh->v += sh->dv;
            lng.x += lng.dx; lng.u += lng.du; lng.v += lng.dv; lng.y0++;
        }
        if (re < sh->y1) {                     /* keep the long edge in step for part 2 */
            s32 k = sh->y1 - (re > rs ? re : rs);
            if (k > 0) { lng.x += lng.dx * k; lng.u += lng.du * k; lng.v += lng.dv * k; lng.y0 += k; }
        }
    }
}

/* ------------------------------------------------------------- building */
IWRAM_FN static int shade_for(s32 nx, s32 ny) {           /* world normal (any scale) */
    s32 len = (nx < 0 ? -nx : nx) + (ny < 0 ? -ny : ny);
    if (!len) return 1;
    s32 d = nx * SUN_X + ny * SUN_Y;              /* ~ Q12 cos * len */
    if (d > 1200 * len) return 0;
    if (d > -1400 * len) return 1;
    return 2;
}

/* screen position of the start corner (at ground level) of wall `aidx` */
IWRAM_CODE int bld_anchor(int bi, int aidx, s32 *ax, s32 *ay) {
    const BuildingDef *b = &town_buildings[bi];
    const MWall *w = &town_mesh[b->mesh].walls[aidx];
    s32 lx = w->x0, lz = w->z0, wx, wy;
    switch (b->rot) {
        case 0: wx = lx; wy = lz; break;
        case 1: wx = -lz; wy = lx; break;
        case 2: wx = -lx; wy = -lz; break;
        default: wx = lz; wy = -lx; break;
    }
    s32 X, Z;
    cam_xform((b->x + wx) << 8, (b->y + wy) << 8, &X, &Z);
    if (Z < NEAR_Z) return 0;
    s32 iz = recip28(Z);
    *ax = 120 + mul64sh(X, iz * FOCAL, 28);
    *ay = HORIZON + mul64sh(CAM_H * FOCAL, iz, 20);
    return 1;
}

IWRAM_CODE int bld_prepare(int bi, Canvas *cv, int max_slots) {
    const BuildingDef *b = &town_buildings[bi];
    const Mesh *m = &town_mesh[b->mesh];
    s32 Xo, Zo;
    s32 dxw = (b->x << 8) - cam.x, dyw = (b->y << 8) - cam.y;
    if (dxw > (900 << 8) || dxw < -(900 << 8) || dyw > (900 << 8) || dyw < -(900 << 8)) return 0;
    cam_xform(b->x << 8, b->y << 8, &Xo, &Zo);
    s32 R = m->radius << 8;
    if (Zo + R < NEAR_Z || Zo - R > FAR_Z) return 0;
    {
        s32 ax = Xo < 0 ? -Xo : Xo;
        if (ax - R > ((Zo + R) * 132) / FOCAL + (8 << 8)) return 0;
    }
    /* local axes -> camera space (Q12) */
    s32 exx, exy, ezx, ezy;    /* world dirs of local x and local z */
    switch (b->rot) {
        case 0: exx = 1; exy = 0; ezx = 0; ezy = 1; break;
        case 1: exx = 0; exy = 1; ezx = -1; ezy = 0; break;
        case 2: exx = -1; exy = 0; ezx = 0; ezy = -1; break;
        default: exx = 0; exy = -1; ezx = 1; ezy = 0; break;
    }
    s32 AX = exx * cam.cs + exy * cam.sn, AZ = exx * cam.sn - exy * cam.cs;
    s32 BX = ezx * cam.cs + ezy * cam.sn, BZ = ezx * cam.sn - ezy * cam.cs;
#define TX(lx, lz) (Xo + (((lx) * AX + (lz) * BX) >> 4))
#define TZ(lx, lz) (Zo + (((lx) * AZ + (lz) * BZ) >> 4))

    s32 bx0 = 9999, by0 = 9999, bx1 = -9999, by1 = -9999;
    int nw = 0, np = 0;

    int far = Zo > (230 << 8);                 /* LOD: drop posts and porch roofs far away */
    for (int i = 0; i < m->nwalls; i++) {
        const MWall *w = &m->walls[i];
        if (far && (w->flags & WALL_DOUBLE)) continue;
        s32 Xa = TX(w->x0, w->z0), Za = TZ(w->x0, w->z0);
        s32 Xb = TX(w->x1, w->z1), Zb = TZ(w->x1, w->z1);
        s32 ua = w->u0, ub = w->u1;

        s64 cr = (s64)Xa * Zb - (s64)Xb * Za;
        int shade;
        s32 lnx = -(w->z1 - w->z0), lnz = (w->x1 - w->x0);
        s32 wnx = lnx * exx + lnz * ezx, wny = lnx * exy + lnz * ezy;
        if (cr >= 0) {
            if (!(w->flags & WALL_DOUBLE)) continue;
            s32 t;
            t = Xa; Xa = Xb; Xb = t; t = Za; Za = Zb; Zb = t; t = ua; ua = ub; ub = t;
            shade = 2;
        } else {
            shade = shade_for(wnx, wny);
        }
        if (Za < NEAR_Z && Zb < NEAR_Z) continue;
        if (Za < NEAR_Z) {
            s32 t = ((NEAR_Z - Za) << 12) / (Zb - Za);
            Xa += mul64sh(Xb - Xa, t, 12); ua += mul64sh(ub - ua, t, 12); Za = NEAR_Z;
        } else if (Zb < NEAR_Z) {
            s32 t = ((NEAR_Z - Zb) << 12) / (Za - Zb);
            Xb += mul64sh(Xa - Xb, t, 12); ub += mul64sh(ua - ub, t, 12); Zb = NEAR_Z;
        }
        if (nw >= 40) break;
        WallJob *j = &wjobs[nw++];
        j->Xa = Xa; j->Za = Za; j->Xb = Xb; j->Zb = Zb; j->ua = ua; j->ub = ub; j->w = w; j->shade = shade;
        s32 iza = recip28(Za), izb = recip28(Zb);
        j->iza = iza; j->izb = izb;
        j->sxa16 = 120 * 16 + mul64sh(Xa, iza * FOCAL, 24);
        j->sxb16 = 120 * 16 + mul64sh(Xb, izb * FOCAL, 24);
        /* screen bbox */
        s32 sxa = j->sxa16 >> 4, sxb = j->sxb16 >> 4;
        s32 hy1 = (CAM_H - w->y1) * FOCAL, hy0 = (CAM_H - w->y0) * FOCAL;
        s32 ta = HORIZON + mul64sh(hy1, iza, 20), tb = HORIZON + mul64sh(hy1, izb, 20);
        s32 ga = HORIZON + mul64sh(hy0, iza, 20), gb = HORIZON + mul64sh(hy0, izb, 20);
        if (sxa < bx0) bx0 = sxa;
        if (sxb > bx1) bx1 = sxb;
        if (ta < by0) by0 = ta;
        if (tb < by0) by0 = tb;
        if (ga > by1) by1 = ga;
        if (gb > by1) by1 = gb;
        /* solid part of the wall: ground up to its top (less any cut-out parapet) */
        j->occ_top = -1;
        if (w->y0 == 0 && !(w->flags & WALL_DOUBLE)) {
            s32 hs = (CAM_H - (w->y1 - ((w->flags & WALL_CUTTOP) ? 9 : 0))) * FOCAL;
            s32 sa = HORIZON + mul64sh(hs, iza, 20), sb = HORIZON + mul64sh(hs, izb, 20);
            j->occ_top = sa > sb ? sa : sb;
            j->occ_bot = ga < gb ? ga : gb;
        }
    }
    for (int i = 0; i < m->npolys; i++) {
        const MPoly *p = &m->polys[i];
        if (far && (p->flags & WALL_DOUBLE)) continue;
        PolyJob *j = &pjobs[np];
        int ok = 1;
        s32 zs = 0;
        for (int k = 0; k < p->n; k++) {
            s32 X = TX(p->x[k], p->z[k]), Z = TZ(p->x[k], p->z[k]);
            if (Z < NEAR_Z) { ok = 0; break; }
            s32 iz = recip28(Z);
            j->x[k] = 120 * 16 + mul64sh(X, iz * FOCAL, 24);                  /* screen Q4 for now */
            j->y[k] = HORIZON * 16 + mul64sh((CAM_H - p->y[k]) * FOCAL, iz, 16);
            j->u[k] = p->u[k]; j->v[k] = p->v[k];
            zs += Z;
        }
        if (!ok) continue;
        s32 area = 0;
        for (int k = 0; k < p->n; k++) {
            int k2 = (k + 1) % p->n;
            area += ((j->x[k] >> 2) * (j->y[k2] >> 2) - (j->x[k2] >> 2) * (j->y[k] >> 2));
        }
        if (area <= 0) {
            if (!(p->flags & WALL_DOUBLE)) continue;
            j->shade = 2;
        } else {
            j->shade = (p->y[0] != p->y[1] || p->y[1] != p->y[2]) ? 1 : 0;
            if (p->n == 3 && p->y[0] == p->y[2]) j->shade = 0;
        }
        j->z = zs / p->n;
        j->p = p;
        for (int k = 0; k < p->n; k++) {
            s32 sx = j->x[k] >> 4, sy = j->y[k] >> 4;
            if (sx < bx0) bx0 = sx;
            if (sx > bx1) bx1 = sx;
            if (sy < by0) by0 = sy;
            if (sy > by1) by1 = sy;
        }
        if (++np >= 24) break;
    }
    if (!nw && !np) return 0;
    bx0 -= 1; by0 -= 1; bx1 += 2; by1 += 2;
    if (bx0 < 0) bx0 = 0;
    if (by0 < 0) by0 = 0;
    if (bx1 > SCREEN_W) bx1 = SCREEN_W;
    if (by1 > SCREEN_H) by1 = SCREEN_H;
    s32 w = bx1 - bx0, h = by1 - by0;
    if (w <= 0 || h <= 0) return 0;
    if (h < 5 && w < 12) return 0;                  /* a speck on the horizon */
    if (!shade_ready) {
        for (int i = 0; i < 48; i++) shade_iw[i] = town_shade[i];
        u32 off = 0;                  /* copy textures to EWRAM: faster random byte reads than ROM */
        for (int i = 0; i < N_TOWN_TEX; i++) {
            u32 sz = 1u << (town_tex[i].wshift + town_tex[i].hshift);
            if (off + sz <= sizeof(tex_ewram)) {
                const u32 *s = (const u32 *)town_tex[i].pix; u32 *d = (u32 *)(tex_ewram + off);
                for (u32 k = 0; k < sz / 4; k++) d[k] = s[k];
                tex_pix[i] = tex_ewram + off; off += sz;
            } else tex_pix[i] = town_tex[i].pix;
        }
        shade_ready = 1;
    }
    int s = (w <= 22 && h <= 26) ? 1 : 2;
    int cw = (w + s - 1) / s, ch = (h + s - 1) / s;           /* canvas pixels needed */
    int nx, ny, ow = 64, oh = 64;
    if (cw <= 64 && ch <= 64) {
        /* one sprite, smallest OBJ shape that fits: 16x16 .. 64x64 */
        static const u8 shapes[7][2] = {{16,16},{32,16},{16,32},{32,32},{64,32},{32,64},{64,64}};
        for (int k = 0; k < 7; k++)
            if (shapes[k][0] >= cw && shapes[k][1] >= ch) { ow = shapes[k][0]; oh = shapes[k][1]; break; }
        nx = ny = 1;
    } else {
        nx = (cw + 63) / 64; ny = (ch + 63) / 64;
    }
    int tiles = nx * ny * (ow / 8) * (oh / 8);
    if (tiles > max_slots) return 0;
    prep_nw = nw; prep_np = np; prep_bx0 = bx0; prep_by0 = by0; prep_s = s; prep_nx = nx; prep_ny = ny;
    prep_ow = ow; prep_oh = oh;
    cv->sx0 = bx0; cv->sy0 = by0; cv->scale = s; cv->nx = nx; cv->ny = ny; cv->ow = ow; cv->oh = oh;
    cv->bx1 = bx1; cv->by1 = by1;
    return tiles;
}

/* Occlusion: per screen column, the rows already hidden by a solid wall of a
   nearer building. Buildings are drawn nearest first, so one fully inside
   what is already covered can be skipped. */
IWRAM_CODE void occ_reset(void) {
    for (int x = 0; x < SCREEN_W + 2; x++) { occ_top[x] = 255; occ_bot[x] = 0; }
}

IWRAM_CODE int occ_hidden(const Canvas *cv) {
    int y0 = cv->sy0, y1 = cv->by1;
    for (int x = cv->sx0; x < cv->bx1; x++)
        if (occ_top[x] > y0 || occ_bot[x] < y1) return 0;
    return 1;
}

IWRAM_CODE void occ_add(void) {           /* walls of the building just prepared */
    for (int i = 0; i < prep_nw; i++) {
        const WallJob *j = &wjobs[i];
        if (j->occ_top < 0) continue;
        s32 t = j->occ_top, b = j->occ_bot;
        if (t < 0) t = 0;
        if (b > SCREEN_H) b = SCREEN_H;
        if (b - t < 4) continue;
        s32 x0 = (j->sxa16 >> 4) + 1, x1 = j->sxb16 >> 4;   /* inside the edges */
        if (x0 < 0) x0 = 0;
        if (x1 > SCREEN_W) x1 = SCREEN_W;
        for (s32 x = x0; x < x1; x++) {
            /* keep whichever span is taller; spans from one wall are never merged */
            if (occ_top[x] == 255 || (b - t) > (occ_bot[x] - occ_top[x])) { occ_top[x] = t; occ_bot[x] = b; }
        }
    }
}

/* draw the building prepared by bld_prepare into 4bpp tiles at `staging` */
IWRAM_CODE void bld_draw(u8 *staging) {
    int nw = prep_nw, np = prep_np, s = prep_s, nx = prep_nx, ny = prep_ny;
    s32 bx0 = prep_bx0, by0 = prep_by0;
    int ow = prep_ow, oh = prep_oh;
    cv_s = s; cv_sx0 = bx0; cv_sy0 = by0; cv_w = nx * ow; cv_h = ny * oh;
    if (cv_h > CROWS) cv_h = CROWS;           /* rows past the screen are never drawn */
    /* clear canvas */
    for (int r = 0; r < cv_h; r++) canvas_clear_row(canvas + r * CSTRIDE, cv_w);
    /* polys to canvas coords (Q4) */
    for (int i = 0; i < np; i++) {
        PolyJob *j = &pjobs[i];
        for (int k = 0; k < j->p->n; k++) {
            j->x[k] = (j->x[k] - bx0 * 16) >> (s - 1);
            j->y[k] = (j->y[k] - by0 * 16) >> (s - 1);
        }
    }
    /* painter's order, far to near */
    Face faces[64];
    int nf = 0;
    for (int i = 0; i < nw; i++) { faces[nf].key = (wjobs[i].Za + wjobs[i].Zb) >> 1; faces[nf].kind = 0; faces[nf].idx = i; nf++; }
    for (int i = 0; i < np; i++) { faces[nf].key = pjobs[i].z; faces[nf].kind = 1; faces[nf].idx = i; nf++; }
    for (int i = 1; i < nf; i++) {
        Face f = faces[i];
        int k = i - 1;
        while (k >= 0 && faces[k].key < f.key) { faces[k + 1] = faces[k]; k--; }
        faces[k + 1] = f;
    }
    for (int i = 0; i < nf; i++) {
        if (faces[i].kind == 0) draw_wall(&wjobs[faces[i].idx]);
        else {
            PolyJob *j = &pjobs[faces[i].idx];
            draw_tri(j, 0, 1, 2);
            if (j->p->n == 4) draw_tri(j, 0, 2, 3);
        }
    }
    /* pack 8bpp canvas -> 4bpp OBJ tiles (ARM asm, one row of 8x8 tiles per call) */
    u32 *out = (u32 *)staging;
    int tw = ow / 8;
    for (int sy = 0; sy < ny; sy++)
        for (int sx = 0; sx < nx; sx++)
            for (int ty = 0; ty < oh / 8; ty++) {
                int row0 = sy * oh + ty * 8;
                if (row0 >= cv_h) { for (int k = 0; k < tw * 8; k++) *out++ = 0; continue; }
                pack_row(out, canvas + row0 * CSTRIDE + sx * ow, tw);
                out += tw * 8;
            }
}

/* ------------------------------------------------------------- Mode 7 table */
typedef struct { u16 pa, pb, pc, pd; s32 x, y; } M7Line;

IWRAM_CODE void m7_build_iw(void *tp) {
    M7Line *t = (M7Line *)tp;
    s32 sn = cam.sn, cs = cam.cs;
    for (int y = HORIZON; y <= SCREEN_H; y++) {
        int dy = y - HORIZON + 1;
        s32 lam = (s32)((CAM_H * lut_recip[dy]) >> 16);       /* Q8 world units per pixel */
        s32 Z4 = (FOCAL * lam) >> 4;                           /* Q4 distance */
        s32 pa = (cs * lam) >> 12, pc = (sn * lam) >> 12;
        s32 x0 = cam.x + ((sn * Z4) >> 8) - pa * 120;
        s32 y0 = cam.y - ((cs * Z4) >> 8) - pc * 120;
        M7Line *l = &t[y];
        l->pa = (u16)pa; l->pb = 0; l->pc = (u16)pc; l->pd = 0;
        l->x = x0; l->y = y0;
    }
    for (int y = 0; y < HORIZON; y++) t[y] = t[HORIZON];
}

#ifdef PLATFORM_GBA
/* ------------------------------------------------------------- vblank IRQ
 * Repeating HBlank DMAs keep incrementing their source address, so they are
 * re-armed every vblank (even when the game loop runs slower than 60 Hz). */
typedef struct { u16 pa, pb, pc, pd; s32 x, y; } M7L;
IWRAM_CODE void vblank_isr(void) {
    M7L *t = (M7L *)m7_front;
    if (!t) return;
    REG_DMA0CNT = 0;
    REG_DMA2CNT = 0;
    REG_BG2PA = t[0].pa; REG_BG2PC = t[0].pc;
    REG_BG2X = t[0].x; REG_BG2Y = t[0].y;
    REG_DMA0SAD = (u32)&t[1];
    REG_DMA0DAD = 0x04000020;
    REG_DMA0CNT = 4 | DMA_DST_RELOAD | DMA_REPEAT | DMA_32 | DMA_HBLANK | DMA_ENABLE;
    REG_BLDY = haze[0];
    REG_DMA2SAD = (u32)&haze[1];
    REG_DMA2DAD = 0x04000054;
    REG_DMA2CNT = 1 | DMA_DST_FIXED | DMA_REPEAT | DMA_HBLANK | DMA_ENABLE;
}
#endif
