"""
make_android_preview.py - Compose the Android UI preview images.

Tiles the on-device screenshots in assets/android-shots/ into
docs/android-ui-preview.jpg (the four portrait app screens) and frames the
landscape home-screen widget shot into docs/android-widget-preview.jpg. Both
are referenced from README.md. Re-run after replacing the source shots:

    python assets/make_android_preview.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SHOTS = os.path.join(_HERE, "android-shots")
_OUT = os.path.join(_ROOT, "docs", "android-ui-preview.jpg")
_WIDGET_OUT = os.path.join(_ROOT, "docs", "android-widget-preview.jpg")

# (source filename, caption) in left-to-right display order.
SCREENS = [
    ("01-list.png", "목록 보기"),
    ("02-detail.png", "자세히 · 앨범아트"),
    ("03-table.png", "표 보기 (다크)"),
    ("04-player.png", "재생 · 재생목록"),
]

# Home-screen widget preview: a landscape on-device crop, framed on its own
# (the portrait phone montage above cannot hold a wide widget shot).
WIDGET_SHOT = "05-widget.png"
WIDGET_CAPTION = "홈 화면 위젯 — 앨범아트 위 곡 정보 + 재생 컨트롤"
WIDGET_W = 900                   # width the widget shot is scaled to (px)

PHONE_H = 1040                   # height each phone shot is scaled to (px)
GAP = 44                         # horizontal gap between phones
PAD = 56                         # canvas padding
CAP_GAP = 20                     # gap between a phone and its caption
CAP_H = 70                       # vertical room reserved for captions
RADIUS = 30                      # phone corner rounding
BG = (255, 255, 255)
BORDER = (223, 223, 223)
CAP_FILL = (90, 90, 90)


def _font(size: int) -> ImageFont.FreeTypeFont:
    """Load a Hangul-capable TrueType font, falling back to PIL's default."""
    for name in ("malgun.ttf", "malgunbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except Exception:
            continue
    return ImageFont.load_default()


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    """Return *img* (RGBA) with rounded corners via an alpha mask."""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255
    )
    img.putalpha(mask)
    return img


def main() -> None:
    """Compose and save the Android preview montage."""
    phones = []
    for fname, caption in SCREENS:
        shot = Image.open(os.path.join(_SHOTS, fname)).convert("RGB")
        width = round(shot.width * PHONE_H / shot.height)
        shot = shot.resize((width, PHONE_H), Image.LANCZOS)
        phones.append((_rounded(shot, RADIUS), caption, width))

    total_w = sum(w for _, _, w in phones) + GAP * (len(phones) - 1) + PAD * 2
    total_h = PAD + PHONE_H + CAP_GAP + CAP_H + PAD
    canvas = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(canvas)
    font = _font(38)

    x = PAD
    for shot, caption, width in phones:
        canvas.paste(shot, (x, PAD), shot)
        draw.rounded_rectangle(
            [x, PAD, x + width - 1, PAD + PHONE_H - 1],
            radius=RADIUS, outline=BORDER, width=2,
        )
        text_w = draw.textlength(caption, font=font)
        draw.text((x + (width - text_w) / 2, PAD + PHONE_H + CAP_GAP),
                  caption, font=font, fill=CAP_FILL)
        x += width + GAP

    canvas.save(_OUT, quality=90)
    print(f"wrote {_OUT} ({canvas.size[0]}x{canvas.size[1]})")


def make_widget_preview() -> None:
    """Frame the landscape widget shot into docs/android-widget-preview.jpg."""
    shot = Image.open(os.path.join(_SHOTS, WIDGET_SHOT)).convert("RGB")
    height = round(shot.height * WIDGET_W / shot.width)
    shot = _rounded(shot.resize((WIDGET_W, height), Image.LANCZOS), RADIUS)

    total_w = WIDGET_W + PAD * 2
    total_h = PAD + height + CAP_GAP + CAP_H + PAD
    canvas = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(canvas)
    font = _font(38)

    canvas.paste(shot, (PAD, PAD), shot)
    draw.rounded_rectangle(
        [PAD, PAD, PAD + WIDGET_W - 1, PAD + height - 1],
        radius=RADIUS, outline=BORDER, width=2,
    )
    text_w = draw.textlength(WIDGET_CAPTION, font=font)
    draw.text((PAD + (WIDGET_W - text_w) / 2, PAD + height + CAP_GAP),
              WIDGET_CAPTION, font=font, fill=CAP_FILL)

    canvas.save(_WIDGET_OUT, quality=90)
    print(f"wrote {_WIDGET_OUT} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
    make_widget_preview()
