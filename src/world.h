#ifndef WORLD_H
#define WORLD_H
#include "game.h"

typedef struct { s32 sx, sy, Z, scale; } Proj;

#define FX_FLASH  (TILE_FX)
#define FX_DUST   (TILE_FX + 4)
#define FX_SHADOW (TILE_FX + 16)
#define FX_SPARK  (TILE_FX + 24)

enum { FXT_DUST = 1, FXT_SPARK = 2 };
typedef struct { s32 x, y; u8 type, t; s16 h; } FxEnt;
#define MAX_FX 12
extern FxEnt fx[MAX_FX];

extern u8 bslot_stage[];
extern u8 bslot_dirty[];
extern u16 bill_tile[];
extern u16 bill_kinv[];
extern int bslots_used;

void world_init(void);
IWRAM_CODE int project(s32 wx, s32 wy, Proj *p);
IWRAM_CODE void put_scaled(const Proj *p, s32 scale_q8, int w, int h, int shape, int size, u16 tile, int pal,
                int foot, int lift_px, int semi, s32 depth_bias);
IWRAM_CODE void draw_billboards(void);
IWRAM_CODE void draw_buildings(void);
IWRAM_CODE void draw_shadow(const Proj *p, s32 scale_q8, s32 depth);
void fx_spawn(s32 x, s32 y, int type, int h);
void fx_update(void);
void draw_fx(void);
IWRAM_CODE int blocked(s32 x, s32 y, s32 r);
int ray_block(s32 x0, s32 y0, s32 x1, s32 y1);

/* actors.c */
void actors_init(void);
void actors_update(u16 keys, u16 pressed);
void actors_draw(void);
void camera_follow(int snap);
extern const u8 *player_frame_src;
extern const u8 *npc_frame_src[MAX_NPC];
extern u16 npc_frame_bytes[MAX_NPC];
extern u8 tumble_frame;
#endif
