"""
Carousel image engine — matches the uploaded terracotta template style,
adapted to 1080x1920 vertical (TikTok/Instagram) instead of the original
landscape layout, since that's the established posting format.

Takes the JSON output from the content-brain prompt and renders each
slide as a branded PNG. Includes:
- A rotating set of curated color palettes (varies daily)
- Built-in graphic elements (checkmark badges, stat call-out boxes)
"""

from PIL import Image, ImageDraw, ImageFont
import json
import os
import re
import datetime

W, H = 1080, 1920
MARGIN = 72

FONT_DIR = "/usr/share/fonts/truetype/liberation"
F_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
F_REG = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")

# --- Curated palette set (rotates automatically) ---
PALETTES = [
    {  # Terracotta — original reference look
        "bg": (208, 90, 58),
        "white": (255, 255, 255),
        "light": (255, 235, 227),
        "accent": (240, 200, 180),
        "pill_bg": (255, 255, 255),
        "pill_text": (150, 60, 35),
        "badge_bg": (235, 160, 130),
    },
    {  # Deep navy — sharper, more "data/tech" feel
        "bg": (30, 42, 68),
        "white": (255, 255, 255),
        "light": (198, 210, 235),
        "accent": (110, 150, 220),
        "pill_bg": (255, 255, 255),
        "pill_text": (30, 42, 68),
        "badge_bg": (60, 85, 140),
    },
    {  # Forest green — calmer, trust/authority feel
        "bg": (35, 74, 58),
        "white": (255, 255, 255),
        "light": (205, 230, 215),
        "accent": (140, 200, 165),
        "pill_bg": (255, 255, 255),
        "pill_text": (35, 74, 58),
        "badge_bg": (70, 120, 95),
    },
    {  # Charcoal + gold accent — premium/authority feel
        "bg": (32, 32, 34),
        "white": (255, 255, 255),
        "light": (215, 210, 200),
        "accent": (210, 165, 90),
        "pill_bg": (255, 255, 255),
        "pill_text": (32, 32, 34),
        "badge_bg": (90, 78, 50),
    },
]


def palette_for(batch_date, carousel_index):
    """Deterministic but varying: shifts daily so the same carousel slot
    doesn't always get the same look, but re-running the same day+index
    gives consistent results."""
    try:
        day_num = datetime.date.fromisoformat(batch_date).toordinal()
    except (ValueError, TypeError):
        day_num = 0
    idx = (day_num + carousel_index) % len(PALETTES)
    return PALETTES[idx]


NUMBER_PATTERN = re.compile(
    r"(?:[€$£]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)"
)


def extract_stat(text):
    """Pull the first currency/percentage figure out of a line of text,
    if there is one, so it can be rendered as a big call-out badge."""
    match = NUMBER_PATTERN.search(text)
    return match.group(0) if match else None


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


def fit_headline(draw, text, max_width, max_lines=5):
    for size in range(104, 47, -4):
        font = ImageFont.truetype(F_BOLD, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines, size
    font = ImageFont.truetype(F_BOLD, 48)
    return font, wrap_text(draw, text, font, max_width), 48


def draw_checkmark_badge(draw, x, y, size, ring_color, mark_color):
    """Small circular badge with a checkmark — used on body slides for
    the info-graphic / checklist feel."""
    draw.ellipse([x, y, x + size, y + size], outline=ring_color, width=4)
    # checkmark as two short lines
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
    th = 56
    box = [x, y, x + tw + pad_x * 2, y + th + pad_y * 2]
    draw.rounded_rectangle(box, radius=18, fill=pal["badge_bg"])
    draw.text((x + pad_x, y + pad_y - 4), stat_text, font=f_stat, fill=pal["white"])
    return box[3] - box[1]  # height consumed


def render_slide(eyebrow_left, eyebrow_right, headline, body_lines,
                  pal, show_swipe=False, cta_text=None, show_check=False,
                  out_path="slide.png"):
    img = Image.new("RGB", (W, H), pal["bg"])
    draw = ImageDraw.Draw(img)

    f_eyebrow = ImageFont.truetype(F_REG, 30)
    f_body = ImageFont.truetype(F_REG, 42)
    f_pill = ImageFont.truetype(F_BOLD, 32)
    f_swipe = ImageFont.truetype(F_BOLD, 34)

    draw.text((MARGIN, 70), eyebrow_left, font=f_eyebrow, fill=pal["light"])
    rw = draw.textlength(eyebrow_right, font=f_eyebrow)
    draw.text((W - MARGIN - rw, 70), eyebrow_right, font=f_eyebrow, fill=pal["light"])

    max_w = W - 2 * MARGIN

    # If the text contains a stat (e.g. "$500", "23%"), pull it out as a
    # big badge above the headline instead of leaving it buried in text
    stat = extract_stat(headline)
    stat_badge_h = 0

    f_headline, lines, size = fit_headline(draw, headline, max_w)
    line_height = int(size * 1.18)

    body_wrapped = [wrap_text(draw, para, f_body, max_w) for para in body_lines]

    headline_block_h = line_height * len(lines)
    body_block_h = sum(len(w) * 58 + 36 for w in body_wrapped)
    rule_h = 40 if body_wrapped else 0
    stat_h = 110 if stat else 0
    check_w = 70 if show_check else 0
    total_h = stat_h + headline_block_h + rule_h + body_block_h

    start_y = max(320, (H - total_h) // 2 - 60)
    y = start_y

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
    paths = []

    total_slides = 2 + len(carousel["body_slides"])

    p = render_slide(
        eyebrow_left=f"\u00a92026 \u00b7 {niche}",
        eyebrow_right=f"01/{total_slides:02d}",
        headline=carousel["hook_slide"],
        body_lines=[],
        pal=pal,
        show_swipe=True,
        out_path=os.path.join(out_dir, "slide_01.png"),
    )
    paths.append(p)

    for i, body in enumerate(carousel["body_slides"], start=2):
        p = render_slide(
            eyebrow_left=carousel["angle"],
            eyebrow_right=f"{i:02d}/{total_slides:02d}",
            headline=body,
            body_lines=[],
            pal=pal,
            show_check=True,
            out_path=os.path.join(out_dir, f"slide_{i:02d}.png"),
        )
        paths.append(p)

    last = total_slides
    p = render_slide(
        eyebrow_left="Follow for more",
        eyebrow_right=f"{last:02d}/{total_slides:02d}",
        headline=carousel["cta_slide"],
        body_lines=[carousel["caption"][:120]],
        pal=pal,
        cta_text="Follow @youragency",
        out_path=os.path.join(out_dir, f"slide_{last:02d}.png"),
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
    ]
    for idx, sample in enumerate(samples):
        out = render_carousel(sample, "2026-07-10", "/home/claude/sample_carousel_v3", carousel_index=idx)
        print(out)
