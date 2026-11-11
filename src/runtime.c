/* Freestanding C runtime pieces the compiler may call into. */
#include <stddef.h>
#include "gba.h"

void *memcpy(void *dst, const void *src, size_t n) {
    u8 *d = dst; const u8 *s = src;
    if ((((u32)d | (u32)s | n) & 3) == 0) {
        u32 *dw = (u32 *)d; const u32 *sw = (const u32 *)s;
        for (n >>= 2; n; n--) *dw++ = *sw++;
        return dst;
    }
    while (n--) *d++ = *s++;
    return dst;
}

void *memmove(void *dst, const void *src, size_t n) {
    u8 *d = dst; const u8 *s = src;
    if (d < s) { while (n--) *d++ = *s++; }
    else { d += n; s += n; while (n--) *--d = *--s; }
    return dst;
}

void *memset(void *dst, int c, size_t n) {
    u8 *d = dst;
    if ((((u32)d | n) & 3) == 0) {
        u32 v = (u8)c; v |= v << 8; v |= v << 16;
        u32 *dw = (u32 *)d;
        for (n >>= 2; n; n--) *dw++ = v;
        return dst;
    }
    while (n--) *d++ = (u8)c;
    return dst;
}

int memcmp(const void *a, const void *b, size_t n) {
    const u8 *x = a, *y = b;
    for (; n; n--, x++, y++) if (*x != *y) return *x - *y;
    return 0;
}

void __aeabi_memcpy(void *d, const void *s, size_t n) { memcpy(d, s, n); }
void __aeabi_memcpy4(void *d, const void *s, size_t n) { memcpy(d, s, n); }
void __aeabi_memcpy8(void *d, const void *s, size_t n) { memcpy(d, s, n); }
void __aeabi_memmove(void *d, const void *s, size_t n) { memmove(d, s, n); }
void __aeabi_memmove4(void *d, const void *s, size_t n) { memmove(d, s, n); }
void __aeabi_memmove8(void *d, const void *s, size_t n) { memmove(d, s, n); }
void __aeabi_memset(void *d, size_t n, int c) { memset(d, c, n); }
void __aeabi_memset4(void *d, size_t n, int c) { memset(d, c, n); }
void __aeabi_memset8(void *d, size_t n, int c) { memset(d, c, n); }
void __aeabi_memclr(void *d, size_t n) { memset(d, 0, n); }
void __aeabi_memclr4(void *d, size_t n) { memset(d, 0, n); }
void __aeabi_memclr8(void *d, size_t n) { memset(d, 0, n); }

long long __aeabi_lmul(long long a, long long b) {
    unsigned long long ua = (unsigned long long)a, ub = (unsigned long long)b;
    u32 al = (u32)ua, ah = (u32)(ua >> 32), bl = (u32)ub, bh = (u32)(ub >> 32);
    /* 32x32 -> 64 by halves (no 64-bit multiply instruction in Thumb-1) */
    u32 a0 = al & 0xFFFF, a1 = al >> 16, b0 = bl & 0xFFFF, b1 = bl >> 16;
    u32 p00 = a0 * b0, p01 = a0 * b1, p10 = a1 * b0, p11 = a1 * b1;
    u32 mid = (p00 >> 16) + (p01 & 0xFFFF) + (p10 & 0xFFFF);
    u32 lo = (p00 & 0xFFFF) | (mid << 16);
    u32 hi = p11 + (p01 >> 16) + (p10 >> 16) + (mid >> 16);
    hi += al * bh + ah * bl;
    return (long long)(((unsigned long long)hi << 32) | lo);
}

long long __aeabi_llsl(long long a, int s) {
    u32 lo = (u32)a, hi = (u32)((unsigned long long)a >> 32);
    if (s >= 32) { hi = lo << (s - 32); lo = 0; }
    else if (s) { hi = (hi << s) | (lo >> (32 - s)); lo <<= s; }
    return (long long)(((unsigned long long)hi << 32) | lo);
}
long long __aeabi_llsr(long long a, int s) {
    u32 lo = (u32)a, hi = (u32)((unsigned long long)a >> 32);
    if (s >= 32) { lo = hi >> (s - 32); hi = 0; }
    else if (s) { lo = (lo >> s) | (hi << (32 - s)); hi >>= s; }
    return (long long)(((unsigned long long)hi << 32) | lo);
}
long long __aeabi_lasr(long long a, int s) {
    s32 hi = (s32)((unsigned long long)a >> 32); u32 lo = (u32)a;
    if (s >= 32) { lo = (u32)(hi >> (s - 32)); hi = hi >> 31; }
    else if (s) { lo = (lo >> s) | ((u32)hi << (32 - s)); hi >>= s; }
    return (long long)(((unsigned long long)(u32)hi << 32) | lo);
}
