"""
Carousel image engine v5 — real typography (Poppins), 3 rotating card-style
templates, gradient + depth backgrounds, topic icons, inline stat highlight.

Fonts expected at fonts/Poppins-{Black,Bold,Medium,Regular}.ttf relative to
this file (commit them to the repo alongside the script).
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import re
import math
import datetime

W, H = 1080, 1920
MARGIN = 76

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")


def _font(name, fallback_regular=False):
    path = os.path.join(FONT_DIR, name)
    if os.path.exists(path):
        return path
    # fall back to system font if Poppins wasn't committed to the repo yet
    sysdir = "/usr/share/fonts/truetype/liberation"
    return os.path.join(sysdir, "LiberationSans-Bold.ttf" if not fallback_regular
                         else "LiberationSans-Regular.ttf")


F_BLACK = _font("Poppins-Black.ttf")
F_BOLD = _font("Poppins-Bold.ttf")
F_MEDIUM = _font("Poppins-Medium.ttf")
F_REG = _font("Poppins-Regular.ttf", fallback_regular=True)

PALETTES = [
    {  # Deep navy — sharp, data/tech feel
     "bg": (30, 42, 68), "bg2": (18, 26, 46), "white": (255, 255, 255),
     "light": (198, 210, 235), "accent": (120, 165, 235),
     "card": (232, 238, 250), "card_text": (24, 35, 60),
     "pill_bg": (255, 255, 255), "pill_text": (30, 42, 68),
     "badge_bg": (60, 85, 140), "blob": (70, 100, 170)},
    {  # Forest green — calm authority feel
     "bg": (35, 74, 58), "bg2": (20, 50, 38), "white": (255, 255, 255),
     "light": (205, 230, 215), "accent": (150, 215, 175),
     "card": (228, 244, 235), "card_text": (25, 55, 42),
     "pill_bg": (255, 255, 255), "pill_text": (35, 74, 58),
     "badge_bg": (70, 120, 95), "blob": (80, 140, 110)},
    {  # Charcoal + gold — premium feel
     "bg": (32, 32, 34), "bg2": (18, 18, 20), "white": (255, 255, 255),
     "light": (215, 210, 200), "accent": (225, 180, 100),
     "card": (245, 236, 220), "card_text": (45, 36, 15),
     "pill_bg": (255, 255, 255), "pill_text": (32, 32, 34),
     "badge_bg": (90, 78, 50), "blob": (150, 120, 60)},
    {  # Deep plum/burgundy — bold, distinct from the other three
     "bg": (58, 28, 48), "bg2": (36, 16, 30), "white": (255, 255, 255),
     "light": (232, 205, 220), "accent": (220, 140, 180),
     "card": (245, 232, 240), "card_text": (60, 24, 44),
     "pill_bg": (255, 255, 255), "pill_text": (58, 28, 48),
     "badge_bg": (120, 60, 95), "blob": (150, 80, 120)},
]


def palette_for(batch_date, carousel_index):
    try:
        day_num = datetime.date.fromisoformat(batch_date).toordinal()
    except (ValueError, TypeError):
        day_num = 0
    return PALETTES[(day_num + carousel_index) % len(PALETTES)]


NUMBER_PATTERN = re.compile(r"(?:[€$£]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)")


def extract_stat(text):
    m = NUMBER_PATTERN.search(text)
    return m.group(0) if m else None


def make_gradient_bg(pal):
    top, bottom = pal["bg"], pal["bg2"]
    base = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(base)
    for row in range(H):
        t = row / H
        draw.line([(0, row), (W, row)], fill=tuple(
            int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base


def add_depth_blobs(img, pal, seed=0):
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    positions = [
        (W * 0.88, H * 0.10, 320, 38),
        (W * -0.08, H * 0.5, 400, 28),
        (W * 0.8, H * 0.95, 360, 32),
        (W * 0.1, H * 0.92, 300, 26),
    ]
    rot = positions[seed % len(positions):] + positions[:seed % len(positions)]
    for cx, cy, r, alpha in rot[:2]:
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*pal["blob"], alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(95))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


TOPIC_ICONS = [
    (("review", "reputation", "star"), "star"),
    (("budget", "roi", "cost", "spend", "price"), "coin"),
    (("landing page", "conversion", "convert"), "cursor"),
    (("myth", "mistake", "wrong"), "bulb"),
    (("meta", "instagram", "google ads", "ppc", "audience", "targeting"), "target"),
]


def icon_for(niche):
    n = niche.lower()
    for keywords, icon in TOPIC_ICONS:
        if any(k in n for k in keywords):
            return icon
    return "target"


def draw_icon(draw, cx, cy, size, icon, color):
    r = size / 2
    if icon == "target":
        for frac in (1.0, 0.62, 0.28):
            rr = r * frac
            draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=color, width=7)
    elif icon == "star":
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        draw.polygon(pts, outline=color, width=7)
    elif icon == "coin":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=7)
        f = ImageFont.truetype(F_BLACK, int(size * 0.6))
        tw = draw.textlength("$", font=f)
        draw.text((cx - tw / 2, cy - size * 0.38), "$", font=f, fill=color)
    elif icon == "cursor":
        draw.polygon([
            (cx - r * 0.5, cy - r), (cx - r * 0.5, cy + r * 0.7),
            (cx - r * 0.05, cy + r * 0.3), (cx + r * 0.25, cy + r * 0.75),
            (cx + r * 0.45, cy + r * 0.55), (cx + r * 0.15, cy + r * 0.15),
            (cx + r * 0.55, cy + r * 0.1),
        ], outline=color, width=6)
    elif icon == "bulb":
        draw.ellipse([cx - r * 0.6, cy - r, cx + r * 0.6, cy + r * 0.3], outline=color, width=7)
        draw.line([cx - r * 0.25, cy + r * 0.3, cx - r * 0.25, cy + r * 0.75], fill=color, width=7)
        draw.line([cx + r * 0.25, cy + r * 0.3, cx + r * 0.25, cy + r * 0.75], fill=color, width=7)
        draw.line([cx - r * 0.3, cy + r * 0.85, cx + r * 0.3, cy + r * 0.85], fill=color, width=7)


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, max_width, max_lines, max_size, min_size, font_path):
    for size in range(max_size, min_size - 1, -4):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines, size
    font = ImageFont.truetype(font_path, min_size)
    return font, wrap_text(draw, text, font, max_width), min_size


def draw_multicolor_line(draw, x, y, line, font, stat, base_color, highlight_color, shadow=False):
    """Draw one line of text, coloring the stat substring (if present in
    this line) in the highlight color instead of a separate badge box.
    Optional soft shadow pass improves legibility over textured backgrounds."""

    def draw_run(cx, cy, text, color):
        if shadow:
            draw.text((cx + 2, cy + 4), text, font=font, fill=(0, 0, 0))
        draw.text((cx, cy), text, font=font, fill=color)

    if not stat or stat not in line:
        draw_run(x, y, line, base_color)
        return
    before, _, after = line.partition(stat)
    cx = x
    if before:
        draw_run(cx, y, before, base_color)
        cx += draw.textlength(before, font=font)
    draw_run(cx, y, stat, highlight_color)
    cx += draw.textlength(stat, font=font)
    if after:
        draw_run(cx, y, after, base_color)


def draw_checkmark_badge(draw, x, y, size, ring_color, mark_color):
    draw.ellipse([x, y, x + size, y + size], outline=ring_color, width=5)
    cx, cy = x + size * 0.5, y + size * 0.5
    draw.line(
        [(cx - size * 0.22, cy), (cx - size * 0.05, cy + size * 0.18),
         (cx + size * 0.25, cy - size * 0.2)],
        fill=mark_color, width=6, joint="curve"
    )


def draw_pill(draw, x, y, text, font, bg, fg):
    pad_x, pad_y = 40, 22
    tw = draw.textlength(text, font=font)
    box = [x, y, x + tw + pad_x * 2, y + 56 + pad_y * 2]
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=fg)
    return box[3] - box[1]


def draw_topic_tag(draw, x, y, label, font, bg, fg):
    """Small uppercase pill tag — replaces the plain top-of-slide text
    that read like a hyperlink. Reusable as a real designed element."""
    label = label.upper()
    pad_x, pad_y = 26, 14
    tw = draw.textlength(label, font=font)
    box = [x, y, x + tw + pad_x * 2, y + 34 + pad_y * 2]
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), label, font=font, fill=fg)
    return box


# ---------------------------------------------------------------- templates

def template_full_bleed(img, draw, pal, headline, is_hook, icon, show_check, eyebrow_h, label):
    """Big text directly on the gradient/blob background, stat inline-
    highlighted in the accent color. Clean, bold, minimal."""
    max_w = W - 2 * MARGIN
    stat = extract_stat(headline)
    icon_h = 0
    if is_hook and icon:
        isz = 120
        draw_icon(draw, MARGIN + isz / 2, eyebrow_h + isz / 2, isz, icon, pal["accent"])
        icon_h = isz + 46

    max_size = 118 if is_hook else 92
    font, lines, size = fit_text(draw, headline, max_w, 5, max_size, 50, F_BLACK)
    line_h = int(size * 1.16)
    check_w = 74 if show_check else 0
    total_h = icon_h + line_h * len(lines)
    y = max(eyebrow_h + 30, (H - total_h) // 2 - 30) + icon_h
    text_x = MARGIN + check_w
    if show_check:
        draw_checkmark_badge(draw, MARGIN, y + (line_h - 50) // 2, 50, pal["accent"], pal["white"])
    for line in lines:
        draw_multicolor_line(draw, text_x, y, line, font, stat, pal["white"], pal["accent"], shadow=True)
        y += line_h
    y += 30
    f_tag = ImageFont.truetype(F_BOLD, 28)
    draw_topic_tag(draw, text_x, y, label, f_tag, pal["badge_bg"], pal["white"])
    return y


def template_card(img, draw, pal, headline, is_hook, icon, show_check, eyebrow_h, label):
    """Text sits inside a light rounded card floating over the textured
    background — strong contrast, quote-card aesthetic."""
    max_w = W - 2 * MARGIN - 80
    stat = extract_stat(headline)
    max_size = 88 if is_hook else 68
    font, lines, size = fit_text(draw, headline, max_w, 6, max_size, 42, F_BLACK)
    line_h = int(size * 1.16)

    pad = 56
    card_h = line_h * len(lines) + pad * 2
    card_y = max(eyebrow_h + 70, (H - card_h) // 2 - 20)
    card_box = [MARGIN - 10, card_y, W - MARGIN + 10, card_y + card_h]

    f_tag = ImageFont.truetype(F_BOLD, 28)
    draw_topic_tag(draw, MARGIN - 10, card_y - 76, label, f_tag, pal["badge_bg"], pal["white"])

    draw.rounded_rectangle(card_box, radius=36, fill=pal["card"])

    if is_hook and icon:
        isz = 84
        icon_cx = W - MARGIN - isz / 2 - 20
        icon_cy = card_y - isz / 2 - 18
        draw.ellipse([icon_cx - isz / 2 - 14, icon_cy - isz / 2 - 14,
                      icon_cx + isz / 2 + 14, icon_cy + isz / 2 + 14], fill=pal["accent"])
        draw_icon(draw, icon_cx, icon_cy, isz * 0.7, icon, pal["card_text"])

    y = card_y + pad
    text_x = MARGIN + 30
    for line in lines:
        draw_multicolor_line(draw, text_x, y, line, font, stat, pal["card_text"], pal["pill_text"])
        y += line_h
    if show_check:
        draw_checkmark_badge(draw, W - MARGIN - 60, card_y + card_h - 70, 44, pal["accent"], pal["card_text"])
    return card_box[3]


def template_block_split(img, draw, pal, headline, is_hook, icon, show_check, eyebrow_h, label):
    """A solid accent-color band anchors the bottom third; headline spans
    across the gradient background above it. High visual contrast."""
    band_top = int(H * 0.66)
    draw.rectangle([0, band_top, W, H], fill=pal["accent"])

    max_w = W - 2 * MARGIN
    stat = extract_stat(headline)
    max_size = 104 if is_hook else 84
    font, lines, size = fit_text(draw, headline, max_w, 4, max_size, 46, F_BLACK)
    line_h = int(size * 1.18)

    icon_h = 0
    if is_hook and icon:
        isz = 100
        draw_icon(draw, MARGIN + isz / 2, eyebrow_h + isz / 2, isz, icon, pal["accent"])
        icon_h = isz + 40

    total_h = icon_h + line_h * len(lines)
    y = max(eyebrow_h + 20, (band_top - total_h) // 2) + icon_h
    for line in lines:
        draw_multicolor_line(draw, MARGIN, y, line, font, stat, pal["white"], pal["card"], shadow=True)
        y += line_h

    # fill the band with a real element: topic tag + big slide-icon mark,
    # instead of leaving it empty
    f_tag = ImageFont.truetype(F_BOLD, 30)
    draw_topic_tag(draw, MARGIN, band_top + 46, label, f_tag, pal["card"], pal["card_text"])
    isz = 120
    icon_cx, icon_cy = W - MARGIN - isz / 2, band_top + (H - band_top) / 2 + 20
    draw_icon(draw, icon_cx, icon_cy, isz, icon or "target", pal["card_text"])

    return band_top


TEMPLATES = [template_full_bleed, template_card, template_block_split]


def render_slide(eyebrow_left, eyebrow_right, headline, pal,
                  show_swipe=False, cta_text=None, show_check=False,
                  is_hook=False, icon=None, seed=0, template_idx=0,
                  out_path="slide.png"):
    img = make_gradient_bg(pal)
    img = add_depth_blobs(img, pal, seed=seed)
    draw = ImageDraw.Draw(img)

    f_eyebrow = ImageFont.truetype(F_MEDIUM, 30)
    f_pill = ImageFont.truetype(F_BOLD, 32)
    f_swipe = ImageFont.truetype(F_BOLD, 34)

    # Only the slide-progress counter stays at the very top now — the
    # plain descriptive text there used to read like a stray hyperlink.
    # The label itself is now shown as a proper designed tag inside
    # each template instead.
    rw = draw.textlength(eyebrow_right, font=f_eyebrow)
    draw.text((W - MARGIN - rw, 68), eyebrow_right, font=f_eyebrow, fill=pal["light"])
    eyebrow_h = 150

    template = TEMPLATES[template_idx % len(TEMPLATES)]
    template(img, draw, pal, headline, is_hook, icon, show_check, eyebrow_h, eyebrow_left)

    if cta_text:
        draw_pill(draw, MARGIN, H - 220, cta_text, f_pill, pal["pill_bg"], pal["pill_text"])

    if show_swipe:
        draw.text((MARGIN, H - 120), "Swipe  \u2192", font=f_swipe, fill=pal["white"])

    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path


def render_carousel(carousel, batch_date, out_dir, carousel_index=0):
    os.makedirs(out_dir, exist_ok=True)
    niche = carousel["niche"]
    pal = palette_for(batch_date, carousel_index)
    icon = icon_for(niche)
    paths = []
    total_slides = 2 + len(carousel["body_slides"])

    p = render_slide(
        eyebrow_left=niche, eyebrow_right=f"01/{total_slides:02d}",
        headline=carousel["hook_slide"], pal=pal, show_swipe=True, is_hook=True,
        icon=icon, seed=carousel_index, template_idx=carousel_index,
        out_path=os.path.join(out_dir, "slide_01.jpg"),
    )
    paths.append(p)

    for i, body in enumerate(carousel["body_slides"], start=2):
        p = render_slide(
            eyebrow_left=carousel["angle"], eyebrow_right=f"{i:02d}/{total_slides:02d}",
            headline=body, pal=pal, show_check=True,
            seed=carousel_index + i, template_idx=carousel_index + i,
            out_path=os.path.join(out_dir, f"slide_{i:02d}.jpg"),
        )
        paths.append(p)

    last = total_slides
    p = render_slide(
        eyebrow_left="Follow for more", eyebrow_right=f"{last:02d}/{total_slides:02d}",
        headline=carousel["cta_slide"], pal=pal, cta_text="Follow @youragency",
        seed=carousel_index + last, template_idx=carousel_index + last,
        out_path=os.path.join(out_dir, f"slide_{last:02d}.jpg"),
    )
    paths.append(p)

    return paths


if __name__ == "__main__":
    sample = {
        "niche": "Meta/Instagram Ads mistakes/mechanics",
        "angle": "Mistake/myth-busting",
        "hook_slide": "Your $500 ad spend just vanished. Here's why.",
        "body_slides": [
            "You targeted women 25-54 because it's the default setting.",
            "Creative fatigue kicks in after about 3 days of the same ad.",
            "23% of budget usually leaks to placements that never convert.",
            "A good cost-per-lead sits far lower than most owners assume."
        ],
        "cta_slide": "Comment AUDIT and I'll tell you what to check first",
        "caption": "Most accounts don't have a targeting problem #meta #ads"
    }
    out = render_carousel(sample, "2026-07-10", "/home/claude/sample_v5", carousel_index=0)
    print(out)
    
