"""Build packaging/windows/chronos.ico from the chronos mark.

    pip install pillow
    python packaging/windows/make_icon.py

The mark is frontend/public/brand/chronos-mark-dark.svg:

    M100 0 H0 V100 H100 V64 H50 V36 H100 Z      square with a notch cut from the right
    M50 28 A22 22 0 1 1 49.99 28 Z               circle, centre (50,50), radius 22
    fill-rule: evenodd

so a point is painted when it is inside exactly one of the two shapes. It is
drawn from that geometry directly rather than rasterising the SVG, which
needs no SVG renderer and renders each icon size natively (much sharper at
16x16 than shrinking one large image).

Placement: the mark is near-black (#232326) on transparent, which vanishes on
Windows' dark taskbar, so it sits on a white rounded tile. It stays large —
78% of the tile — so the notch and the circle are still readable at 16 px.
(The old favicon shrank it to 67% and inverted it, and it read as a blob.)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

INK = (0x23, 0x23, 0x26, 255)
TILE = (255, 255, 255, 255)
EDGE = (0xD6, 0xD6, 0xDC, 255)  # hairline so the white tile has an edge on white backgrounds
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SUPERSAMPLE = 8
OUT = Path(__file__).with_name("chronos.ico")


def mark_mask(px: int) -> Image.Image:
    """The mark as a 1-bit mask, px x px, in 0..100 mark units."""
    s = px / 100.0
    body = Image.new("1", (px, px), 0)
    d = ImageDraw.Draw(body)
    d.rectangle([0, 0, px - 1, px - 1], fill=1)
    d.rectangle([round(50 * s), round(36 * s), px - 1, round(64 * s) - 1], fill=0)  # the notch
    circle = Image.new("1", (px, px), 0)
    ImageDraw.Draw(circle).ellipse(
        [round(28 * s), round(28 * s), round(72 * s) - 1, round(72 * s) - 1], fill=1
    )
    return ImageChops.logical_xor(body, circle)  # evenodd


def render(size: int) -> Image.Image:
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = round(big * 0.22)
    if size >= 32:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=radius, fill=EDGE)
        inset = SUPERSAMPLE  # one icon pixel
        d.rounded_rectangle(
            [inset, inset, big - 1 - inset, big - 1 - inset], radius=radius - inset, fill=TILE
        )
    else:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=radius, fill=TILE)

    # Size and offset in whole icon pixels, so the mark's outer edges land on
    # pixel boundaries instead of blurring across two.
    mark_px = round(size * 0.78)
    offset = (size - mark_px) // 2
    mask = mark_mask(mark_px * SUPERSAMPLE).convert("L")
    ink = Image.new("RGBA", mask.size, INK)
    img.paste(ink, (offset * SUPERSAMPLE, offset * SUPERSAMPLE), mask)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    images = [render(s) for s in SIZES]
    largest = images[-1]
    largest.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, sizes {SIZES})")


if __name__ == "__main__":
    main()
