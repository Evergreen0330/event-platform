#!/usr/bin/env python3
"""生成 og:image（1200x630 JPEG，quality 90）。

按 skill 的坑位清单：社交平台的 og:image 优先用 JPEG，PNG 同图体积常大 5 倍，SVG 不被支持。
用法：python3 tools/make-og-cover.py [输出路径]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "og-cover.jpg"

BG = (18, 20, 26)
FG = (230, 232, 238)
ACCENT = (78, 201, 138)
MUTED = (152, 160, 176)


def font(size, bold=False):
    for name in (("PingFang.ttc" if not bold else "PingFang.ttc"),
                 "Hiragino Sans GB.ttc", "Arial Unicode.ttf", "Arial.ttf"):
        for base in ("/System/Library/Fonts/", "/Library/Fonts/", "/System/Library/Fonts/Supplemental/"):
            p = Path(base + name)
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    continue
    return ImageFont.load_default()


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# 左侧强调色竖条
d.rectangle([72, 150, 82, 480], fill=ACCENT)

d.text((120, 168), "GitHub Pages Deploy", font=font(64, bold=True), fill=FG)
d.text((120, 258), "Skill 全链路自检", font=font(46), fill=ACCENT)
d.text((120, 350), "建仓 → 推送 → 开 Pages → 三层线上验证", font=font(28), fill=MUTED)
d.text((120, 400), "api.github.com 兜底路径 · main /docs 发布", font=font(28), fill=MUTED)
d.text((120, 500), "Evergreen0330 / event-platform", font=font(24), fill=MUTED)

img.save(OUT, "JPEG", quality=90, optimize=True)
print(f"已生成 {OUT}  {OUT.stat().st_size / 1024:.1f} KB")
