"""Render the gold disc brand mark to favicon and app icon PNGs."""
import math
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "arm", "ui", "static", "img")
BG = (18, 18, 18, 255)


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


STOPS = [(0.0, hexrgb("f3d07a")), (0.42, hexrgb("e0b04a")), (1.0, hexrgb("8a6a28"))]


def color_at(t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    for i in range(len(STOPS) - 1):
        t0, c0 = STOPS[i]
        t1, c1 = STOPS[i + 1]
        if t <= t1:
            u = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(round(c0[j] + (c1[j] - c0[j]) * u)) for j in range(3))
    return STOPS[-1][1]


def render_disc(size, background=BG, padding_ratio=0.08, supersample=4):
    width = size * supersample
    canvas = Image.new("RGBA", (width, width), background)
    pixels = canvas.load()
    pad = width * padding_ratio
    inner = width - 2 * pad

    def unit(value):
        return pad + (value / 32.0) * inner

    cx, cy = unit(16), unit(16)
    gx, gy = unit(1.4 + 0.36 * 29.2), unit(1.4 + 0.30 * 29.2)
    gradient_r = (0.72 * 29.2 / 32.0) * inner
    disc_r = (14.6 / 32.0) * inner

    for y in range(width):
        for x in range(width):
            dx = x + 0.5 - cx
            dy = y + 0.5 - cy
            dist = math.hypot(dx, dy)
            if dist > disc_r + 0.75:
                continue
            t = math.hypot((x + 0.5) - gx, (y + 0.5) - gy) / gradient_r if gradient_r else 0
            rgb = color_at(t)
            if dist <= disc_r - 0.5:
                alpha = 255
            else:
                alpha = int(max(0, min(255, 255 * (disc_r + 0.5 - dist))))
            old = pixels[x, y]
            mix = alpha / 255.0
            pixels[x, y] = (
                int(rgb[0] * mix + old[0] * (1 - mix)),
                int(rgb[1] * mix + old[1] * (1 - mix)),
                int(rgb[2] * mix + old[2] * (1 - mix)),
                int(old[3] + (255 - old[3]) * mix) if background[3] else alpha,
            )

    def ring(radius_u, color, width_u, opacity):
        radius = (radius_u / 32.0) * inner
        stroke = max(1, int(round((width_u / 32.0) * inner)))
        overlay = Image.new("RGBA", (width, width), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=color + (int(round(255 * opacity)),),
            width=stroke,
        )
        return overlay

    for overlay in (
        ring(11.2, hexrgb("121212"), 0.7, 0.16),
        ring(8.1, hexrgb("f7e7b8"), 0.8, 0.40),
        ring(5.4, hexrgb("121212"), 0.7, 0.20),
    ):
        canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    hub_r = (3.35 / 32.0) * inner
    hub_w = max(1, int(round((1.15 / 32.0) * inner)))
    draw.ellipse(
        [cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
        fill=hexrgb("1a1a1a") + (255,),
        outline=hexrgb("c49a3c") + (255,),
        width=hub_w,
    )
    dot_r = (1.2 / 32.0) * inner
    draw.ellipse(
        [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
        fill=hexrgb("e0b04a") + (255,),
    )
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def save(image, name):
    path = os.path.join(OUT, name)
    image.save(path, "PNG")
    print(name, image.size, os.path.getsize(path))


def main():
    os.makedirs(OUT, exist_ok=True)
    save(render_disc(16, padding_ratio=0.04), "favicon-16x16.png")
    save(render_disc(32, padding_ratio=0.05), "favicon-32x32.png")
    save(render_disc(32, padding_ratio=0.05), "favicon.png")
    ico = render_disc(32, padding_ratio=0.05)
    ico.save(os.path.join(OUT, "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32)])
    print("favicon.ico", os.path.getsize(os.path.join(OUT, "favicon.ico")))
    save(render_disc(180, padding_ratio=0.12), "apple-touch-icon.png")
    save(render_disc(192, padding_ratio=0.12), "android-chrome-192x192.png")
    save(render_disc(512, padding_ratio=0.12), "android-chrome-512x512.png")
    save(render_disc(80, padding_ratio=0.08), "arm80.png")
    save(render_disc(80, padding_ratio=0.08), "arm80nw.png")
    save(render_disc(40, padding_ratio=0.08), "arm40nw.png")


if __name__ == "__main__":
    main()
