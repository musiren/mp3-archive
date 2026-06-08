"""
make_presplash.py - Generate the Android loading (presplash) image.

Builds assets/presplash.png: a full-white screen showing the app icon, the app
name, and the version (read from buildozer.spec). python-for-android shows this
single image (centred on android.presplash_color) while the app loads, so all
of the loading-screen content lives in this one composed image. Re-run after
bumping the version:

    python assets/make_presplash.py
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_ICON = os.path.join(_HERE, "icon.png")
_OUT = os.path.join(_HERE, "presplash.png")
sys.path.insert(0, os.path.join(_ROOT, "src"))

SIZE = 1024                      # square canvas; p4a centres it on white
NAME = "MP3 Archive"


def _read_version() -> str:
    """Return the latest NEWS version (e.g. "v20260608"), matching the About box."""
    try:
        from ui_util import latest_news_version
        with open(os.path.join(_ROOT, "NEWS"), encoding="utf-8") as fh:
            version = latest_news_version(fh.read())
        if version:
            return version
    except Exception:
        pass
    return "v1.0.0"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a TrueType font at *size*, falling back to PIL's default."""
    names = (["arialbd.ttf", "segoeuib.ttf"] if bold
             else ["arial.ttf", "segoeui.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except Exception:
            continue
    return ImageFont.load_default()


def _centre(draw: ImageDraw.ImageDraw, text: str, font, y: int, fill) -> None:
    """Draw *text* horizontally centred on the canvas at vertical *y*."""
    width = draw.textlength(text, font=font)
    draw.text(((SIZE - width) / 2, y), text, font=font, fill=fill)


def main() -> None:
    """Compose and save the presplash image."""
    version = _read_version()
    canvas = Image.new("RGB", (SIZE, SIZE), "white")

    icon = Image.open(_ICON).convert("RGBA").resize((460, 460), Image.LANCZOS)
    canvas.paste(icon, ((SIZE - 460) // 2, 170), icon)

    draw = ImageDraw.Draw(canvas)
    _centre(draw, NAME, _load_font(78, bold=True), 690, (33, 33, 33))
    _centre(draw, version, _load_font(46), 800, (120, 120, 120))
    _centre(draw, "Loading...", _load_font(42), 882, (150, 150, 150))

    canvas.save(_OUT)
    print(f"wrote {_OUT} (version {version})")


if __name__ == "__main__":
    main()
