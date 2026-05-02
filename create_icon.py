"""Generates icon.ico for the TelegramManager exe."""
from PIL import Image, ImageDraw, ImageFont
import math, os

SIZES = [256, 128, 64, 48, 32, 16]


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Blue circle background
    margin = size * 0.04
    d.ellipse([margin, margin, size - margin, size - margin], fill="#2b91d1")

    # Paper-plane shape (simplified triangle + tail)
    s = size
    # Main triangle points (pointing right)
    cx, cy = s * 0.54, s * 0.50
    r = s * 0.30

    # Wing tip (right)
    p1 = (cx + r, cy)
    # Top-left
    p2 = (cx - r * 0.80, cy - r * 0.75)
    # Bottom-left
    p3 = (cx - r * 0.80, cy + r * 0.30)
    # Tail fold
    p4 = (cx - r * 0.10, cy + r * 0.10)

    d.polygon([p1, p2, p4, p3], fill="white")

    # Dark triangle (bottom fold)
    d.polygon([p1, p4, p3], fill="rgba(0,0,0,50)")

    return img


def main():
    frames = [draw_icon(s) for s in SIZES]
    out = os.path.join(os.path.dirname(__file__), "icon.ico")
    frames[0].save(out, format="ICO", sizes=[(s, s) for s in SIZES],
                   append_images=frames[1:])
    print(f"✓ icon.ico saved → {out}")


if __name__ == "__main__":
    main()
