#!/usr/bin/env python3
"""Generate macOS .icns icon from scratch (no SVG dependency)."""
import os
import glob
from PIL import Image, ImageDraw, ImageFont

iconset_dir = "icon.iconset"
os.makedirs(iconset_dir, exist_ok=True)


def find_font(size):
    """Find a usable TrueType font on the system."""
    # macOS font paths
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    # Also glob for any .ttf/.ttc in common font dirs
    for pattern in ["/System/Library/Fonts/*.ttf", "/System/Library/Fonts/*.ttc",
                    "/Library/Fonts/*.ttf", "/System/Library/Fonts/Supplemental/*.ttf"]:
        candidates.extend(glob.glob(pattern))

    for fp in candidates:
        try:
            font = ImageFont.truetype(fp, size)
            # Test that textbbox works
            font.getbbox("SS")
            return font
        except Exception:
            continue

    # Fallback: load_default with size (Pillow 10+)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


sizes = [16, 32, 64, 128, 256, 512]
for sz in sizes:
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Blue circle background (#2860E1)
    margin = int(sz * 0.05)
    draw.ellipse([margin, margin, sz - margin, sz - margin], fill=(0x28, 0x60, 0xE1, 255))
    # White "SS" text
    font_size = int(sz * 0.48)
    font = find_font(font_size)
    text = "SS"

    # Get text bounding box safely
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (sz - tw) // 2 - bbox[0]
        y = int(sz * 0.66) - th - bbox[1]
    except Exception:
        # Fallback: estimate text size
        tw = int(sz * 0.6)
        th = int(sz * 0.4)
        x = (sz - tw) // 2
        y = int(sz * 0.2)

    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    # Save normal and @2x
    img.save(os.path.join(iconset_dir, "icon_%dx%d.png" % (sz, sz)))
    if sz <= 256:
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img2 = img.resize((sz * 2, sz * 2), resample)
        img2.save(os.path.join(iconset_dir, "icon_%dx%d@2x.png" % (sz, sz)))

print("Icon PNGs generated in %s" % iconset_dir)
