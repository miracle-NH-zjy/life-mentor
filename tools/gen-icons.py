#!/usr/bin/env python3
"""生成 PWA 图标：深青圆角底 + 白色对勾，4x 超采样抗锯齿。

    python tools/gen-icons.py
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "icons"

BG = (13, 110, 102)      # #0D6E66
FG = (255, 255, 255)
SS = 4                   # 超采样倍数


def write_png(path, w, h, pixels):
    raw = b"".join(b"\x00" + bytes(pixels[y]) for y in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9))
    data += chunk(b"IEND", b"")
    path.write_bytes(data)


def dist_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def rounded_rect_inside(x, y, r):
    """归一化坐标 (0..1)，判断点是否在圆角方形内。"""
    cx = min(max(x, r), 1 - r)
    cy = min(max(y, r), 1 - r)
    # 四角
    corner_x = r if x < r else (1 - r if x > 1 - r else x)
    corner_y = r if y < r else (1 - r if y > 1 - r else y)
    if (x < r or x > 1 - r) and (y < r or y > 1 - r):
        return ((x - corner_x) ** 2 + (y - corner_y) ** 2) ** 0.5 <= r
    return True


def make(size, radius_ratio, check_scale, out_name, transparent_bg=False):
    w = h = size
    # 对勾两点，围绕中心缩放
    def P(ax, ay):
        return (0.5 + (ax - 0.5) * check_scale, 0.5 + (ay - 0.5) * check_scale)

    a = P(0.315, 0.515)
    b = P(0.445, 0.645)
    c = P(0.700, 0.370)
    half = 0.058 * check_scale * 1.0

    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            acc_r = acc_g = acc_b = 0.0
            acc_a = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    ux = (x + (sx + 0.5) / SS) / w
                    uy = (y + (sy + 0.5) / SS) / h
                    inside_bg = rounded_rect_inside(ux, uy, radius_ratio)
                    d = min(dist_seg(ux, uy, *a, *b), dist_seg(ux, uy, *b, *c))
                    on_check = d <= half
                    if on_check:
                        acc_r += FG[0]; acc_g += FG[1]; acc_b += FG[2]; acc_a += 1
                    elif inside_bg:
                        acc_r += BG[0]; acc_g += BG[1]; acc_b += BG[2]; acc_a += 1
                    else:
                        acc_r += 245; acc_g += 244; acc_b += 241
            n = SS * SS
            # 圆角外 → 透明（alpha 通道不支持，这里用底色近似；maskable 版铺满）
            if transparent_bg:
                inside = rounded_rect_inside((x + 0.5) / w, (y + 0.5) / h, radius_ratio)
                if not inside:
                    row += bytes((245, 244, 241))
                    continue
            row += bytes((int(acc_r / n), int(acc_g / n), int(acc_b / n)))
        rows.append(row)
    write_png(OUT / out_name, w, h, rows)
    print("wrote", out_name, size)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make(192, 0.235, 1.0, "icon-192.png")
    make(512, 0.235, 1.0, "icon-512.png")
    # maskable：内容缩到安全区（80%），底色铺满整块
    make(512, 0.001, 0.78, "icon-maskable-512.png")
