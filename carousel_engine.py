"""
Carousel image engine v5 — real typography (Poppins), 3 rotating card-style
templates, gradient + depth backgrounds, topic icons, inline stat highlight.

Fonts expected at fonts/Poppins-{Black,Bold,Medium,Regular}.ttf relative to
this file (commit them to the repo alongside the script).
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import re
import io
import math
import datetime
import requests

W, H = 1080, 1920
MARGIN = 76

# Your actual handle — edit this ONE line if it ever changes, nowhere else.
AGENCY_HANDLE = "@rd.marketing0"

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
INTER_PATH = os.path.join(FONT_DIR, "Inter-Variable.ttf")

# Weight name constants — used as arguments to weighted_font(), not raw
# file paths, since Inter is loaded as a single variable font file.
F_BLACK = "Black"
F_BOLD = "Bold"
F_MEDIUM = "Medium"
F_REG = "Regular"

_FALLBACK_STATIC = {
    "Black": os.path.join(FONT_DIR, "Poppins-Black.ttf"),
    "Bold": os.path.join(FONT_DIR, "Poppins-Bold.ttf"),
    "Medium": os.path.join(FONT_DIR, "Poppins-Medium.ttf"),
    "Regular": os.path.join(FONT_DIR, "Poppins-Regular.ttf"),
}


def weighted_font(weight_name, size):
    """Loads Inter at the requested weight (Black/Bold/Medium/Regular)
    using Pillow's variable-font support — one font file, full weight
    range. Falls back to a static Poppins file, then system Liberation,
    if Inter-Variable.ttf hasn't been committed to the repo yet."""
    if os.path.exists(INTER_PATH):
        try:
            font = ImageFont.truetype(INTER_PATH, size)
            font.set_variation_by_name(weight_name)
            return font
        except Exception:
            pass
    fallback = _FALLBACK_STATIC.get(weight_name)
    if fallback and os.path.exists(fallback):
        return ImageFont.truetype(fallback, size)
    sysdir = "/usr/share/fonts/truetype/liberation"
    sysfile = "LiberationSans-Bold.ttf" if weight_name in ("Black", "Bold") else "LiberationSans-Regular.ttf"
    return ImageFont.truetype(os.path.join(sysdir, sysfile), size)

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

# Key terms worth colorizing when there's no number to highlight instead —
# keeps slides visually punchy even on non-numeric hooks/lines.
KEYWORD_PATTERN = re.compile(
    r"\b(Google Ads|Meta Ads|Instagram Ads|Facebook Ads|TikTok Ads|"
    r"Quality Score|Google Reviews|Local SEO|SEO|ROI|CPC|CPA|CTR|"
    r"budget|conversions?|remarketing|retargeting)\b",
    re.IGNORECASE,
)


def extract_stat(text):
    """Returns the first number/stat if present, otherwise the first
    key marketing term worth highlighting, otherwise None."""
    m = NUMBER_PATTERN.search(text)
    if m:
        return m.group(0)
    m = KEYWORD_PATTERN.search(text)
    return m.group(0) if m else None


PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
BACKGROUND_IMAGES_DIR = os.path.join(HERE, "background_images")

NICHE_CATEGORY = [
    (("google ads",), "google_ads"),
    (("meta", "instagram"), "meta_ads"),
    (("review", "reputation", "seo"), "reviews_seo"),
    (("email",), "email_marketing"),
]

NICHE_PHOTO_QUERIES = [
    (("google ads",), "computer analytics screen"),
    (("meta", "instagram"), "phone social media"),
    (("review", "reputation", "seo"), "five star rating"),
    (("email",), "laptop email typing"),
]


def category_for(niche):
    n = niche.lower()
    for keywords, category in NICHE_CATEGORY:
        if any(k in n for k in keywords):
            return category
    return "general"


def photo_query_for(niche):
    n = niche.lower()
    for keywords, query in NICHE_PHOTO_QUERIES:
        if any(k in n for k in keywords):
            return query
    return "business marketing"


def get_local_photo(niche, seed=0):
    """Picks a photo from your own curated background_images/{category}/
    folder if you've added any — gives you full control over the exact
    aesthetic instead of relying on a live keyword search every time.
    Falls back to background_images/general/ if the category folder is
    empty, and returns None (caller falls back to Pexels) if nothing's
    there at all."""
    category = category_for(niche)
    for folder in (category, "general"):
        path = os.path.join(BACKGROUND_IMAGES_DIR, folder)
        if not os.path.isdir(path):
            continue
        files = sorted([
            f for f in os.listdir(path)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ])
        if files:
            chosen = files[seed % len(files)]
            try:
                photo = Image.open(os.path.join(path, chosen)).convert("RGB")
                return crop_to_fill(photo)
            except Exception as e:
                print(f"Local photo load failed ({chosen}): {e}")
                continue
    return None


def crop_to_fill(photo):
    target_ratio = W / H
    pw, ph = photo.size
    photo_ratio = pw / ph
    if photo_ratio > target_ratio:
        new_w = int(ph * target_ratio)
        left = (pw - new_w) // 2
        photo = photo.crop((left, 0, left + new_w, ph))
    else:
        new_h = int(pw / target_ratio)
        top = (ph - new_h) // 2
        photo = photo.crop((0, top, pw, top + new_h))
    return photo.resize((W, H))


def get_background_photo(niche, seed=0):
    """Curated local folder only — no live Pexels calls. If nothing's
    in background_images/{category}/ (or background_images/general/)
    for this niche, returns None and the caller falls back to the
    gradient look for that slide."""
    return get_local_photo(niche, seed)


def fetch_background_photo(query):
    """Pulls a relevant photo from Pexels (free, no cost). Returns a PIL
    Image cropped to fill 1080x1920, or None if anything goes wrong —
    callers should always fall back to the gradient background on None."""
    if not PEXELS_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "portrait", "per_page": 10},
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get("photos", [])
        if not results:
            return None
        photo_url = results[0]["src"]["large2x"]
        img_resp = requests.get(photo_url, timeout=20)
        img_resp.raise_for_status()
        photo = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
        return crop_to_fill(photo)
    except Exception as e:
        print(f"Background photo fetch skipped: {e}")
        return None


def make_gradient_bg(pal):
    top, bottom = pal["bg"], pal["bg2"]
    base = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(base)
    for row in range(H):
        t = row / H
        draw.line([(0, row), (W, row)], fill=tuple(
            int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base


def dominant_color(photo):
    """Pulls a representative rich color out of the photo itself, so the
    panel/accent color can adapt per-photo instead of using a fixed
    palette regardless of what's actually in the image."""
    small = photo.resize((60, 60))
    quant = small.quantize(colors=6, method=Image.MEDIANCUT)
    palette = quant.getpalette()
    counts = sorted(quant.getcolors(), reverse=True)
    for count, idx in counts:
        r, g, b = palette[idx * 3:idx * 3 + 3]
        brightness = (r + g + b) / 3
        sat = max(r, g, b) - min(r, g, b)
        if 35 < brightness < 215 and sat > 18:
            return (r, g, b)
    count, idx = counts[0]
    return tuple(palette[idx * 3:idx * 3 + 3])


def darken(color, factor=0.35):
    return tuple(int(c * factor) for c in color)


def lighten_for_text(color):
    r, g, b = color
    return tuple(min(255, int(c + (255 - c) * 0.55)) for c in (r, g, b))


def grade_photo(photo, tint_color, strength=0.16):
    """Consistent darken + subtle color tint so photos pulled from
    different sources still feel like one cohesive branded set instead
    of mismatched random stock images."""
    from PIL import ImageEnhance
    graded = ImageEnhance.Contrast(photo).enhance(1.06)
    graded = ImageEnhance.Color(graded).enhance(0.96)
    graded = ImageEnhance.Brightness(graded).enhance(0.94)
    tint = Image.new("RGB", graded.size, tint_color)
    return Image.blend(graded, tint, strength)


def make_photo_bg(photo, pal):
    """Photo with a branded color-tinted gradient overlay on top, so text
    stays legible and the palette identity is preserved rather than just
    slapping a random stock photo behind text."""
    overlay = make_gradient_bg(pal).convert("RGBA")
    overlay.putalpha(190)  # tint strength — high enough to guarantee text contrast
    return Image.alpha_composite(photo.convert("RGBA"), overlay).convert("RGB")


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
        f = weighted_font(F_BLACK, int(size * 0.6))
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


def fit_text(draw, text, max_width, max_lines, max_size, min_size, weight_name):
    for size in range(max_size, min_size - 1, -4):
        font = weighted_font(weight_name, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines and _all_lines_fit(draw, lines, font, max_width):
            return font, lines, size

    # Guaranteed-fit fallback: a single very long word (a long compound
    # number, hyphenated term, etc.) can still overflow even at min_size
    # since wrap_text can't break mid-word. Keep shrinking past min_size
    # until every line genuinely fits, down to a hard floor so text never
    # runs off the edge of the canvas.
    size = min_size
    while size > 22:
        size -= 3
        font = weighted_font(weight_name, size)
        lines = wrap_text(draw, text, font, max_width)
        if _all_lines_fit(draw, lines, font, max_width):
            return font, lines, size

    font = weighted_font(weight_name, 22)
    return font, wrap_text(draw, text, font, max_width), 22


def _all_lines_fit(draw, lines, font, max_width):
    return all(draw.textlength(line, font=font) <= max_width for line in lines)


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
    f_tag = weighted_font(F_BOLD, 28)
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

    f_tag = weighted_font(F_BOLD, 28)
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
    f_tag = weighted_font(F_BOLD, 30)
    draw_topic_tag(draw, MARGIN, band_top + 46, label, f_tag, pal["card"], pal["card_text"])
    isz = 120
    icon_cx, icon_cy = W - MARGIN - isz / 2, band_top + (H - band_top) / 2 + 20
    draw_icon(draw, icon_cx, icon_cy, isz, icon or "target", pal["card_text"])

    return band_top


def draw_chat_bubble_icon(draw, x, y, size, color):
    """Small speech-bubble outline icon — matches the reference exactly:
    rounded rect with a small tail, sits above the text box on the photo."""
    bw, bh = size, size * 0.72
    draw.rounded_rectangle([x, y, x + bw, y + bh], radius=bh * 0.32, outline=color, width=4)
    tail = [(x + bw * 0.18, y + bh - 2), (x + bw * 0.32, y + bh - 2), (x + bw * 0.18, y + bh + size * 0.22)]
    draw.polygon(tail, fill=color)
    # three small dots inside, like the reference
    dot_r = size * 0.05
    for i, frac in enumerate((0.28, 0.5, 0.72)):
        cx = x + bw * frac
        cy = y + bh * 0.5
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=color)


def template_photo_panel(img, headline, is_hook, icon, show_check, label,
                          photo, slide_num, total_slides, cta_text=None,
                          show_swipe=False, support_text=None):
    """Full-bleed photo with a strong gradient across the ENTIRE frame
    (not just the bottom) for guaranteed legibility anywhere text lands,
    text block vertically centered, bold heading + smaller regular
    supporting line, chat-bubble icon accent."""
    accent = dominant_color(photo)
    scrim_color = darken(accent, 0.18)

    graded = grade_photo(photo, scrim_color, strength=0.08)
    img.paste(graded, (0, 0))

    # Strong gradient across the whole photo — darkest at the very top
    # and bottom (where UI elements sit), lighter but still present in
    # the middle so centered text always has contrast to work with.
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(scrim)
    for row in range(H):
        t = row / H
        # U-shaped alpha curve: strong top, lighter middle, strong bottom
        dist_from_mid = abs(t - 0.5) * 2  # 0 at middle, 1 at edges
        alpha = int(120 + dist_from_mid * 135)
        sdraw.line([(0, row), (W, row)], fill=(*scrim_color, alpha))
    img.paste(Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(img)

    left = 64
    right_edge = W - 64
    max_w = right_edge - left

    head_size = 66 if is_hook else 54
    font_head, head_lines, head_size = fit_text(draw, headline, max_w, 4, head_size, 34, F_BLACK)
    line_h = int(head_size * 1.22)

    f_body = weighted_font(F_MEDIUM, 30)
    support_lines = wrap_text(draw, support_text, f_body, max_w)[:3] if support_text else []

    head_h = len(head_lines) * line_h
    support_h = (20 + len(support_lines) * int(30 * 1.4)) if support_lines else 0
    bubble_h = 56 + 34
    block_h = bubble_h + head_h + support_h

    # Vertically center the whole text block in the frame, leaving room
    # for the slide-counter area up top and CTA/swipe area at the bottom.
    top_bound = 140
    bottom_bound = H - (170 if cta_text else 110)
    ty = top_bound + max(0, (bottom_bound - top_bound - block_h) // 2)

    bubble_size = 56
    draw_chat_bubble_icon(draw, left, ty, bubble_size, (255, 255, 255))
    ty += bubble_size + 34

    for line in head_lines:
        draw.text((left, ty), line, font=font_head, fill=(255, 255, 255))
        ty += line_h

    if support_lines:
        ty += 20
        for line in support_lines:
            draw.text((left, ty), line, font=f_body, fill=(225, 225, 225))
            ty += int(30 * 1.4)

    if cta_text:
        f_pill = weighted_font(F_BOLD, 28)
        draw_pill(draw, left, H - 110, cta_text, f_pill, (255, 255, 255), scrim_color)

    return img


TEMPLATES = [template_full_bleed, template_card, template_block_split]


def render_slide(eyebrow_left, eyebrow_right, headline, pal,
                  show_swipe=False, cta_text=None, show_check=False,
                  is_hook=False, icon=None, seed=0, template_idx=0,
                  photo=None, slide_num=1, total_slides=6, support_text=None,
                  out_path="slide.png"):
    if photo is not None:
        img = photo.copy()
        img = template_photo_panel(
            img, headline, is_hook, icon, show_check, eyebrow_left,
            photo, slide_num, total_slides, cta_text=cta_text, show_swipe=show_swipe,
            support_text=support_text,
        )
        img.convert("RGB").save(out_path, "JPEG", quality=92)
        return out_path

    # Fallback path — no photo available this run (Pexels not configured
    # or the fetch failed), use the gradient/blob templates instead.
    img = make_gradient_bg(pal)
    img = add_depth_blobs(img, pal, seed=seed)
    draw = ImageDraw.Draw(img)

    f_eyebrow = weighted_font(F_MEDIUM, 30)
    f_pill = weighted_font(F_BOLD, 32)
    f_swipe = weighted_font(F_BOLD, 34)

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
    photo = get_background_photo(niche, seed=carousel_index)
    paths = []
    total_slides = 2 + len(carousel["body_slides"])

    p = render_slide(
        eyebrow_left=niche, eyebrow_right=f"01/{total_slides:02d}",
        headline=carousel["hook_slide"], pal=pal, show_swipe=True, is_hook=True,
        icon=icon, seed=carousel_index, template_idx=carousel_index, photo=photo,
        slide_num=1, total_slides=total_slides,
        support_text=carousel["body_slides"][0] if carousel["body_slides"] else None,
        out_path=os.path.join(out_dir, "slide_01.jpg"),
    )
    paths.append(p)

    for i, body in enumerate(carousel["body_slides"], start=2):
        p = render_slide(
            eyebrow_left=carousel["angle"], eyebrow_right=f"{i:02d}/{total_slides:02d}",
            headline=body, pal=pal, show_check=True,
            seed=carousel_index + i, template_idx=carousel_index + i, photo=photo,
            slide_num=i, total_slides=total_slides,
            out_path=os.path.join(out_dir, f"slide_{i:02d}.jpg"),
        )
        paths.append(p)

    last = total_slides
    p = render_slide(
        eyebrow_left="Follow for more", eyebrow_right=f"{last:02d}/{total_slides:02d}",
        headline=carousel["cta_slide"], pal=pal, cta_text=f"Follow {AGENCY_HANDLE}",
        seed=carousel_index + last, template_idx=carousel_index + last, photo=photo,
        slide_num=last, total_slides=total_slides,
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
