"""
Carousel image engine — FIXED SIZE EDITION:
- Fixed font sizes per slide type (no auto-growing)
- Smart shrink-only fitting (if text is too long, shrink; never grow beyond target)
- Visual fill elements: accent bars, decorative spacing, centered layouts
- Every slide looks designed and full regardless of text length
"""

from PIL import Image, ImageDraw, ImageFont
import os

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

# FIXED FONT SIZES — never auto-grow beyond these
HOOK_FONT_SIZE = 96       # Hook slides: big, dramatic, consistent
BRIDGE_FONT_SIZE = 88     # Bridge slides: slightly smaller than hook
BODY_FONT_SIZE = 56       # Body slides: readable, punchy, consistent
RECAP_HEADER_SIZE = 48    # Recap "Save This" header
RECAP_CARD_TEXT_SIZE = 26 # Recap card text
CTA_SAVE_SIZE = 36        # CTA save ask
CTA_COMMENT_SIZE = 52     # CTA comment keyword
CTA_PROMISE_SIZE = 30     # CTA promise line

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
    circle_size = 44
    cx = W - MARGIN - circle_size
    cy = 46
    draw.ellipse([cx, cy, cx + circle_size, cy + circle_size], fill=dark_color)
    draw.text((cx + (circle_size - cw) / 2, cy + 10), counter, font=f_counter, fill=WHITE)


def draw_header_v2(draw, niche, slide_num, total_slides, colors):
    draw_topic_badge(draw, niche, colors)
    f_handle = ImageFont.truetype(F_SANS_REG, 20)
    hw = draw.textlength(AGENCY_HANDLE, font=f_handle)
    draw.text(((W - hw) / 2, 58), AGENCY_HANDLE, font=f_handle, fill=GRAY)
    draw_slide_counter(draw, slide_num, total_slides, colors["dark"])


def find_highlight_word(text):
    import re
    m = re.search(r"(?:[\u20ac$\u00a3]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)", text)
    if m:
        return m.group(0)
    words = text.split()
    if len(words) >= 3:
        return " ".join(words[-2:]).rstrip(".")
    return None


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


def draw_accent_bar(draw, y, colors, width=None):
    bar_h = 6
    w = width if width else (W - 2 * MARGIN)
    draw.rectangle([MARGIN, y, MARGIN + w, y + bar_h], fill=colors["accent"])


def draw_swipe_arrow(draw, colors):
    f_arrow = ImageFont.truetype(F_SANS_BOLD, 30)
    arrow_text = "Swipe \u2192"
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
    draw.text((MARGIN - 10, y), "\u201c", font=f_quote, fill=colors["light"])
    draw.text((W - MARGIN - 50, y + 200), "\u201d", font=f_quote, fill=colors["light"])


def draw_vertical_accent_line(draw, x, y0, y1, colors):
    """Vertical accent line for visual interest."""
    draw.rectangle([x, y0, x + 4, y1], fill=colors["accent"])


def draw_bottom_accent_block(draw, y, height, colors):
    """Large accent color block at bottom to fill space."""
    draw.rectangle([0, y, W, y + height], fill=colors["light"])


# ============================================================
# HOOK SLIDE — fixed size, designed fill
# ============================================================

def render_hook_slide_fixed(headline, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 40  # slightly narrower for better line breaks

    # FIXED SIZE: 96px, shrink only if needed
    font, lines, size = fit_text_shrink_only(draw, headline, max_w, 4, HOOK_FONT_SIZE, 52, F_SERIF_BOLD)
    line_h = int(size * 1.2)
    highlight = find_highlight_word(headline)

    total_h = line_h * len(lines)

    # CENTER the text block vertically, with generous spacing
    available_h = H - 280 - 180  # header to progress bar
    ty = 280 + (available_h - total_h) // 2

    # If text is very short (1-2 lines), add decorative elements
    if len(lines) <= 2:
        draw_decorative_quote_marks(draw, ty - 40, colors)
        # Add accent bars above and below with more spacing
        draw_accent_bar(draw, ty - 60, colors, width=200)
        draw_accent_bar(draw, ty + total_h + 40, colors, width=200)
    else:
        draw_accent_bar(draw, ty - 30, colors)
        draw_accent_bar(draw, ty + total_h + 20, colors)

    for line in lines:
        draw_text_highlighted_v2(draw, MARGIN + 20, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    img.save(out_path, "JPEG", quality=92)
    return out_path


# ============================================================
# BRIDGE SLIDE — fixed size, designed fill
# ============================================================

def render_bridge_slide_fixed(headline, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN - 40
    font, lines, size = fit_text_shrink_only(draw, headline, max_w, 4, BRIDGE_FONT_SIZE, 48, F_SERIF_BOLD)
    line_h = int(size * 1.2)
    highlight = find_highlight_word(headline)

    total_h = line_h * len(lines)
    available_h = H - 280 - 180
    ty = 280 + (available_h - total_h) // 2

    # Bridge gets a vertical accent line on the left for visual distinction
    if len(lines) <= 2:
        draw_vertical_accent_line(draw, MARGIN, ty - 20, ty + total_h + 20, colors)
        draw_decorative_quote_marks(draw, ty - 30, colors)
    else:
        draw_vertical_accent_line(draw, MARGIN, ty - 10, ty + total_h + 10, colors)

    for line in lines:
        draw_text_highlighted_v2(draw, MARGIN + 30, ty, line, font, highlight, TEXT, colors["accent"])
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
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    badge_size = 80
    badge_x = MARGIN
    text_x = badge_x + badge_size + 32
    max_w = W - MARGIN - text_x - 20

    # FIXED SIZE: 56px, shrink only if needed
    font, lines, size = fit_text_shrink_only(draw, full_text, max_w, 4, BODY_FONT_SIZE, 36, F_SANS_BOLD)
    line_h = int(size * 1.25)

    total_h = line_h * len(lines)
    available_h = H - 280 - 200
    badge_y = 280 + (available_h - total_h) // 2

    # Number badge or checkbox
    if number is not None:
        if checklist_mode:
            draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size], 
                                  radius=8, outline=colors["dark"], width=4)
            f_check = ImageFont.truetype(F_SANS_BOLD, 36)
            draw.text((badge_x + 22, badge_y + 18), "\u2713", font=f_check, fill=colors["dark"])
        else:
            draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size], 
                         fill=colors["dark"])
            f_num = ImageFont.truetype(F_SANS_BOLD, int(badge_size * 0.45))
            num_text = str(number)
            tw = draw.textlength(num_text, font=f_num)
            draw.text((badge_x + (badge_size - tw) / 2, badge_y + badge_size * 0.24), 
                     num_text, font=f_num, fill=WHITE)

    # If text is very short, center it vertically in the available space
    # and add a subtle accent block behind it
    if len(lines) <= 2:
        block_y = badge_y + (badge_size if not checklist_mode else badge_size) // 2 - 20
        block_h = total_h + 60
        draw.rounded_rectangle([text_x - 20, block_y, W - MARGIN, block_y + block_h], 
                              radius=12, fill=colors["light"])

    ty = badge_y + 4
    for line in lines:
        draw_text_highlighted_v2(draw, text_x, ty, line, font, find_highlight_word(full_text), TEXT, colors["accent"])
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
    sub_text = f"Your {niche.lower()} cheat sheet"
    sub_w = draw.textlength(sub_text, font=f_sub)
    draw.text(((W - sub_w) / 2, bar_y + 80), sub_text, font=f_sub, fill=GRAY)

    # Card grid: 2 columns x 3 rows
    card_w = (W - 2 * MARGIN - 20) // 2
    card_h = 280
    gap_x = 20
    gap_y = 16
    start_y = 280

    for i, item in enumerate(recap_lines[:6]):
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
        f_card = ImageFont.truetype(F_SANS_BOLD, RECAP_CARD_TEXT_SIZE)

        wrapped = wrap_text(draw, item, f_card, text_max_w)
        for line in wrapped:
            draw.text((text_x, text_y), line, font=f_card, fill=TEXT)
            text_y += 38

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

def render_cta_slide_fixed(headline, cta_word, cta_promise, support_text, niche, slide_num, total_slides, out_path):
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
    ty = 240

    # SAVE ask
    f_save = ImageFont.truetype(F_SANS_BOLD, CTA_SAVE_SIZE)
    save_text = f"Save this for your next {niche.lower()} audit"
    tw = draw.textlength(save_text, font=f_save)
    pad_x = 24
    pill_w = tw + pad_x * 2
    pill_h = 64
    px = (W - pill_w) / 2
    draw.rounded_rectangle([px, ty, px + pill_w, ty + pill_h], radius=pill_h // 2, fill=colors["dark"])
    draw.text((px + pad_x, ty + 12), save_text, font=f_save, fill=WHITE)
    ty += 100

    # Headline
    if headline:
        f_head = ImageFont.truetype(F_SANS_REG, 32)
        head_lines = wrap_text(draw, headline, f_head, max_w)
        for line in head_lines:
            tw = draw.textlength(line, font=f_head)
            draw.text(((W - tw) / 2, ty), line, font=f_head, fill=TEXT)
            ty += 48
        ty += 20

    # COMMENT ask — FIXED SIZE, never grows
    f_cta = ImageFont.truetype(F_SANS_BOLD, CTA_COMMENT_SIZE)
    cta_text = f"Comment \u2018{cta_word}\u2019"
    tw = draw.textlength(cta_text, font=f_cta)
    cta_x = (W - tw) / 2
    draw.text((cta_x, ty), cta_text, font=f_cta, fill=BLACK)
    draw.line([(cta_x, ty + 76), (cta_x + tw, ty + 76)], fill=colors["dark"], width=6)
    ty += 110

    # Promise
    if cta_promise:
        f_promise = ImageFont.truetype(F_SANS_BOLD, CTA_PROMISE_SIZE)
        promise_text = f"and I\u2019ll DM you {cta_promise}"
        tw = draw.textlength(promise_text, font=f_promise)
        draw.text(((W - tw) / 2, ty), promise_text, font=f_promise, fill=colors["dark"])
        ty += 70

    # Support
    if support_text:
        f_support = ImageFont.truetype(F_SANS_REG, 30)
        support_lines = wrap_text(draw, support_text, f_support, max_w - 80)
        for line in support_lines:
            tw = draw.textlength(line, font=f_support)
            draw.text(((W - tw) / 2, ty), line, font=f_support, fill=(80, 80, 80))
            ty += 48

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
                                 os.path.join(out_dir, "slide_01.jpg"))
    paths.append(p)

    bridge = carousel.get("bridge_slide") or carousel.get("hook_slide_2") or ""
    if not bridge:
        bridge = f"The {carousel.get('angle', 'mistake')} most {niche.lower()} owners miss"
    p = render_bridge_slide_fixed(bridge, niche, 2, total_slides,
                                   os.path.join(out_dir, "slide_02.jpg"))
    paths.append(p)

    checklist_mode = carousel.get("format", "").lower() in ("checklist", "quick-win checklist", "steal-this")
    for i, body in enumerate(body_slides, start=1):
        slide_num = i + 2
        show_swipe = (i == 1) or (i == 4) or (i == len(body_slides) - 1)
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
        "hook_slide": "Your Google Ads are burning 30% of budget on browsers",
        "bridge_slide": "The setting most clinics miss costs them \u20ac400/week",
        "body_slides": [
            "Switch broad match to phrase match. Cuts waste 30%",
            "Check search terms weekly, not just the dashboard",
            "Add negative keywords for \u2018free\u2019 and \u2018jobs\u2019",
            "A good cost-per-lead sits lower than most assume",
            "Pause keywords with zero conversions after 30 days",
            "Set location targeting to \u2018people in\u2019 not \u2018interested in\u2019"
        ],
        "recap_slide": [
            "Switch broad match to phrase match",
            "Check search terms weekly",
            "Add negative keywords for \u2018free\u2019 and \u2018jobs\u2019",
            "Good cost-per-lead is lower than you think",
            "Pause zero-conversion keywords after 30 days",
            "Set location to \u2018people in\u2019 only"
        ],
        "cta_slide": "Stop wasting budget. Start booking calls.",
        "cta_word": "AUDIT",
        "cta_promise": "my 7-point Google Ads audit checklist",
        "caption": "Save this 7-point Google Ads audit checklist \u2193 Most business owners don\u2019t know their ads are burning budget on the wrong searches. #googleads #smallbusiness #marketingtips #ppc #businessowner"
    }
    out = render_carousel(sample, "2026-07-19", "/tmp/sample_carousel")
    print(out)
