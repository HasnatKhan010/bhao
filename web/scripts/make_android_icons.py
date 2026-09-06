"""Generate Android launcher icons for Bhao into web/android/app/src/main/res.

Legacy mipmaps (all densities) + adaptive icon (foreground PNG + background
color resource) so the icon looks right on every launcher from Android 8+.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_icons import draw_sparkline, rounded_gradient  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

RES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"

DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
ADAPTIVE = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}


def legacy_icon(size: int) -> Image.Image:
    """Full-bleed rounded-square icon (legacy launchers)."""
    img = rounded_gradient(size, radius=int(size * 0.19))
    draw_sparkline(img)
    return img


def adaptive_foreground(size: int) -> Image.Image:
    """Transparent canvas; artwork inside the inner 66% safe zone."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = int(size * 0.62)
    art = rounded_gradient(inner, radius=int(inner * 0.22))
    draw_sparkline(art)
    off = (size - inner) // 2
    img.paste(art, (off, off), art)
    return img


def adaptive_background(size: int) -> Image.Image:
    """Solid emerald background layer."""
    img = Image.new("RGBA", (size, size), (6, 95, 70, 255))
    return img


def main() -> None:
    for density, size in DENSITIES.items():
        d = RES / f"mipmap-{density}"
        d.mkdir(parents=True, exist_ok=True)
        legacy_icon(size).save(d / "ic_launcher.png", optimize=True)
        legacy_icon(size).save(d / "ic_launcher_round.png", optimize=True)
    for density, size in ADAPTIVE.items():
        d = RES / f"mipmap-{density}"
        adaptive_foreground(size).save(d / "ic_launcher_foreground.png", optimize=True)
        adaptive_background(size).save(d / "ic_launcher_background.png", optimize=True)

    vals = RES / "values"
    vals.mkdir(parents=True, exist_ok=True)
    (vals / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n  <color name=\"ic_launcher_background\">#065F46</color>\n</resources>\n",
        encoding="utf-8",
    )
    print("launcher icons written to", RES)


if __name__ == "__main__":
    main()
