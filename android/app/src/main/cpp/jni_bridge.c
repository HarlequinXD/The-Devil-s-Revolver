/* JNI bridge: Kotlin calls init once, then frame() once per 60 Hz tick. */
#include <jni.h>
#include <android/bitmap.h>
#include "game.h"

void ppu_render(u32 *out);
static int ready;

JNIEXPORT void JNICALL
Java_com_harlequinxd_devilsrevolver_NativeGame_init(JNIEnv *env, jclass cls) {
    if (!ready) { game_init(); ready = 1; }
}

JNIEXPORT void JNICALL
Java_com_harlequinxd_devilsrevolver_NativeGame_frame(JNIEnv *env, jclass cls, jint keys, jobject bitmap) {
    if (!ready) { game_init(); ready = 1; }
    game_tick((u16)keys, 1);
    game_present();
    void *pixels;
    if (AndroidBitmap_lockPixels(env, bitmap, &pixels) < 0) return;
    ppu_render((u32 *)pixels);              /* 240x160 RGBA_8888 */
    AndroidBitmap_unlockPixels(env, bitmap);
}
