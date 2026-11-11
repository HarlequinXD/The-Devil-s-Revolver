@ Integer division for the ARM EABI, in fast IWRAM ARM code.
@ __aeabi_uidivmod: r0 = n / d, r1 = n % d   (unsigned)
@ __aeabi_idivmod : r0 = n / d, r1 = n % d   (signed, C semantics)
    .syntax unified
    .section .iwram, "ax"
    .arm
    .align 2

    .global __aeabi_uidiv
    .global __aeabi_uidivmod
    .type __aeabi_uidiv, %function
    .type __aeabi_uidivmod, %function
__aeabi_uidiv:
__aeabi_uidivmod:
    mov     r3, #0
    cmp     r1, #0
    beq     .Ldz
    mov     r2, r1
    mov     ip, #1
.Lalign:
    cmp     r2, #0x80000000
    cmpcc   r2, r0
    movcc   r2, r2, lsl #1
    movcc   ip, ip, lsl #1
    bcc     .Lalign
.Lloop:
    cmp     r0, r2
    subcs   r0, r0, r2
    orrcs   r3, r3, ip
    movs    ip, ip, lsr #1
    movne   r2, r2, lsr #1
    bne     .Lloop
    mov     r1, r0
    mov     r0, r3
    bx      lr
.Ldz:
    mov     r1, r0
    mvn     r0, #0
    bx      lr

    .global __aeabi_idiv
    .global __aeabi_idivmod
    .type __aeabi_idiv, %function
    .type __aeabi_idivmod, %function
__aeabi_idiv:
__aeabi_idivmod:
    stmfd   sp!, {r4, r5, lr}
    movs    r4, r0
    rsbmi   r0, r0, #0
    eor     r5, r4, r1
    cmp     r1, #0
    rsbmi   r1, r1, #0
    bl      __aeabi_uidivmod
    cmp     r5, #0
    rsbmi   r0, r0, #0
    cmp     r4, #0
    rsbmi   r1, r1, #0
    ldmfd   sp!, {r4, r5, lr}
    bx      lr
