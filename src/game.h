/* The Devil's Revolver - shared engine definitions */
#ifndef GAME_H
#define GAME_H
#include "gba.h"
#include "assets/assets.h"

/* Free roam: no outlaws, no shooting - just explore the town and desert.
   Set to 0 to bring back the bounty-hunting gameplay. */
/* 0: moving sprites (player, outlaws, gulls, dust, shadows)
   stay one size at any distance - the size they have at the chase-camera
   distance - instead of shrinking and growing. Scenery keeps perspective. */
#define SPRITE_SCALING 1
#if SPRITE_SCALING
#define ACTOR_SCALE(s) (s)
#else
#define ACTOR_SIZE_PCT 70  /* size of moving sprites vs their old chase-distance size */
#define ACTOR_SCALE(s) ((((((1 << 20) / CAM_DIST) * FOCAL) >> 12) * ACTOR_SIZE_PCT) / 100)
#endif
/* palms and hibiscus: size vs their art scale */
#define FLORA_SIZE_PCT  100
#define FREE_ROAM 1

/* ---- projection (must match tools/common.py) ---- */
#define HORIZON   GEN_HORIZON     /* first ground scanline */
#define FOCAL     GEN_FOCAL       /* focal length in pixels */
#define CAM_H     GEN_CAM_H       /* camera height in world units */
#define CAM_DIST  40              /* camera distance behind the player */
#define NEAR_Z    (6 << 8)        /* near plane, Q8 world units */
#define FAR_Z     (760 << 8)      /* objects beyond this are not drawn */
#define BLD_FAR_Z (560 << 8)      /* buildings beyond this are left to the haze */
#define SCREEN_W  240
#define SCREEN_H  160

/* angles are 16-bit (65536 = full turn), trig tables are Q12 */
INLINE s32 isin(u32 a) { return lut_sin[(a >> 7) & 511]; }
INLINE s32 icos(u32 a) { return lut_sin[((a >> 7) + 128) & 511]; }

/* 2^28 / x via the reciprocal table (~11 bits precision); x > 0 */
INLINE s32 recip28_t(s32 x) {
    u32 v = (u32)x; int sh = 0;
    while (v >= 4096) { v >>= 1; sh++; }
    if (!v) v = 1;
    return (s32)((lut_recip[v] << 4) >> sh);
}

/* free-running cycle counter (timers 0+1 cascaded, set up at boot) */
INLINE u32 timer_cycles(void) {
    u32 hi = REG_TM1D, lo = REG_TM0D, hi2 = REG_TM1D;
    if (hi != hi2) lo = REG_TM0D;
    return (hi2 << 16) | lo;
}

/* ---- OBJ VRAM layout (tile = 32 bytes) ---- */
#define TILE_PLAYER     0      /* 64x64 (64 tiles) */
#define TILE_NPC        64     /* 6 x 32x64 (32 tiles each) */
#define MAX_NPC         6
#define TILE_BILLS      256    /* static billboard art */
#define TILE_FX         528
#define TILE_BSLOT      576    /* building canvases (tile pool) */
#define BLD_TILES       448

/* ---- OBJ palette banks ---- */
#define PAL_COWBOY 0
#define PAL_OUTLAW 1
#define PAL_FX     4
#define PAL_TOWN   5

/* ---- camera ---- */
typedef struct {
    s32 x, y;          /* Q8 world position */
    u16 yaw;
    s32 sn, cs;        /* Q12 sin / cos of yaw */
} Camera;

extern Camera cam;

/* camera-space transform of a world point (Q8 in, Q8 out) */
INLINE void cam_xform(s32 wx, s32 wy, s32 *X, s32 *Z) {
    s32 dx = wx - cam.x, dy = wy - cam.y;
    *X = (dx * cam.cs + dy * cam.sn) >> 12;
    *Z = (dx * cam.sn - dy * cam.cs) >> 12;
}

/* ---- sprite list (sorted by depth, then written to OAM) ---- */
typedef struct {
    s32 depth;
    u16 a0, a1, a2;
    u16 pa;            /* affine: exact 1/scale (Q8) to get a matrix for, 0 = none */
} SprEnt;

#define MAX_SPR 120
extern SprEnt spr_list[MAX_SPR];
extern int spr_count;
IWRAM_CODE void spr_add(s32 depth, u16 a0, u16 a1, u16 a2);
IWRAM_CODE void spr_add_aff(s32 depth, u16 a0, u16 a1, u16 a2, u16 pa);

/* ---- building renderer (IWRAM, ARM) ---- */
typedef struct {
    s32 sx0, sy0;      /* screen origin of canvas */
    int scale;         /* 1 or 2 screen pixels per canvas pixel */
    int nx, ny;        /* canvas size in OBJs (64x64 each when more than one) */
    int ow, oh;        /* size of each OBJ in pixels */
    s32 ax, ay;        /* screen position of the anchor corner */
    int aidx;          /* anchor: wall whose start corner is farthest from the camera */
    s32 bx1, by1;      /* screen bbox: (sx0, sy0) .. (bx1, by1) */
} Canvas;
IWRAM_CODE void occ_reset(void);
IWRAM_CODE int occ_hidden(const Canvas *cv);
IWRAM_CODE void occ_add(void);

IWRAM_CODE int bld_prepare(int bi, Canvas *cv, int max_tiles);  /* returns tiles needed, 0 = not visible */
IWRAM_CODE void bld_draw(u8 *staging);
IWRAM_CODE int bld_anchor(int bi, int aidx, s32 *ax, s32 *ay);
IWRAM_CODE void m7_build_iw(void *table);
IWRAM_CODE void vblank_isr(void);
extern void *m7_front;
extern u16 haze[];       /* per-scanline affine table (161 x 16 bytes) */

/* ---- game ---- */
typedef struct {
    s32 x, y;          /* Q8 */
    u16 heading;
    u8 alive, state;
    s16 timer;
    u16 anim;
    s32 tx, ty;        /* walk target (Q8) */
    u8 slot, frame, dir, shoot_cd;
} Npc;

typedef struct {
    s32 x, y;
    u16 heading;
    u16 anim;
    s16 health;
    s16 ammo, reload;
    s16 shoot_timer, hurt;
    u8 moving, running;
    u32 bounty;
} Player;

extern Player player;


extern Npc npcs[MAX_NPC];
extern u32 game_frame;

void hud_init(void);
void game_init(void);
void game_tick(u16 keys, int steps);
void game_present(void);
void bld_invalidate(void);
extern int title_mode;
void hud_text(int x, int y, const char *s, int gold);
void hud_clear_row(int y);
void hud_update(int title);

s32 iatan2(s32 y, s32 x);   /* returns 16-bit angle of vector (x east, y south) */
u32 rand32(void);

#endif
