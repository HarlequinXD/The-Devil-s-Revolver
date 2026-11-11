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

@ void pack_row(u32 *out, const u8 *src, u32 ntiles)
@ Packs an (8*ntiles)x8 strip of the 8bpp canvas (stride 128, values 0..15) into
@ ntiles consecutive 4bpp 8x8 tiles (32 bytes each).
    .global pack_row
    .type pack_row, %function
pack_row:
    stmfd   sp!, {r4-r8, lr}
    ldr     r8, =0x00FF00FF
    mov     r7, r2                  @ tiles
.Lptile:
    mov     r6, #8                  @ rows
    mov     r2, r1
.Lprow:
    ldmia   r2, {r3, r4}
    orr     r3, r3, r3, lsr #4
    and     r3, r3, r8
    orr     r3, r3, r3, lsr #8
    orr     r4, r4, r4, lsr #4
    and     r4, r4, r8
    orr     r4, r4, r4, lsr #8
    mov     r3, r3, lsl #16
    mov     r3, r3, lsr #16
    orr     r3, r3, r4, lsl #16
    str     r3, [r0], #4
    add     r2, r2, #128
    subs    r6, r6, #1
    bne     .Lprow
    add     r1, r1, #8
    subs    r7, r7, #1
    bne     .Lptile
    ldmfd   sp!, {r4-r8, lr}
    bx      lr
    .ltorg

@ void canvas_clear_row(u8 *dst, u32 bytes)  -- bytes is a multiple of 32
    .global canvas_clear_row
    .type canvas_clear_row, %function
canvas_clear_row:
    stmfd   sp!, {r4-r9}
    mov     r2, #0
    mov     r3, #0
    mov     r4, #0
    mov     r5, #0
    mov     r6, #0
    mov     r7, #0
    mov     r8, #0
    mov     r9, #0
.Lclr:
    stmia   r0!, {r2-r9}
    subs    r1, r1, #32
    bgt     .Lclr
    ldmfd   sp!, {r4-r9}
    bx      lr
