package com.harlequinxd.devilsrevolver

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.view.Choreographer
import android.view.HapticFeedbackConstants
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.min

/**
 * Draws the game screen inside a handheld-style body with on-screen controls
 * shaped like the GBA's: cross D-pad, round A/B, L/R shoulders and pill
 * Start/Select. Runs the native game at a fixed 60 ticks per second.
 */
class GameView(context: Context) : View(context), Choreographer.FrameCallback {
    private val screen = Bitmap.createBitmap(240, 160, Bitmap.Config.ARGB_8888)
    private var running = false
    private var lastNanos = 0L
    private var accNanos = 0L

    private var touchKeys = 0
    private var padKeys = 0
    private var axisKeys = 0
    private val keys get() = touchKeys or padKeys or axisKeys

    // ---- layout (computed in onSizeChanged)
    private val screenRect = RectF()
    private val bezelRect = RectF()
    private var dpadX = 0f; private var dpadY = 0f; private var dpadR = 0f
    private var aX = 0f; private var aY = 0f; private var bX = 0f; private var bY = 0f; private var abR = 0f
    private val selectRect = RectF(); private val startRect = RectF()
    private val lRect = RectF(); private val rRect = RectF()

    // ---- palette (indigo handheld)
    private val bodyTop = Color.rgb(98, 84, 168)
    private val bodyBottom = Color.rgb(66, 54, 124)
    private val bodyEdge = Color.rgb(48, 38, 94)
    private val plastic = Color.rgb(46, 42, 58)
    private val plasticHi = Color.rgb(84, 78, 104)
    private val label = Color.rgb(206, 198, 238)

    private val pPix = Paint().apply { isFilterBitmap = false; isAntiAlias = false }
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val pText = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD_ITALIC)
        textAlign = Paint.Align.CENTER
    }

    init {
        NativeGame.init()
        isFocusable = true
        isFocusableInTouchMode = true
        isHapticFeedbackEnabled = true
    }

    fun resume() {
        if (running) return
        running = true
        lastNanos = 0L
        Choreographer.getInstance().postFrameCallback(this)
    }

    fun pause() {
        running = false
        Choreographer.getInstance().removeFrameCallback(this)
    }

    override fun doFrame(frameTimeNanos: Long) {
        if (!running) return
        if (lastNanos == 0L) lastNanos = frameTimeNanos - TICK
        accNanos += frameTimeNanos - lastNanos
        lastNanos = frameTimeNanos
        if (accNanos > TICK * 4) accNanos = TICK * 4      // don't spiral after a stall
        var ticked = false
        while (accNanos >= TICK) {                        // fixed 60 Hz, also on 90/120 Hz screens
            NativeGame.frame(keys, screen)
            accNanos -= TICK
            ticked = true
        }
        if (ticked) invalidate()
        Choreographer.getInstance().postFrameCallback(this)
    }

    // ------------------------------------------------------------------ layout
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        val W = w.toFloat(); val H = h.toFloat()
        var sh = H * 0.74f
        var sw = sh * 1.5f
        if (sw > W * 0.58f) { sw = W * 0.58f; sh = sw / 1.5f }
        val cx = W / 2f
        val top = H * 0.10f
        screenRect.set(cx - sw / 2, top, cx + sw / 2, top + sh)
        val pad = sh * 0.07f
        bezelRect.set(screenRect.left - pad * 1.6f, screenRect.top - pad, screenRect.right + pad * 1.6f, screenRect.bottom + pad * 1.4f)

        val sideW = bezelRect.left
        dpadR = min(sideW * 0.36f, H * 0.19f)
        dpadX = sideW * 0.52f
        dpadY = H * 0.50f
        abR = min(sideW * 0.15f, H * 0.085f)
        val rx = W - sideW * 0.50f
        aX = rx + abR * 1.25f; aY = H * 0.44f
        bX = rx - abR * 1.25f; bY = H * 0.44f + abR * 1.05f

        val pillW = abR * 1.35f; val pillH = abR * 0.5f
        val py = H * 0.86f
        selectRect.set(dpadX - pillW * 1.15f, py, dpadX - pillW * 0.15f, py + pillH)
        startRect.set(dpadX + pillW * 0.15f, py, dpadX + pillW * 1.15f, py + pillH)

        val shH = H * 0.11f
        lRect.set(-H * 0.05f, -shH * 0.4f, sideW * 0.95f, shH)
        rRect.set(W - sideW * 0.95f, -shH * 0.4f, W + H * 0.05f, shH)
    }

    // ------------------------------------------------------------------ drawing
    override fun onDraw(c: Canvas) {
        val W = width.toFloat(); val H = height.toFloat()
        // body
        p.shader = LinearGradient(0f, 0f, 0f, H, bodyTop, bodyBottom, Shader.TileMode.CLAMP)
        c.drawRect(0f, 0f, W, H, p)
        p.shader = null
        // subtle grip curves on both sides
        p.color = Color.argb(40, 0, 0, 0)
        c.drawOval(RectF(-W * 0.12f, H * 0.12f, bezelRect.left * 1.05f, H * 1.25f), p)
        c.drawOval(RectF(W - bezelRect.left * 1.05f, H * 0.12f, W * 1.12f, H * 1.25f), p)
        p.color = Color.argb(28, 255, 255, 255)
        c.drawOval(RectF(-W * 0.10f, H * 0.10f, bezelRect.left, H * 1.2f), p)
        c.drawOval(RectF(W - bezelRect.left, H * 0.10f, W * 1.10f, H * 1.2f), p)

        drawShoulder(c, lRect, "L", NativeGame.KEY_L, true)
        drawShoulder(c, rRect, "R", NativeGame.KEY_R, false)

        // screen bezel
        val br = bezelRect.height() * 0.08f
        p.color = bodyEdge
        c.drawRoundRect(RectF(bezelRect.left - 3f, bezelRect.top - 3f, bezelRect.right + 3f, bezelRect.bottom + 3f), br + 3f, br + 3f, p)
        p.color = Color.rgb(32, 30, 42)
        c.drawRoundRect(bezelRect, br, br, p)
        // power LED + title
        p.color = Color.rgb(90, 220, 110)
        val ledR = bezelRect.height() * 0.018f
        c.drawCircle(bezelRect.left + (screenRect.left - bezelRect.left) * 0.5f, screenRect.top + screenRect.height() * 0.35f, ledR, p)
        pText.textSize = (bezelRect.bottom - screenRect.bottom) * 0.42f
        pText.color = Color.rgb(140, 132, 184)
        c.drawText("THE DEVIL'S REVOLVER", screenRect.centerX(), bezelRect.bottom - (bezelRect.bottom - screenRect.bottom) * 0.3f, pText)

        // game picture, nearest-neighbour scaled
        c.drawBitmap(screen, null, screenRect, pPix)

        drawDpad(c)
        drawRound(c, aX, aY, "A", NativeGame.KEY_A)
        drawRound(c, bX, bY, "B", NativeGame.KEY_B)
        drawPill(c, selectRect, "SELECT", NativeGame.KEY_SELECT)
        drawPill(c, startRect, "START", NativeGame.KEY_START)
        drawSpeaker(c)
    }

    private fun drawDpad(c: Canvas) {
        val r = dpadR; val arm = r * 0.36f
        // recess
        p.color = Color.argb(60, 0, 0, 0)
        c.drawCircle(dpadX, dpadY + r * 0.04f, r * 1.12f, p)
        p.color = Color.argb(35, 255, 255, 255)
        c.drawCircle(dpadX, dpadY - r * 0.03f, r * 1.08f, p)
        val cross = Path().apply {
            addRoundRect(RectF(dpadX - arm, dpadY - r, dpadX + arm, dpadY + r), arm * 0.35f, arm * 0.35f, Path.Direction.CW)
            addRoundRect(RectF(dpadX - r, dpadY - arm, dpadX + r, dpadY + arm), arm * 0.35f, arm * 0.35f, Path.Direction.CW)
        }
        // drop shadow, body, top highlight
        c.save(); c.translate(0f, r * 0.06f)
        p.color = Color.argb(120, 0, 0, 0); c.drawPath(cross, p)
        c.restore()
        p.shader = LinearGradient(0f, dpadY - r, 0f, dpadY + r, plasticHi, plastic, Shader.TileMode.CLAMP)
        c.drawPath(cross, p)
        p.shader = null
        // pressed arms darken
        val k = keys
        p.color = Color.argb(110, 0, 0, 0)
        if (k and NativeGame.KEY_UP != 0) c.drawRect(dpadX - arm, dpadY - r, dpadX + arm, dpadY - arm, p)
        if (k and NativeGame.KEY_DOWN != 0) c.drawRect(dpadX - arm, dpadY + arm, dpadX + arm, dpadY + r, p)
        if (k and NativeGame.KEY_LEFT != 0) c.drawRect(dpadX - r, dpadY - arm, dpadX - arm, dpadY + arm, p)
        if (k and NativeGame.KEY_RIGHT != 0) c.drawRect(dpadX + arm, dpadY - arm, dpadX + r, dpadY + arm, p)
        // centre dimple + arrows
        p.color = Color.argb(70, 0, 0, 0)
        c.drawCircle(dpadX, dpadY, arm * 0.55f, p)
        p.color = Color.argb(90, 255, 255, 255)
        val t = arm * 0.42f; val o = r * 0.70f
        arrow(c, dpadX, dpadY - o, t, 0)
        arrow(c, dpadX, dpadY + o, t, 2)
        arrow(c, dpadX - o, dpadY, t, 3)
        arrow(c, dpadX + o, dpadY, t, 1)
    }

    private fun arrow(c: Canvas, x: Float, y: Float, s: Float, dir: Int) {
        val path = Path()
        when (dir) {
            0 -> { path.moveTo(x, y - s); path.lineTo(x + s, y + s * 0.6f); path.lineTo(x - s, y + s * 0.6f) }
            2 -> { path.moveTo(x, y + s); path.lineTo(x + s, y - s * 0.6f); path.lineTo(x - s, y - s * 0.6f) }
            3 -> { path.moveTo(x - s, y); path.lineTo(x + s * 0.6f, y - s); path.lineTo(x + s * 0.6f, y + s) }
            else -> { path.moveTo(x + s, y); path.lineTo(x - s * 0.6f, y - s); path.lineTo(x - s * 0.6f, y + s) }
        }
        path.close()
        c.drawPath(path, p)
    }

    private fun drawRound(c: Canvas, x: Float, y: Float, name: String, bit: Int) {
        val down = keys and bit != 0
        val r = abR
        p.color = Color.argb(70, 0, 0, 0)
        c.drawCircle(x, y + r * 0.05f, r * 1.18f, p)                 // recess ring
        p.color = Color.argb(110, 0, 0, 0)
        c.drawCircle(x, y + r * (if (down) 0.02f else 0.12f), r, p)  // shadow
        val cy = y + if (down) r * 0.06f else 0f
        p.shader = RadialGradient(x - r * 0.35f, cy - r * 0.4f, r * 1.4f,
            if (down) plastic else plasticHi, Color.rgb(28, 26, 36), Shader.TileMode.CLAMP)
        c.drawCircle(x, cy, r * (if (down) 0.96f else 1f), p)
        p.shader = null
        // the letter is printed on the body beside the button, like the GBA
        pText.color = label
        pText.textSize = r * 0.75f
        c.drawText(name, x + r * 0.95f, y + r * 1.65f, pText)
    }

    private fun drawPill(c: Canvas, rect: RectF, name: String, bit: Int) {
        val down = keys and bit != 0
        val rr = rect.height() / 2f
        p.color = Color.argb(80, 0, 0, 0)
        c.drawRoundRect(RectF(rect.left - rr * 0.3f, rect.top - rr * 0.3f, rect.right + rr * 0.3f, rect.bottom + rr * 0.3f), rr * 1.3f, rr * 1.3f, p)
        p.color = if (down) Color.rgb(96, 92, 112) else Color.rgb(150, 146, 168)
        val dy = if (down) rr * 0.15f else 0f
        c.drawRoundRect(RectF(rect.left, rect.top + dy, rect.right, rect.bottom + dy), rr, rr, p)
        pText.color = label
        pText.textSize = rect.height() * 0.9f
        c.drawText(name, rect.centerX(), rect.bottom + rect.height() * 1.4f, pText)
    }

    private fun drawShoulder(c: Canvas, rect: RectF, name: String, bit: Int, left: Boolean) {
        val down = keys and bit != 0
        val r = rect.height() * 0.6f
        p.color = Color.argb(90, 0, 0, 0)
        c.drawRoundRect(RectF(rect.left, rect.top + 4f, rect.right, rect.bottom + 4f), r, r, p)
        p.shader = LinearGradient(0f, rect.top, 0f, rect.bottom,
            if (down) Color.rgb(140, 136, 160) else Color.rgb(196, 192, 214), Color.rgb(120, 114, 146), Shader.TileMode.CLAMP)
        c.drawRoundRect(rect, r, r, p)
        p.shader = null
        pText.color = Color.rgb(70, 62, 110)
        pText.textSize = rect.height() * 0.5f
        val tx = if (left) rect.left + rect.width() * 0.62f else rect.right - rect.width() * 0.62f
        c.drawText(name, tx, rect.bottom - rect.height() * 0.28f, pText)
    }

    private fun drawSpeaker(c: Canvas) {
        p.color = Color.argb(90, 0, 0, 0)
        val r = abR * 0.09f
        val x0 = aX - abR * 0.6f; val y0 = height * 0.80f
        for (j in 0 until 3) for (i in 0 until 6) {
            if ((i + j) % 2 == 1) continue
            c.drawCircle(x0 + i * r * 4f, y0 + j * r * 4f, r, p)
        }
    }

    // ------------------------------------------------------------------ touch
    override fun onTouchEvent(e: MotionEvent): Boolean {
        var k = 0
        val action = e.actionMasked
        for (i in 0 until e.pointerCount) {
            if ((action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) && i == e.actionIndex) continue
            if (action == MotionEvent.ACTION_CANCEL) continue
            k = k or keysAt(e.getX(i), e.getY(i))
        }
        if (k and touchKeys.inv() != 0) performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
        if (k != touchKeys) { touchKeys = k; invalidate() }
        return true
    }

    private fun keysAt(x: Float, y: Float): Int {
        var k = 0
        val dx = x - dpadX; val dy = y - dpadY
        val d = hypot(dx, dy)
        if (d < dpadR * 1.6f && d > dpadR * 0.18f) {
            // 8-way: snap to 45 degree sectors so diagonals are easy
            val sector = ((Math.toDegrees(atan2(dy, dx).toDouble()) + 360.0 + 22.5) / 45.0).toInt() % 8
            k = k or when (sector) {
                0 -> NativeGame.KEY_RIGHT
                1 -> NativeGame.KEY_RIGHT or NativeGame.KEY_DOWN
                2 -> NativeGame.KEY_DOWN
                3 -> NativeGame.KEY_DOWN or NativeGame.KEY_LEFT
                4 -> NativeGame.KEY_LEFT
                5 -> NativeGame.KEY_LEFT or NativeGame.KEY_UP
                6 -> NativeGame.KEY_UP
                else -> NativeGame.KEY_UP or NativeGame.KEY_RIGHT
            }
        }
        val da = hypot(x - aX, y - aY); val db = hypot(x - bX, y - bY)
        if (da < abR * 1.6f || db < abR * 1.6f) {
            k = k or if (da < db) NativeGame.KEY_A else NativeGame.KEY_B
            if (abs(da - db) < abR * 0.35f) k = k or NativeGame.KEY_A or NativeGame.KEY_B   // between: both
        }
        if (inflate(selectRect, abR * 0.5f).contains(x, y)) k = k or NativeGame.KEY_SELECT
        if (inflate(startRect, abR * 0.5f).contains(x, y)) k = k or NativeGame.KEY_START
        if (inflate(lRect, abR * 0.4f).contains(x, y)) k = k or NativeGame.KEY_L
        if (inflate(rRect, abR * 0.4f).contains(x, y)) k = k or NativeGame.KEY_R
        return k
    }

    private fun inflate(r: RectF, by: Float) = RectF(r.left - by, r.top - by, r.right + by, r.bottom + by)

    // ------------------------------------------------------------------ controllers
    fun handleKey(e: KeyEvent): Boolean {
        val bit = when (e.keyCode) {
            KeyEvent.KEYCODE_BUTTON_A, KeyEvent.KEYCODE_X, KeyEvent.KEYCODE_ENTER -> NativeGame.KEY_A
            KeyEvent.KEYCODE_BUTTON_B, KeyEvent.KEYCODE_Z -> NativeGame.KEY_B
            KeyEvent.KEYCODE_BUTTON_X -> NativeGame.KEY_A
            KeyEvent.KEYCODE_BUTTON_Y -> NativeGame.KEY_B
            KeyEvent.KEYCODE_BUTTON_L1, KeyEvent.KEYCODE_BUTTON_L2, KeyEvent.KEYCODE_Q -> NativeGame.KEY_L
            KeyEvent.KEYCODE_BUTTON_R1, KeyEvent.KEYCODE_BUTTON_R2, KeyEvent.KEYCODE_E -> NativeGame.KEY_R
            KeyEvent.KEYCODE_BUTTON_START, KeyEvent.KEYCODE_SPACE -> NativeGame.KEY_START
            KeyEvent.KEYCODE_BUTTON_SELECT, KeyEvent.KEYCODE_TAB -> NativeGame.KEY_SELECT
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_W -> NativeGame.KEY_UP
            KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_S -> NativeGame.KEY_DOWN
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_A -> NativeGame.KEY_LEFT
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_D -> NativeGame.KEY_RIGHT
            else -> return false
        }
        padKeys = if (e.action == KeyEvent.ACTION_DOWN) padKeys or bit else padKeys and bit.inv()
        invalidate()
        return true
    }

    fun handleMotion(e: MotionEvent): Boolean {
        if (e.source and InputDevice.SOURCE_JOYSTICK != InputDevice.SOURCE_JOYSTICK) return false
        val x = e.getAxisValue(MotionEvent.AXIS_X) + e.getAxisValue(MotionEvent.AXIS_HAT_X)
        val y = e.getAxisValue(MotionEvent.AXIS_Y) + e.getAxisValue(MotionEvent.AXIS_HAT_Y)
        var k = 0
        if (x < -0.4f) k = k or NativeGame.KEY_LEFT
        if (x > 0.4f) k = k or NativeGame.KEY_RIGHT
        if (y < -0.4f) k = k or NativeGame.KEY_UP
        if (y > 0.4f) k = k or NativeGame.KEY_DOWN
        if (e.getAxisValue(MotionEvent.AXIS_LTRIGGER) > 0.5f) k = k or NativeGame.KEY_L
        if (e.getAxisValue(MotionEvent.AXIS_RTRIGGER) > 0.5f) k = k or NativeGame.KEY_R
        axisKeys = k
        return true
    }

    companion object {
        private const val TICK = 16_666_667L   // 60 Hz in nanoseconds
    }
}
