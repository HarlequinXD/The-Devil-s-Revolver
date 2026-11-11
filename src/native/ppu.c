/* Native (Android / desktop) display compositor for The Devil's Revolver.
 *
 * On the GBA the game builds its picture out of hardware layers: a sky
 * background, a HUD background, the Mode 7 ground (affine BG2 whose
 * parameters change every scanline), up to 128 sprites (scaled with affine
 * matrices) and blending for the distance haze and sprite shadows.
 *
 * The native build keeps exactly the same game code, which writes the same
 * "video memory" (here plain arrays). This file then draws those layers into
 * an RGBA image in C - no CPU emulation involved, just the game's own scene
 * description turned into pixels. */
#include <string.h>
#include "../gba.h"

u8 plat_io[0x400] __attribute__((aligned(4)));
u16 plat_vram[0xC000] __attribute__((aligned(4)));
u16 plat_pal[512] __attribute__((aligned(4)));
u16 plat_oam[512] __attribute__((aligned(4)));
volatile u32 irq_vblank_count;

extern void *m7_front;
extern u16 haze[];

typedef struct { u16 pa, pb, pc, pd; s32 x, y; } M7L;

#define IO16(o) (*(u16 *)(plat_io + (o)))

static const u8 obj_dims[3][4][2] = {
    {{8, 8}, {16, 16}, {32, 32}, {64, 64}},   /* square */
    {{16, 8}, {32, 8}, {32, 16}, {64, 32}},   /* wide */
    {{8, 16}, {8, 32}, {16, 32}, {32, 64}},   /* tall */
};

static inline u32 rgb_of(u16 c) {
    u32 r = c & 31, g = (c >> 5) & 31, b = (c >> 10) & 31;
    r = (r << 3) | (r >> 2); g = (g << 3) | (g >> 2); b = (b << 3) | (b >> 2);
    return 0xFF000000u | (b << 16) | (g << 8) | r;
}

/* sprites on one scanline: palette index (OBJ palette, 0 = none), priority, semi-transparent */
static u16 ocol[240];
static u8 oprio[240], osemi[240];

static void obj_line(int y) {
    const u8 *ovram = (const u8 *)plat_vram + 0x10000;
    memset(ocol, 0, sizeof(ocol));
    for (int i = 0; i < 128; i++) {
        u16 a0 = plat_oam[i * 4], a1 = plat_oam[i * 4 + 1], a2 = plat_oam[i * 4 + 2];
        int affine = (a0 >> 8) & 1, dbl = (a0 >> 9) & 1;
        if (!affine && dbl) continue;                       /* hidden */
        int shape = a0 >> 14, size = a1 >> 14;
        if (shape == 3) continue;
        int w = obj_dims[shape][size][0], h = obj_dims[shape][size][1];
        int bw = w << (affine && dbl), bh = h << (affine && dbl);
        int iy = (y - (a0 & 255)) & 255;
        if (iy >= bh) continue;
        int x0 = a1 & 511;
        if (x0 >= 240) x0 -= 512;
        int mode = (a0 >> 10) & 3;
        int tile0 = a2 & 1023, bank = (a2 >> 12) * 16, prio = (a2 >> 10) & 3;
        int pa = 256, pb = 0, pc = 0, pd = 256;
        if (affine) {
            int m = (a1 >> 9) & 31;
            pa = (s16)plat_oam[m * 16 + 3]; pb = (s16)plat_oam[m * 16 + 7];
            pc = (s16)plat_oam[m * 16 + 11]; pd = (s16)plat_oam[m * 16 + 15];
        }
        int hflip = !affine && (a1 & 0x1000), vflip = !affine && (a1 & 0x2000);
        int xs = x0 < 0 ? 0 : x0, xe = x0 + bw > 240 ? 240 : x0 + bw;
        for (int x = xs; x < xe; x++) {
            if (ocol[x]) continue;
            int tx, ty;
            if (affine) {
                int dx = x - x0 - bw / 2, dy = iy - bh / 2;
                tx = ((pa * dx + pb * dy) >> 8) + w / 2;
                ty = ((pc * dx + pd * dy) >> 8) + h / 2;
                if (tx < 0 || ty < 0 || tx >= w || ty >= h) continue;
            } else {
                tx = hflip ? w - 1 - (x - x0) : x - x0;
                ty = vflip ? h - 1 - iy : iy;
            }
            int t = tile0 + (ty >> 3) * (w >> 3) + (tx >> 3);
            u8 b = ovram[((t & 1023) << 5) + ((ty & 7) << 2) + ((tx & 7) >> 1)];
            int n = (tx & 1) ? b >> 4 : b & 15;
            if (!n) continue;
            ocol[x] = bank + n; oprio[x] = prio; osemi[x] = mode == 1;
        }
    }
}

/* regular 4bpp text background pixel (palette index, 0 = transparent) */
static inline int text_px(u16 cnt, int px, int py) {
    int size = cnt >> 14;
    int wpx = (size & 1) ? 512 : 256, hpx = (size & 2) ? 512 : 256;
    px &= wpx - 1; py &= hpx - 1;
    int tx = px >> 3, ty = py >> 3;
    int sb = (cnt >> 8) & 31;
    sb += tx >> 5;
    if (size == 3) sb += (ty >> 5) * 2;
    else if (size == 2) sb += ty >> 5;
    u16 e = plat_vram[sb * 0x400 + (ty & 31) * 32 + (tx & 31)];
    int ix = px & 7, iy = py & 7;
    if (e & 0x400) ix = 7 - ix;
    if (e & 0x800) iy = 7 - iy;
    const u8 *cb = (const u8 *)plat_vram + ((cnt >> 2) & 3) * 0x4000;
    u8 b = cb[((e & 1023) << 5) + (iy << 2) + (ix >> 1)];
    int n = (ix & 1) ? b >> 4 : b & 15;
    return n ? ((e >> 12) << 4) + n : 0;
}

static inline u16 brighten(u16 c, int evy) {
    int r = c & 31, g = (c >> 5) & 31, b = (c >> 10) & 31;
    r += ((31 - r) * evy) >> 4; g += ((31 - g) * evy) >> 4; b += ((31 - b) * evy) >> 4;
    return (u16)(r | (g << 5) | (b << 10));
}

static inline u16 alpha(u16 a, u16 b, int eva, int evb) {
    int r = ((a & 31) * eva + (b & 31) * evb) >> 4;
    int g = (((a >> 5) & 31) * eva + ((b >> 5) & 31) * evb) >> 4;
    int bl = (((a >> 10) & 31) * eva + ((b >> 10) & 31) * evb) >> 4;
    if (r > 31) r = 31;
    if (g > 31) g = 31;
    if (bl > 31) bl = 31;
    return (u16)(r | (g << 5) | (bl << 10));
}

/* Draw the current frame into `out` (240x160, RGBA8888 as 0xAABBGGRR). */
void ppu_render(u32 *out) {
    u16 disp = IO16(0x00);
    if (disp & 0x80) { for (int i = 0; i < 240 * 160; i++) out[i] = 0xFFFFFFFF; return; }
    u16 bgcnt[3] = {IO16(0x08), IO16(0x0A), IO16(0x0C)};
    int hofs[2] = {IO16(0x10) & 511, IO16(0x14) & 511}, vofs[2] = {IO16(0x12) & 511, IO16(0x16) & 511};
    int w0t = IO16(0x44) >> 8, w0b = IO16(0x44) & 255;
    u16 winin = IO16(0x48), winout = IO16(0x4A);
    u16 bldcnt = IO16(0x50), bldalpha = IO16(0x52);
    int eva = bldalpha & 31, evb = (bldalpha >> 8) & 31;
    if (eva > 16) eva = 16;
    if (evb > 16) evb = 16;
    int bmode = (bldcnt >> 6) & 3;
    const M7L *m7 = (const M7L *)m7_front;
    const u8 *gmap = (const u8 *)plat_vram + ((bgcnt[2] >> 8) & 31) * 0x800;
    const u8 *gchr = (const u8 *)plat_vram + ((bgcnt[2] >> 2) & 3) * 0x4000;
    int gwrap = (bgcnt[2] >> 13) & 1;
    u16 backdrop = plat_pal[0];
    for (int y = 0; y < 160; y++) {
        int inwin = (disp & 0x2000) && y >= w0t && y < w0b;
        int mask = (disp & 0x2000) ? (inwin ? winin : winout) & 0x3F : 0x3F;
        int en = ((disp >> 8) & 0x1F) & mask;              /* bits 0..3 BG, bit 4 OBJ */
        int fx = (mask >> 5) & 1;
        int evy = haze[y] > 16 ? 16 : haze[y];
        if (en & 0x10) obj_line(y);
        s32 gx = 0, gy = 0; int gpa = 0, gpc = 0;
        if ((en & 4) && m7) { gx = m7[y].x; gy = m7[y].y; gpa = (s16)m7[y].pa; gpc = (s16)m7[y].pc; }
        u32 *row = out + y * 240;
        for (int x = 0; x < 240; x++) {
            /* gather opaque layer pixels as (priority, layer id, colour) */
            u16 col1 = backdrop, col2 = backdrop;
            int lay1 = 5, lay2 = 5, pr1 = 4, pr2 = 4;
#define CONSIDER(pr, lay, c) do { int p_ = (pr) * 2 + ((lay) == 4 ? 0 : 1); \
                if (p_ < pr1) { pr2 = pr1; lay2 = lay1; col2 = col1; pr1 = p_; lay1 = (lay); col1 = (c); } \
                else if (p_ < pr2) { pr2 = p_; lay2 = (lay); col2 = (c); } } while (0)
            pr1 = pr2 = 99;
            if (en & 1) { int n = text_px(bgcnt[0], x + hofs[0], y + vofs[0]); if (n) CONSIDER(bgcnt[0] & 3, 0, plat_pal[n]); }
            if (en & 2) { int n = text_px(bgcnt[1], x + hofs[1], y + vofs[1]); if (n) CONSIDER(bgcnt[1] & 3, 1, plat_pal[n]); }
            if (en & 4) {
                s32 px = (gx + gpa * x) >> 8, py = (gy + gpc * x) >> 8;
                int ok = 1;
                if (gwrap) { px &= 1023; py &= 1023; }
                else if (px < 0 || py < 0 || px >= 1024 || py >= 1024) ok = 0;
                if (ok) {
                    u8 t = gmap[(py >> 3) * 128 + (px >> 3)];
                    u8 n = gchr[t * 64 + (py & 7) * 8 + (px & 7)];
                    if (n) CONSIDER(bgcnt[2] & 3, 2, plat_pal[n]);
                }
            }
            if ((en & 0x10) && ocol[x]) CONSIDER(oprio[x], 4, plat_pal[256 + ocol[x]]);
            if (pr1 == 99) { col1 = backdrop; lay1 = 5; }
            if (pr2 == 99) { col2 = backdrop; lay2 = 5; }
            u16 c = col1;
            if (fx) {
                if (lay1 == 4 && osemi[x] && ((bldcnt >> (8 + lay2)) & 1))
                    c = alpha(col1, col2, eva, evb);
                else if (bmode == 2 && ((bldcnt >> lay1) & 1))
                    c = brighten(col1, evy);
                else if (bmode == 1 && ((bldcnt >> lay1) & 1) && ((bldcnt >> (8 + lay2)) & 1))
                    c = alpha(col1, col2, eva, evb);
            }
            row[x] = rgb_of(c);
        }
    }
}
