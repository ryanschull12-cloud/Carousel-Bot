"""
Carousel image engine v4 — gradient backgrounds, soft depth shapes,
topic icons, and a punchier hook-slide treatment on top of the v3
palette rotation + graphic badges.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import re
import datetime

W, H = 1080, 1920
MARGIN = 72

FONT_DIR = "/usr/share/fonts/truetype/liberation"
F_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
F_REG = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")

PALETTES = [
    {"bg": (208, 90, 58), "bg2": (168, 62, 40), "white": (255, 255, 255),
     "light": (255, 235, 227), "accent": (240, 200, 180),
     "pill_bg": (255, 255, 255), "pill_text": (150, 60, 35),
     "badge_bg": (235, 160, 130), "blob": (235, 130, 95)},
    {"bg": (30, 42, 68), "bg2": (18, 26, 46), "white": (255, 255, 255),
     "light": (198, 210, 235), "accent": (110, 150, 220),
     "pill_bg": (255, 255, 255), "pill_text": (30, 42, 68),
     "badge_bg": (60, 85, 140), "blob": (70, 100, 170)},
    {"bg": (35, 74, 58), "bg2": (20, 50, 38), "white": (255, 255, 255),
     "light": (205, 230, 215), "accent": (140, 200, 165),
     "pill_bg": (255, 255, 255), "pill_text": (35, 74, 58),
     "badge_bg": (70, 120, 95), "blob": (80, 140, 110)},
    {"bg": (32, 32, 34), "bg2": (18, 18, 20), "white": (255, 255, 255),
     "light": (215, 210, 200), "accent": (210, 165, 90),
     "pill_bg": (255, 255, 255), "pill_text": (32, 32, 34),
     "badge_bg": (90, 78, 50), "blob": (150, 120, 60)},
]


def palette_for(batch_date, carousel_index):
    try:
        day_num = datetime.date.fromisoformat(batch_date).toordinal()
    except (ValueError, TypeError):
        day_num = 0
    idx = (day_num + carousel_index) % len(PALETTES)
    return PALETTES[idx]


NUMBER_PATTERN = re.compile(r"(?:[€$£]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)")


def extract_stat(text):
    match = NUMBER_PATTERN.search(text)
    return match.group(0) if match else None


def make_gradient_bg(pal):
    """Diagonal-ish vertical gradient from bg to bg2 — instant depth
    vs a flat fill."""
    top = pal["bg"]
    bottom = pal["bg2"]
    base = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(base)
    for row in range(H):
        t = row / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, row), (W, row)], fill=(r, g, b))
    return base


def add_depth_blobs(img, pal, seed=0):
    """Soft blurred circles for a modern layered-background feel."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    positions = [
        (W * 0.85, H * 0.12, 340, 60),
        (W * -0.05, H * 0.55, 420, 45),
        (W * 0.75, H * 0.92, 380, 50),
    ]
    pos = positions[seed % len(positions):] + positions[:seed % len(positions)]
    for cx, cy, r, alpha in pos[:2]:
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*pal["blob"], alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(90))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    return img


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
            draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=color, width=6)
    elif icon == "star":
        import math
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        draw.polygon(pts, outline=color, width=6)
    elif icon == "coin":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=6)
        f = ImageFont.truetype(F_BOLD, int(size * 0.7))
        tw = draw.textlength("$", font=f)
        draw.text((cx - tw / 2, cy - size * 0.4), "$", font=f, fill=color)
    elif icon == "cursor":
        draw.polygon([
            (cx - r * 0.5, cy - r), (cx - r * 0.5, cy + r * 0.7),
            (cx - r * 0.05, cy + r * 0.3), (cx + r * 0.25, cy + r * 0.75),
            (cx + r * 0.45, cy + r * 0.55), (cx + r * 0.15, cy + r * 0.15),
            (cx + r * 0.55, cy + r * 0.1),
        ], outline=color, width=5)
    elif icon == "bulb":
        draw.ellipse([cx - r * 0.6, cy - r, cx + r * 0.6, cy + r * 0.3], outline=color, width=6)
        draw.line([cx - r * 0.25, cy + r * 0.3, cx - r * 0.25, cy + r * 0.75], fill=color, width=6)
        draw.line([cx + r * 0.25, cy + r * 0.3, cx + r * 0.25, cy + r * 0.75], fill=color, width=6)
        draw.line([cx - r * 0.3, cy + r * 0.85, cx + r * 0.3, cy + r * 0.85], fill=color, width=6)


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


def fit_headline(draw, text, max_width, max_lines=5, max_size=104):
    for size in range(max_size, 47, -4):
        font = ImageFont.truetype(F_BOLD, size)
        lines = wrap_text(draw, text, max_width, font) if False else wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines, size
    font = ImageFont.truetype(F_BOLD, 48)
    return font, wrap_text(draw, text, font, max_width), 48


def draw_checkmark_badge(draw, x, y, size, ring_color, mark_color):
    draw.ellipse([x, y, x + size, y + size], outline=ring_color, width=4)
    cx, cy = x + size * 0.5, y + size * 0.5
    draw.line(
        [(cx - size * 0.22, cy), (cx - size * 0.05, cy + size * 0.18),
         (cx + size * 0.25, cy - size * 0.2)],
        fill=mark_color, width=6, joint="curve"
    )


def draw_stat_badge(draw, x, y, stat_text, pal):
    f_stat = ImageFont.truetype(F_BOLD, 56)
    pad_x, pad_y = 32, 20
    tw = draw.textlength(stat_text, font=f_stat)
    box = [x, y, x + tw + pad_x * 2, y + 56 + pad_y * 2]
    draw.rounded_rectangle(box, radius=18, fill=pal["badge_bg"])
    draw.text((x + pad_x, y + pad_y - 4), stat_text, font=f_stat, fill=pal["white"])


def render_slide(eyebrow_left, eyebrow_right, headline, body_lines, pal,
                  show_swipe=False, cta_text=None, show_check=False,
                  is_hook=False, icon=None, seed=0, out_path="slide.png"):
    img = make_gradient_bg(pal)
    img = add_depth_blobs(img, pal, seed=seed)
    draw = ImageDraw.Draw(img)

    f_eyebrow = ImageFont.truetype(F_REG, 30)
    f_body = ImageFont.truetype(F_REG, 42)
    f_pill = ImageFont.truetype(F_BOLD, 32)
    f_swipe = ImageFont.truetype(F_BOLD, 34)

    draw.text((MARGIN, 70), eyebrow_left, font=f_eyebrow, fill=pal["light"])
    rw = draw.textlength(eyebrow_right, font=f_eyebrow)
    draw.text((W - MARGIN - rw, 70), eyebrow_right, font=f_eyebrow, fill=pal["light"])

    max_w = W - 2 * MARGIN
    stat = extract_stat(headline)

    icon_h = 0
    if is_hook and icon:
        icon_size = 130
        draw_icon(draw, MARGIN + icon_size / 2, 260 + icon_size / 2, icon_size, icon, pal["accent"])
        icon_h = icon_size + 50

    max_headline_size = 116 if is_hook else 96
    f_headline, lines, size = fit_headline(draw, headline, max_w, max_lines=5, max_size=max_headline_size)
    line_height = int(size * 1.18)

    body_wrapped = [wrap_text(draw, para, f_body, max_w) for para in body_lines]
    headline_block_h = line_height * len(lines)
    body_block_h = sum(len(w) * 58 + 36 for w in body_wrapped)
    rule_h = 40 if body_wrapped else 0
    stat_h = 110 if stat else 0
    check_w = 70 if show_check else 0
    total_h = icon_h + stat_h + headline_block_h + rule_h + body_block_h

    start_y = max(300, (H - total_h) // 2 - 40)
    y = start_y + icon_h

    if stat:
        draw_stat_badge(draw, MARGIN, y, stat, pal)
        y += 110

    text_x = MARGIN + check_w
    if show_check:
        badge_y = y + (line_height - 48) // 2
        draw_checkmark_badge(draw, MARGIN, badge_y, 48, pal["accent"], pal["white"])

    for line in lines:
        draw.text((text_x, y), line, font=f_headline, fill=pal["white"])
        y += line_height
    y += 24

    if body_wrapped:
        draw.rectangle([text_x, y, text_x + 120, y + 6], fill=pal["accent"])
        y += 40
        for wrapped in body_wrapped:
            for line in wrapped:
                draw.text((text_x, y), line, font=f_body, fill=pal["light"])
                y += 58
            y += 36

    if cta_text:
        pad_x, pad_y = 40, 24
        tw = draw.textlength(cta_text, font=f_pill)
        pill_w, pill_h = tw + pad_x * 2, 68 + pad_y - 24
        px0, py0 = MARGIN, H - 220
        px1, py1 = px0 + pill_w, py0 + pill_h
        draw.rounded_rectangle([px0, py0, px1, py1], radius=pill_h // 2, fill=pal["pill_bg"])
        draw.text((px0 + pad_x, py0 + (pill_h - 32) // 2), cta_text, font=f_pill, fill=pal["pill_text"])

    if show_swipe:
        draw.text((MARGIN, H - 120), "Swipe  \u2192", font=f_swipe, fill=pal["white"])

    img.save(out_path)
    return out_path


def render_carousel(carousel, batch_date, out_dir, carousel_index=0):
    os.makedirs(out_dir, exist_ok=True)
    niche = carousel["niche"]
    pal = palette_for(batch_date, carousel_index)
    icon = icon_for(niche)
    paths = []

    total_slides = 2 + len(carousel["body_slides"])

    p = render_slide(
        eyebrow_left=f"\u00a92026 \u00b7 {niche}",
        eyebrow_right=f"01/{total_slides:02d}",
        headline=carousel["hook_slide"],
        body_lines=[], pal=pal, show_swipe=True, is_hook=True, icon=icon,
        seed=carousel_index, out_path=os.path.join(out_dir, "slide_01.png"),
    )
    paths.append(p)

    for i, body in enumerate(carousel["body_slides"], start=2):
        p = render_slide(
            eyebrow_left=carousel["angle"],
            eyebrow_right=f"{i:02d}/{total_slides:02d}",
            headline=body, body_lines=[], pal=pal, show_check=True,
            seed=carousel_index + i, out_path=os.path.join(out_dir, f"slide_{i:02d}.png"),
        )
        paths.append(p)

    last = total_slides
    p = render_slide(
        eyebrow_left="Follow for more",
        eyebrow_right=f"{last:02d}/{total_slides:02d}",
        headline=carousel["cta_slide"],
        body_lines=[], pal=pal, cta_text="Follow @youragency",
        seed=carousel_index + last, out_path=os.path.join(out_dir, f"slide_{last:02d}.png"),
    )
    paths.append(p)

    return paths


if __name__ == "__main__":
    samples = [
        {
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
            "caption": "Most accounts don't have a targeting problem, they have a fatigue problem"
        },
        {
            "niche": "Google reviews & local reputation",
            "angle": "Numbers/proof",
            "hook_slide": "20 to 80 reviews changes how Google ranks you locally",
            "body_slides": [
                "Review volume is one of the strongest local ranking signals.",
                "Businesses with 50+ reviews convert nearly double the rate.",
                "Responding to every review measurably improves trust signals.",
            ],
            "cta_slide": "Save this before you ask your next customer for a review",
            "caption": "Review volume is quietly one of your best marketing levers"
        },
    ]
    for idx, sample in enumerate(samples):
        out = render_carousel(sample, "2026-07-10", f"/home/claude/sample_v4_{idx}", carousel_index=idx)
        print(out)
