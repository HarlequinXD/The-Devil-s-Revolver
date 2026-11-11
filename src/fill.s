@ Inner loops for the building renderer (ARM, IWRAM).
@ void col_fill(u8 *dst, const u8 *col, u32 vv, u32 vstp, u32 n,
@               const u8 *shade, u32 sh, u32 mask)
@ Draws n canvas pixels down one column (stride 128):
@   texel = col[(vv >> sh) & mask]; vv += vstp; *dst = shade ? shade[texel] : texel
@ All town textures are opaque, so there is no transparency test. Unrolled x4.
    .syntax unified
    .section .iwram, "ax"
    .arm
    .align 2
    .global col_fill
    .type col_fill, %function
col_fill:
    stmfd   sp!, {r4-r9, lr}
    ldr     r4, [sp, #28]           @ n
    ldr     r5, [sp, #32]           @ shade LUT or 0
    ldr     r6, [sp, #36]           @ sh
    ldr     r7, [sp, #40]           @ mask
    cmp     r4, #0
    beq     .Ldone
    cmp     r5, #0
    beq     .Lplain
    @ ---- shaded
    ands    r9, r4, #3
    beq     .Ls4
.Ls1:
    and     r8, r7, r2, lsr r6
    ldrb    r8, [r1, r8]
    add     r2, r2, r3
    ldrb    r8, [r5, r8]
    strb    r8, [r0], #128
    subs    r9, r9, #1
    bne     .Ls1
.Ls4:
    movs    r4, r4, lsr #2
    beq     .Ldone
.Ls4loop:
    and     r8, r7, r2, lsr r6
    ldrb    r8, [r1, r8]
    add     r2, r2, r3
    and     r9, r7, r2, lsr r6
    ldrb    r9, [r1, r9]
    add     r2, r2, r3
    ldrb    r8, [r5, r8]
    ldrb    r9, [r5, r9]
    strb    r8, [r0], #128
    strb    r9, [r0], #128
    and     r8, r7, r2, lsr r6
    ldrb    r8, [r1, r8]
    add     r2, r2, r3
    and     r9, r7, r2, lsr r6
    ldrb    r9, [r1, r9]
    add     r2, r2, r3
    ldrb    r8, [r5, r8]
    ldrb    r9, [r5, r9]
    strb    r8, [r0], #128
    strb    r9, [r0], #128
    subs    r4, r4, #1
    bne     .Ls4loop
    b       .Ldone
    @ ---- unshaded (sunlit faces)
.Lplain:
    ands    r9, r4, #3
    beq     .Lp4
.Lp1:
    and     r8, r7, r2, lsr r6
    ldrb    r8, [r1, r8]
    add     r2, r2, r3
    strb    r8, [r0], #128
    subs    r9, r9, #1
    bne     .Lp1
.Lp4:
    movs    r4, r4, lsr #2
    beq     .Ldone
.Lp4loop:
    and     r8, r7, r2, lsr r6
    ldrb    r8, [r1, r8]
    add     r2, r2, r3
    and     r9, r7, r2, lsr r6
    ldrb    r9, [r1, r9]
    add     r2, r2, r3
    strb    r8, [r0], #128
    strb    r9, [r0], #128
    and     r8, r7, r2, lsr r6
    ldrb    r8, [r1, r8]
    add     r2, r2, r3
    and     r9, r7, r2, lsr r6
    ldrb    r9, [r1, r9]
    add     r2, r2, r3
    strb    r8, [r0], #128
    strb    r9, [r0], #128
    subs    r4, r4, #1
    bne     .Lp4loop
.Ldone:
    ldmfd   sp!, {r4-r9, lr}
    bx      lr
