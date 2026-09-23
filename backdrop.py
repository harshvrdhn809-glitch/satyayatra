"""
Bulletin ke liye backdrop banata hai — bina kisi photo ke.

Kyun: kisi bhi khaas Indian khabar ke liye free-licensed sateek photo maujood
hi nahi hoti. Isliye visual ka bhaar design uthata hai, tasveer nahi. Yahan
sirf texture banti hai; saara text libass se aata hai taaki Devanagari sahi
shape ho.

Har style 1920x1080 ka PNG deta hai. Koi network nahi, koi asset nahi.
"""

import math
import random

from PIL import Image, ImageDraw, ImageFilter

# Naap do tarah ka hai: bulletin 16:9 ka, aur Reel 9:16 ka.
#
# Ye module-level hai kyunki poore render mein naap ek hi jagah se aata hai
# (render_core yahin se uthata hai). Ek waqt mein ek hi video banti hai,
# isliye render se pehle set_size() bula kar naap badal dena surakshit hai -
# aur yahi sabse saada tareeka hai ki ek hi code dono roop bana sake.
LAND = (1920, 1080)
REEL = (1080, 1920)

W, H = LAND


def set_size(vertical=False):
    """Aage ke sab kaam is naap par honge. (chaudai, oonchai) lauta ta hai."""
    global W, H
    W, H = REEL if vertical else LAND
    return W, H

# Khabar ki shreni se rang. Yahi ek cheez har video ko alag pehchaan deti hai
# bina bhadkile hue.
PALETTES = {
    "politics":  {"bg": (11, 18, 32),  "accent": (200, 16, 46),  "glow": (32, 54, 96)},
    "crime":     {"bg": (16, 14, 18),  "accent": (198, 40, 40),  "glow": (72, 32, 38)},
    "education": {"bg": (10, 22, 30),  "accent": (0, 137, 150),  "glow": (18, 66, 78)},
    "economy":   {"bg": (12, 20, 16),  "accent": (26, 138, 90),  "glow": (22, 70, 52)},
    "weather":   {"bg": (10, 18, 34),  "accent": (0, 122, 194),  "glow": (18, 58, 104)},
    "sport":     {"bg": (14, 18, 14),  "accent": (216, 122, 20), "glow": (70, 52, 20)},
    "civic":     {"bg": (13, 17, 26),  "accent": (140, 82, 190), "glow": (48, 38, 84)},
    "default":   {"bg": (11, 18, 32),  "accent": (200, 16, 46),  "glow": (30, 44, 78)},
}


def palette(category):
    return PALETTES.get(str(category or "").strip().lower(), PALETTES["default"])


def _base(pal, seed):
    """Sapaat rang nahi — halka sa radial glow, taaki frame mari hui na lage."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), pal["bg"])
    glow = Image.new("RGB", (W // 8, H // 8), pal["bg"])
    d = ImageDraw.Draw(glow)
    cx = rnd.uniform(0.55, 0.85) * (W // 8)
    cy = rnd.uniform(0.15, 0.45) * (H // 8)
    r = (W // 8) * 0.62
    steps = 34
    for i in range(steps, 0, -1):
        t = i / float(steps)
        col = tuple(int(pal["bg"][k] + (pal["glow"][k] - pal["bg"][k]) * (1 - t) ** 1.7)
                    for k in range(3))
        d.ellipse([cx - r * t, cy - r * t, cx + r * t, cy + r * t], fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BICUBIC)
    return glow


def style_grid(category, seed=0):
    """DIRECTION 1 — 'Grid'
    Baareek dot grid, upar se accent ka halka wash. Shaant, bharosemand,
    news-graphics jaisa. Headline ke peechhe kuch bhi shor nahi karta."""
    pal = palette(category)
    img = _base(pal, seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    step = 34
    for y in range(0, H, step):
        for x in range(0, W, step):
            # Neeche ki taraf dots halke, taaki headline saaf padhe
            fade = 1.0 - (y / float(H)) * 0.75
            a = int(30 * fade)
            if a <= 2:
                continue
            d.ellipse([x, y, x + 2.4, y + 2.4], fill=(255, 255, 255, a))

    # Ek moti accent lakeer, kone se kone tak nahi — sirf ishara
    d.rectangle([0, H - 210, W, H - 206], fill=pal["accent"] + (40,))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return _scrim(img)


def style_bands(category, seed=0):
    """DIRECTION 2 — 'Bands'
    Tirchhi bands, alag-alag chaudai. Zyada urja, aaj ki khabar jaisa.
    Bulletin package ka ehsaas deta hai."""
    pal = palette(category)
    img = _base(pal, seed).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    rnd = random.Random(seed + 7)
    x = -400
    while x < W + 600:
        w = rnd.choice([8, 14, 26, 46, 70])
        a = rnd.choice([10, 14, 20, 26])
        use_accent = rnd.random() < 0.22
        col = (pal["accent"] + (a + 14,)) if use_accent else (255, 255, 255, a)
        d.polygon([(x, H), (x + w, H), (x + w + 520, 0), (x + 520, 0)], fill=col)
        x += w + rnd.choice([30, 50, 80, 120])

    layer = layer.filter(ImageFilter.GaussianBlur(0.6))
    img = Image.alpha_composite(img, layer)

    # Neeche gehra karo taaki type ke neeche shanti rahe
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(scrim)
    for i in range(60):
        y0 = int(H * 0.30) + i * ((H - int(H * 0.30)) // 60)
        ds.rectangle([0, y0, W, y0 + 14], fill=(0, 0, 0, int(3 + i * 1.9)))
    img = Image.alpha_composite(img, scrim)
    return _scrim(img.convert("RGB"))


def style_frame(category, seed=0):
    """DIRECTION 3 — 'Frame'
    Daayein taraf ek thos accent panel, baayein saaf jagah. Sabse sakht
    structure, sabse zyada 'channel' jaisa. Panel par shreni ka naam khada
    likha jaata hai (wo text libass se aata hai)."""
    pal = palette(category)
    img = _base(pal, seed).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    panel_x = int(W * 0.735)
    d.rectangle([panel_x, 0, W, H], fill=pal["accent"] + (30,))
    d.rectangle([panel_x, 0, panel_x + 5, H], fill=pal["accent"] + (255,))

    # Panel ke andar baareek horizontal rules — ek scale jaisa
    for i in range(1, 26):
        y = int(H * i / 26.0)
        d.rectangle([panel_x + 40, y, W - 60, y + 1], fill=(255, 255, 255, 16))

    # Baayein taraf upar ek chhota kona
    d.rectangle([110, 96, 110 + 3, 96 + 84], fill=pal["accent"] + (255,))

    img = Image.alpha_composite(img, layer)
    return _scrim(img.convert("RGB"))


def _scrim(img):
    """Neeche ki taraf gehrapan, taaki type saaf padhe.

    Ye scrim yahan PIL se banti hai, ffmpeg ke drawbox se nahi. drawbox ki
    patti-patti wali nakli gradient frame ke beech mein ek saaf kinara chhod
    deti thi - pehle sample mein wo lakeer साफ dikh rahi thi."""
    top = int(H * 0.30)
    grad = Image.new("L", (1, H), 0)
    px = grad.load()
    for y in range(H):
        if y < top:
            px[0, y] = 0
        else:
            t = (y - top) / float(H - top)
            px[0, y] = int(238 * (t ** 1.45))
    mask = grad.resize((W, H))
    dark = Image.new("RGB", (W, H), (2, 5, 10))
    return Image.composite(dark, img, mask)


STYLES = {"grid": style_grid, "bands": style_bands, "frame": style_frame}


def build(style, category, seed, path):
    fn = STYLES.get(style, style_grid)
    fn(category, seed).save(path, quality=95)
    return path


if __name__ == "__main__":
    import sys
    s = sys.argv[1] if len(sys.argv) > 1 else "grid"
    c = sys.argv[2] if len(sys.argv) > 2 else "default"
    build(s, c, 3, "bd_%s.png" % s)
    print("ok bd_%s.png" % s)
