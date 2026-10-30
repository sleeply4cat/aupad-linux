#!/usr/bin/env python3
"""Summarise a raw evdev capture from a multitouch screen.  usage: evdec.py <file>"""
import struct, sys

d = open(sys.argv[1], 'rb').read()
sz = 24
ABS = {0x2f: 'slot', 0x35: 'x', 0x36: 'y', 0x39: 'id'}
slots, cur, gestures, frames = {}, 0, [], []
active = {}
t0 = None
maxf = 0
for i in range(0, len(d) - sz + 1, sz):
    sec, usec, typ, code, val = struct.unpack('<qqHHi', d[i:i + sz])
    t = sec + usec / 1e6
    t0 = t0 or t
    if typ == 3 and code in ABS:
        n = ABS[code]
        if n == 'slot':
            cur = val
        elif n == 'id':
            if val < 0:
                g = active.pop(cur, None)
                if g:
                    g['end'] = t
                    gestures.append(g)
            else:
                active[cur] = {'slot': cur, 'start': t, 'pts': []}
                slots[cur] = {}
        elif cur in slots:
            slots[cur][n] = val
    elif typ == 0 and code == 0:
        for s, g in active.items():
            p = slots.get(s, {})
            if 'x' in p and 'y' in p:
                g['pts'].append((p['x'], p['y']))
        maxf = max(maxf, len(active))
        frames.append((t, len(active)))
print(f'{len(d) // sz} events, {len(frames)} frames, max simultaneous {maxf}')
if len(frames) > 1:
    print(f'rate while active: {len(frames) / max(frames[-1][0] - frames[0][0], 1e-3):.0f} frames/s overall')
for g in sorted(gestures, key=lambda g: g['start']):
    p = g['pts'] or [(-1, -1)]
    xs, ys = [a for a, _ in p], [b for _, b in p]
    print(f"t={g['start'] - t0:6.2f} {g['end'] - g['start']:5.2f}s slot {g['slot']} n={len(p):4} "
          f"start {p[0]} end {p[-1]} x {min(xs)}-{max(xs)} y {min(ys)}-{max(ys)}")
