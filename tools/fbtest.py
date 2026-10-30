#!/usr/bin/env python3
"""Make a raw XRGB8888 test pattern for the panel.  usage: fbtest.py <out.raw> [stride_bytes]
Corners: red TL, green TR, blue BL, white BR.  Middle: "TOP" text, 1-px checker, gradients."""
import sys

out = sys.argv[1]
W, H = 1200, 1920
STRIDE = int(sys.argv[2]) if len(sys.argv) > 2 else W * 4
FONT = {'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
        'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
        'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....']}
fb = bytearray(W * H * 4)


def px(x, y, r, g, b):
    i = (y * W + x) * 4
    fb[i:i + 4] = bytes((b, g, r, 0))


def rect(x0, y0, x1, y1, r, g, b):
    row = bytes((b, g, r, 0)) * (x1 - x0)
    for y in range(y0, y1):
        i = (y * W + x0) * 4
        fb[i:i + len(row)] = row


# 1-px white border: shows overscan or a shifted image
rect(0, 0, W, 1, 255, 255, 255); rect(0, H - 1, W, H, 255, 255, 255)
rect(0, 0, 1, H, 255, 255, 255); rect(W - 1, 0, W, H, 255, 255, 255)
C = 200
rect(1, 1, C, C, 255, 0, 0); rect(W - C, 1, W - 1, C, 0, 255, 0)
rect(1, H - C, C, H - 1, 0, 0, 255); rect(W - C, H - C, W - 1, H - 1, 255, 255, 255)
# text near the top edge of the buffer
s, x0, y0 = 40, (W - 3 * 6 * 40) // 2, 260
for n, ch in enumerate('TOP'):
    for j, line in enumerate(FONT[ch]):
        for i, c in enumerate(line):
            if c == '#':
                rect(x0 + n * 6 * s + i * s, y0 + j * s, x0 + n * 6 * s + (i + 1) * s, y0 + (j + 1) * s, 255, 255, 0)
# 1-px checker: uniform grey if sharp, moire or colour fringes if not
for y in range(620, 820):
    for x in range(200, W - 200):
        if (x + y) & 1:
            px(x, y, 255, 255, 255)
# gradients: red, green, blue, grey.  Bands show lost colour depth
for k, (r, g, b) in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1))):
    for x in range(W):
        v = x * 255 // (W - 1)
        rect(x, 900 + k * 180, x + 1, 1070 + k * 180, v * r, v * g, v * b)
pad = bytes(STRIDE - W * 4)
open(out, 'wb').write(b''.join(bytes(fb[y * W * 4:(y + 1) * W * 4]) + pad for y in range(H)))
