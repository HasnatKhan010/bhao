"""Generate Bhao app icons — geometric, brand-consistent, no font shaping needed.

192/512 for the manifest, maskable 512 (extra padding), apple-touch 180, favicon 32.
"""

from __future__ import annotations

from PIL import Image, ImageDraw


def rounded_gradient(size: int, radius: int, pad: float = 0.0) -> Image.Image:
    """Emerald gradient rounded square with optional extra padding (maskable)."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    top, bottom = (4, 120, 87), (6, 95, 70)  # emerald-700 -> emerald-800
    for y in range(s):
        f = y / s
        gd.line([(0, y), (s, y)], fill=tuple(int(a + (b - a) * f) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (s, s), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    if pad:  # maskable: scale the artwork into the safe zone
        inner = int(s * (1 - pad))
        img = img.resize((inner, inner), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (6, 95, 70, 255))
        off = (size - inner) // 2
        canvas.paste(img, (off, off))
        img = canvas
    return img


def draw_sparkline(img: Image.Image, scale: float = 1.0) -> None:
    """White price sparkline with a forecast dot — the banner motif."""
    d = ImageDraw.Draw(img)
    s = img.size[0]
    pts = [(0.19, 0.76), (0.30, 0.72), (0.42, 0.75), (0.54, 0.67),
           (0.66, 0.70), (0.78, 0.62), (0.87, 0.63)]  # observed
    fc = [(0.87, 0.63), (0.925, 0.545)]  # forecast (dashed feel via two segments)
    line = [(round(x * s), round(y * s)) for x, y in pts]
    d.line(line, fill=(255, 255, 255, 255), width=max(3, int(s * 0.02)), joint="curve")
    # forecast band
    band = line[-1:] + [(round(x * s), round(y * s)) for x, y in fc]
    d.line(band, fill=(110, 231, 183, 220), width=max(3, int(s * 0.018)), joint="curve")
    x, y = line[-1]
    r = max(4, int(s * 0.016))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
    fx, fy = band[-1]
    d.ellipse([fx - r, fy - r, fx + r, fy + r], outline=(110, 231, 183, 255), width=max(2, int(s * 0.012)))


def make(size: int, maskable: bool = False) -> Image.Image:
    img = rounded_gradient(size, radius=int(size * 0.19), pad=0.12 if maskable else 0.0)
    draw_sparkline(img)
    return img


out = "web/public/icons"
make(512).save(f"{out}/icon-512.png", optimize=True)
make(192).save(f"{out}/icon-192.png", optimize=True)
make(512, maskable=True).save(f"{out}/icon-maskable-512.png", optimize=True)
make(180).save(f"{out}/apple-touch-icon.png", optimize=True)
make(32).save(f"{out}/favicon-32.png", optimize=True)
print("icons generated")
