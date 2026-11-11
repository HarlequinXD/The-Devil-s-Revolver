/* The Devil's Revolver - game loop and display (GBA, and native Android via ppu.c)
 *
 * Display: Mode 1
 *   BG0  regular 4bpp  sky panorama (scrolls with camera yaw)
 *   BG1  regular 4bpp  HUD text
 *   BG2  affine  8bpp  Mode 7 desert, BG2 params rewritten every scanline by HBlank DMA
 *   OBJ               billboards (hardware scaled), 8-way characters, software-rendered buildings
 * Window 0 keeps the ground below the horizon; BLDY (also HBlank DMA) adds distance haze.
 */
#include "game.h"
#include "world.h"

typedef struct { u16 pa, pb, pc, pd; s32 x, y; } M7Line;

static M7Line m7tab[2][SCREEN_H + 1] EWRAM_BSS ALIGN4;
u16 haze[SCREEN_H + 1] ALIGN4;
void *m7_front;
static ObjAttr oam_shadow[128] ALIGN4;
static int m7_back;

u32 game_frame;
int title_mode;
u32 render_count;
u32 perf_parts[6];
u32 perf_cycles;
int show_perf;
extern u16 hud_map[];
extern int hud_dirty;

static void video_init(void) {
    REG_DISPCNT = 0x80;                                     /* forced blank while loading */
#ifdef PLATFORM_GBA
    REG_WAITCNT = 0x4317;                                   /* faster ROM access + prefetch */
#endif
    dma_copy32(PAL_BG, bg_palette, 512);
    dma_copy32(PAL_OBJ, obj_palette, 512);
    dma_copy32(CHARBLOCK(0), ground_tiles, sizeof(ground_tiles));
    dma_copy32(SCREENBLOCK(16), ground_map, sizeof(ground_map));
    dma_copy32(CHARBLOCK(1), sky_tiles, sizeof(sky_tiles));
    dma_copy32((u8 *)CHARBLOCK(1) + N_SKY_TILES * 32, font_tiles, sizeof(font_tiles));
    for (int y = 0; y < 32; y++) {                          /* 512x256 map = two 32x32 blocks */
        dma_copy32(SCREENBLOCK(24) + y * 32, sky_map + y * 64, 64);
        dma_copy32(SCREENBLOCK(25) + y * 32, sky_map + y * 64 + 32, 64);
    }
    REG_BG0CNT = 3 | (1 << 2) | (24 << 8) | (1 << 14);      /* sky: prio 3, 512x256 */
    REG_BG1CNT = 0 | (1 << 2) | (26 << 8);                  /* HUD: prio 0 */
    REG_BG2CNT = 2 | (0 << 2) | (16 << 8) | (1 << 13) | (3 << 14); /* ground: 1024x1024 wrap */
    REG_BG0VOFS = 64 - HORIZON;
    REG_WIN0H = (0 << 8) | 240;
    REG_WIN0V = (HORIZON << 8) | 160;
    REG_WININ = 0x36;                                       /* inside: BG1 BG2 OBJ + effects */
    REG_WINOUT = 0x33;                                      /* sky region: BG0 BG1 OBJ + effects */
    REG_BLDCNT = (1 << 2) | (2 << 6) | (1 << 10);           /* brighten BG2 (haze); BG2 = 2nd target for shadows */
    REG_BLDALPHA = (0) | (11 << 8);
    /* haze per scanline: fade the far ground into the horizon colour */
    for (int y = 0; y <= SCREEN_H; y++) {
        int v = 12;
        if (y >= HORIZON) {
            int dy = y - HORIZON + 1;
            int z = CAM_H * FOCAL / dy;
            v = z < 240 ? 0 : (z - 240) * 11 / 700;
            if (v > 11) v = 11;
            if (dy < 2) v = 12;
        }
        haze[y] = v;
    }
    /* OBJ affine matrices: 31 scale levels + identity */
    for (int i = 0; i < 128; i++) { oam_shadow[i].attr0 = 0x200; oam_shadow[i].attr1 = 0; oam_shadow[i].attr2 = 0; }
    for (int m = 0; m < 32; m++) {
        u16 pa = m == 0 ? 128 : 256;                 /* 0: 2x for building canvases */
        oam_shadow[m * 4 + 0].fill = pa; oam_shadow[m * 4 + 1].fill = 0;
        oam_shadow[m * 4 + 2].fill = 0;  oam_shadow[m * 4 + 3].fill = pa;
    }
#ifdef PLATFORM_GBA
    /* cycle counter for the CPU meter */
    REG_TM0CNT = 0; REG_TM1CNT = 0; REG_TM0D = 0; REG_TM1D = 0;
    REG_TM1CNT = 0x84; REG_TM0CNT = 0x80;
    /* vblank interrupt */
    REG_DISPSTAT = 1 << 3;
    REG_IE = 1;
    REG_IME = 1;
#endif
}

INLINE u32 cycles(void) {
    u32 hi = REG_TM1D, lo = REG_TM0D, hi2 = REG_TM1D;
    if (hi != hi2) lo = REG_TM0D;
    return (hi2 << 16) | lo;
}

#define NBUCKET 256
static u8 bucket_head[NBUCKET] ALIGN4;
static u8 spr_next[MAX_SPR];

/* Affine matrices: 0 is fixed at 2x (building canvases), 1..31 are handed
   out each frame to the exact scales sprites ask for, nearest sprites first.
   Scales within ~0.4% share a matrix (invisible); once all 31 are taken the
   remaining (far, small) sprites use the closest one. */
static u16 mat_pa[32];
static int nmat;

IWRAM_CODE static int matrix_for(u16 pa) {
    s32 tol = (pa >> 8) + 1;
    for (int k = nmat - 1, lim = nmat > 6 ? nmat - 6 : 1; k >= lim; k--) {   /* recent ones first */
        s32 d = (s32)mat_pa[k] - pa;
        if (d <= tol && d >= -tol) return k;
    }
    if (nmat < 32) { mat_pa[nmat] = pa; return nmat++; }
    int best = 1; s32 bd = 0x7FFFFFFF;
    for (int k = 1; k < 32; k++) {
        s32 d = (s32)mat_pa[k] - pa;
        if (d < 0) d = -d;
        if (d < bd) { bd = d; best = k; }
    }
    return best;
}

IWRAM_CODE static void build_oam(void) {
    nmat = 1;
    /* bucket sort by depth (2 world units per bucket), nearest first:
       a lower OAM index is drawn on top */
    dma_fill32(bucket_head, 0xFFFFFFFF, NBUCKET);
    for (int i = spr_count - 1; i >= 0; i--) {
        s32 b = spr_list[i].depth >> 10;
        if (b < 0) b = 0;
        if (b >= NBUCKET) b = NBUCKET - 1;
        spr_next[i] = bucket_head[b];
        bucket_head[b] = i;
    }
    int n = 0;
    for (int b = 0; b < NBUCKET && n < 128; b++)
        for (int i = bucket_head[b]; i != 0xFF && n < 128; i = spr_next[i]) {
            u16 a1 = spr_list[i].a1, pa = spr_list[i].pa;
            if (pa) a1 |= matrix_for(pa) << 9;
            oam_shadow[n].attr0 = spr_list[i].a0;
            oam_shadow[n].attr1 = a1;
            oam_shadow[n].attr2 = spr_list[i].a2;
            n++;
        }
    for (int k = 1; k < nmat; k++) {
        oam_shadow[k * 4 + 0].fill = mat_pa[k];
        oam_shadow[k * 4 + 3].fill = mat_pa[k];
    }
    for (int i = n; i < 128; i++) oam_shadow[i].attr0 = 0x200;
}

void game_present(void) {
    M7Line *t = m7tab[m7_back];
    m7_front = t;
#ifdef PLATFORM_GBA
    REG_DMA0CNT = 0;
    REG_DMA2CNT = 0;
    REG_BG2PA = t[0].pa; REG_BG2PB = 0; REG_BG2PC = t[0].pc; REG_BG2PD = 0;
    REG_BG2X = t[0].x; REG_BG2Y = t[0].y;
    REG_DMA0SAD = (u32)&t[1];
    REG_DMA0DAD = 0x04000020;
    REG_DMA0CNT = 4 | DMA_DST_RELOAD | DMA_REPEAT | DMA_32 | DMA_HBLANK | DMA_ENABLE;
    REG_BLDY = haze[0];
    REG_DMA2SAD = (u32)&haze[1];
    REG_DMA2DAD = 0x04000054;
    REG_DMA2CNT = 1 | DMA_DST_FIXED | DMA_REPEAT | DMA_HBLANK | DMA_ENABLE;
#endif
    m7_back ^= 1;

    dma_copy32(OAM_MEM, oam_shadow, sizeof(oam_shadow));
    REG_BG0HOFS = (cam.yaw >> 6) & 511;
    if (player_frame_src) dma_copy32((u8 *)OBJ_VRAM + TILE_PLAYER * 32, player_frame_src, 2048);
    if (horse_frame_src) dma_copy32((u8 *)OBJ_VRAM + TILE_HORSE * 32, horse_frame_src, 2048);
    for (int i = 0; i < MAX_NPC; i++)
        if (npc_frame_src[i]) dma_copy32((u8 *)OBJ_VRAM + (TILE_NPC + i * 32) * 32, npc_frame_src[i], npc_frame_bytes[i]);
    if (bslots_used) dma_copy32((u8 *)OBJ_VRAM + TILE_BSLOT * 32, bslot_stage, bslots_used * 32);
    if (hud_dirty) { dma_copy32(SCREENBLOCK(26), hud_map, 32 * 20 * 2); hud_dirty = 0; }
}

static void render_frame(void) {
    u32 t = cycles(), t2;
    spr_count = 0;
    m7_build_iw(m7tab[m7_back]);
    t2 = cycles(); perf_parts[0] = t2 - t; t = t2;
    draw_buildings();
    t2 = cycles(); perf_parts[1] = t2 - t; t = t2;
    actors_draw();
    t2 = cycles(); perf_parts[2] = t2 - t; t = t2;
    draw_billboards();
    t2 = cycles(); perf_parts[3] = t2 - t; t = t2;
    draw_fx();
    build_oam();
    t2 = cycles(); perf_parts[4] = t2 - t; t = t2;
}

/* ------------------------------------------------------------- game state machine */
static int title;
static u16 prev_keys;
static u32 orbit;

void game_init(void) {
    video_init();
    world_init();
    actors_init();
    hud_init();
    title = 1;
    title_mode = 1;
    prev_keys = 0;
    orbit = 0;
    render_frame();
    game_present();
    REG_DISPCNT = 1 | (1 << 6) | (1 << 8) | (1 << 9) | (1 << 10) | (1 << 12) | (1 << 13);
}

/* advance the game by `steps` 60 Hz ticks and render one frame */
void game_tick(u16 keys, int steps) {
    u32 t0 = cycles();
    u16 pressed = keys & ~prev_keys;
    prev_keys = keys;
    if (steps < 1) steps = 1;
    if (steps > 3) steps = 3;
    if (title) {
        /* attract mode: a slow dolly up the main street */
        orbit += steps;
        s32 along = (orbit * 40) % (560 << 8);
        cam.yaw = (u16)(isin(orbit * 90) >> 2);
        cam.sn = isin(cam.yaw); cam.cs = icos(cam.yaw);
        cam.x = (512 << 8) + (isin(orbit * 60) << 2);
        cam.y = (820 << 8) - along;
        for (int s = 0; s < steps; s++) { game_frame++; actors_update(0, 0); }
        if (pressed & KEY_START) { title = 0; title_mode = 0; actors_init(); bld_invalidate(); }
    } else {
        u32 tl = cycles();
        for (int s = 0; s < steps; s++) {
            game_frame++;
            actors_update(keys, s == 0 ? pressed : 0);
            camera_follow(0);
        }
        perf_parts[5] = (cycles() - tl) / steps;
        if (pressed & KEY_START) {
            if (player.health <= 0) { actors_init(); bld_invalidate(); }
            else show_perf ^= 1;
        }
    }
    render_frame();
    render_count++;
    hud_update(title);
    perf_cycles = cycles() - t0;
}

#ifdef PLATFORM_GBA
int main(void) {
    game_init();
    u32 last_vb = irq_vblank_count;
    u32 last_present = irq_vblank_count;
    while (1) {
        u16 keys = ~REG_KEYINPUT & 0x3FF;
        u32 vb = irq_vblank_count;
        int steps = (int)(vb - last_vb);
        last_vb = vb;
        game_tick(keys, steps);
        /* locked 30 fps: buildings are fully re-rendered in 3D every frame */
        do { vblank_wait(); } while ((irq_vblank_count - last_present) < 2);
        last_present = irq_vblank_count;
        game_present();
    }
}
#endif
