/* Desktop test driver for the native build: runs the game with scripted input
   and writes frames as PPM images.  cc -DPLATFORM_NATIVE ... (see Makefile: host) */
#include <stdio.h>
#include <stdlib.h>
#include "../game.h"

void ppu_render(u32 *out);
static u32 fb[240 * 160];
#ifdef BLD_DEBUG
int dbg_nb, dbg_nv;
#endif

static void save(const char *name) {
    FILE *f = fopen(name, "wb");
    fprintf(f, "P6 240 160 255\n");
    for (int i = 0; i < 240 * 160; i++) { u32 c = fb[i]; fputc(c & 255, f); fputc((c >> 8) & 255, f); fputc((c >> 16) & 255, f); }
    fclose(f);
}

int main(int argc, char **argv) {
    /* script lines: frames keys(hex) [file] */
    FILE *s = fopen(argc > 1 ? argv[1] : "script.txt", "r");
    game_init();
    char line[256], name[200];
    int frames; unsigned keys;
    while (fgets(line, sizeof line, s)) {
        name[0] = 0;
        if (sscanf(line, "%d %x %199s", &frames, &keys, name) < 2) continue;
        for (int i = 0; i < frames; i++) {
            game_tick((u16)keys, 1);
            game_present();
            ppu_render(fb);
        }
        if (name[0]) { save(name);
#ifdef BLD_DEBUG
            extern int dbg_nb, dbg_nv; printf("%s visible %d tiles %d\n", name, dbg_nb, dbg_nv);
#endif
        }
    }
    return 0;
}
