#!/usr/bin/env python3
"""Generate synthetic PNG documents for the Bayyan claims audit."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "docs" / "test-fixtures" / "bayyan-claims-audit"
MANIFEST = FIXTURE_DIR / "documents.json"
OUTPUT_DIR = FIXTURE_DIR / "generated"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: int,
    fill: tuple[int, int, int],
    line_gap: int,
) -> int:
    max_chars = max(24, width // 18)
    for line in textwrap.wrap(text, width=max_chars) or [""]:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def render_document(item: dict) -> None:
    width, height = 1500, 2100
    img = Image.new("RGB", (width, height), "#fffdf7")
    draw = ImageDraw.Draw(img)

    title_font = _font(56, bold=True)
    heading_font = _font(34, bold=True)
    body_font = _font(30)
    small_font = _font(24)

    green = (31, 94, 75)
    ink = (40, 38, 32)
    muted = (106, 99, 86)
    line = (220, 208, 188)

    draw.rectangle((56, 56, width - 56, height - 56), outline=line, width=4)
    draw.rectangle((56, 56, width - 56, 220), fill="#e8f2ea", outline=line, width=3)
    draw.text((96, 92), "Bayyan Claims Audit - Synthetic Fixture", font=heading_font, fill=green)
    draw.text((96, 148), "Demo document only - no real taxpayer data", font=small_font, fill=muted)

    y = 300
    draw.text((96, y), item["title"], font=title_font, fill=ink)
    y += 90
    draw.line((96, y, width - 96, y), fill=line, width=3)
    y += 54

    header_rows = [
        ("Vendor", item["vendor"]),
        ("Date", item["date"]),
        ("Document type", item["document_type"]),
        ("Expected category", item["expected_category"]),
        ("Expected amount", f'{item["expected_amount"]:,.3f} JD'),
    ]
    for label, value in header_rows:
        draw.text((96, y), f"{label}:", font=heading_font, fill=green)
        draw.text((430, y), str(value), font=body_font, fill=ink)
        y += 58

    y += 30
    draw.text((96, y), "Visible document text", font=heading_font, fill=green)
    y += 58

    for line_text in item["lines"]:
        y = _draw_wrapped(
            draw,
            f"- {line_text}",
            x=120,
            y=y,
            font=body_font,
            width=width - 240,
            fill=ink,
            line_gap=14,
        )
        y += 10

    draw.line((96, height - 220, width - 96, height - 220), fill=line, width=2)
    footer = (
        "Extraction target: vendor, amount, date, category, document_type, "
        "confidence, raw_text."
    )
    _draw_wrapped(
        draw,
        footer,
        x=96,
        y=height - 178,
        font=small_font,
        width=width - 192,
        fill=muted,
        line_gap=8,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT_DIR / item["filename"], format="PNG", optimize=True)


def main() -> None:
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in items:
        render_document(item)
    print(f"Generated {len(items)} fixture PNGs in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
