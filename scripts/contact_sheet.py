# -*- coding: utf-8 -*-
"""Lay candidates out in a labelled grid (plus an optional small-size strip) for review.

    python contact_sheet.py <dir-or-images...> --out sheet.png [--cell 384] [--cols 4] [--small 96]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXTS = {".png", ".jpg", ".jpeg", ".webp"}

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _collect(inputs: list[str], out: Path) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in EXTS)
        elif p.suffix.lower() in EXTS:
            files.append(p)
    return [f for f in files if f.resolve() != out.resolve()]


def _checker(size: tuple[int, int], step: int = 12) -> Image.Image:
    bg = Image.new("RGB", size, (235, 235, 235))
    draw = ImageDraw.Draw(bg)
    for y in range(0, size[1], step):
        for x in range((y // step) % 2 * step, size[0], step * 2):
            draw.rectangle([x, y, x + step - 1, y + step - 1], fill=(205, 205, 205))
    return bg


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("msyh.ttc", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cell", type=int, default=384)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--small", type=int, default=0, help="额外一行小尺寸预览的边长，0 关闭")
    args = parser.parse_args()

    out = Path(args.out)
    files = _collect(args.inputs, out)
    if not files:
        print("no images", file=sys.stderr)
        return 1
    cols = min(args.cols, len(files))
    rows = (len(files) + cols - 1) // cols
    label_h = 28
    small_h = args.small + 16 if args.small else 0
    sheet = Image.new("RGB", (cols * args.cell, rows * (args.cell + label_h) + small_h), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    font = _font(16)

    for i, f in enumerate(files):
        with Image.open(f) as img:
            img = img.convert("RGBA")
            label = f"{i + 1}. {f.name} {img.width}x{img.height}"
            img.thumbnail((args.cell, args.cell))
            x, y = (i % cols) * args.cell, (i // cols) * (args.cell + label_h)
            tile = _checker((args.cell, args.cell))
            tile.paste(img, ((args.cell - img.width) // 2, (args.cell - img.height) // 2), img)
            sheet.paste(tile, (x, y))
            draw.text((x + 6, y + args.cell + 5), label, fill=(30, 30, 30), font=font)
            if args.small:
                thumb = img.copy()
                thumb.thumbnail((args.small, args.small))
                sx = 8 + i * (args.small + 8)
                if sx + args.small <= sheet.width:
                    sheet.paste(_checker(thumb.size, 6), (sx, sheet.height - small_h + 8))
                    sheet.paste(thumb, (sx, sheet.height - small_h + 8), thumb)

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"{len(files)} images -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
