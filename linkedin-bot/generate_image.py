"""
generate_image.py

Builds the final LinkedIn graphic (single PNG, 1200x1560) from the JSON
produced by generate_copy.py.

v10 — design rebuild. What changed vs v9 and why:

  * One system, not three. The mint subtitle band is gone; the subtitle
    now lives inside the hero under the title, so the page is two zones
    (dark hero, light chart) instead of three stacked strangers.
  * Editorial type contrast. Title is Liberation SERIF Bold (display
    voice); everything else is Sans. One weight/size per role was making
    the whole page read as system-default.
  * The boldness is spent in ONE place: the "what works" column is solid
    deep teal with white bold text. The weak column is quiet — white
    cards, hairline border, red edge strip. Symmetric pink-vs-green
    pastel blocks are the single biggest "template infographic" tell,
    and the asymmetry makes the eye land on the answer, which is the
    entire point of the format.
  * Number badges are white with a teal ring, bridging the light and
    dark columns instead of floating as a third color moment.
  * Robustness: if Pollinations is down, a deterministic gradient hero
    renders instead of the whole daily run crashing. If the subtitle's
    leading count doesn't match the number of pairs ("9 Questions" over
    8 rows), it is corrected automatically.

Fonts: system Liberation fonts only (ship on GitHub Actions ubuntu-latest).
"""

import io
import os
import re
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

CANVAS_W, CANVAS_H = 1200, 1560
PAD = 56

# ---- palette (locked: one accent family, warm paper, ink) ----
COLOR_BG = (250, 249, 246)           # paper
COLOR_INK = (24, 28, 33)             # near-black text
COLOR_ACCENT = (11, 110, 101)        # petrol teal (locked accent)
COLOR_ACCENT_DARK = (7, 60, 55)      # deep teal — strong-column card fill
COLOR_ACCENT_LINE = (11, 110, 101)
COLOR_HERO_EYEBROW = (156, 214, 205) # light teal caps on dark hero
COLOR_HERO_SUB = (222, 230, 228)     # near-white subtitle on dark hero
COLOR_WEAK_CARD = (255, 255, 255)
COLOR_WEAK_BORDER = (226, 222, 215)
COLOR_WEAK_EDGE = (185, 56, 56)      # red strip on weak cards
COLOR_WEAK_TEXT = (122, 38, 38)
COLOR_STRONG_TEXT = (255, 255, 255)
COLOR_HEADER_TEXT = (24, 28, 33)
COLOR_RULE = (216, 212, 205)
COLOR_FOOTER_TEXT = (112, 108, 100)

HERO_H = 336
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"

FONT_DIR = "/usr/share/fonts/truetype/liberation"
FONT_SERIF_BOLD = os.path.join(FONT_DIR, "LiberationSerif-Bold.ttf")
FONT_SANS_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
FONT_SANS_REG = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")

# Small footer wordmark. Edit this one constant to change/remove branding.
FOOTER_TEXT = "MARKETING-RD.COM"

QUOTE_STRIP_RE = re.compile(r'^[\s"\'‘’“”]+|[\s"\'‘’“”]+$')
LEADING_NUM_RE = re.compile(r"^(\d+)\b")


def _font(path, size):
    return ImageFont.truetype(path, size)


def clean_phrase(text):
    return QUOTE_STRIP_RE.sub("", text.strip())


def fix_subtitle_count(subtitle: str, n_pairs: int) -> str:
    """If the subtitle starts with a number that doesn't match the number
    of rows actually rendered ('9 Questions' over 8 rows), correct it.
    Cheap insurance for an unattended daily bot."""
    m = LEADING_NUM_RE.match(subtitle.strip())
    if m and int(m.group(1)) != n_pairs:
        return LEADING_NUM_RE.sub(str(n_pairs), subtitle.strip(), count=1)
    return subtitle.strip()


def _fit_font_to_width(draw, text, font_path, max_width, start_size, min_size):
    size = start_size
    while size > min_size:
        font = _font(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return _font(font_path, min_size)


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _draw_multiline(draw, lines, font, xy, fill, line_h):
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def _tracked_text(draw, xy, text, font, fill, tracking=3, anchor_center_x=None):
    """Letter-spaced caps. Pillow has no tracking, so draw per-glyph.
    If anchor_center_x is given, the whole tracked string is centered on it."""
    widths = [draw.textbbox((0, 0), ch, font=font)[2] for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (anchor_center_x - total / 2) if anchor_center_x is not None else xy[0]
    y = xy[1]
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking
    return total


def _drawn_hero(width: int, height: int, seed: int) -> Image.Image:
    """Fully drawn hero: deep teal gradient + a few precise geometric
    accents. Deterministic, crisp every day, zero network dependency —
    replaces the fetched FLUX texture, which was a daily lottery. The
    seed nudges the accent geometry so consecutive days aren't clones."""
    import random as _r
    rng = _r.Random(seed)
    img = Image.new("RGB", (width, height))
    top = (8, 34, 33)
    bottom = (17, 72, 67)
    px = img.load()
    for yy in range(height):
        t = yy / max(1, height - 1)
        row = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        for xx in range(width):
            px[xx, yy] = row
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # large thin circle, off-canvas right
    cr = rng.randint(300, 380)
    cx = width - rng.randint(60, 160)
    cy = rng.randint(-40, 60)
    od.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=(120, 200, 190, 34), width=3)
    od.ellipse([cx - cr + 40, cy - cr + 40, cx + cr - 40, cy + cr - 40], outline=(120, 200, 190, 22), width=2)
    # soft diagonal light band
    bx = rng.randint(-200, 0)
    od.polygon([(bx, height), (bx + 340, 0), (bx + 480, 0), (bx + 140, height)], fill=(200, 240, 234, 12))
    # small dot cluster bottom-left
    ox, oy = rng.randint(50, 90), height - rng.randint(70, 100)
    for r_i in range(3):
        for c_i in range(7):
            od.ellipse([ox + c_i * 22 - 2, oy + r_i * 22 - 2, ox + c_i * 22 + 2, oy + r_i * 22 + 2],
                       fill=(140, 205, 196, 46))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img


def fetch_hero_background(prompt: str, width: int, height: int, seed: int) -> Image.Image:
    """Kept for pipeline compatibility, but the hero is now fully drawn in
    Pillow (see _drawn_hero): deterministic, always crisp, no network call.
    The FLUX fetch was a daily lottery — some days it returned murk, and it
    was the last external dependency in the render path."""
    return _drawn_hero(width, height, seed)


def draw_icon_badge(draw, cx, cy, r, bg, symbol):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bg)
    w = max(3, r // 4)
    if symbol == "check":
        draw.line(
            [(cx - r * 0.5, cy + r * 0.05), (cx - r * 0.12, cy + r * 0.42), (cx + r * 0.55, cy - r * 0.35)],
            fill=(255, 255, 255), width=w, joint="curve",
        )
    else:
        off = r * 0.4
        draw.line([(cx - off, cy - off), (cx + off, cy + off)], fill=(255, 255, 255), width=w)
        draw.line([(cx - off, cy + off), (cx + off, cy - off)], fill=(255, 255, 255), width=w)


def add_soft_shadow(img, box, radius, offset=(0, 5), blur=9, opacity=60):
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    x0, y0, x1, y1 = box
    sdraw.rounded_rectangle(
        [x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]],
        radius=radius, fill=(20, 30, 35, opacity),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    img.paste(Image.alpha_composite(img.convert("RGBA"), shadow_layer).convert("RGB"), (0, 0))


def render_graphic(data: dict, seed: int = 0) -> Image.Image:
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BG)

    pairs = data["pairs"]
    n = len(pairs)

    # ---------- HERO: image + scrim + eyebrow + serif title + subtitle ----------
    hero = _drawn_hero(CANVAS_W, HERO_H, seed)
    img.paste(hero, (0, 0))

    draw = ImageDraw.Draw(img)

    # eyebrow — tracked caps, topic-derived
    eyebrow = clean_phrase(data.get("topic", "the agency playbook")).upper()
    eyebrow_font = _font(FONT_SANS_BOLD, 21)
    _tracked_text(draw, (0, 58), eyebrow, eyebrow_font, COLOR_HERO_EYEBROW,
                  tracking=6, anchor_center_x=CANVAS_W // 2)
    # short rule under eyebrow
    draw.rectangle([CANVAS_W // 2 - 26, 96, CANVAS_W // 2 + 26, 99], fill=COLOR_ACCENT)

    main = data["title_main"].upper().strip()
    highlight = data["title_highlight"].upper().strip()
    max_title_w = CANVAS_W - 2 * PAD

    chip_pad_x, chip_pad_y = 18, 10
    gap_word = 16

    title_font = _fit_font_to_width(
        draw, f"{main} {highlight}", FONT_SERIF_BOLD,
        max_title_w - chip_pad_x * 2 - gap_word, start_size=92, min_size=48,
    )
    mb = draw.textbbox((0, 0), main, font=title_font)
    hb = draw.textbbox((0, 0), highlight, font=title_font)
    main_w = mb[2] - mb[0]
    hi_w = hb[2] - hb[0]
    # shared vertical metrics so main text and chip text sit on one baseline
    asc, desc = title_font.getmetrics()
    cap_top = min(mb[1], hb[1])
    cap_bot = max(mb[3], hb[3])
    cap_h = cap_bot - cap_top

    total_w = main_w + gap_word + hi_w + chip_pad_x * 2
    one_line = total_w <= max_title_w

    title_y = 128  # cap-top y for the title line
    if one_line:
        start_x = (CANVAS_W - total_w) // 2
        draw.text((start_x, title_y - cap_top), main, font=title_font, fill=(255, 255, 255))
        chip_x0 = start_x + main_w + gap_word
        chip_box = [chip_x0, title_y - chip_pad_y,
                    chip_x0 + hi_w + chip_pad_x * 2, title_y + cap_h + chip_pad_y]
        add_soft_shadow(img, chip_box, radius=12, offset=(0, 5), blur=9, opacity=110)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(chip_box, radius=12, fill=COLOR_ACCENT)
        draw.text((chip_x0 + chip_pad_x - hb[0], title_y - cap_top), highlight,
                  font=title_font, fill=(255, 255, 255))
        sub_y = title_y + cap_h + chip_pad_y + 34
    else:
        draw.text(((CANVAS_W - main_w) // 2, title_y - cap_top), main,
                  font=title_font, fill=(255, 255, 255))
        chip_y = title_y + cap_h + 26
        chip_x0 = (CANVAS_W - hi_w - chip_pad_x * 2) // 2
        chip_box = [chip_x0, chip_y - chip_pad_y,
                    chip_x0 + hi_w + chip_pad_x * 2, chip_y + cap_h + chip_pad_y]
        add_soft_shadow(img, chip_box, radius=12, offset=(0, 5), blur=9, opacity=110)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(chip_box, radius=12, fill=COLOR_ACCENT)
        draw.text((chip_x0 + chip_pad_x - hb[0], chip_y - cap_top), highlight,
                  font=title_font, fill=(255, 255, 255))
        sub_y = chip_y + cap_h + chip_pad_y + 30

    # subtitle inside hero
    subtitle = fix_subtitle_count(data["subtitle"], n)
    sub_font = _fit_font_to_width(draw, subtitle, FONT_SANS_REG, CANVAS_W - 2 * PAD,
                                  start_size=30, min_size=20)
    sb = draw.textbbox((0, 0), subtitle, font=sub_font)
    draw.text(((CANVAS_W - (sb[2] - sb[0])) // 2, sub_y - sb[1]), subtitle,
              font=sub_font, fill=COLOR_HERO_SUB)

    # ---------- CHART ----------
    chart_top = HERO_H + 34
    footer_h = 56
    chart_bottom = CANVAS_H - footer_h

    gutter_w = 72
    col_w = (CANVAS_W - gutter_w - 2 * PAD) // 2
    left_x0 = PAD
    left_x1 = left_x0 + col_w
    gutter_cx = CANVAS_W // 2
    right_x1 = CANVAS_W - PAD
    right_x0 = right_x1 - col_w

    # column headers: icon badge + tracked caps + hairline rule
    header_font = _font(FONT_SANS_BOLD, 22)
    icon_r = 15
    head_cy = chart_top + 18
    draw_icon_badge(draw, left_x0 + icon_r, head_cy, icon_r, COLOR_WEAK_EDGE, "cross")
    _tracked_text(draw, (left_x0 + icon_r * 2 + 14, head_cy - 12),
                  "WHAT OWNERS SAY", header_font, COLOR_HEADER_TEXT, tracking=2)
    draw_icon_badge(draw, right_x0 + icon_r, head_cy, icon_r, COLOR_ACCENT, "check")
    _tracked_text(draw, (right_x0 + icon_r * 2 + 14, head_cy - 12),
                  "WHAT WORKS", header_font, COLOR_HEADER_TEXT, tracking=2)
    rule_y = head_cy + icon_r + 12
    draw.rectangle([left_x0, rule_y, left_x1, rule_y + 2], fill=COLOR_RULE)
    draw.rectangle([right_x0, rule_y, right_x1, rule_y + 2], fill=COLOR_RULE)

    rows_top = rule_y + 18
    rows_bottom = chart_bottom

    card_pad_x = 28
    edge_w = 6
    col_text_w = col_w - card_pad_x * 2 - edge_w
    min_pad_y = 21
    available_guess = rows_bottom - rows_top

    # Bolder body type for feed legibility (27px), stepping down only if
    # the full set of rows genuinely won't fit at that size.
    for body_size in (27, 25, 24, 22):
        weak_font = _font(FONT_SANS_REG, body_size)
        strong_font = _font(FONT_SANS_BOLD, body_size)
        line_h = int(body_size * 1.28)
        wrapped = []
        natural_heights = []
        for pair in pairs:
            # quotes stay on the weak side (they ARE quotes); the strong
            # side reads as directives, sharpening the column contrast
            weak = f'“{clean_phrase(pair["weak"])}”'
            strong = clean_phrase(pair["strong"])
            weak_lines = _wrap_text(draw, weak, weak_font, col_text_w)
            strong_lines = _wrap_text(draw, strong, strong_font, col_text_w)
            wrapped.append((weak_lines, strong_lines))
            content_h = max(len(weak_lines), len(strong_lines)) * line_h
            natural_heights.append(content_h + min_pad_y * 2)
        if sum(natural_heights) + 14 * (n - 1) <= available_guess:
            break

    available = rows_bottom - rows_top
    min_gap = 14
    natural_total = sum(natural_heights) + min_gap * (n - 1)
    leftover = max(0, available - natural_total)
    # Distribute leftover space carefully so short rows stay TIGHT:
    # a little into card padding (capped), a little into gaps (capped),
    # and whatever remains centers the whole block instead of bloating it.
    extra_pad_per_row = min(9.0, leftover / n / 2) if n else 0
    leftover -= extra_pad_per_row * 2 * n
    gap = min_gap + (min(10.0, leftover / (n - 1)) if n > 1 else 0)
    leftover -= (gap - min_gap) * (n - 1)
    rows_top += min(leftover / 2, 14)  # nudge down slightly; rest breathes at the bottom
    row_heights = [h + extra_pad_per_row * 2 for h in natural_heights]
    total_h = sum(row_heights) + gap * (n - 1)
    if total_h > available:
        gap = max(4, gap - (total_h - available) / max(1, n - 1))

    # timeline spine
    draw.line([(gutter_cx, rows_top + row_heights[0] / 2),
               (gutter_cx, rows_top + sum(row_heights) + gap * (n - 1) - row_heights[-1] / 2)],
              fill=COLOR_ACCENT_LINE, width=3)

    radius = 12
    row_top = rows_top
    for i, (weak_lines, strong_lines) in enumerate(wrapped):
        row_h = row_heights[i]
        row_center = row_top + row_h / 2
        left_box = [left_x0, row_top, left_x1, row_top + row_h]
        right_box = [right_x0, row_top, right_x1, row_top + row_h]

        # weak card: white, hairline border, red edge strip — quiet
        draw.rounded_rectangle(left_box, radius=radius, fill=COLOR_WEAK_CARD,
                               outline=COLOR_WEAK_BORDER, width=1)
        draw.rounded_rectangle([left_x0, row_top, left_x0 + edge_w * 2, row_top + row_h],
                               radius=radius, fill=COLOR_WEAK_EDGE)
        draw.rectangle([left_x0 + edge_w, row_top, left_x0 + edge_w * 2, row_top + row_h],
                       fill=COLOR_WEAK_CARD)

        # strong card: solid deep teal, white bold text — the loud column
        add_soft_shadow(img, right_box, radius=radius, offset=(0, 4), blur=8, opacity=50)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(right_box, radius=radius, fill=COLOR_ACCENT_DARK)

        weak_h = len(weak_lines) * line_h
        strong_h = len(strong_lines) * line_h
        _draw_multiline(draw, weak_lines, weak_font,
                        (left_x0 + edge_w + card_pad_x, row_center - weak_h / 2 + 3),
                        COLOR_WEAK_TEXT, line_h)
        _draw_multiline(draw, strong_lines, strong_font,
                        (right_x0 + card_pad_x, row_center - strong_h / 2 + 3),
                        COLOR_STRONG_TEXT, line_h)

        # swap badge: white fill, teal ring, weak→strong chevron. The rows
        # aren't a sequence, so numbers implied an order that doesn't
        # exist; the chevron encodes the actual story — swap this for that.
        badge_r = 23
        draw.ellipse([gutter_cx - badge_r, row_center - badge_r,
                      gutter_cx + badge_r, row_center + badge_r],
                     fill=COLOR_BG, outline=COLOR_ACCENT, width=3)
        ch_h, ch_w, ch_gap = 9, 7, 9
        for k in (-1, 0):
            x0 = gutter_cx + k * ch_gap - ch_w / 2 + 2
            draw.line([(x0, row_center - ch_h), (x0 + ch_w, row_center),
                       (x0, row_center + ch_h)],
                      fill=COLOR_ACCENT, width=4, joint="curve")

        row_top += row_h + gap

    # ---------- FOOTER ----------
    if FOOTER_TEXT:
        f_font = _font(FONT_SANS_BOLD, 18)
        _tracked_text(draw, (0, CANVAS_H - footer_h + 16), FOOTER_TEXT, f_font,
                      COLOR_FOOTER_TEXT, tracking=4, anchor_center_x=CANVAS_W // 2)
    draw.rectangle([0, CANVAS_H - 8, CANVAS_W, CANVAS_H], fill=COLOR_ACCENT)

    return img


def build_image(data: dict, seed: int | None = None) -> Image.Image:
    import random
    if seed is None:
        seed = random.randint(1, 999999)
    return render_graphic(data, seed=seed)


if __name__ == "__main__":
    import json
    import sys

    with open(sys.argv[1]) as f:
        data = json.load(f)
    out_path = sys.argv[2] if len(sys.argv) > 2 else "output.png"
    image = build_image(data)
    image.save(out_path, "PNG")
    print(f"Saved {out_path}")
