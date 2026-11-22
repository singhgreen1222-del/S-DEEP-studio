"""Auto wardrobe: turban + jacket recolor on YOUR host photo (face/pose untouched, no GPU, free).
Masks are tuned for host/original.png framing (turban = blue pixels on top, jacket = dark torso region)."""
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageDraw

REF = (1448, 1086)
# name: (hue_deg, sat_scale, val_scale, val_add)
TURBAN = {
    "maroon": (350, 1.7, 0.55, 0.0), "black": (0, 0.0, 0.28, 0.0), "white": (0, 0.04, 0.55, 0.42),
    "mustard": (45, 2.0, 1.0, 0.0), "green": (140, 1.4, 0.65, 0.0), "orange": (22, 2.2, 1.05, 0.0),
    "navy": (225, 1.9, 0.5, 0.0), "teal": (178, 1.4, 0.75, 0.0), "grey": (0, 0.0, 0.6, 0.05),
    "pink": (335, 1.0, 1.05, 0.05), "purple": (275, 1.3, 0.75, 0.0),
}
# name: (hue_deg, sat, gain, add)
JACKET = {
    "navy": (220, 0.75, 2.8, 0.02), "maroon": (350, 0.75, 2.5, 0.02), "green": (150, 0.65, 2.3, 0.02),
    "brown": (25, 0.6, 2.5, 0.02), "steel_grey": (210, 0.06, 3.6, 0.07), "olive": (70, 0.55, 2.4, 0.02),
}


def _scale_pts(pts, size):
    sx, sy = size[0] / REF[0], size[1] / REF[1]
    return [(int(x * sx), int(y * sy)) for x, y in pts]


def turban_mask(img):
    w, h = img.size
    hsv = np.array(img.convert("HSV")).astype(np.int32)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = (H > 120) & (H < 180) & (S > 35) & (V > 50)
    yy, xx = np.mgrid[0:h, 0:w]
    m &= (yy < 0.40 * h) & (xx > 0.28 * w) & (xx < 0.65 * w)
    mi = Image.fromarray((m * 255).astype("uint8"))
    mi = mi.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(5))
    return mi.filter(ImageFilter.GaussianBlur(1.5))


def jacket_mask(img):
    w, h = img.size
    outer = [(350, 545), (480, 522), (610, 505), (850, 505), (1010, 522), (1140, 545), (1190, 600),
             (1232, 700), (1272, 800), (1312, 900), (1336, 1000), (1342, 1086), (62, 1086), (70, 1000),
             (130, 900), (215, 800), (270, 740), (295, 700), (322, 620)]
    poly = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(poly)
    d.polygon(_scale_pts(outer, (w, h)), fill=255)
    (x0, y0), (x1, y1) = _scale_pts([(640, 500), (832, 1086)], (w, h))
    d.rectangle([x0, y0, x1, y1], fill=0)  # inner t-shirt + neck stay as they are
    for box in ([(525, 935), (815, 1086)], [(815, 985), (915, 1086)]):  # hands + watch dial
        (a0, b0), (a1, b1) = _scale_pts(box, (w, h))
        d.rectangle([a0, b0, a1, b1], fill=0)
    V = np.array(img.convert("HSV"))[..., 2]  # bright pixels (hands, watch) are skipped automatically
    dark = (V < 110) * 255
    m = np.minimum(np.array(poly), dark.astype("uint8"))
    return Image.fromarray(m).filter(ImageFilter.GaussianBlur(1.2))


def _apply(img, mask, hue_deg, sat, val_scale, val_add, sat_is_scale):
    hsv = np.array(img.convert("HSV")).astype(np.float32)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    H2 = np.full_like(H, hue_deg / 360 * 255)
    S2 = np.clip(S * sat, 0, 255) if sat_is_scale else np.full_like(S, sat * 255)
    V2 = np.clip(V * val_scale + val_add * 255, 0, 255)
    new = Image.fromarray(np.stack([H2, S2, V2], -1).astype("uint8"), "HSV").convert("RGB")
    return Image.composite(new, img, mask)


def make_look(base, turban="original", jacket="original"):
    img = base.convert("RGB")
    if turban != "original":
        hd, ss, vs, va = TURBAN[turban]
        img = _apply(img, turban_mask(base.convert("RGB")), hd, ss, vs, va, True)
    if jacket != "original":
        hd, s, g, a = JACKET[jacket]
        img = _apply(img, jacket_mask(base.convert("RGB")), hd, s, g, a, False)
    return img


def make_looks(base_path, out_dir, n=12, seed=7):
    base = Image.open(base_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    combos = [(t, j) for t in ["original"] + list(TURBAN) for j in ["original"] + list(JACKET)]
    combos.remove(("original", "original"))
    random.Random(seed).shuffle(combos)
    made = []
    for i, (t, j) in enumerate([("original", "original")] + combos[: n - 1]):
        p = out_dir / f"look_{i:02d}_{t}_{j}.jpg"
        make_look(base, t, j).save(p, quality=95)
        made.append(p)
    return made
