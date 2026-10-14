"""The Android app's images, made from the website's logo (frontend/icons/icon-512.png):

    mipmap-*/ic_launcher.png, ic_launcher_round.png   the icon on Android 5.0 to 7.1
    mipmap-*/ic_launcher_foreground.png               the logo on Android 8.0 and newer, which
                                                      lays it on white and cuts the shape
    mipmap-*/ic_launcher_monochrome.png               the one-colour logo for themed icons (13+)
    drawable-*/ic_notification.png                    the white logo in the status bar
    drawable-*/splash.png                             the logo shown while the app opens

Run after changing the logo:  python3 android/tools/make_icons.py   (needs Pillow and numpy)
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "..", "..", "frontend", "icons", "icon-512.png")
RES = os.path.join(HERE, "..", "app", "src", "main", "res")
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def logo_on_transparent():
    """The logo with its white background made see-through. Each pixel keeps the colour that,
    laid over white, gives the original back, so the soft edges stay smooth."""
    rgb = np.asarray(Image.open(LOGO).convert("RGB")).astype(np.float64) / 255
    alpha = (1 - rgb).max(axis=2)
    alpha[alpha < 0.06] = 0  # the faint grey specks of the white background
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    colour = np.clip((rgb - (1 - alpha[..., None])) / safe, 0, 1)
    image = Image.fromarray(np.uint8(np.dstack([colour, alpha]) * 255 + 0.5), "RGBA")
    return image.crop(image.getbbox())


def silhouette(logo):
    """The logo in one colour (white), solid where the logo is, for the status bar and themed icons."""
    alpha = np.asarray(logo)[..., 3].astype(np.float64) / 255
    solid = np.clip((alpha - 0.15) / 0.25, 0, 1)
    white = np.full(alpha.shape + (3,), 255, np.uint8)
    return Image.fromarray(np.dstack([white, np.uint8(solid * 255 + 0.5)]), "RGBA")


def placed(logo, canvas_px, logo_px):
    """The logo, logo_px across, centred on a transparent square canvas_px across."""
    scale = logo_px / max(logo.size)
    size = (max(1, round(logo.width * scale)), max(1, round(logo.height * scale)))
    canvas = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    canvas.alpha_composite(logo.resize(size, Image.LANCZOS),
                           ((canvas_px - size[0]) // 2, (canvas_px - size[1]) // 2))
    return canvas


def legacy_icon(logo, px):
    """Android 5.0 to 7.1: a white disc with a soft shadow, the logo on it."""
    big = px * 4  # drawn large, then shrunk, for smooth edges
    icon = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    disc = round(big * 44 / 48)
    corner = (big - disc) // 2
    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([corner, corner + big // 96, corner + disc, corner + disc + big // 96],
                                   fill=(0, 0, 0, 70))
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(big / 96)))
    ImageDraw.Draw(icon).ellipse([corner, corner, corner + disc, corner + disc], fill=(255, 255, 255, 255))
    icon.alpha_composite(placed(logo, big, round(big * 37 / 48)))
    return icon.resize((px, px), Image.LANCZOS)


def save(image, folder, name, one_colour=False):
    """Saved small: the white silhouettes as grey + transparency, the coloured images with
    a palette of 256 colours (a third of the size, and the APK is downloaded on mobile data)."""
    if one_colour:
        image = image.convert("LA")
    else:
        image = image.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
    os.makedirs(os.path.join(RES, folder), exist_ok=True)
    image.save(os.path.join(RES, folder, name), optimize=True)


def main():
    logo = logo_on_transparent()
    mono = silhouette(logo)
    for density, factor in DENSITIES.items():
        legacy = legacy_icon(logo, round(48 * factor))
        save(legacy, f"mipmap-{density}", "ic_launcher.png")
        save(legacy, f"mipmap-{density}", "ic_launcher_round.png")
        # Adaptive icons: a 108dp square of which about 72dp shows; keep the logo in the
        # 66dp circle that every launcher shape leaves whole
        save(placed(logo, round(108 * factor), round(62 * factor)), f"mipmap-{density}", "ic_launcher_foreground.png")
        save(placed(mono, round(108 * factor), round(58 * factor)), f"mipmap-{density}", "ic_launcher_monochrome.png", True)
        save(placed(mono, round(24 * factor), round(22 * factor)), f"drawable-{density}", "ic_notification.png", True)
        save(placed(logo, round(112 * factor), round(112 * factor)), f"drawable-{density}", "splash.png")
    adaptive = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                '    <background android:drawable="@color/ic_launcher_background" />\n'
                '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
                '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />\n'
                '</adaptive-icon>\n')
    os.makedirs(os.path.join(RES, "mipmap-anydpi-v26"), exist_ok=True)
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        with open(os.path.join(RES, "mipmap-anydpi-v26", name), "w", encoding="utf-8") as f:
            f.write(adaptive)
    print("icons written to", os.path.relpath(RES))


if __name__ == "__main__":
    main()
