"""
Carousel image engine — EDITORIAL BOLD EDITION (v3, full redesign).

Design language: cream "press" background, near-black ink type, a single
bold accent ink color per niche (no pastel blocks), thin rules instead of
heavy colored panels, and everything center-aligned. The goal is to look
like a genuinely well-produced marketing publication, not a template.

Fixed font sizes, shrink-only fitting (never grows past target), and only
the three system fonts this project is allowed to use: LiberationSerif-Bold
(headlines, stat numbers, big serif moments), LiberationSans-Bold (badges,
tags, CTAs, anything that needs to shout at small size), and
LiberationSans-Regular (body copy, support text, handle — body slides now
carry real explanations, and regular weight reads better than bold at
paragraph length).

No trademarked platform logos are drawn anywhere — draw_topic_icon() draws
simple, original geometric marks (a ringed "G" glyph, a speech-bubble, an
envelope) that gesture at the topic without reproducing anyone's brand mark.

All primary content blocks (hook, bridge, body) are vertically centered in
the same CONTENT_TOP..CONTENT_BOTTOM zone between the header rule and the
footer rule, so short and long text both look intentionally composed
instead of stranded near the top with dead space below.
"""

from PIL import Image, ImageDraw, ImageFont
import os
import re

W, H = 1080, 1350
MARGIN = 84
CONTENT_TOP = 156
CONTENT_BOTTOM = H - 132

SYS_DIR = "/usr/share/fonts/truetype/liberation"
F_SERIF_BOLD = os.path.join(SYS_DIR, "LiberationSerif-Bold.ttf")
F_SANS_BOLD = os.path.join(SYS_DIR, "LiberationSans-Bold.ttf")
F_SANS_REG = os.path.join(SYS_DIR, "LiberationSans-Regular.ttf")

AGENCY_HANDLE = "@rd.marketing0"

BG = (245, 243, 238)
INK = (23, 22, 20)
MUTED = (128, 124, 116)
WHITE = (255, 255, 255)
CARD_BG = (255, 255, 254)

HOOK_FONT_SIZE = 92
BRIDGE_FONT_SIZE = 84
# Body copy is bold, not regular weight. Regular weight reads fine at full
# resolution but most people encounter a carousel as a small feed
# thumbnail first — thin strokes lose contrast and legibility fast at that
# size, which is exactly the wrong place to lose it. Bold at a slightly
# smaller size than the old v2 (56px) still fits the longer standalone-value
# body slides without sacrificing thumbnail-scale readability.
BODY_FONT_SIZE = 38
BODY_FONT_SIZE_MIN = 26
RECAP_HEADER_SIZE = 46
RECAP_CARD_TEXT_SIZE = 25
CTA_SAVE_SIZE = 34
CTA_COMMENT_SIZE = 50
CTA_PROMISE_SIZE = 28

FORMAT_TAG_STYLES = {
    "before-after": [("BEFORE", "muted"), ("AFTER", "accent")],
    "comparison": [("THIS", "muted"), ("THAT", "accent")],
    "myth-buster": [("MYTH", "muted"), ("FACT", "accent")],
    "step-by-step": [("STEP", "accent")],
    "steal-this": [("TEMPLATE", "accent")],
    # Previously missing entirely, which meant checklist-format carousels —
    # the format most prone to feeling like six disconnected facts — were
    # also the only format with zero visual identity tying its slides
    # together. Same tag every slide is intentional: it's a checklist, the
    # visual repetition IS the signal that these all belong to one list.
    "checklist": [("CHECKLIST", "accent")],
}

TOPIC_COLORS = {
    "google ads": {"accent": (196, 84, 42), "accent_light": (238, 219, 205)},
    "meta": {"accent": (179, 43, 58), "accent_light": (240, 209, 210)},
    "instagram": {"accent": (179, 43, 58), "accent_light": (240, 209, 210)},
    "email": {"accent": (99, 59, 130), "accent_light": (222, 210, 232)},
}
DEFAULT_COLORS = {"accent": (196, 84, 42), "accent_light": (238, 219, 205)}

ICON_KINDS = {
    "google ads": "google",
    "email": "email",
    "meta": "chat",
    "instagram": "chat",
}


def colors_for(niche):
    n = (niche or "").lower()
    for key, colors in TOPIC_COLORS.items():
        if key in n:
            return colors
    return DEFAULT_COLORS


def icon_kind_for(niche):
    n = (niche or "").lower()
    for key, kind in ICON_KINDS.items():
        if key in n:
            return kind
    return "spark"


def display_niche(niche):
    """Preserve the content brain's own casing ('Google Ads', 'Email
    Marketing') instead of forcing .lower() everywhere it's interpolated
    into a sentence — lowercasing a proper noun mid-sentence reads as a
    typo, not a style choice."""
    return niche or "Marketing"


# ============================================================
# TEXT HELPERS — centered wrap + shrink-only fit
# ============================================================

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


def fit_text_shrink_only(draw, text, max_width, max_lines, target_size, min_size, font_path):
    for size in range(target_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_width for l in lines):
            return font, lines, size
    size = min_size
    font = ImageFont.truetype(font_path, size)
    return font, wrap_text(draw, text, font, max_width), size


def draw_centered_line(draw, y, text, font, fill):
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, y), text, font=font, fill=fill)
    return tw


def draw_centered_block(draw, lines, font, start_y, line_h, fill):
    y = start_y
    for line in lines:
        draw_centered_line(draw, y, line, font, fill)
        y += line_h
    return y


STAT_RE = re.compile(r"(?:[€$£]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)")


def find_stat(text):
    m = STAT_RE.search(text)
    return m.group(0) if m else None


# ============================================================
# ORIGINAL ICONS — no trademarked logos, just simple original marks
# ============================================================

def draw_topic_icon(draw, cx, cy, kind, color, size=34):
    r = size / 2
    if kind == "google":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=4)
        f = ImageFont.truetype(F_SERIF_BOLD, int(size * 1.05))
        gw = draw.textlength("G", font=f)
        draw.text((cx - gw / 2, cy - size * 0.62), "G", font=f, fill=color)
    elif kind == "chat":
        draw.rounded_rectangle([cx - r, cy - r * 0.8, cx + r, cy + r * 0.6], radius=r * 0.5, outline=color, width=4)
        draw.polygon([(cx - r * 0.35, cy + r * 0.5), (cx - r * 0.05, cy + r * 0.5), (cx - r * 0.35, cy + r * 1.1)], fill=color)
    elif kind == "email":
        draw.rounded_rectangle([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7], radius=6, outline=color, width=4)
        draw.line([(cx - r, cy - r * 0.6), (cx, cy + r * 0.1), (cx + r, cy - r * 0.6)], fill=color, width=4, joint="curve")
    else:
        draw.line([(cx - r, cy), (cx + r, cy)], fill=color, width=4)
        draw.line([(cx, cy - r), (cx, cy + r)], fill=color, width=4)
        draw.line([(cx - r * 0.7, cy - r * 0.7), (cx + r * 0.7, cy + r * 0.7)], fill=color, width=4)
        draw.line([(cx - r * 0.7, cy + r * 0.7), (cx + r * 0.7, cy - r * 0.7)], fill=color, width=4)


def draw_bg_accent(draw, colors):
    """
    A single, very pale ring arcing in from the bottom-left corner on
    every slide — mostly off-canvas, thin, in accent_light. Purely a
    texture/cohesion device: a flat cream field on every single slide
    read as sparse once slides got more whitespace-forward, and a
    repeated quiet mark in the same spot on every slide (hook through
    CTA) is what makes a 10-slide carousel feel like one designed object
    instead of ten separate cards that happen to share a font.
    """
    r = 330
    cx, cy = -60, H + 60
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colors["accent_light"], width=3)


# ============================================================
# SHARED CHROME — folio header, footer, progress bar
# ============================================================

def draw_folio_header(draw, niche, slide_num, total_slides, colors):
    topic = display_niche(niche).upper()
    f_badge = ImageFont.truetype(F_SANS_BOLD, 21)
    counter = f"{slide_num:02d} / {total_slides}"
    label = f"{topic}   ·   {counter}"
    tw = draw.textlength(label, font=f_badge)
    icon_gap = 34
    icon_size = 30
    total_w = icon_size + icon_gap + tw
    start_x = (W - total_w) / 2
    icon_cx = start_x + icon_size / 2
    icon_cy = 66
    draw_topic_icon(draw, icon_cx, icon_cy, icon_kind_for(niche), colors["accent"], size=icon_size)
    draw.text((start_x + icon_size + icon_gap, icon_cy - 12), label, font=f_badge, fill=INK)

    f_handle = ImageFont.truetype(F_SANS_REG, 19)
    draw_centered_line(draw, 100, AGENCY_HANDLE, f_handle, MUTED)

    draw.line([(MARGIN, 138), (W - MARGIN, 138)], fill=INK, width=2)


def draw_footer_rule_and_progress(draw, slide_num, total_slides, colors):
    draw.line([(MARGIN, H - 118), (W - MARGIN, H - 118)], fill=(210, 207, 199), width=2)
    f_follow = ImageFont.truetype(F_SANS_REG, 19)
    draw_centered_line(draw, H - 100, "Follow for more", f_follow, MUTED)

    bar_y = H - 30
    bar_h = 6
    full_w = W - 2 * MARGIN
    seg_w = full_w / total_slides
    for i in range(total_slides):
        x0 = MARGIN + i * seg_w
        x1 = MARGIN + (i + 1) * seg_w - 4
        fill = INK if i < slide_num else (222, 219, 211)
        draw.rounded_rectangle([x0, bar_y, x1, bar_y + bar_h], radius=3, fill=fill)


def draw_format_tag_centered(draw, y, text, style, colors):
    f_tag = ImageFont.truetype(F_SANS_BOLD, 19)
    tw = draw.textlength(text, font=f_tag)
    pad_x = 16
    tag_w = tw + pad_x * 2
    tag_h = 34
    x = (W - tag_w) / 2
    if style == "accent":
        draw.rounded_rectangle([x, y, x + tag_w, y + tag_h], radius=tag_h // 2, fill=colors["accent"])
        fg = WHITE
    else:
        draw.rounded_rectangle([x, y, x + tag_w, y + tag_h], radius=tag_h // 2, outline=INK, width=2)
        fg = INK
    draw.text((x + pad_x, y + 7), text, font=f_tag, fill=fg)
    return tag_h


def draw_swipe_cue_centered(draw, y, colors):
    f = ImageFont.truetype(F_SANS_BOLD, 24)
    draw_centered_line(draw, y, "Keep swiping →", f, colors["accent"])


# ============================================================
# HOOK SLIDE
# ============================================================

def render_hook_slide_fixed(headline, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_bg_accent(draw, colors)
    draw_folio_header(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 20
    stat = find_stat(headline)

    font, lines, size = fit_text_shrink_only(draw, headline, max_w, 4, HOOK_FONT_SIZE, 52, F_SERIF_BOLD)
    line_h = int(size * 1.18)
    text_h = line_h * len(lines)

    stat_h = 0
    stat_font = None
    stat_line = None
    if stat:
        stat_font, stat_lines, _ = fit_text_shrink_only(draw, stat, max_w, 1, 150, 100, F_SERIF_BOLD)
        stat_line = stat_lines[0]
        ascent, descent = stat_font.getmetrics()
        stat_h = int((ascent + descent) * 0.92) + 24

    rule_gap = 30
    block_h = stat_h + rule_gap + text_h + rule_gap + 6

    top = CONTENT_TOP + max(0, ((CONTENT_BOTTOM - CONTENT_TOP) - block_h) // 2)
    y = top
    if stat:
        draw_centered_line(draw, y, stat_line, stat_font, colors["accent"])
        y += stat_h

    draw.line([((W - 140) / 2, y), ((W + 140) / 2, y)], fill=colors["accent"], width=5)
    y += rule_gap
    draw_centered_block(draw, lines, font, y, line_h, INK)
    y += text_h + (rule_gap - 4)
    draw.line([((W - 140) / 2, y), ((W + 140) / 2, y)], fill=colors["accent"], width=5)

    draw_footer_rule_and_progress(draw, slide_num, total_slides, colors)
    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# BRIDGE SLIDE
# ============================================================

def render_bridge_slide_fixed(headline, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_bg_accent(draw, colors)
    draw_folio_header(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 20
    stat = find_stat(headline)

    font, lines, size = fit_text_shrink_only(draw, headline, max_w, 4, BRIDGE_FONT_SIZE, 48, F_SERIF_BOLD)
    line_h = int(size * 1.18)
    text_h = line_h * len(lines)

    label_h = 52
    stat_h = 0
    stat_font = None
    stat_line = None
    if stat:
        stat_font, stat_lines, _ = fit_text_shrink_only(draw, stat, max_w, 1, 130, 90, F_SERIF_BOLD)
        stat_line = stat_lines[0]
        ascent, descent = stat_font.getmetrics()
        stat_h = int((ascent + descent) * 0.92) + 18

    block_h = (0 if stat else label_h) + stat_h + text_h
    top = CONTENT_TOP + max(0, ((CONTENT_BOTTOM - CONTENT_TOP) - block_h) // 2)
    y = top

    if stat:
        draw_centered_line(draw, y, stat_line, stat_font, colors["accent"])
        y += stat_h
    else:
        f_label = ImageFont.truetype(F_SANS_BOLD, 20)
        draw_centered_line(draw, y, "KEEP READING", f_label, colors["accent"])
        y += label_h

    draw_centered_block(draw, lines, font, y, line_h, INK)

    draw_footer_rule_and_progress(draw, slide_num, total_slides, colors)
    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# BODY SLIDE
# ============================================================

def render_numbered_slide_fixed(number, full_text, niche, slide_num, total_slides, out_path,
                                checklist_mode=False, show_swipe=False, format_type="", body_position=0):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_bg_accent(draw, colors)
    draw_folio_header(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 40
    font, lines, size = fit_text_shrink_only(draw, full_text, max_w, 7, BODY_FONT_SIZE, BODY_FONT_SIZE_MIN, F_SANS_BOLD)
    line_h = int(size * 1.34)
    text_h = line_h * len(lines)

    tag_options = FORMAT_TAG_STYLES.get((format_type or "").lower())
    tag_h = 34 + 30 if tag_options else 0
    badge_size = 64
    badge_block_h = badge_size + 40
    rule_gap = 20 + 4
    swipe_h = 56 if show_swipe else 0

    block_h = tag_h + badge_block_h + text_h + rule_gap + swipe_h
    y = CONTENT_TOP + max(0, ((CONTENT_BOTTOM - CONTENT_TOP) - block_h) // 2)

    if tag_options:
        text, style = tag_options[body_position % len(tag_options)]
        th = draw_format_tag_centered(draw, y, text, style, colors)
        y += th + 30

    badge_cx = W / 2
    badge_cy = y + badge_size / 2
    shadow_off = 4
    # One consistent badge shape across every format — a numbered ink
    # circle. The checkbox variant (square outline + checkmark) tested
    # weaker: it read as clutter next to the format tag pill above it, and
    # two different "this is item N" signals stacked on one slide was
    # doing more harm than good. The CHECKLIST/STEAL-THIS/etc. tag pill
    # already carries the format identity; the circle just needs to say
    # "you're on step N of the sequence," which a plain number does better
    # than an icon.
    draw.ellipse([badge_cx - badge_size / 2 + shadow_off, badge_cy - badge_size / 2 + shadow_off,
                  badge_cx + badge_size / 2 + shadow_off, badge_cy + badge_size / 2 + shadow_off], fill=(222, 219, 211))
    draw.ellipse([badge_cx - badge_size / 2, badge_cy - badge_size / 2,
                  badge_cx + badge_size / 2, badge_cy + badge_size / 2], fill=INK)
    f_num = ImageFont.truetype(F_SANS_BOLD, 28)
    num_text = str(number)
    nw = draw.textlength(num_text, font=f_num)
    draw.text((badge_cx - nw / 2, badge_cy - 18), num_text, font=f_num, fill=WHITE)
    y = badge_cy + badge_size / 2 + 40

    draw_centered_block(draw, lines, font, y, line_h, INK)
    y += text_h + 20

    draw.line([((W - 90) / 2, y), ((W + 90) / 2, y)], fill=colors["accent"], width=4)
    y += rule_gap

    if show_swipe:
        draw_swipe_cue_centered(draw, y, colors)

    draw_footer_rule_and_progress(draw, slide_num, total_slides, colors)
    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# RECAP SLIDE — card grid, re-skinned
# ============================================================

def render_recap_slide_aesthetic(recap_lines, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_bg_accent(draw, colors)
    draw_folio_header(draw, niche, slide_num, total_slides, colors)

    f_save_big = ImageFont.truetype(F_SERIF_BOLD, RECAP_HEADER_SIZE)
    bar_y = 172
    draw_centered_line(draw, bar_y, "Save This", f_save_big, INK)
    draw.line([((W - 120) / 2, bar_y + 66), ((W + 120) / 2, bar_y + 66)], fill=colors["accent"], width=4)

    f_sub = ImageFont.truetype(F_SANS_REG, 21)
    draw_centered_line(draw, bar_y + 82, f"The {display_niche(niche)} cheat sheet", f_sub, MUTED)

    card_w = (W - 2 * MARGIN - 20) // 2
    card_h = 268
    gap_x = 20
    gap_y = 16
    start_y = 300

    for i, item in enumerate(recap_lines[:6]):
        col = i % 2
        row = i // 2
        cx = MARGIN + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)

        draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=14, fill=CARD_BG, outline=(222, 219, 211), width=2)
        draw.rectangle([cx, cy, cx + 5, cy + card_h], fill=colors["accent"])

        badge_size = 40
        badge_cx = cx + card_w / 2
        badge_y = cy + 18
        draw.ellipse([badge_cx - badge_size / 2, badge_y, badge_cx + badge_size / 2, badge_y + badge_size], fill=INK)
        f_num = ImageFont.truetype(F_SANS_BOLD, 20)
        num_text = str(i + 1)
        nw = draw.textlength(num_text, font=f_num)
        draw.text((badge_cx - nw / 2, badge_y + 9), num_text, font=f_num, fill=WHITE)

        text_y = badge_y + badge_size + 18
        text_max_w = card_w - 36
        f_card = ImageFont.truetype(F_SANS_REG, RECAP_CARD_TEXT_SIZE)
        wrapped = wrap_text(draw, item, f_card, text_max_w)[:5]
        for line in wrapped:
            lw = draw.textlength(line, font=f_card)
            draw.text((cx + (card_w - lw) / 2, text_y), line, font=f_card, fill=INK)
            text_y += 32

    f_note = ImageFont.truetype(F_SANS_REG, 19)
    draw_centered_line(draw, H - 150, "Screenshot this page and use it as your checklist", f_note, MUTED)

    draw_footer_rule_and_progress(draw, slide_num, total_slides, colors)
    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# CTA SLIDE
# ============================================================

def render_cta_slide_fixed(headline, cta_word, cta_promise, support_text, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_bg_accent(draw, colors)
    draw_folio_header(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN
    ty = 210

    f_save = ImageFont.truetype(F_SANS_BOLD, CTA_SAVE_SIZE)
    save_text = f"Save this for your next {display_niche(niche)} review"
    save_lines = wrap_text(draw, save_text, f_save, max_w - 60)
    pad_x = 26
    pill_w = max(draw.textlength(l, font=f_save) for l in save_lines) + pad_x * 2
    pill_h = 56 * len(save_lines) + 20
    px = (W - pill_w) / 2
    draw.rounded_rectangle([px, ty, px + pill_w, ty + pill_h], radius=pill_h // 2 if len(save_lines) == 1 else 22, fill=INK)
    ly = ty + 14
    for line in save_lines:
        lw = draw.textlength(line, font=f_save)
        draw.text(((W - lw) / 2, ly), line, font=f_save, fill=WHITE)
        ly += 48
    ty += pill_h + 50

    if headline:
        f_head = ImageFont.truetype(F_SANS_REG, 30)
        head_lines = wrap_text(draw, headline, f_head, max_w - 40)
        for line in head_lines:
            draw_centered_line(draw, ty, line, f_head, INK)
            ty += 44
        ty += 30
    else:
        ty += 20

    f_cta = ImageFont.truetype(F_SANS_BOLD, CTA_COMMENT_SIZE)
    cta_text = f"Comment '{cta_word}'"
    cta_w = draw_centered_line(draw, ty, cta_text, f_cta, INK)
    draw.line([((W - cta_w) / 2, ty + 72), ((W + cta_w) / 2, ty + 72)], fill=colors["accent"], width=5)
    ty += 108

    if cta_promise:
        f_promise = ImageFont.truetype(F_SANS_REG, CTA_PROMISE_SIZE)
        promise_lines = wrap_text(draw, f"and you'll get {cta_promise}", f_promise, max_w - 80)
        for line in promise_lines:
            draw_centered_line(draw, ty, line, f_promise, colors["accent"])
            ty += 40
        ty += 24

    if support_text:
        f_support = ImageFont.truetype(F_SANS_REG, 26)
        support_lines = wrap_text(draw, support_text, f_support, max_w - 120)[:3]
        for line in support_lines:
            draw_centered_line(draw, ty, line, f_support, MUTED)
            ty += 38

    draw_footer_rule_and_progress(draw, slide_num, total_slides, colors)
    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# MAIN RENDERER
# ============================================================

def render_carousel(carousel, batch_date, out_dir, carousel_index=0):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    body_slides = carousel["body_slides"]
    niche = carousel.get("niche", "")
    total_slides = 4 + len(body_slides)

    p = render_hook_slide_fixed(carousel["hook_slide"], niche, 1, total_slides,
                                 os.path.join(out_dir, "slide_01.jpg"))
    paths.append(p)

    bridge = carousel.get("bridge_slide") or carousel.get("hook_slide_2") or ""
    if not bridge:
        bridge = f"The mechanic most {display_niche(niche)} accounts miss"
    p = render_bridge_slide_fixed(bridge, niche, 2, total_slides,
                                   os.path.join(out_dir, "slide_02.jpg"))
    paths.append(p)

    format_type = carousel.get("format", "")
    checklist_mode = format_type.lower() in ("checklist", "quick-win checklist", "steal-this")
    for i, body in enumerate(body_slides, start=1):
        slide_num = i + 2
        show_swipe = (i == 1) or (i == 4) or (i == len(body_slides) - 1)
        p = render_numbered_slide_fixed(i, body, niche, slide_num, total_slides,
                                         os.path.join(out_dir, f"slide_{slide_num:02d}.jpg"),
                                         checklist_mode=checklist_mode, show_swipe=show_swipe,
                                         format_type=format_type, body_position=i - 1)
        paths.append(p)

    recap_lines = carousel.get("recap_slide", body_slides)
    if isinstance(recap_lines, str):
        recap_lines = [line.strip() for line in recap_lines.split("\n") if line.strip()]
    if not recap_lines:
        recap_lines = body_slides
    last_body = total_slides - 1
    p = render_recap_slide_aesthetic(recap_lines, niche, last_body, total_slides,
                                       os.path.join(out_dir, f"slide_{last_body:02d}.jpg"))
    paths.append(p)

    last = total_slides
    cta_word = carousel.get("cta_word", "TIPS")
    cta_promise = carousel.get("cta_promise", "the checklist")
    p = render_cta_slide_fixed(carousel.get("cta_slide", ""), cta_word, cta_promise,
                                carousel.get("caption", ""), niche, last, total_slides,
                                os.path.join(out_dir, f"slide_{last:02d}.jpg"))
    paths.append(p)

    return paths


if __name__ == "__main__":
    sample = {
        "niche": "Google Ads",
        "angle": "Mistake/myth-busting",
        "format": "checklist",
        "hook_slide": "72% of ad budget is spent on searches that never convert",
        "bridge_slide": "One setting decides whether an ad reaches buyers or browsers",
        "body_slides": [
            "Broad match shows ads for any loosely related search. Phrase match only fires when someone means it — that's usually where the wasted budget was going.",
            "The dashboard shows what you're spending. The search terms report shows what people actually typed — most accounts never open it.",
            "Negative keywords block searches like 'free' or 'jobs' from triggering an ad at all — a two-minute fix most accounts skip.",
            "Most people guess cost-per-lead should sit near €50. A healthy account usually lands closer to €10-30 — the gap is targeting, not budget.",
            "A keyword with zero conversions after 30 days is rarely a timing problem. It's usually the wrong keyword.",
            "'People in' a location targets who's actually there. 'Interested in' targets anyone who ever searched it — a very different audience.",
        ],
        "recap_slide": [
            "Switch broad match to phrase match",
            "Check the search terms report weekly",
            "Add negatives for 'free' and 'jobs'",
            "Healthy cost-per-lead: €10-30, not €50",
            "Pause zero-conversion keywords after 30 days",
            "Set location to 'people in' only",
        ],
        "cta_slide": "A healthy account checks all six of these weekly.",
        "cta_word": "AUDIT",
        "cta_promise": "the 7-point Google Ads audit checklist",
        "caption": "Save this 7-point Google Ads audit checklist. Most accounts leak budget on searches that were never going to convert. #googleads #digitalmarketing #ppc"
    }
    out = render_carousel(sample, "2026-07-23", "/tmp/sample_carousel_v3b")
    print(out)
