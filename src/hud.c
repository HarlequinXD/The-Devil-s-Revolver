/* HUD on BG1 (text + bullet icons), rendered from a shadow map copied at vblank. */
#include "game.h"

u16 hud_map[32 * 20] EWRAM_BSS ALIGN4;
int hud_dirty = 1;

#define FONT_BASE   N_SKY_TILES
#define FONT_N      ((int)sizeof(FONT_CHARS) - 1)
#define ICON_BULLET (FONT_BASE + FONT_N * 2)
#define ICON_SPENT  (ICON_BULLET + 1)
#define HUDPAL      (15 << 12)

static int glyph(char c) {
    for (int i = 0; i < FONT_N; i++) if (FONT_CHARS[i] == c) return i;
    return 0;
}

void hud_clear_row(int y) {
    for (int x = 0; x < 32; x++) hud_map[y * 32 + x] = FONT_BASE | HUDPAL;
    hud_dirty = 1;
}

void hud_text(int x, int y, const char *s, int gold) {
    for (; *s && x < 30; s++, x++)
        hud_map[y * 32 + x] = (FONT_BASE + glyph(*s) + (gold ? FONT_N : 0)) | HUDPAL;
    hud_dirty = 1;
}

extern u32 perf_cycles;
extern int show_perf;

static void put_num(char *buf, u32 v, int digits) {
    for (int i = digits - 1; i >= 0; i--) { buf[i] = '0' + v % 10; v /= 10; }
    buf[digits] = 0;
}

void hud_init(void) {
    for (int y = 0; y < 20; y++) hud_clear_row(y);
}


void hud_update(int title) {
    static int last_title = -1;
    static u32 last_bounty = 0xFFFFFFFF;
    static int last_ammo = -1, last_health = -1, last_reload = -1, last_perf = -1;
    if (title != last_title) { hud_init(); last_title = title; last_bounty = 0xFFFFFFFF; last_ammo = -1; last_health = -1; }
    if (title) {
        hud_text(5, 5, "THE DEVIL'S REVOLVER", 1);
        hud_text(9, 7, "A FRONTIER TALE", 0);
        if ((game_frame >> 5) & 1) hud_text(10, 12, "PRESS START", 1);
        else hud_clear_row(12);
        if (FREE_ROAM) {
            hud_text(5, 17, "D-PAD MOVE    A RUN", 0);
            hud_text(5, 18, "L/R STRAFE    FREE ROAM", 0);
        } else {
            hud_text(1, 17, "D-PAD MOVE   A RUN   B SHOOT", 0);
            hud_text(1, 18, "L/R STRAFE   SELECT RELOAD", 0);
        }
        return;
    }
    if (FREE_ROAM) {
        if (show_perf) {
            static int lp = -1;
            int pc = (int)(perf_cycles / 2809);
            if (pc != lp) { char b[8]; lp = pc; b[0]='C'; b[1]='P'; b[2]='U'; b[3]=' '; put_num(b + 4, pc > 999 ? 999 : pc, 3); b[7]=0; hud_text(1, 19, b, 0); }
        } else hud_clear_row(19);
        return;
    }
    char buf[16];
    if (player.bounty != last_bounty) {
        last_bounty = player.bounty;
        buf[0] = '$'; put_num(buf + 1, player.bounty, 5);
        hud_text(1, 0, buf, 1);
    }
    if (player.ammo != last_ammo || (player.reload != 0) != last_reload) {
        last_ammo = player.ammo; last_reload = player.reload != 0;
        for (int i = 0; i < 6; i++)
            hud_map[0 * 32 + 23 + i] = (i < player.ammo ? ICON_BULLET : ICON_SPENT) | HUDPAL;
        if (player.reload) hud_text(20, 1, "RELOADING", 0);
        else hud_text(20, 1, "         ", 0);
        hud_dirty = 1;
    }
    if (player.health != last_health) {
        last_health = player.health;
        hud_text(1, 1, "     ", 1);
        for (int i = 0; i < player.health && i < 5; i++) hud_text(1 + i, 1, "*", 1);
        if (player.health <= 0) { hud_text(7, 9, "YOU'RE PUSHING DAISIES", 1); hud_text(9, 11, "PRESS START", 0); }
        else { hud_clear_row(9); hud_clear_row(11); }
    }
    if (show_perf) {
        int pc = (int)(perf_cycles / 2809);       /* % of one 60Hz frame */
        if (pc != last_perf) {
            last_perf = pc;
            buf[0] = 'C'; buf[1] = 'P'; buf[2] = 'U'; buf[3] = ' ';
            put_num(buf + 4, pc > 999 ? 999 : pc, 3); buf[7] = 0;
            hud_text(1, 19, buf, 0);
        }
    } else if (last_perf != -1) { last_perf = -1; hud_clear_row(19); }
}
