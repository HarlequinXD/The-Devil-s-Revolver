package com.harlequinxd.devilsrevolver

import android.graphics.Bitmap

/** The game itself is native C (shared with the GBA ROM build). */
object NativeGame {
    init {
        System.loadLibrary("devilsrevolver")
    }

    /** Set up the world. Safe to call more than once. */
    @JvmStatic external fun init()

    /** Advance one 60 Hz tick with the given GBA key mask and draw into a 240x160 ARGB_8888 bitmap. */
    @JvmStatic external fun frame(keys: Int, bitmap: Bitmap)

    // GBA key bits (same layout as the KEYINPUT register)
    const val KEY_A = 1
    const val KEY_B = 2
    const val KEY_SELECT = 4
    const val KEY_START = 8
    const val KEY_RIGHT = 16
    const val KEY_LEFT = 32
    const val KEY_UP = 64
    const val KEY_DOWN = 128
    const val KEY_R = 256
    const val KEY_L = 512
}
