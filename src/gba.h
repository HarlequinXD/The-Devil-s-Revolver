/* Minimal GBA hardware definitions (no libgba / libtonc dependency). */
#ifndef GBA_H
#define GBA_H
#include <stdint.h>

typedef uint8_t u8;   typedef int8_t s8;
typedef uint16_t u16; typedef int16_t s16;
typedef uint32_t u32; typedef int32_t s32;
typedef volatile u16 vu16; typedef volatile u32 vu32;

#ifdef PLATFORM_NATIVE
/* native build (Android / desktop): plain memory, no special sections */
#define IWRAM_CODE
#define IWRAM_DATA
#define EWRAM_BSS
#else
#define PLATFORM_GBA 1
#ifdef __clang__
#define IWRAM_CODE __attribute__((section(".iwram"), noinline))
#else
#define IWRAM_CODE __attribute__((section(".iwram"), long_call, noinline))
#endif
#define IWRAM_DATA __attribute__((section(".iwram.data")))
#define EWRAM_BSS  __attribute__((section(".ewram.bss")))
#endif
#define ALIGN4     __attribute__((aligned(4)))
#define INLINE     static inline __attribute__((always_inline))

#ifdef PLATFORM_NATIVE
/* the "hardware" lives in ordinary arrays; ppu.c composites them into pixels */
extern u8 plat_io[0x400];
extern u16 plat_vram[0xC000];
extern u16 plat_pal[512];
extern u16 plat_oam[512];
#define REG(a)      (*(vu16 *)(plat_io + ((a) - 0x04000000)))
#define REG32(a)    (*(vu32 *)(plat_io + ((a) - 0x04000000)))
#else
#define REG(a)      (*(vu16 *)(a))
#define REG32(a)    (*(vu32 *)(a))
#endif

#define REG_DISPCNT   REG(0x04000000)
#define REG_DISPSTAT  REG(0x04000004)
#define REG_VCOUNT    REG(0x04000006)
#define REG_BG0CNT    REG(0x04000008)
#define REG_BG1CNT    REG(0x0400000A)
#define REG_BG2CNT    REG(0x0400000C)
#define REG_BG0HOFS   REG(0x04000010)
#define REG_BG0VOFS   REG(0x04000012)
#define REG_BG1HOFS   REG(0x04000014)
#define REG_BG1VOFS   REG(0x04000016)
#define REG_BG2PA     REG(0x04000020)
#define REG_BG2PB     REG(0x04000022)
#define REG_BG2PC     REG(0x04000024)
#define REG_BG2PD     REG(0x04000026)
#define REG_BG2X      REG32(0x04000028)
#define REG_BG2Y      REG32(0x0400002C)
#define REG_WIN0H     REG(0x04000040)
#define REG_WIN0V     REG(0x04000044)
#define REG_WININ     REG(0x04000048)
#define REG_WINOUT    REG(0x0400004A)
#define REG_MOSAIC    REG(0x0400004C)
#define REG_BLDCNT    REG(0x04000050)
#define REG_BLDALPHA  REG(0x04000052)
#define REG_BLDY      REG(0x04000054)

#define REG_DMA0SAD   REG32(0x040000B0)
#define REG_DMA0DAD   REG32(0x040000B4)
#define REG_DMA0CNT   REG32(0x040000B8)
#define REG_DMA2SAD   REG32(0x040000C8)
#define REG_DMA2DAD   REG32(0x040000CC)
#define REG_DMA2CNT   REG32(0x040000D0)
#define REG_DMA3SAD   REG32(0x040000D4)
#define REG_DMA3DAD   REG32(0x040000D8)
#define REG_DMA3CNT   REG32(0x040000DC)

#define REG_TM0D      REG(0x04000100)
#define REG_TM0CNT    REG(0x04000102)
#define REG_TM1D      REG(0x04000104)
#define REG_TM1CNT    REG(0x04000106)
#define REG_KEYINPUT  REG(0x04000130)
#define REG_IE        REG(0x04000200)
#define REG_IF        REG(0x04000202)
#define REG_WAITCNT   REG(0x04000204)
#define REG_IME       REG(0x04000208)

#define DMA_DST_INC    (0u << 21)
#define DMA_DST_FIXED  (2u << 21)
#define DMA_DST_RELOAD (3u << 21)
#define DMA_SRC_FIXED  (2u << 23)
#define DMA_REPEAT     (1u << 25)
#define DMA_32         (1u << 26)
#define DMA_HBLANK     (2u << 28)
#define DMA_ENABLE     (1u << 31)

#ifdef PLATFORM_NATIVE
#define VRAM        (plat_vram)
#define CHARBLOCK(n) (plat_vram + (n) * 0x2000)
#define SCREENBLOCK(n) (plat_vram + (n) * 0x400)
#define OBJ_VRAM    (plat_vram + 0x8000)
#define PAL_BG      (plat_pal)
#define PAL_OBJ     (plat_pal + 256)
#define OAM_MEM     (plat_oam)
#else
#define VRAM        ((u16 *)0x06000000)
#define CHARBLOCK(n) ((u16 *)(0x06000000 + (n) * 0x4000))
#define SCREENBLOCK(n) ((u16 *)(0x06000000 + (n) * 0x800))
#define OBJ_VRAM    ((u16 *)0x06010000)
#define PAL_BG      ((u16 *)0x05000000)
#define PAL_OBJ     ((u16 *)0x05000200)
#define OAM_MEM     ((u16 *)0x07000000)
#endif

enum { KEY_A = 1, KEY_B = 2, KEY_SELECT = 4, KEY_START = 8, KEY_RIGHT = 16, KEY_LEFT = 32,
       KEY_UP = 64, KEY_DOWN = 128, KEY_R = 256, KEY_L = 512 };

typedef struct { u16 attr0, attr1, attr2, fill; } ObjAttr;

#ifdef PLATFORM_NATIVE
#include <string.h>
INLINE void dma_copy32(void *dst, const void *src, u32 bytes) { memcpy(dst, src, bytes); }
INLINE void dma_fill32(void *dst, u32 value, u32 bytes) {
    u32 *d = (u32 *)dst;
    for (u32 i = 0; i < bytes / 4; i++) d[i] = value;
}
INLINE void vblank_wait(void) {}
#else
/* fast 32-bit copy/fill using DMA3 (sizes in bytes, multiple of 4) */
INLINE void dma_copy32(void *dst, const void *src, u32 bytes) {
    REG_DMA3CNT = 0;
    REG_DMA3SAD = (u32)src; REG_DMA3DAD = (u32)dst;
    REG_DMA3CNT = (bytes >> 2) | DMA_32 | DMA_ENABLE;
    while (REG_DMA3CNT & DMA_ENABLE) {}
}
INLINE void dma_fill32(void *dst, u32 value, u32 bytes) {
    static volatile u32 fillv;
    fillv = value;
    REG_DMA3CNT = 0;
    REG_DMA3SAD = (u32)&fillv; REG_DMA3DAD = (u32)dst;
    REG_DMA3CNT = (bytes >> 2) | DMA_32 | DMA_SRC_FIXED | DMA_ENABLE;
    while (REG_DMA3CNT & DMA_ENABLE) {}
}

INLINE void vblank_wait(void) {
    __asm__ volatile("swi 0x05" ::: "r0", "r1", "r2", "r3", "memory");
}
#endif

extern volatile u32 irq_vblank_count;

#endif
