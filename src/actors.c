/* Player, outlaws, tumbleweeds and the chase camera. */
#include "game.h"
#include "world.h"

Camera cam;
Player player;
Npc npcs[MAX_NPC];

const u8 *player_frame_src;
const u8 *npc_frame_src[MAX_NPC];
u16 npc_frame_bytes[MAX_NPC];
u8 tumble_frame;

#define FRAME_BYTES_COWBOY 2048
#define FRAME_BYTES_OUTLAW 1024
enum { NS_WALK, NS_IDLE, NS_AIM, NS_DEAD };

typedef struct { s32 x, y; s32 vx; u16 phase; } Tumble;
#define N_TUMBLE 5
static Tumble tumbles[N_TUMBLE];

static u32 rng_state = 0x1885BEEF;
u32 rand32(void) {
    u32 x = rng_state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return rng_state = x;
}

s32 iatan2(s32 y, s32 x) {
    if (!x && !y) return 0;
    u32 ax = x < 0 ? -x : x, ay = y < 0 ? -y : y;
    while (ax > (1u << 22) || ay > (1u << 22)) { ax >>= 1; ay >>= 1; }
    s32 a;
    if (ax >= ay) a = lut_atan[(ay << 8) / (ax ? ax : 1)];
    else a = 16384 - lut_atan[(ax << 8) / ay];
    if (x < 0) a = 32768 - a;
    if (y < 0) a = -a;
    return a & 0xFFFF;
}

/* heading that faces along (dx, dy) in world space (forward = (sin, -cos)) */
static u16 heading_of(s32 dx, s32 dy) { return (u16)iatan2(dx, -dy); }

/* which of the 8 drawn directions to show for a character facing `heading` */
static int view_dir(u16 heading) {
    s32 rel = (s16)(heading - cam.yaw);
    return (4 - ((rel + 0x1000) >> 13)) & 7;
}

static void pick_target(Npc *n) {
    u32 r = rand32();
    if (r & 1) {
        n->tx = (490 + (rand32() % 44)) << 8;
        n->ty = (220 + (rand32() % 540)) << 8;
    } else {
        n->tx = (300 + (rand32() % 440)) << 8;
        n->ty = (494 + (rand32() % 36)) << 8;
    }
}

static void spawn_npc(Npc *n, int far_from_player) {
    for (int tries = 0; tries < 8; tries++) {
        int k = rand32() % N_NPC_SPAWNS;
        n->x = npc_spawns[k][0] << 8; n->y = npc_spawns[k][1] << 8;
        s32 dx = (n->x - player.x) >> 8, dy = (n->y - player.y) >> 8;
        if (!far_from_player || dx * dx + dy * dy > 220 * 220) break;
    }
    n->alive = 1; n->state = NS_WALK; n->timer = 0; n->anim = rand32();
    n->shoot_cd = 120 + (rand32() & 127);
    pick_target(n);
}

void actors_init(void) {
    player.x = 512 << 8; player.y = 610 << 8; player.heading = 0;
    player.health = 5; player.ammo = 6; player.reload = 0; player.bounty = 0;
    player.shoot_timer = 0; player.hurt = 0;
    for (int i = 0; i < MAX_NPC; i++) { npcs[i].slot = i; spawn_npc(&npcs[i], 1); }
    for (int i = 0; i < N_TUMBLE; i++) {
        tumbles[i].x = (rand32() % 1000) << 8; tumbles[i].y = (100 + rand32() % 820) << 8;
        tumbles[i].vx = 60 + (rand32() & 63); tumbles[i].phase = rand32();
    }
    cam.yaw = 0;
    camera_follow(1);
}

void camera_follow(int snap) {
    s16 diff = (s16)(player.heading - cam.yaw);
    if (snap) cam.yaw = player.heading;
    else cam.yaw += diff / 7 + (diff > 0 ? 1 : diff < 0 ? -1 : 0);
    cam.sn = isin(cam.yaw); cam.cs = icos(cam.yaw);
    cam.x = player.x - ((cam.sn * CAM_DIST) << 8 >> 12);
    cam.y = player.y + ((cam.cs * CAM_DIST) << 8 >> 12);
}

static void shoot(void) {
    s32 fx_ = isin(player.heading), fy_ = -icos(player.heading);   /* Q12 forward */
    int best = -1; s32 best_along = 0x7FFFFFFF;
    for (int i = 0; i < MAX_NPC; i++) {
        Npc *n = &npcs[i];
        if (!n->alive) continue;
        s32 dx = (n->x - player.x) >> 4, dy = (n->y - player.y) >> 4;       /* Q4 */
        s32 along = (dx * fx_ + dy * fy_) >> 12;
        s32 perp = (dx * fy_ - dy * fx_) >> 12;
        if (perp < 0) perp = -perp;
        if (along < (6 << 4) || along > (420 << 4)) continue;
        if (perp > (6 << 4) + along / 14) continue;
        if (along < best_along) { best_along = along; best = i; }
    }
    s32 reach = best >= 0 ? best_along : (260 << 4);
    s32 ex = player.x + ((fx_ * reach) >> 8), ey = player.y + ((fy_ * reach) >> 8);
    int f = ray_block(player.x, player.y, ex, ey);
    if (f < 256) {
        s32 hx = player.x + (((ex - player.x) >> 8) * f), hy = player.y + (((ey - player.y) >> 8) * f);
        fx_spawn(hx, hy, FXT_SPARK, 12);
        return;
    }
    if (best >= 0) {
        Npc *n = &npcs[best];
        n->alive = 0; n->state = NS_DEAD; n->timer = 540;
        player.bounty += 50;
        fx_spawn(n->x, n->y, FXT_SPARK, 9);
    } else {
        fx_spawn(ex, ey, FXT_DUST, 0);
    }
}

static void move_player(s32 mx, s32 my) {
    if (!blocked(player.x + mx, player.y, 5)) player.x += mx;
    if (!blocked(player.x, player.y + my, 5)) player.y += my;
}

static void update_player(u16 keys, u16 pressed) {
    if (player.health <= 0) {
        if (player.hurt > 0) player.hurt--;
        return;
    }
    int turn = player.running ? 520 : 640;
    if (keys & KEY_LEFT) player.heading -= turn;
    if (keys & KEY_RIGHT) player.heading += turn;
    s32 fx_ = isin(player.heading), fy_ = -icos(player.heading);
    s32 speed = 0, strafe = 0;
    player.running = 0;
    if (keys & KEY_UP) { speed = (keys & KEY_A) ? 330 : 150; player.running = (keys & KEY_A) != 0; }
    else if (keys & KEY_DOWN) speed = -100;
    if (keys & KEY_L) strafe = -110;
    if (keys & KEY_R) strafe = 110;
    if (player.shoot_timer) speed = speed / 3;
    player.moving = speed || strafe;
    if (player.moving) {
        s32 mx = (fx_ * speed + (-fy_) * strafe) >> 12, my = (fy_ * speed + fx_ * strafe) >> 12;
        move_player(mx, my);
        player.anim += player.running ? 7 : (speed < 0 ? 3 : 4);
        if (player.running && (game_frame % 9) == 0)
            fx_spawn(player.x - fx_ * 3 / 16, player.y - fy_ * 3 / 16, FXT_DUST, 0);
    } else player.anim = 0;
    if (player.shoot_timer) player.shoot_timer--;
    if (player.reload) {
        if (--player.reload == 0) player.ammo = 6;
    }
    if ((pressed & KEY_B) && !player.shoot_timer && !player.reload) {
        if (player.ammo > 0) {
            player.ammo--; player.shoot_timer = 16;
            shoot();
            if (!player.ammo) player.reload = 80;
        }
    }
    if ((pressed & KEY_SELECT) && player.ammo < 6 && !player.reload) player.reload = 80;
    if (player.hurt) player.hurt--;
}

static void update_npc(Npc *n) {
    n->anim += 4;
    if (n->state == NS_DEAD) {
        if (--n->timer <= 0) spawn_npc(n, 1);
        return;
    }
    s32 pdx = (player.x - n->x) >> 8, pdy = (player.y - n->y) >> 8;
    s32 pd2 = pdx * pdx + pdy * pdy;
    if (n->shoot_cd) n->shoot_cd--;
    if (n->state != NS_AIM && player.health > 0 && !n->shoot_cd && pd2 < 170 * 170 &&
        ((game_frame + n->slot * 5) & 15) == 0 && ray_block(n->x, n->y, player.x, player.y) == 256) {
        n->state = NS_AIM; n->timer = 60;
    }
    switch (n->state) {
        case NS_AIM:
            n->heading = heading_of(pdx, pdy);
            if (--n->timer == 0) {
                fx_spawn(n->x + ((isin(n->heading) * 6) >> 4), n->y - ((icos(n->heading) * 6) >> 4), FXT_SPARK, 9);
                if ((rand32() & 255) < 150 && player.health > 0 && pd2 < 170 * 170) {
                    player.health--; player.hurt = 40;
                }
                n->state = NS_WALK; n->shoot_cd = 150 + (rand32() & 127);
                pick_target(n);
            }
            break;
        case NS_IDLE:
            if (--n->timer <= 0) { n->state = NS_WALK; pick_target(n); }
            break;
        default: {
            s32 dx = (n->tx - n->x) >> 8, dy = (n->ty - n->y) >> 8;
            if (dx * dx + dy * dy < 16) { n->state = NS_IDLE; n->timer = 60 + (rand32() & 127); break; }
            u16 h = heading_of(dx, dy);
            s16 d = (s16)(h - n->heading);
            n->heading += d / 6;
            s32 mx = (isin(n->heading) * 90) >> 12, my = (-icos(n->heading) * 90) >> 12;
            if (!blocked(n->x + mx, n->y + my, 5)) { n->x += mx; n->y += my; }
            else pick_target(n);
        }
    }
}

void actors_update(u16 keys, u16 pressed) {
    update_player(keys, pressed);
    for (int i = 0; i < MAX_NPC; i++) update_npc(&npcs[i]);
    for (int i = 0; i < N_TUMBLE; i++) {
        Tumble *t = &tumbles[i];
        t->x += t->vx; t->phase += 900;
        t->y += (isin(t->phase >> 2) * 12) >> 12;
        if (t->x > (1020 << 8)) { t->x = 4 << 8; t->y = (100 + rand32() % 820) << 8; }
    }
    if ((game_frame & 7) == 0) tumble_frame ^= 1;
    fx_update();
}

void actors_draw(void) {
    Proj p;
    /* player: crisp 1:1 sprite at the chase distance */
    if (!title_mode && project(player.x, player.y, &p) && !(player.hurt && (game_frame & 4))) {
        int d = view_dir(player.heading);
        int f = 0;
        if (player.health <= 0) f = 0;
        else if (player.shoot_timer) f = 7;
        else if (player.moving) f = 1 + ((player.anim >> 5) % 6);
        player_frame_src = spr_cowboy + (d * CHAR_FRAMES + f) * FRAME_BYTES_COWBOY;
        s32 x = p.sx - 32, y = p.sy - 62;
        spr_add(p.Z, (y & 255) | (0 << 14), (x & 511) | (3 << 14), TILE_PLAYER | (1 << 10) | (PAL_COWBOY << 12));
        draw_shadow(&p, p.scale >> 2, p.Z + (3 << 8));
        if (player.shoot_timer > 10) {
            s32 gx = x + gun_tips[d * 2] - 8, gy = y + gun_tips[d * 2 + 1] - 8;
            spr_add(p.Z - (2 << 8), (gy & 255) | (0 << 14), (gx & 511) | (1 << 14), FX_FLASH | (1 << 10) | (PAL_FX << 12));
        }
    }
    for (int i = 0; i < MAX_NPC; i++) {
        Npc *n = &npcs[i];
        npc_frame_src[i] = 0;
        if (!project(n->x, n->y, &p)) continue;
        s32 s = p.scale >> 2;                       /* outlaw art: 4 px per unit */
        u16 tile = TILE_NPC + i * 32;
        if (n->state == NS_DEAD) {
            npc_frame_src[i] = spr_outlaw_dead; npc_frame_bytes[i] = 1024;
            put_scaled(&p, s, 64, 32, 1, 3, tile, PAL_OUTLAW, 6, 0, 0, 0);
            continue;
        }
        int d = view_dir(n->heading);
        int f = n->state == NS_AIM ? 7 : n->state == NS_WALK ? 1 + ((n->anim >> 5) % 6) : 0;
        npc_frame_src[i] = spr_outlaw + (d * CHAR_FRAMES + f) * FRAME_BYTES_OUTLAW;
        npc_frame_bytes[i] = FRAME_BYTES_OUTLAW;
        put_scaled(&p, s, 32, 64, 2, 3, tile, PAL_OUTLAW, 2, 0, 0, 0);
        draw_shadow(&p, s, p.Z + (3 << 8));
        if (n->state == NS_AIM && n->timer < 6) {
            s32 sq = scale_level_q8[scale_to_level[s > 1023 ? 1023 : s]];
            s32 gx = p.sx + (((gun_tips[16 + d * 2] - 16) * sq) >> 8) - 8;
            s32 gy = p.sy + (((gun_tips[16 + d * 2 + 1] - 62) * sq) >> 8) - 8;
            spr_add(p.Z - (2 << 8), (gy & 255), (gx & 511) | (1 << 14), FX_FLASH | (1 << 10) | (PAL_FX << 12));
        }
    }
    for (int i = 0; i < N_TUMBLE; i++) {
        Tumble *t = &tumbles[i];
        if (!project(t->x, t->y, &p)) continue;
        const BillDef *d = &bill_defs[BILL_TUMBLE0];
        s32 s = (p.scale * bill_kinv[BILL_TUMBLE0]) >> 12;
        s32 hop = (isin(t->phase) < 0 ? -isin(t->phase) : isin(t->phase)) * 3 >> 12;
        put_scaled(&p, s, 32, 32, 0, 2, bill_tile[BILL_TUMBLE0 + tumble_frame], d->pal, 2, (hop * p.scale) >> 8, 0, 0);
    }
}
