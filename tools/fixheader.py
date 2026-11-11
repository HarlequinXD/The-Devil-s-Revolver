#!/usr/bin/env python3
"""Patch the GBA header checksum and pad the ROM to a 4-byte multiple."""
import sys
data = bytearray(open(sys.argv[1], 'rb').read())
chk = -(sum(data[0xA0:0xBD]) + 0x19) & 0xFF
data[0xBD] = chk
while len(data) % 4:
    data.append(0)
open(sys.argv[1], 'wb').write(data)
print('%s: %d bytes, header checksum %02X' % (sys.argv[1], len(data), chk))
