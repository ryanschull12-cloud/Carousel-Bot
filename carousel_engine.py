"""
Carousel image engine — FIXED SIZE EDITION:
- Fixed font sizes per slide type (no auto-growing)
- Smart shrink-only fitting (if text is too long, shrink; never grow beyond target)
- Visual fill elements: accent bars, decorative spacing, centered layouts
- Every slide looks designed and full regardless of text length
"""

from PIL import Image, ImageDraw, ImageFont
import os
import re

W, H = 1080, 1350
MARGIN = 76

SYS_DIR = "/usr/share/fonts/truetype/liberation"
F_SERIF_BOLD = os.path.join(SYS_DIR, "LiberationSerif-Bold.ttf")
F_SANS_BOLD = os.path.join(SYS_DIR, "LiberationSans-Bold.ttf")
F_SANS_REG = os.path.join(SYS_DIR, "LiberationSans-Regular.ttf")

AGENCY_HANDLE = "@rd.marketing0"

BG = (240, 239, 234)
DOT_COLOR = (225, 223, 216)
TEXT = (20, 20, 20)
GRAY = (130, 130, 130)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
SHADOW = (205, 202, 194)  # soft depth shade for badges, one tone below BG

# FIXED FONT SIZES — never auto-grow beyond these
HOOK_FONT_SIZE = 96       # Hook slides: big, dramatic, consistent
BRIDGE_FONT_SIZE = 88     # Bridge slides: slightly smaller than hook
BODY_FONT_SIZE = 64       # Body slides: readable, punchy, consistent (bumped up from 56 for readability)
RECAP_HEADER_SIZE = 48    # Recap "Save This" header
RECAP_CARD_TEXT_SIZE = 26 # Recap card text
CTA_SAVE_SIZE = 36        # CTA save ask
CTA_COMMENT_SIZE = 52     # CTA comment keyword
CTA_PROMISE_SIZE = 30     # CTA promise line

# Design constants the automated design-feedback-loop (experiment_loop.py) is
# allowed to test, with safe min/max bounds. This is the single source of
# truth for "safe design constants" — runner.py checks a constant name is a
# key here before applying an experimental override at render time, and
# experiment_loop.py checks a proposed variant_value falls within its bounds
# before ever proposing or promoting a change. Nothing outside this dict
# (no new slide types, no layout/rendering logic) is ever touched
# automatically. Bounds keep every font at or above the "never auto-grow,
# minimum X" floors documented for each slide type.
EXPERIMENTABLE_CONSTANTS = {
    "HOOK_FONT_SIZE": {"min": 72, "max": 104},
    "BRIDGE_FONT_SIZE": {"min": 64, "max": 96},
    "BODY_FONT_SIZE": {"min": 48, "max": 72},
    "RECAP_HEADER_SIZE": {"min": 36, "max": 56},
    "RECAP_CARD_TEXT_SIZE": {"min": 20, "max": 32},
    "CTA_SAVE_SIZE": {"min": 28, "max": 44},
    "CTA_COMMENT_SIZE": {"min": 40, "max": 60},
    "CTA_PROMISE_SIZE": {"min": 24, "max": 36},
}

TOPIC_COLORS = {
    "google ads": {"accent": (161, 214, 191), "dark": (30, 90, 65), "light": (200, 240, 220)},
    "meta": {"accent": (240, 172, 168), "dark": (140, 45, 45), "light": (255, 220, 215)},
    "instagram": {"accent": (240, 172, 168), "dark": (140, 45, 45), "light": (255, 220, 215)},
    "email": {"accent": (196, 176, 226), "dark": (80, 55, 120), "light": (225, 210, 245)},
}
DEFAULT_COLORS = {"accent": (161, 214, 191), "dark": (30, 90, 65), "light": (200, 240, 220)}


def colors_for(niche):
    n = (niche or "").lower()
    for key, colors in TOPIC_COLORS.items():
        if key in n:
            return colors
    return DEFAULT_COLORS


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
    """
    SHRINK-ONLY fitting: start at target_size, only go DOWN if text doesn't fit.
    Never grows beyond target_size. This ensures consistent sizing.
    """
    for size in range(target_size, min_size - 1, -4):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_width for l in lines):
            return font, lines, size
    # Emergency fallback
    size = min_size
    font = ImageFont.truetype(font_path, size)
    return font, wrap_text(draw, text, font, max_width), size


def draw_dot_grid(draw, spacing=48, radius=2):
    for y in range(60, H - 40, spacing):
        for x in range(60, W - 40, spacing):
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=DOT_COLOR)


def draw_progress_bar(draw, slide_num, total_slides, accent_color, dark_color):
    bar_y = H - 24
    bar_h = 8
    full_w = W - 2 * MARGIN
    segment_w = full_w / total_slides
    for i in range(total_slides):
        x0 = MARGIN + i * segment_w
        x1 = MARGIN + (i + 1) * segment_w - 4
        if i < slide_num:
            fill = dark_color
        else:
            fill = (220, 220, 220)
        draw.rounded_rectangle([x0, bar_y, x1, bar_y + bar_h], radius=4, fill=fill)


def draw_topic_badge(draw, niche, colors):
    topic = niche.upper() if niche else "MARKETING"
    f_badge = ImageFont.truetype(F_SANS_BOLD, 22)
    tw = draw.textlength(topic, font=f_badge)
    pad_x = 20
    badge_w = tw + pad_x * 2
    badge_h = 40
    draw.rounded_rectangle([MARGIN, 48, MARGIN + badge_w, 48 + badge_h],
                            radius=badge_h // 2, fill=colors["accent"])
    draw.text((MARGIN + pad_x, 48 + 8), topic, font=f_badge, fill=colors["dark"])


def draw_slide_counter(draw, slide_num, total_slides, dark_color):
    f_counter = ImageFont.truetype(F_SANS_BOLD, 22)
    counter = f"{slide_num}/{total_slides}"
    cw = draw.textlength(counter, font=f_counter)
    # Circle was a fixed 44px, sized for a single-digit numerator like
    # "1/10". Every carousel's final slide is "10/10" -- a 2-digit
    # numerator that measures wider than the circle, so the leading "1"
    # got drawn mostly outside the dark circle, on the light background,
    # in white text -- effectively invisible, reading as "0/10" on every
    # single post's last slide. Size the circle to the actual text width
    # (with a floor at the old 44px so single-digit counters look
    # unchanged) instead of assuming a fixed width.
    pad = 14
    circle_size = max(44, int(cw) + pad)
    cx = W - MARGIN - circle_size
    cy = 46
    draw.ellipse([cx, cy, cx + circle_size, cy + circle_size], fill=dark_color)
    draw.text((cx + (circle_size - cw) / 2, cy + (circle_size - 22) / 2 - 2), counter, font=f_counter, fill=WHITE)


def draw_header_v2(draw, niche, slide_num, total_slides, colors):
    draw_topic_badge(draw, niche, colors)
    f_handle = ImageFont.truetype(F_SANS_REG, 20)
    hw = draw.textlength(AGENCY_HANDLE, font=f_handle)
    draw.text(((W - hw) / 2, 58), AGENCY_HANDLE, font=f_handle, fill=GRAY)
    draw_slide_counter(draw, slide_num, total_slides, colors["dark"])


STAT_RE = re.compile(r"(?:[€$£]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)")


def find_stat(text):
    """Pull a currency amount or percentage out of a line, if one exists."""
    m = STAT_RE.search(text)
    return m.group(0) if m else None


def find_highlight_word(text):
    stat = find_stat(text)
    if stat:
        return stat
    words = text.split()
    if len(words) >= 3:
        return " ".join(words[-2:]).rstrip(".")
    return None


def slide_text_and_keyword(body):
    """body_slides entries may be either a plain string, or a
    {"text": ..., "keyword": ...} object -- critic_system_prompt.txt's
    schema, used so the critic pass can point at an exact substring to
    highlight instead of leaving it to the find_highlight_word() guess.
    Normalize both shapes here so rendering works regardless of which one
    the content pipeline handed us for a given slide. This is what broke
    daily generation on 2026-07-25: the critic pass started emitting the
    dict shape and this file only ever handled plain strings, so
    full_text.split() crashed on a dict every time a slide came back
    critic-rewritten.
    """
    if isinstance(body, dict):
        return (body.get("text") or ""), (body.get("keyword") or None)
    return body, None


def slide_before_after(body):
    """Optional before/after pair for the before-after format's split
    visual (see draw_before_after_strip / render_numbered_slide_fixed).
    Every format currently renders its body slides with the exact same
    card+badge layout regardless of format -- the only visual difference
    between "checklist" and "before-after" was a checkbox vs a circle.
    This gives the before-after format its own signature moment when the
    content brain supplies explicit before/after values on a slide.
    Returns (None, None) for a plain string or a dict missing either key,
    so every other format's rendering is completely unaffected -- purely
    additive, same defensive pattern as slide_text_and_keyword above.
    """
    if isinstance(body, dict):
        before = (body.get("before") or "").strip()
        after = (body.get("after") or "").strip()
        if before and after:
            return before, after
    return None, None


def draw_right_arrow(draw, x, y, length, color, thickness=6):
    """A drawn arrow, not a unicode glyph -- Liberation Sans Bold doesn't
    reliably include arrow glyphs (same reason the recap checkmark is
    drawn as strokes instead of a '✓' character elsewhere in this file)."""
    draw.line([(x, y), (x + length, y)], fill=color, width=thickness)
    head = 14
    draw.polygon([(x + length - 2, y - head), (x + length + head, y), (x + length - 2, y + head)], fill=color)


def draw_before_after_strip(draw, before_val, after_val, colors, y, max_width):
    """
    The before-after format's signature visual: a muted, struck-through
    old value, an arrow, and the new value bold in the niche accent color
    -- distinct from every other format's plain text card, so a
    before/after carousel finally looks like a transformation instead of
    just another list of facts. Shrinks both values together if the pair
    is too wide for the card at full size, same shrink-only pattern used
    everywhere else in this file.
    """
    target, min_size = 60, 34
    size = target
    f_val = ImageFont.truetype(F_SERIF_BOLD, size)
    f_arrow_gap = 70
    while size > min_size:
        before_w = draw.textlength(before_val, font=f_val)
        after_w = draw.textlength(after_val, font=f_val)
        total_w = before_w + f_arrow_gap + after_w
        if total_w <= max_width:
            break
        size -= 4
        f_val = ImageFont.truetype(F_SERIF_BOLD, size)
    before_w = draw.textlength(before_val, font=f_val)
    after_w = draw.textlength(after_val, font=f_val)
    total_w = before_w + f_arrow_gap + after_w
    x = (W - total_w) / 2

    # BEFORE — muted gray, struck through
    draw.text((x, y), before_val, font=f_val, fill=GRAY)
    strike_y = y + size * 0.5
    draw.line([(x - 4, strike_y), (x + before_w + 4, strike_y)], fill=GRAY, width=4)
    x += before_w

    # arrow, centered in the gap between the two values
    arrow_len = f_arrow_gap - 36
    draw_right_arrow(draw, x + 14, y + size * 0.45, arrow_len, colors["dark"], thickness=6)
    x += f_arrow_gap

    # AFTER — bold, accent-colored, same flat shadow-pop treatment as the
    # hook/bridge mega-stat so this reads as the carousel's other hero
    # moments do.
    shadow_off = max(3, size // 16)
    draw.text((x + shadow_off, y + shadow_off), after_val, font=f_val, fill=colors["accent"])
    draw.text((x, y), after_val, font=f_val, fill=colors["dark"])

    return int(size * 1.5)  # height this strip occupied, for the caller to reserve


def slide_comparison(body):
    """Optional side-by-side pair for the comparison format's split visual
    (see draw_comparison_strip). Distinct from slide_before_after: a
    comparison is two options being weighed against each other (broad
    match vs phrase match), not a temporal old-value-to-new-value
    transformation, so it gets its own key names and its own visual
    treatment (a VS badge, not a struck-through arrow) rather than
    overloading before/after semantics onto something that isn't a
    before/after. Returns (None, None) unless both are present, same
    purely-additive fail-safe pattern as slide_before_after."""
    if isinstance(body, dict):
        a = (body.get("compare_a") or "").strip()
        b = (body.get("compare_b") or "").strip()
        if a and b:
            return a, b
    return None, None


def draw_comparison_strip(draw, side_a, side_b, colors, y, max_width):
    """
    The comparison format's signature visual: two short labels with a bold
    'VS' badge between them, both sides equally weighted (unlike
    before/after, neither side is struck through or muted -- a comparison
    format is choosing between two live options, not showing one replace
    the other). Shrinks both labels together if they're too wide for the
    card, same shrink-only pattern as draw_before_after_strip.
    """
    target, min_size = 52, 30
    size = target
    f_val = ImageFont.truetype(F_SERIF_BOLD, size)
    badge_gap = 90  # space reserved for the VS badge between the two sides
    while size > min_size:
        a_w = draw.textlength(side_a, font=f_val)
        b_w = draw.textlength(side_b, font=f_val)
        total_w = a_w + badge_gap + b_w
        if total_w <= max_width:
            break
        size -= 4
        f_val = ImageFont.truetype(F_SERIF_BOLD, size)
    a_w = draw.textlength(side_a, font=f_val)
    b_w = draw.textlength(side_b, font=f_val)
    total_w = a_w + badge_gap + b_w
    x = (W - total_w) / 2
    text_h = int(size * 1.05)

    # Side A — dark, flat shadow-pop, same treatment every hero moment in
    # this design gets.
    shadow_off = max(3, size // 16)
    draw.text((x + shadow_off, y + shadow_off), side_a, font=f_val, fill=colors["accent"])
    draw.text((x, y), side_a, font=f_val, fill=colors["dark"])
    x += a_w

    # VS badge, centered in the gap
    badge_d = 56
    badge_cx = x + badge_gap / 2
    badge_cy = y + text_h / 2
    draw.ellipse([badge_cx - badge_d / 2, badge_cy - badge_d / 2,
                  badge_cx + badge_d / 2, badge_cy + badge_d / 2], fill=colors["dark"])
    f_vs = ImageFont.truetype(F_SANS_BOLD, 22)
    vs_w = draw.textlength("VS", font=f_vs)
    draw.text((badge_cx - vs_w / 2, badge_cy - 13), "VS", font=f_vs, fill=WHITE)
    x += badge_gap

    # Side B — same treatment as side A, no visual hierarchy between them.
    draw.text((x + shadow_off, y + shadow_off), side_b, font=f_val, fill=colors["accent"])
    draw.text((x, y), side_b, font=f_val, fill=colors["dark"])

    return int(size * 1.5)


def draw_marker_bold(draw, x, y, w, h, color):
    r, g, b = color
    marker_color = (r, g, b, 200)
    pts = [(x - 8, y + h * 0.12), (x + w + 10, y - h * 0.10),
           (x + w + 8, y + h * 0.98), (x - 10, y + h * 1.08)]
    draw.polygon(pts, fill=marker_color)


def draw_text_highlighted_v2(draw, x, y, line, font, highlight, text_color, marker_color):
    if not highlight or highlight not in line:
        draw.text((x, y), line, font=font, fill=text_color)
        return
    before, _, after = line.partition(highlight)
    cx = x
    if before:
        cx += draw.textlength(before, font=font)
    hw = draw.textlength(highlight, font=font)
    ascent, _ = font.getmetrics()
    draw_marker_bold(draw, cx, y + ascent * 0.06, hw, ascent * 0.88, marker_color)
    draw.text((x, y), line, font=font, fill=text_color)


def draw_text_highlighted_centered(draw, y, line, font, highlight, text_color, marker_color):
    """Same as draw_text_highlighted_v2, but centers this line horizontally
    on the page instead of drawing from a fixed left x. Used everywhere the
    design should read as centered rather than left-aligned."""
    lw = draw.textlength(line, font=font)
    x = (W - lw) / 2
    draw_text_highlighted_v2(draw, x, y, line, font, highlight, text_color, marker_color)


def draw_corner_flag(draw, colors):
    """
    UPGRADE 2 — bold diagonal accent wedge in the top-right corner.
    A consistent, non-photo, no-extra-font brand mark on every single slide.
    Sits under the slide counter, which is drawn on top of it afterward.
    """
    size = 130
    draw.polygon([(W, 0), (W, size), (W - size, 0)], fill=colors["accent"])


def draw_mega_stat(draw, text, y, colors, max_width, font_path=F_SERIF_BOLD, target=170, min_size=110):
    """
    UPGRADE 1 — render a pulled-out number/€/% stat at oversized scale above the
    headline. Only fires when the hook/bridge line actually contains a stat, so
    every loss-aversion-framed hook (the format the content brain is told to
    prioritize) gets a genuine pattern-interrupt instead of just bigger body text.
    Centered horizontally to match the centered headline below it.

    Carries a flat drop-shadow duplicate behind the main glyphs — same
    depth technique already used for the number badges elsewhere in this
    file (SHADOW color, a few px offset), not a blur/glow, so the giant
    stat gets more visual pop without breaking the flat, sharp, editorial
    look the rest of the design commits to.
    """
    font, lines, size = fit_text_shrink_only(draw, text, max_width, 1, target, min_size, font_path)
    line = lines[0] if lines else text
    lw = draw.textlength(line, font=font)
    x = (W - lw) / 2
    shadow_off = max(4, size // 28)
    draw.text((x + shadow_off, y + shadow_off), line, font=font, fill=SHADOW)
    draw.text((x, y), line, font=font, fill=colors["dark"])
    ascent, descent = font.getmetrics()
    return y + int((ascent + descent) * 0.92), size


def draw_mega_phrase(draw, text, y, colors, max_width, font_path=F_SERIF_BOLD, target=130, min_size=76):
    """
    Same pattern-interrupt role as draw_mega_stat, for hooks/bridges that
    don't contain a €/$/% figure (which, per the content brain's BENEFIT
    OVER RAW STAT rule, is most of them now). Renders the content brain's
    hook_pop_phrase/bridge_pop_phrase — a short, punchy consequence phrase —
    at oversized scale, centered, so every hook gets the same visual
    pattern-interrupt a number-led hook gets, not just the minority that
    happen to cite a stat. Allows up to 2 lines since phrases run longer
    than a bare number.

    hook_pop_phrase/bridge_pop_phrase are pulled as an exact mid-sentence
    substring (required so the inline highlight marker can find them in
    the headline below), so they usually arrive lowercase — e.g. "beat 10k
    cold ones" or "charges you double". That reads as a typo once it's
    blown up to 130px and standing alone as its own heading, so the first
    character is capitalized for THIS display only; the original `text`
    string (and therefore the highlight match against the headline) is
    left untouched.
    """
    font, lines, size = fit_text_shrink_only(draw, text, max_width, 2, target, min_size, font_path)
    line_h = int(size * 1.05)
    shadow_off = max(4, size // 28)
    for i, line in enumerate(lines):
        display_line = line[0].upper() + line[1:] if i == 0 and line else line
        lw = draw.textlength(display_line, font=font)
        x = (W - lw) / 2
        # Same flat drop-shadow depth treatment as draw_mega_stat, so a
        # benefit-led hook's giant phrase pops exactly as hard as a
        # number-led hook's giant stat does — no visual tier difference
        # between the two hook styles now that BENEFIT OVER RAW STAT means
        # most hooks take this path instead of draw_mega_stat's.
        draw.text((x + shadow_off, y + shadow_off), display_line, font=font, fill=SHADOW)
        draw.text((x, y), display_line, font=font, fill=colors["dark"])
        y += line_h
    return y + 14, size


def draw_accent_bar(draw, y, colors, width=None):
    bar_h = 6
    w = width if width else (W - 2 * MARGIN)
    x0 = (W - w) / 2
    draw.rectangle([x0, y, x0 + w, y + bar_h], fill=colors["accent"])


def draw_swipe_arrow(draw, colors):
    f_arrow = ImageFont.truetype(F_SANS_BOLD, 30)
    arrow_text = "Swipe →"
    tw = draw.textlength(arrow_text, font=f_arrow)
    pad = 16
    pill_w = tw + pad * 2
    pill_h = 44
    px = W - MARGIN - pill_w
    py = H - 140
    draw.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=pill_h // 2, fill=colors["accent"])
    draw.text((px + pad, py + 6), arrow_text, font=f_arrow, fill=colors["dark"])


def draw_follow_pill(draw, colors):
    f_follow = ImageFont.truetype(F_SANS_REG, 18)
    follow_text = "Follow for more"
    tw = draw.textlength(follow_text, font=f_follow)
    pad = 12
    pill_w = tw + pad * 2
    pill_h = 32
    px = (W - pill_w) / 2
    py = H - 60
    draw.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=pill_h // 2,
                            outline=colors["dark"], width=1)
    draw.text((px + pad, py + 5), follow_text, font=f_follow, fill=colors["dark"])


# ============================================================
# DECORATIVE FILL ELEMENTS — make short text look designed
# ============================================================

def draw_decorative_quote_marks(draw, y, colors):
    """Large decorative quote marks to fill space on short hook slides."""
    f_quote = ImageFont.truetype(F_SERIF_BOLD, 120)
    draw.text((MARGIN - 10, y), "“", font=f_quote, fill=colors["light"])
    draw.text((W - MARGIN - 50, y + 200), "”", font=f_quote, fill=colors["light"])


def draw_vertical_accent_line(draw, x, y0, y1, colors):
    """Vertical accent line for visual interest."""
    draw.rectangle([x, y0, x + 4, y1], fill=colors["accent"])


def draw_bottom_accent_block(draw, y, height, colors):
    """Large accent color block at bottom to fill space."""
    draw.rectangle([0, y, W, y + height], fill=colors["light"])


# ============================================================
# HOOK SLIDE — fixed size, designed fill
# ============================================================

def render_hook_slide_fixed(headline, niche, slide_num, total_slides, out_path, pop_phrase=None):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_corner_flag(draw, colors)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 40  # slightly narrower for better line breaks

    # UPGRADE 1: pull a stat out and render it oversized before the headline.
    # Most hooks won't have one now (BENEFIT OVER RAW STAT pushed the content
    # brain toward outcome-led hooks) — when there's no stat, fall back to
    # the content brain's hook_pop_phrase so every hook still gets the same
    # giant-text pattern-interrupt, not just the number-led minority.
    stat = find_stat(headline)
    top_y = 260
    if stat:
        top_y, _ = draw_mega_stat(draw, stat, top_y, colors, max_w)
        top_y += 24
    elif pop_phrase and pop_phrase in headline:
        top_y, _ = draw_mega_phrase(draw, pop_phrase, top_y, colors, max_w)
        top_y += 24

    # FIXED SIZE: 96px, shrink only if needed
    font, lines, size = fit_text_shrink_only(draw, headline, max_w, 4, HOOK_FONT_SIZE, 52, F_SERIF_BOLD)
    line_h = int(size * 1.2)
    have_pop = bool(pop_phrase and pop_phrase in headline)
    highlight = pop_phrase if have_pop else find_highlight_word(headline)

    total_h = line_h * len(lines)

    # CENTER the remaining text block in whatever space is left below the stat
    available_h = H - top_y - 180  # header/stat to progress bar
    ty = top_y + max(0, (available_h - total_h) // 2)

    # If text is very short (1-2 lines) and there's no mega element already
    # doing the attention-grabbing work, add decorative elements
    if len(lines) <= 2 and not stat and not have_pop:
        draw_decorative_quote_marks(draw, ty - 40, colors)
        draw_accent_bar(draw, ty - 60, colors, width=200)
        draw_accent_bar(draw, ty + total_h + 40, colors, width=200)
    else:
        draw_accent_bar(draw, ty - 30, colors)
        draw_accent_bar(draw, ty + total_h + 20, colors)

    for line in lines:
        draw_text_highlighted_centered(draw, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# BRIDGE SLIDE — fixed size, designed fill
# ============================================================

def render_bridge_slide_fixed(headline, niche, slide_num, total_slides, out_path, pop_phrase=None):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_corner_flag(draw, colors)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 40

    # UPGRADE 1, scaled down: bridge should carry the same weight as the hook
    # without literally duplicating it, so the mega-stat/phrase here targets
    # a smaller size. Same stat-first, pop_phrase-fallback logic as the hook.
    stat = find_stat(headline)
    top_y = 260
    if stat:
        top_y, _ = draw_mega_stat(draw, stat, top_y, colors, max_w, target=140, min_size=90)
        top_y += 20
    elif pop_phrase and pop_phrase in headline:
        top_y, _ = draw_mega_phrase(draw, pop_phrase, top_y, colors, max_w, target=110, min_size=68)
        top_y += 20

    font, lines, size = fit_text_shrink_only(draw, headline, max_w, 4, BRIDGE_FONT_SIZE, 48, F_SERIF_BOLD)
    line_h = int(size * 1.2)
    have_pop = bool(pop_phrase and pop_phrase in headline)
    highlight = pop_phrase if have_pop else find_highlight_word(headline)

    total_h = line_h * len(lines)
    available_h = H - top_y - 180
    ty = top_y + max(0, (available_h - total_h) // 2)

    # Bridge mirrors the hook's centered framing (top/bottom accent bars,
    # plus decorative quote marks on short lines) so slides 1 and 2 carry
    # the same visual weight, per the re-hook rule.
    if len(lines) <= 2 and not stat and not have_pop:
        draw_decorative_quote_marks(draw, ty - 30, colors)
        draw_accent_bar(draw, ty - 50, colors, width=200)
        draw_accent_bar(draw, ty + total_h + 30, colors, width=200)
    else:
        draw_accent_bar(draw, ty - 25, colors)
        draw_accent_bar(draw, ty + total_h + 15, colors)

    for line in lines:
        draw_text_highlighted_centered(draw, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# BODY SLIDE — fixed size, designed fill
# ============================================================

def render_numbered_slide_fixed(number, full_text, niche, slide_num, total_slides, out_path,
                                checklist_mode=False, show_swipe=False):
    before_val, after_val = slide_before_after(full_text)
    side_a, side_b = slide_comparison(full_text)
    full_text, explicit_keyword = slide_text_and_keyword(full_text)
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_corner_flag(draw, colors)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    badge_size = 80
    gap_below_badge = 28
    card_pad_x = 44
    card_pad_y = 36
    max_w = W - 2 * MARGIN - 2 * card_pad_x

    # FIXED SIZE: 64px (bumped up from 56 for readability), shrink only if
    # needed. Floor raised from 36 to 44 too, so a long body line shrinks
    # less aggressively before it stops looking like the same slide type.
    font, lines, size = fit_text_shrink_only(draw, full_text, max_w, 4, BODY_FONT_SIZE, 44, F_SANS_BOLD)
    line_h = int(size * 1.3)  # slightly more breathing room between lines than other slide types

    total_h = line_h * len(lines)

    # Before-after and comparison formats each get their own signature
    # strip (see draw_before_after_strip / draw_comparison_strip), which
    # reserves extra room at the top of the card. strip_h is 0 whenever a
    # slide supplies neither, which makes every formula below identical to
    # the old behavior for every other format. A slide should only ever
    # carry one of the two (each is scoped to a different format), but if
    # both were somehow present, before/after wins rather than stacking
    # two strips on one card.
    has_before_after = bool(before_val and after_val)
    has_comparison = bool(side_a and side_b) and not has_before_after
    strip_h = 108 if (has_before_after or has_comparison) else 0

    # Centered stack: number badge on top, card of text centered below it —
    # both centered horizontally on the page instead of left-aligned.
    content_h = badge_size + gap_below_badge + card_pad_y * 2 + strip_h + total_h
    available_h = H - 280 - 200
    top_y = 280 + max(0, (available_h - content_h) // 2)

    badge_x = (W - badge_size) / 2
    badge_y = top_y
    block_y = badge_y + badge_size + gap_below_badge
    block_h = card_pad_y * 2 + strip_h + total_h
    block_x0 = MARGIN
    block_x1 = W - MARGIN

    # UPGRADE 3: accent block renders behind EVERY body slide, not just
    # short-text ones — this is what was making some slides look designed
    # and others look plain within the same carousel.
    draw.rounded_rectangle([block_x0, block_y, block_x1, block_y + block_h],
                          radius=14, fill=colors["light"])

    # Number badge or checkbox, now with a soft drop shadow for depth
    shadow_off = 5
    if number is not None:
        if checklist_mode:
            draw.rounded_rectangle([badge_x + shadow_off, badge_y + shadow_off,
                                     badge_x + badge_size + shadow_off, badge_y + badge_size + shadow_off],
                                  radius=8, fill=SHADOW)
            draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                                  radius=8, outline=colors["dark"], width=4, fill=BG)
            # Drawn as strokes rather than the "✓" glyph -- Liberation Sans
            # Bold doesn't reliably include that character, which was
            # rendering as a tofu/notdef box instead of a checkmark.
            draw.line([
                (badge_x + 18, badge_y + 42),
                (badge_x + 32, badge_y + 56),
                (badge_x + 62, badge_y + 22),
            ], fill=colors["dark"], width=7, joint="curve")
        else:
            draw.ellipse([badge_x + shadow_off, badge_y + shadow_off,
                          badge_x + badge_size + shadow_off, badge_y + badge_size + shadow_off],
                         fill=SHADOW)
            draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                         fill=colors["dark"])
            f_num = ImageFont.truetype(F_SANS_BOLD, int(badge_size * 0.45))
            num_text = str(number)
            tw = draw.textlength(num_text, font=f_num)
            draw.text((badge_x + (badge_size - tw) / 2, badge_y + badge_size * 0.24),
                     num_text, font=f_num, fill=WHITE)

    highlight = explicit_keyword or find_highlight_word(full_text)
    ty = block_y + card_pad_y
    if has_before_after:
        strip_used = draw_before_after_strip(draw, before_val, after_val, colors, ty, max_w)
        ty += max(strip_used, strip_h)
    elif has_comparison:
        strip_used = draw_comparison_strip(draw, side_a, side_b, colors, ty, max_w)
        ty += max(strip_used, strip_h)
    for line in lines:
        draw_text_highlighted_centered(draw, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    if show_swipe:
        draw_swipe_arrow(draw, colors)

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# AESTHETIC RECAP SLIDE — card based (already good, keep it)
# ============================================================

def render_recap_slide_aesthetic(recap_lines, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    # "Save This" badge
    f_save_big = ImageFont.truetype(F_SERIF_BOLD, RECAP_HEADER_SIZE)
    save_text = "Save This"
    stw = draw.textlength(save_text, font=f_save_big)
    bar_pad = 30
    bar_y = 155
    bar_h = 70
    draw.rounded_rectangle([ (W - stw)/2 - bar_pad, bar_y, (W + stw)/2 + bar_pad, bar_y + bar_h ],
                            radius=bar_h // 2, fill=colors["accent"])
    draw.text(((W - stw) / 2, bar_y + 10), save_text, font=f_save_big, fill=colors["dark"])

    f_sub = ImageFont.truetype(F_SANS_REG, 22)
    # Was niche.lower() — broke proper-noun capitalization for "Google
    # Ads" and "Meta/Instagram Ads" ("Your google ads cheat sheet",
    # "Your meta/instagram ads cheat sheet"), found on every recap slide
    # in the 2026-07-27 batch. niche already arrives correctly cased from
    # the content brain, so use it as-is.
    sub_text = f"Your {niche} cheat sheet"
    sub_w = draw.textlength(sub_text, font=f_sub)
    draw.text(((W - sub_w) / 2, bar_y + 80), sub_text, font=f_sub, fill=GRAY)

    # Card grid: 2 columns x 3 rows
    card_w = (W - 2 * MARGIN - 20) // 2
    card_h = 280
    gap_x = 20
    gap_y = 16
    start_y = 280

    for i, item in enumerate(recap_lines[:6]):
        # recap_lines falls back to body_slides in render_carousel() below
        # when a carousel has no recap_slide of its own -- and body_slides
        # entries can be {"text":..., "keyword":...} objects now, so this
        # needs the same normalization render_numbered_slide_fixed uses.
        item, _ = slide_text_and_keyword(item)
        col = i % 2
        row = i // 2
        cx = MARGIN + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)

        draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=16, fill=colors["light"])
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=16, outline=colors["accent"], width=2)

        badge_size = 48
        badge_x = cx + 16
        badge_y = cy + 16
        draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size], fill=colors["dark"])
        f_num = ImageFont.truetype(F_SANS_BOLD, 24)
        num_text = str(i + 1)
        nw = draw.textlength(num_text, font=f_num)
        draw.text((badge_x + (badge_size - nw) / 2, badge_y + 10), num_text, font=f_num, fill=WHITE)

        text_x = cx + 20
        text_y = cy + badge_size + 28
        text_max_w = card_w - 40
        # Card has a fixed 280px height, and this text was drawn at a fixed
        # 26px with no shrink logic — a recap item longer than ~5-6 short
        # lines runs past the bottom of its card and overlaps the row
        # below it. recap_slide has no enforced word count in the content
        # brain schema, so a defensive shrink-to-fit here (same pattern
        # fit_text_shrink_only already uses for hook/bridge/body text)
        # protects the render even if a future batch sends a long item.
        text_bottom_pad = 20
        available_text_h = (cy + card_h) - text_y - text_bottom_pad
        f_card, wrapped, card_size = fit_text_shrink_only(
            draw, item, text_max_w, max(1, available_text_h // 30),
            RECAP_CARD_TEXT_SIZE, 16, F_SANS_BOLD
        )
        line_h = int(card_size * 1.35)
        # If even the min size still overflows (pathologically long item),
        # clip lines rather than let them spill into the next card.
        max_lines_fit = max(1, available_text_h // line_h)
        for line in wrapped[:max_lines_fit]:
            draw.text((text_x, text_y), line, font=f_card, fill=TEXT)
            text_y += line_h

    f_note = ImageFont.truetype(F_SANS_REG, 20)
    note_text = "Screenshot this page and use it as your checklist"
    note_w = draw.textlength(note_text, font=f_note)
    draw.text(((W - note_w) / 2, H - 130), note_text, font=f_note, fill=GRAY)

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# CTA SLIDE — fixed size, designed fill
# ============================================================

def render_cta_slide_fixed(headline, cta_word, cta_promise, cta_support, save_line, niche, slide_num, total_slides, out_path):
    """
    Rebuilt from the ground up (2026-07-28) to fix two real problems Ryan
    flagged after looking at actual posted output:

    1. The full Instagram caption -- including its hashtag block -- was
       being rendered as pixels onto this slide (the old `support_text`
       param was wired to carousel["caption"]). That's pure duplication:
       instagram_post.py already sends the same caption as the post's
       actual caption field. On screen it just meant a wall of gray
       hashtag text dumped under the CTA, with a few hundred px of dead
       empty space below it since nothing filled the rest of the frame --
       the single biggest reason this slide read as a cluttered plug
       instead of a clean sign-off. `cta_support` now takes a short,
       genuine, optional line of its own (urgency/context, per the
       content brain's CTA RULES) instead of the caption.
    2. The save-ask line was hardcoded to always say "...audit" on every
       single carousel regardless of format -- a checklist carousel, a
       before/after, a comparison, all got the identical word every day.
       That repetition is exactly what makes a CTA read as templated
       rather than considered. `save_line` is now written per-carousel by
       the content brain (varying the closing noun with the format) and
       rendered as-is instead of a fixed phrase.

    Layout is also fully vertically centered now (the whole block's
    height is measured first, same pattern render_numbered_slide_fixed
    uses) instead of top-anchored at a fixed y with whatever's left over
    just sitting empty -- and the giant "Comment" moment gets the same
    top/bottom accent-bar framing the hook and bridge slides use, so this
    slide finally reads as part of the same design system instead of a
    bolted-on ad at the end.
    """
    colors = colors_for(niche)
    bg_bottom = tuple(min(255, int(c * 0.6 + 255 * 0.4)) for c in colors["accent"])
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    for row in range(H):
        t = row / H
        color = tuple(int(255 + (bg_bottom[i] - 255) * t) for i in range(3))
        draw.line([(0, row), (W, row)], fill=color)
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN

    f_save = ImageFont.truetype(F_SANS_BOLD, CTA_SAVE_SIZE)
    save_text = save_line or f"Save this for your next {niche} review"
    f_head = ImageFont.truetype(F_SANS_REG, 32)
    head_lines = wrap_text(draw, headline, f_head, max_w) if headline else []
    f_cta = ImageFont.truetype(F_SANS_BOLD, CTA_COMMENT_SIZE)
    cta_text = f"Comment ‘{cta_word}’"
    cta_shadow_off = max(3, CTA_COMMENT_SIZE // 14)
    f_promise = ImageFont.truetype(F_SANS_BOLD, CTA_PROMISE_SIZE)
    promise_text = f"and I’ll DM you {cta_promise}" if cta_promise else ""
    f_support = ImageFont.truetype(F_SANS_REG, 26)
    support_lines = wrap_text(draw, cta_support, f_support, max_w - 80) if cta_support else []

    # Measure the whole block before drawing anything, so it can be
    # centered in the space below the header instead of anchored at a
    # fixed y with leftover space just left blank underneath.
    pill_h = 64
    save_gap = 56
    head_line_h = 48
    head_gap = 40
    bar_gap = 28
    cta_h = int(CTA_COMMENT_SIZE * 1.05)
    cta_gap = 36
    promise_gap = 46 if promise_text else 0
    support_line_h = 38

    total_h = pill_h + save_gap
    total_h += len(head_lines) * head_line_h + (head_gap if head_lines else 0)
    total_h += bar_gap + cta_h + bar_gap  # accent bars above + below the comment moment
    total_h += cta_gap
    total_h += (CTA_PROMISE_SIZE + promise_gap) if promise_text else 0
    total_h += len(support_lines) * support_line_h + (30 if support_lines else 0)

    header_bottom = 170
    footer_reserve = 170
    available_h = H - header_bottom - footer_reserve
    ty = header_bottom + max(0, (available_h - total_h) // 2)

    # SAVE ask
    tw = draw.textlength(save_text, font=f_save)
    pad_x = 24
    pill_w = tw + pad_x * 2
    px = (W - pill_w) / 2
    draw.rounded_rectangle([px, ty, px + pill_w, ty + pill_h], radius=pill_h // 2, fill=colors["dark"])
    draw.text((px + pad_x, ty + 12), save_text, font=f_save, fill=WHITE)
    ty += pill_h + save_gap

    # Headline (short context line from the content brain, optional)
    for line in head_lines:
        tw = draw.textlength(line, font=f_head)
        draw.text(((W - tw) / 2, ty), line, font=f_head, fill=TEXT)
        ty += head_line_h
    if head_lines:
        ty += head_gap

    # COMMENT ask — FIXED SIZE, never grows. Same flat drop-shadow depth
    # treatment as the hook/bridge mega-stat and mega-phrase, now framed
    # with the same top/bottom accent bars the hook/bridge give their own
    # hero text, so this is visibly the same design system, not a
    # different slide type that showed up late.
    draw_accent_bar(draw, ty, colors, width=180)
    ty += bar_gap
    tw = draw.textlength(cta_text, font=f_cta)
    cta_x = (W - tw) / 2
    draw.text((cta_x + cta_shadow_off, ty + cta_shadow_off), cta_text, font=f_cta, fill=colors["accent"])
    draw.text((cta_x, ty), cta_text, font=f_cta, fill=BLACK)
    ty += cta_h
    draw_accent_bar(draw, ty, colors, width=180)
    ty += bar_gap + cta_gap

    # Promise
    if promise_text:
        tw = draw.textlength(promise_text, font=f_promise)
        draw.text(((W - tw) / 2, ty), promise_text, font=f_promise, fill=colors["dark"])
        ty += CTA_PROMISE_SIZE + promise_gap

    # Support — short urgency/context line from the content brain, e.g.
    # "No cost, just the checklist" — never the raw caption anymore.
    if support_lines:
        ty += 30
        for line in support_lines:
            tw = draw.textlength(line, font=f_support)
            draw.text(((W - tw) / 2, ty), line, font=f_support, fill=(90, 90, 90))
            ty += support_line_h

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

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
                                 os.path.join(out_dir, "slide_01.jpg"),
                                 pop_phrase=carousel.get("hook_pop_phrase"))
    paths.append(p)

    bridge = carousel.get("bridge_slide") or carousel.get("hook_slide_2") or ""
    if not bridge:
        # Fallback only — the content brain always supplies a bridge_slide
        # now. niche.lower() here had the same "google ads"/"meta" bug as
        # the recap and CTA slides; niche is already correctly cased.
        bridge = f"The {carousel.get('angle', 'mistake')} most {niche} owners miss"
    p = render_bridge_slide_fixed(bridge, niche, 2, total_slides,
                                   os.path.join(out_dir, "slide_02.jpg"),
                                   pop_phrase=carousel.get("bridge_pop_phrase"))
    paths.append(p)

    checklist_mode = carousel.get("format", "").lower() in ("checklist", "quick-win checklist", "steal-this")
    for i, body in enumerate(body_slides, start=1):
        slide_num = i + 2
        # Used to only show on slides 1, 4, 5 — an arbitrary subset that
        # didn't line up with the content brain's own swipe-cue rule
        # (which now expects forward motion on every body slide except
        # the last, see SWIPE COPY CUES). Every slide but the final one
        # now gets the visual nudge too, so the design reinforces the
        # same "keep going" signal the copy is writing into every slide,
        # instead of the two disagreeing about which slides matter.
        show_swipe = i != len(body_slides)
        p = render_numbered_slide_fixed(i, body, niche, slide_num, total_slides,
                                         os.path.join(out_dir, f"slide_{slide_num:02d}.jpg"),
                                         checklist_mode=checklist_mode, show_swipe=show_swipe)
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
    # cta_support/cta_save_line are new fields (see content brain OUTPUT
    # FORMAT) — .get() with a safe fallback so a batch generated by an
    # older prompt version (before these existed) still renders instead
    # of KeyError-ing the whole run.
    p = render_cta_slide_fixed(carousel.get("cta_slide", ""), cta_word, cta_promise,
                                carousel.get("cta_support", ""), carousel.get("cta_save_line", ""),
                                niche, last, total_slides,
                                os.path.join(out_dir, f"slide_{last:02d}.jpg"))
    paths.append(p)

    return paths


if __name__ == "__main__":
    sample = {
        "niche": "Google Ads",
        "angle": "Mistake/myth-busting",
        "format": "checklist",
        "hook_slide": "Your Google Ads are burning 30% of budget on browsers",
        "bridge_slide": "The setting most clinics miss costs them €400/week",
        "body_slides": [
            "Switch broad match to phrase match. Cuts waste 30%",
            "Check search terms weekly, not just the dashboard",
            "Add negative keywords for ‘free’ and ‘jobs’",
            "A good cost-per-lead sits lower than most assume",
            "Pause keywords with zero conversions after 30 days",
            "Set location targeting to ‘people in’ not ‘interested in’"
        ],
        "recap_slide": [
            "Switch broad match to phrase match",
            "Check search terms weekly",
            "Add negative keywords for ‘free’ and ‘jobs’",
            "Good cost-per-lead is lower than you think",
            "Pause zero-conversion keywords after 30 days",
            "Set location to ‘people in’ only"
        ],
        "cta_slide": "Stop wasting budget. Start booking calls.",
        "cta_word": "AUDIT",
        "cta_promise": "my 7-point Google Ads audit checklist",
        "cta_save_line": "Save this for your next Google Ads checklist run",
        "cta_support": "No cost, just the checklist",
        "caption": "Save this 7-point Google Ads audit checklist ↓ Most business owners don’t know their ads are burning budget on the wrong searches. #googleads #smallbusiness #marketingtips #ppc #businessowner"
    }
    out = render_carousel(sample, "2026-07-19", "/tmp/sample_carousel")
    print(out)
