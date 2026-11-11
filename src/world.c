/* World objects -> hardware sprites: billboards, characters, effects, buildings. */
#include "game.h"
#include "world.h"

SprEnt spr_list[MAX_SPR];
int spr_count;

u8 bslot_stage[MAX_BSLOTS * 2048] EWRAM_BSS ALIGN4;
static u8 bslot_scratch[MAX_BSLOTS * 2048] EWRAM_BSS ALIGN4;
u8 bslot_dirty[MAX_BSLOTS];
typedef struct { u8 valid, slot, nx, ny, scale, aidx; u32 last, epoch; s16 offx, offy; } BCache;
static u32 cam_epoch;
#define BLD_BUDGET 45000
static BCache bcache[N_BUILDINGS];
void bld_invalidate(void) { for (int i = 0; i < N_BUILDINGS; i++) bcache[i].valid = 0; }
static s32 last_cam_x, last_cam_y; static u16 last_cam_yaw;
int bslots_used;
u16 bill_tile[N_BILL_DEFS];
u16 bill_kinv[N_BILL_DEFS];

FxEnt fx[MAX_FX];

IWRAM_CODE void spr_add(s32 depth, u16 a0, u16 a1, u16 a2) {
    if (spr_count >= MAX_SPR) return;
    SprEnt *e = &spr_list[spr_count++];
    e->depth = depth; e->a0 = a0; e->a1 = a1; e->a2 = a2;
}

void world_init(void) {
    u16 t = TILE_BILLS;
    for (int i = 0; i < N_BILL_DEFS; i++) {
        bill_tile[i] = t;
        bill_kinv[i] = (16 << 12) / bill_defs[i].k16;
        dma_copy32((u8 *)OBJ_VRAM + t * 32, bill_defs[i].tiles, bill_defs[i].bytes);
        t += bill_defs[i].bytes / 32;
    }
    dma_copy32((u8 *)OBJ_VRAM + FX_FLASH * 32, fx_flash, sizeof(fx_flash));
    dma_copy32((u8 *)OBJ_VRAM + FX_DUST * 32, fx_dust, sizeof(fx_dust));
    dma_copy32((u8 *)OBJ_VRAM + FX_SHADOW * 32, fx_shadow, sizeof(fx_shadow));
    dma_copy32((u8 *)OBJ_VRAM + FX_SPARK * 32, fx_spark, sizeof(fx_spark));
}

/* project a ground point: returns 0 when not visible */
IWRAM_CODE int project(s32 wx, s32 wy, Proj *p) {
    s32 dx = wx - cam.x, dy = wy - cam.y;
    if (dx > (800 << 8) || dx < -(800 << 8) || dy > (800 << 8) || dy < -(800 << 8)) return 0;
    s32 X, Z;
    cam_xform(wx, wy, &X, &Z);
    if (Z < (10 << 8) || Z > FAR_Z) return 0;
    s32 ax = X < 0 ? -X : X;
    if (ax > Z + (Z >> 1)) return 0;                    /* well outside the 75 degree view */
    s32 iz = recip28_t(Z);                              /* 2^20 / Z(units) */
    p->Z = Z;
    p->sx = 120 + (((X >> 6) * ((iz * FOCAL) >> 10)) >> 12);
    p->sy = HORIZON + ((CAM_H * FOCAL * iz) >> 20);
    p->scale = (iz * FOCAL) >> 12;                      /* Q8 screen px per world unit */
    return 1;
}

/* an affine, double-size sprite whose art bottom row (minus foot) sits on the ground point */
IWRAM_CODE void put_scaled(const Proj *p, s32 scale_q8, int w, int h, int shape, int size, u16 tile, int pal,
                int foot, int lift_px, int semi, s32 depth_bias) {
    if (scale_q8 < 5) return;
    if (scale_q8 > 1023) scale_q8 = 1023;
    int lvl = scale_to_level[scale_q8];
    s32 sq = scale_level_q8[lvl];
    s32 cx = p->sx;
    s32 cy = p->sy - (((h / 2 - foot) * sq) >> 8) - lift_px;
    s32 x = cx - w, y = cy - h;                         /* double-size box is 2w x 2h */
    if (x + 2 * w < 0 || x >= SCREEN_W || y + 2 * h < 0 || y >= SCREEN_H) return;
    u16 a0 = (y & 255) | (3 << 8) | (shape << 14) | (semi ? (1 << 10) : 0);
    u16 a1 = (x & 511) | (lvl << 9) | (size << 14);
    u16 a2 = tile | (1 << 10) | (pal << 12);
    spr_add(p->Z + depth_bias, a0, a1, a2);
}

IWRAM_CODE void draw_billboards(void) {
    Proj p;
    /* world_bills are sorted into 128x128 cells (see BILL_CELL in assets.h) */
    s32 fx = cam.sn, fy = -cam.cs;
    for (int c = 0; c < 64; c++) {
        s32 ccx = ((c & 7) * 128 + 64) << 8, ccy = ((c >> 3) * 128 + 64) << 8;
        s32 dx = (ccx - cam.x) >> 8, dy = (ccy - cam.y) >> 8;
        s32 along = (dx * fx + dy * fy) >> 12;
        if (along < -96 || along > 860) continue;            /* cell entirely behind / too far */
        s32 side = (dx * cam.cs + dy * cam.sn) >> 12;
        if (side < 0) side = -side;
        if (side > along + (along >> 1) + 140) continue;     /* outside the view cone */
        for (int i = bill_cell_start[c]; i < bill_cell_start[c + 1]; i++) {
        const BillPlace *b = &world_bills[i];
        if (!project(b->x << 8, b->y << 8, &p)) continue;
        if (bill_defs[b->type].k16 >= 32 && p.Z > (380 << 8)) continue;  /* small props fade out early */
        const BillDef *d = &bill_defs[b->type];
        s32 s = (p.scale * bill_kinv[b->type]) >> 12;
        put_scaled(&p, s, d->w, d->h, d->shape, d->size, bill_tile[b->type], d->pal, 2, 0, 0, 0);
        }
    }
}

IWRAM_CODE void draw_shadow(const Proj *p, s32 scale_q8, s32 depth) {
    put_scaled(p, scale_q8, 32, 16, 1, 2, FX_SHADOW, PAL_FX, 8, 0, 1, depth);
}

/* ------------------------------------------------------------- buildings */
typedef struct { s32 z; u8 i; } BOrd;

IWRAM_CODE void draw_buildings(void) {
    BOrd ord[N_BUILDINGS];
    int n = 0;
    for (int i = 0; i < N_BUILDINGS; i++) {
        const BuildingDef *b = &town_buildings[i];
        s32 dx = (b->x << 8) - cam.x, dy = (b->y << 8) - cam.y;
        if (dx > (800 << 8) || dx < -(800 << 8) || dy > (800 << 8) || dy < -(800 << 8)) continue;
        s32 X, Z;
        cam_xform(b->x << 8, b->y << 8, &X, &Z);
        if (Z < -(80 << 8) || Z > FAR_Z + (60 << 8)) continue;
        ord[n].z = Z; ord[n].i = i; n++;
    }
    for (int i = 1; i < n; i++) {           /* nearest first gets canvas slots first */
        BOrd o = ord[i]; int k = i - 1;
        while (k >= 0 && ord[k].z > o.z) { ord[k + 1] = ord[k]; k--; }
        ord[k + 1] = o;
    }
    /* Canvases are cached between frames in their OBJ slots. Each frame:
       - buildings that appeared or changed canvas size are always drawn,
       - the rest are refreshed most-stale-first (near ones age faster) until the
         CPU budget for buildings is spent; cached canvases are re-placed by
         following an anchor corner of the building,
       - only slots whose content changed are uploaded to VRAM at vblank. */
    Canvas cvs[N_BUILDINGS];
    u8 slot_of[N_BUILDINGS], drawn[N_BUILDINGS], fresh[N_BUILDINGS];
    s32 prio[N_BUILDINGS];
    s32 jx = cam.x - last_cam_x, jy = cam.y - last_cam_y; s16 jyaw = (s16)(cam.yaw - last_cam_yaw);
    int moved = jx || jy || jyaw;
    if (moved) cam_epoch++;
    if (jx > (24 << 8) || jx < -(24 << 8) || jy > (24 << 8) || jy < -(24 << 8) || jyaw > 2000 || jyaw < -2000)
        bld_invalidate();                               /* camera cut: nothing is reusable */
    u32 t0 = timer_cycles();
    int used_total = 0;
    /* 1. visibility, canvas size and slot assignment */
    u8 alloc[N_BUILDINGS];
    for (int k = 0; k < n; k++) {
        int bi = ord[k].i;
        drawn[k] = 0; slot_of[k] = 0xFF;
        if (used_total >= MAX_BSLOTS) continue;
        BCache *c = &bcache[bi];
        int used;
        if (c->valid && ((game_frame + bi) & 3) && c->nx * c->ny <= MAX_BSLOTS - used_total) {
            /* cheap path: keep the cached canvas geometry, re-check every 4th frame */
            cvs[k].nx = c->nx; cvs[k].ny = c->ny; cvs[k].scale = c->scale;
            used = c->nx * c->ny;
        } else {
            used = bld_prepare(bi, &cvs[k], MAX_BSLOTS - used_total);
            if (!used) continue;
        }
        int have = c->valid ? c->nx * c->ny : 0;
        int same = c->valid && c->nx == cvs[k].nx && c->ny == cvs[k].ny && c->scale == cvs[k].scale;
        int a = used > have ? used : have;
        if (used_total + a > MAX_BSLOTS) { a = used; have = 0; same = 0; c->valid = 0; }
        fresh[k] = !c->valid;
        alloc[k] = a;
        slot_of[k] = used_total;
        s32 zu = ord[k].z >> 8;
        int w8 = zu < 100 ? 8 : zu < 220 ? 4 : 2;
        if (fresh[k]) prio[k] = 0x7FFFFFFF;                       /* nothing to show yet: must draw */
        else if (!same) prio[k] = 0x40000000;                     /* resized: soon, but within budget */
        else prio[k] = c->epoch != cam_epoch ? (s32)(game_frame - c->last) * w8 + 1 : -1;
        used_total += a;
    }
    /* 2. cached canvases that changed slot: move them (via scratch, order-safe) */
    for (int k = 0; k < n; k++) {
        if (slot_of[k] == 0xFF || fresh[k]) continue;
        BCache *c = &bcache[ord[k].i];
        if (c->slot != slot_of[k])
            dma_copy32(bslot_scratch + slot_of[k] * 2048, bslot_stage + c->slot * 2048, c->nx * c->ny * 2048);
    }
    for (int k = 0; k < n; k++) {
        if (slot_of[k] == 0xFF || fresh[k]) continue;
        BCache *c = &bcache[ord[k].i];
        if (c->slot != slot_of[k]) {
            int used = c->nx * c->ny;
            dma_copy32(bslot_stage + slot_of[k] * 2048, bslot_scratch + slot_of[k] * 2048, used * 2048);
            for (int s = 0; s < used; s++) bslot_dirty[slot_of[k] + s] = 1;
        }
    }
    /* 3. draw: new ones always, then stalest first within the budget */
    for (;;) {
        int best = -1; s32 bp = 0;
        for (int k = 0; k < n; k++)
            if (slot_of[k] != 0xFF && !drawn[k] && prio[k] > bp) { bp = prio[k]; best = k; }
        if (best < 0) break;
        if (prio[best] != 0x7FFFFFFF && timer_cycles() - t0 >= BLD_BUDGET) break;
        Canvas tmp;
        int bi = ord[best].i;
        if (!bld_prepare(bi, &tmp, alloc[best])) { drawn[best] = 0; prio[best] = -1; continue; }
        bld_draw(bslot_stage + slot_of[best] * 2048);
        drawn[best] = 1;
        BCache *c = &bcache[bi];
        c->last = game_frame; c->epoch = cam_epoch;
        c->offx = tmp.sx0 - tmp.ax; c->offy = tmp.sy0 - tmp.ay; c->aidx = tmp.aidx;
        cvs[best] = tmp;
        c->nx = tmp.nx; c->ny = tmp.ny; c->scale = tmp.scale; c->valid = 1;
        for (int s = 0; s < tmp.nx * tmp.ny; s++) bslot_dirty[slot_of[best] + s] = 1;
    }
    /* 4. sprites */
    for (int k = 0; k < n; k++) {
        if (slot_of[k] == 0xFF) continue;
        int bi = ord[k].i;
        BCache *c = &bcache[bi];
        Canvas *cv = &cvs[k];
        if (!drawn[k]) {
            if (!c->valid) continue;                    /* fresh but could not be drawn */
            cv->nx = c->nx; cv->ny = c->ny; cv->scale = c->scale;   /* show the cached canvas */
            s32 ax, ay;                                 /* follow the building */
            if (bld_anchor(bi, c->aidx, &ax, &ay)) { cv->sx0 = ax + c->offx; cv->sy0 = ay + c->offy; }
        }
        c->valid = 1; c->slot = slot_of[k];
        s32 depth = ord[k].z;
        for (int j = 0; j < cv->ny; j++)
            for (int i = 0; i < cv->nx; i++) {
                int slot = slot_of[k] + j * cv->nx + i;
                u16 tile = TILE_BSLOT + slot * 64;
                if (cv->scale == 1) {
                    s32 x = cv->sx0 + i * 64, y = cv->sy0 + j * 64;
                    spr_add(depth, (y & 255) | (0 << 14), (x & 511) | (3 << 14), tile | (1 << 10) | (PAL_TOWN << 12));
                } else {
                    s32 x = cv->sx0 + i * 128, y = cv->sy0 + j * 128;
                    spr_add(depth, (y & 255) | (3 << 8) | (0 << 14), (x & 511) | (0 << 9) | (3 << 14),
                            tile | (1 << 10) | (PAL_TOWN << 12));
                }
            }
    }
    for (int i = 0; i < N_BUILDINGS; i++) {          /* forget buildings that were not drawn */
        int seen = 0;
        for (int k = 0; k < n; k++) if (ord[k].i == i && slot_of[k] != 0xFF) seen = 1;
        if (!seen) bcache[i].valid = 0;
    }
    last_cam_x = cam.x; last_cam_y = cam.y; last_cam_yaw = cam.yaw;
    bslots_used = used_total;
}

/* ------------------------------------------------------------- effects */
void fx_spawn(s32 x, s32 y, int type, int h) {
    for (int i = 0; i < MAX_FX; i++)
        if (!fx[i].t) {
            fx[i].x = x; fx[i].y = y; fx[i].type = type; fx[i].t = type == FXT_DUST ? 24 : 10; fx[i].h = h;
            return;
        }
}

void fx_update(void) {
    for (int i = 0; i < MAX_FX; i++) if (fx[i].t) fx[i].t--;
}

void draw_fx(void) {
    Proj p;
    for (int i = 0; i < MAX_FX; i++) {
        FxEnt *f = &fx[i];
        if (!f->t || !project(f->x, f->y, &p)) continue;
        s32 s = p.scale >> 1;                              /* 2 art px per unit */
        if (f->type == FXT_DUST) {
            int fr = 2 - f->t / 9;
            if (fr < 0) fr = 0;
            put_scaled(&p, s, 16, 16, 0, 1, FX_DUST + fr * 4, PAL_FX, 1, 0, 0, -(4 << 8));
        } else {
            s32 lift = (f->h * p.scale) >> 8;
            put_scaled(&p, s, 16, 16, 0, 1, FX_SPARK, PAL_FX, 8, lift, 0, -(6 << 8));
        }
    }
}

/* ------------------------------------------------------------- collision */
IWRAM_CODE int blocked(s32 x, s32 y, s32 r) {
    s32 ux = x >> 8, uy = y >> 8;
    if (ux < 16 || uy < 16 || ux > 1008 || uy > 1008) return 1;
    for (int i = 0; i < N_BUILDINGS; i++) {
        const BuildingDef *b = &town_buildings[i];
        if (ux > b->bx0 - r && ux < b->bx1 + r && uy > b->by0 - r && uy < b->by1 + r) return 1;
    }
    int cx0 = (ux - 24) >> 7, cx1 = (ux + 24) >> 7, cy0 = (uy - 24) >> 7, cy1 = (uy + 24) >> 7;
    if (cx0 < 0) cx0 = 0;
    if (cy0 < 0) cy0 = 0;
    if (cx1 > 7) cx1 = 7;
    if (cy1 > 7) cy1 = 7;
    for (int cy = cy0; cy <= cy1; cy++)
        for (int cx = cx0; cx <= cx1; cx++) {
            int c = cy * 8 + cx;
            for (int i = bill_cell_start[c]; i < bill_cell_start[c + 1]; i++) {
                const BillPlace *b = &world_bills[i];
                int rad = bill_defs[b->type].radius;
                if (!rad) continue;
                s32 dx = ux - b->x, dy = uy - b->y;
                if (dx > 20 || dx < -20 || dy > 20 || dy < -20) continue;
                rad += r - 2;
                if (dx * dx + dy * dy < rad * rad) return 1;
            }
        }
    return 0;
}

/* first building hit along a segment (Q8 coords), returns fraction 0..256 or 256 */
int ray_block(s32 x0, s32 y0, s32 x1, s32 y1) {
    /* only test buildings whose box overlaps the segment's bounding box */
    s32 ax = x0 >> 8, ay = y0 >> 8, bx = x1 >> 8, by = y1 >> 8;
    s32 mnx = ax < bx ? ax : bx, mxx = ax < bx ? bx : ax, mny = ay < by ? ay : by, mxy = ay < by ? by : ay;
    u8 cand[N_BUILDINGS]; int nc = 0;
    for (int i = 0; i < N_BUILDINGS; i++) {
        const BuildingDef *b = &town_buildings[i];
        if (b->bx1 < mnx || b->bx0 > mxx || b->by1 < mny || b->by0 > mxy) continue;
        cand[nc++] = i;
    }
    if (!nc) return 256;
    for (int k = 1; k <= 32; k++) {
        s32 ux = (x0 + (((x1 - x0) >> 5) * k)) >> 8, uy = (y0 + (((y1 - y0) >> 5) * k)) >> 8;
        for (int c = 0; c < nc; c++) {
            const BuildingDef *b = &town_buildings[cand[c]];
            if (ux >= b->bx0 && ux < b->bx1 && uy >= b->by0 && uy < b->by1) return k * 8;
        }
    }
    return 256;
}
