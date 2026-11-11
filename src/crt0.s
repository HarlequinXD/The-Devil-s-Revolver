@ The Devil's Revolver - startup code and ROM header (ARM7TDMI, GNU as syntax)
    .syntax unified
    .section .header, "ax"
    .arm
    .global _start
_start:
    b       start_vector
    .space  156             @ Nintendo logo area - filled in by gbafix for real hardware
    .ascii  "DEVILREVOLVR"  @ game title (12)
    .ascii  "ADRE"          @ game code
    .ascii  "HX"            @ maker code
    .byte   0x96            @ fixed value
    .byte   0x00            @ main unit code
    .byte   0x00            @ device type
    .space  7               @ reserved
    .byte   0x00            @ software version
    .byte   0x00            @ header checksum (patched by tools/fixheader.py)
    .space  2               @ reserved

    .section .text.start, "ax"
    .arm
start_vector:
    @ IRQ stack
    mov     r0, #0x12
    msr     cpsr_c, r0
    ldr     sp, =0x03007FA0
    @ system mode stack
    mov     r0, #0x1F
    msr     cpsr_c, r0
    ldr     sp, =0x03007F00

    @ copy IWRAM code + data from ROM
    ldr     r0, =__iwram_lma
    ldr     r1, =__iwram_start
    ldr     r2, =__iwram_end
1:  cmp     r1, r2
    ldrlo   r3, [r0], #4
    strlo   r3, [r1], #4
    blo     1b

    @ clear IWRAM bss
    ldr     r1, =__bss_start
    ldr     r2, =__bss_end
    mov     r3, #0
2:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     2b

    @ clear EWRAM bss
    ldr     r1, =__ewram_bss_start
    ldr     r2, =__ewram_bss_end
3:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     3b

    @ install interrupt handler
    ldr     r0, =0x03007FFC
    ldr     r1, =irq_handler
    str     r1, [r0]

    ldr     r0, =main
    mov     lr, pc
    bx      r0
4:  b       4b

    @ IRQ handler (ARM, runs from IWRAM). Acknowledges IRQs, tells the BIOS
    @ (for VBlankIntrWait) and counts vblanks.
    .section .iwram, "ax"
    .arm
    .align 2
    .global irq_handler
irq_handler:
    mov     r0, #0x04000000
    add     r0, r0, #0x200
    ldr     r1, [r0]                @ IE | IF<<16
    and     r1, r1, r1, lsr #16     @ IE & IF
    strh    r1, [r0, #2]            @ acknowledge
    ldr     r2, =0x03007FF8
    ldrh    r3, [r2]
    orr     r3, r3, r1
    strh    r3, [r2]                @ BIOS IF flags
    tst     r1, #1
    bxeq    lr
    ldr     r2, =irq_vblank_count
    ldr     r3, [r2]
    add     r3, r3, #1
    str     r3, [r2]
    stmfd   sp!, {lr}
    ldr     r0, =vblank_isr
    mov     lr, pc
    bx      r0
    ldmfd   sp!, {lr}
    bx      lr
    .ltorg

    .section .iwram.data, "aw"
    .align 2
    .global irq_vblank_count
irq_vblank_count:
    .word 0
