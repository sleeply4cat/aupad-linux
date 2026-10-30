#!/usr/bin/env python3
"""Split userdata on LUN 0: shrink it in place and add 'pmos' behind it.  Writes new GPT images, touches no device.
usage: gptsplit.py <primary.bin> <backup.bin> <userdata_GiB> <out_primary> <out_backup>"""
import struct, sys, uuid, zlib

SEC = 4096
FS_LINUX = uuid.UUID('0FC63DAF-8483-4772-8E79-3D69D8477DE4')
prim, back = bytearray(open(sys.argv[1], 'rb').read()), bytearray(open(sys.argv[2], 'rb').read())
gib = int(sys.argv[3])
hdr = prim[SEC:2 * SEC]
assert hdr[:8] == b'EFI PART', 'no primary header'
hsize, = struct.unpack_from('<I', hdr, 12)
cur, alt, first, last = struct.unpack_from('<QQQQ', hdr, 24)
ent_lba, n_ent, ent_size, ent_crc = struct.unpack_from('<QIII', hdr, 72)
print(f'cur {cur} alt {alt} usable {first}..{last} entries lba {ent_lba} n {n_ent} size {ent_size}')
assert cur == 1 and ent_lba == 2 and ent_size == 128
bytes_ent = n_ent * ent_size
assert bytes_ent <= 4 * SEC, 'entries do not fit the 6 sector dump'
ents = bytearray(prim[2 * SEC:2 * SEC + bytes_ent])
assert zlib.crc32(ents) == ent_crc, 'bad entry crc'
assert zlib.crc32(bytes(hdr[:16]) + b'\0' * 4 + bytes(hdr[20:hsize])) == struct.unpack_from('<I', hdr, 16)[0], 'bad hdr crc'

bh = back[-SEC:]
assert bh[:8] == b'EFI PART' and struct.unpack_from('<Q', bh, 24)[0] == alt
bent_lba, = struct.unpack_from('<Q', bh, 72)
assert bent_lba == alt - 4 and back[:bytes_ent] == ents, 'backup entries differ'

used, ud = [], None
for i in range(n_ent):
    e = ents[i * 128:(i + 1) * 128]
    if e[:16] == b'\0' * 16:
        continue
    s, t = struct.unpack_from('<QQ', e, 32)
    name = e[56:128].decode('utf-16-le').rstrip('\0')
    used.append((s, t, name, i))
    if name == 'userdata':
        ud = i
print('sorted tail:', [(n, s, t) for s, t, n, _ in sorted(used)[-3:]])
assert ud is not None and sum(1 for u in used if u[2] == 'pmos') == 0
s, t = struct.unpack_from('<QQ', ents, ud * 128 + 32)
assert (s, t) == max(u[:2] for u in used), 'userdata is not the last partition'
free = next(i for i in range(n_ent) if ents[i * 128:i * 128 + 16] == b'\0' * 16)
new_t = s + gib * (1 << 30) // SEC - 1
p_s = (new_t + 1 + 255) & ~255		# 1 MiB aligned
assert s < new_t < p_s < t
print(f'userdata {s}..{t} ({(t - s + 1) * SEC >> 30} GiB) -> {s}..{new_t} ({gib} GiB)')
print(f'pmos     slot {free}: {p_s}..{t} ({(t - p_s + 1) * SEC >> 30} GiB)')
struct.pack_into('<Q', ents, ud * 128 + 40, new_t)
e = FS_LINUX.bytes_le + uuid.uuid4().bytes_le + struct.pack('<QQQ', p_s, t, 0) + 'pmos'.encode('utf-16-le').ljust(72, b'\0')
ents[free * 128:(free + 1) * 128] = e

crc = zlib.crc32(ents)
def fix(h):
    struct.pack_into('<I', h, 88, crc)
    struct.pack_into('<I', h, 16, 0)
    struct.pack_into('<I', h, 16, zlib.crc32(bytes(h[:hsize])))
fix(hdr)
prim[SEC:2 * SEC] = hdr
prim[2 * SEC:2 * SEC + bytes_ent] = ents
back[:bytes_ent] = ents
fix(bh)
back[-SEC:] = bh
open(sys.argv[4], 'wb').write(prim)
open(sys.argv[5], 'wb').write(back)
print('ok, changed entries:', sum(ents[i * 128:(i + 1) * 128] != bytes(open(sys.argv[1], 'rb').read()[2 * SEC + i * 128:2 * SEC + (i + 1) * 128]) for i in range(n_ent)))
