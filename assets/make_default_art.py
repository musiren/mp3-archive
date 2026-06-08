"""
make_default_art.py - Generate the default "no album art" placeholder.

Builds src/default_art.png: a square blue-grey tile with a white music note,
shown on the player tab when the current track has no embedded album art. It
lives under src/ (not assets/) so python-for-android bundles it into the APK
(source.dir = src, source.include_exts includes png) and the app can load it at
runtime. Re-run with:

    python assets/make_default_art.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_OUT = os.path.join(_ROOT, "src", "default_art.png")

SIZE = 512
BG = (69, 90, 100)        # blue-grey (#455A64), readable in light or dark theme
GLYPH = "♫"          # ♫ beamed eighth notes


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a font that carries the music-note glyph, else PIL's default."""
    for name in ("seguisym.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except Exception:
            continue
    return ImageFont.load_default()


def main() -> None:
    """Compose and save the default album-art placeholder."""
    canvas = Image.new("RGB", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(canvas)
    font = _load_font(300)
    bbox = draw.textbbox((0, 0), GLYPH, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SIZE - tw) / 2 - bbox[0], (SIZE - th) / 2 - bbox[1]),
              GLYPH, font=font, fill=(255, 255, 255))
    canvas.save(_OUT)
    print(f"wrote {_OUT}")


if __name__ == "__main__":
    main()
