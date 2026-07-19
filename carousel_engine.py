"""
Carousel image engine — upgraded design: cream background with dot-grid texture,
bold text, per-topic accent colors, highlighter-marker emphasis, swipe indicators,
recap slide, save bookmark cue, checklist mode. No photos, no custom font uploads.
"""

from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1080, 1350  # 4:5 — Instagram's optimal feed carousel ratio
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

# Per-topic accent colors — each niche gets its own consistent color identity
TOPIC_COLORS = {
    "google ads": {"accent": (161, 214, 191), "dark": (30, 90, 65)},      # sage green
    "meta": {"accent": (240, 172, 168), "dark": (140, 45, 45)},           # coral/pink
    "instagram": {"accent": (240, 172, 168), "dark": (140, 45, 45)},
    "email": {"accent": (196, 176, 226), "dark": (80, 55, 120)},          # lavender
}
DEFAULT_COLORS = {"accent": (161, 214, 191), "dark": (30, 90, 65)}


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


def fit_text(draw, text, max_width, max_lines, max_size, min_size, font_path):
    for size in range(max_size, min_size - 1, -4):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_width for l in lines):
            return font, lines, size
    size = min_size
    while size > 22:
        size -= 3
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if all(draw.textlength(l, font=font) <= max_width for l in lines):
            return font, lines, size
    font = ImageFont.truetype(font_path, 22)
    return font, wrap_text(draw, text, font, max_width), 22


def draw_dot_grid(draw, spacing=48, radius=2):
    for y in range(60, H - 40, spacing):
        for x in range(60, W - 40, spacing):
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=DOT_COLOR)


def draw_header(draw, slide_num, total_slides, dark_color):
    f_author = ImageFont.truetype(F_SANS_REG, 24)
    author = AGENCY_HANDLE
    aw = draw.textlength(author, font=f_author)
    draw.text(((W - aw) / 2, 56), author, font=f_author, fill=GRAY)

    f_counter = ImageFont.truetype(F_SANS_BOLD, 24)
    counter = f"{slide_num}/{total_slides}"
    cw = draw.textlength(counter, font=f_counter)
    draw.rounded_rectangle([W - MARGIN - cw - 36, 48, W - MARGIN + 4, 48 + 46],
                            radius=23, fill=dark_color)
    draw.text((W - MARGIN - cw - 18, 60), counter, font=f_counter, fill=WHITE)


def find_highlight_word(text):
    import re
    m = re.search(r"(?:[€$£]\s?\d[\d,]*(?:\.\d+)?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%)", text)
    if m:
        return m.group(0)
    words = text.split()
    if len(words) >= 3:
        return " ".join(words[-2:]).rstrip(".")
    return None


def draw_marker(draw, x, y, w, h, color):
    # More visible marker — 70% opacity accent
    r, g, b = color
    marker_color = (r, g, b, 180)
    pts = [(x - 6, y + h * 0.15), (x + w + 8, y - h * 0.08),
           (x + w + 6, y + h * 0.95), (x - 8, y + h * 1.05)]
    draw.polygon(pts, fill=marker_color)


def draw_text_highlighted(draw, x, y, line, font, highlight, text_color, marker_color):
    if not highlight or highlight not in line:
        draw.text((x, y), line, font=font, fill=text_color)
        return
    before, _, after = line.partition(highlight)
    cx = x
    if before:
        cx += draw.textlength(before, font=font)
    hw = draw.textlength(highlight, font=font)
    ascent, _ = font.getmetrics()
    draw_marker(draw, cx, y + ascent * 0.08, hw, ascent * 0.85, marker_color)
    draw.text((x, y), line, font=font, fill=text_color)


def draw_number_badge(draw, x, y, size, number, bg_color, text_color):
    draw.ellipse([x, y, x + size, y + size], fill=bg_color)
    f_num = ImageFont.truetype(F_SANS_BOLD, int(size * 0.5))
    num_text = str(number)
    tw = draw.textlength(num_text, font=f_num)
    draw.text((x + (size - tw) / 2, y + size * 0.22), num_text, font=f_num, fill=text_color)


def draw_checkbox(draw, x, y, size, color):
    """Draw a checkbox outline instead of a number circle for checklist mode."""
    draw.rounded_rectangle([x, y, x + size, y + size], radius=6, outline=color, width=3)


def draw_swipe_indicator(draw, dark_color):
    """Subtle swipe indicator bottom-right."""
    f_swipe = ImageFont.truetype(F_SANS_BOLD, 26)
    swipe_text = "Swipe →"
    tw = draw.textlength(swipe_text, font=f_swipe)
    draw.text((W - MARGIN - tw, H - 100), swipe_text, font=f_swipe, fill=dark_color)


def draw_save_bookmark(draw, x, y, color):
    """Simple bookmark outline icon to cue save behavior."""
    w, h = 40, 50
    draw.rounded_rectangle([x, y, x + w, y + h], radius=4, outline=color, width=2)
    # Bookmark notch
    draw.polygon([(x + w//2, y + h - 12), (x + 8, y + h - 4), (x + w - 8, y + h - 4)], fill=color)


def render_hook_slide(headline, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    max_w = W - 2 * MARGIN
    # Bumped max size from 92 to 110 for more dramatic hooks
    font, lines, size = fit_text(draw, headline, max_w, 5, 110, 46, F_SERIF_BOLD)
    line_h = int(size * 1.2)
    highlight = find_highlight_word(headline)

    total_h = line_h * len(lines)
    ty = max(300, (H - total_h) // 2 - 40)
    for line in lines:
        draw_text_highlighted(draw, MARGIN, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_numbered_slide(number, full_text, niche, slide_num, total_slides, out_path,
                          checklist_mode=False, show_swipe=False):
    """
    checklist_mode: draw checkbox instead of number circle.
    show_swipe: add swipe indicator on specific slides (2, 5, 8).
    """
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    badge_size = 76
    badge_x = MARGIN
    text_x = badge_x + badge_size + 28
    max_w = W - MARGIN - text_x

    # Ensure minimum bottom margin of 200px
    effective_max_h = H - 200 - 280  # top offset ~280, bottom margin 200
    max_lines_for_fit = min(4, effective_max_h // 80)

    highlight = find_highlight_word(full_text)
    font, lines, size = fit_text(draw, full_text, max_w, max_lines_for_fit, 82, 44, F_SANS_BOLD)
    line_h = int(size * 1.24)

    total_h = line_h * len(lines)
    badge_y = max(280, (H - total_h) // 2 - 20)

    if number is not None:
        if checklist_mode:
            draw_checkbox(draw, badge_x, badge_y, badge_size, colors["accent"])
        else:
            draw_number_badge(draw, badge_x, badge_y, badge_size, number, colors["accent"], TEXT)

    ty = badge_y - 2
    for line in lines:
        draw_text_highlighted(draw, text_x, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    if show_swipe:
        draw_swipe_indicator(draw, colors["dark"])

    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_recap_slide(recap_lines, niche, slide_num, total_slides, out_path):
    """Recap slide: compact list of all body points, designed for screenshotting."""
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    # "Save this ↓" header
    f_header = ImageFont.truetype(F_SANS_BOLD, 36)
    header_text = "Save this ↓"
    tw = draw.textlength(header_text, font=f_header)
    draw.text(((W - tw) / 2, 180), header_text, font=f_header, fill=colors["dark"])

    # Save bookmark icon top-right
    draw_save_bookmark(draw, W - MARGIN - 50, 170, colors["accent"])

    # Recap items
    f_item = ImageFont.truetype(F_SANS_REG, 28)
    max_w = W - 2 * MARGIN - 40
    y = 280
    for item in recap_lines:
        # Checkmark bullet
        draw.text((MARGIN + 20, y), "✓", font=f_item, fill=colors["dark"])
        # Wrapped item text
        wrapped = wrap_text(draw, item, f_item, max_w - 50)
        for line in wrapped:
            draw.text((MARGIN + 60, y), line, font=f_item, fill=TEXT)
            y += 40
        y += 16

    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_cta_slide(headline, cta_word, cta_promise, support_text, niche, slide_num, total_slides, out_path):
    """
    Upgraded CTA: SAVE ask + COMMENT ask + support text + stronger gradient.
    """
    colors = colors_for(niche)
    # More pronounced gradient — bottom 50% clearly tinted
    bg_bottom = tuple(min(255, int(c * 0.7 + 255 * 0.3)) for c in colors["accent"])
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    for row in range(H):
        t = row / H
        color = tuple(int(255 + (bg_bottom[i] - 255) * t) for i in range(3))
        draw.line([(0, row), (W, row)], fill=color)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    max_w = W - 2 * MARGIN
    ty = 260

    # SAVE ask (top)
    f_save = ImageFont.truetype(F_SANS_BOLD, 36)
    save_text = f"Save this for your next {niche.lower()} audit"
    tw = draw.textlength(save_text, font=f_save)
    draw.text(((W - tw) / 2, ty), save_text, font=f_save, fill=colors["dark"])
    ty += 70

    # Headline (context line)
    if headline:
        f_head = ImageFont.truetype(F_SANS_REG, 30)
        head_lines = wrap_text(draw, headline, f_head, max_w)
        for line in head_lines:
            tw = draw.textlength(line, font=f_head)
            draw.text(((W - tw) / 2, ty), line, font=f_head, fill=TEXT)
            ty += 44
        ty += 30

    # COMMENT ask (big, underlined)
    f_cta = ImageFont.truetype(F_SANS_BOLD, 52)
    cta_text = f"Comment ‘{cta_word}’"
    tw = draw.textlength(cta_text, font=f_cta)
    cta_x = (W - tw) / 2
    draw.text((cta_x, ty), cta_text, font=f_cta, fill=colors["dark"])
    draw.line([(cta_x, ty + 68), (cta_x + tw, ty + 68)], fill=colors["dark"], width=4)
    ty += 100

    # Promise line
    if cta_promise:
        f_promise = ImageFont.truetype(F_SANS_BOLD, 32)
        promise_text = f"and I’ll DM you {cta_promise}"
        tw = draw.textlength(promise_text, font=f_promise)
        draw.text(((W - tw) / 2, ty), promise_text, font=f_promise, fill=colors["dark"])
        ty += 60

    # Support text (bottom)
    if support_text:
        f_support = ImageFont.truetype(F_SANS_REG, 28)
        support_lines = wrap_text(draw, support_text, f_support, max_w - 100)
        for line in support_lines:
            tw = draw.textlength(line, font=f_support)
            draw.text(((W - tw) / 2, ty), line, font=f_support, fill=(60, 60, 60))
            ty += 44

    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_carousel(carousel, batch_date, out_dir, carousel_index=0):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    body_slides = carousel["body_slides"]
    niche = carousel.get("niche", "")
    total_slides = 4 + len(body_slides)  # hook + bridge + body + recap + cta

    # Slide 1: Hook
    p = render_hook_slide(carousel["hook_slide"], niche, 1, total_slides,
                           os.path.join(out_dir, "slide_01.jpg"))
    paths.append(p)

    # Slide 2: Bridge (re-hook, same visual weight as slide 1)
    bridge = carousel.get("bridge_slide") or carousel.get("hook_slide_2") or ""
    if not bridge:
        # Fallback: generate a re-hook from the angle
        bridge = f"The {carousel.get('angle', 'mistake')} most {niche.lower()} owners miss"
    p = render_hook_slide(bridge, niche, 2, total_slides,
                           os.path.join(out_dir, "slide_02.jpg"))
    paths.append(p)

    # Body slides (3-8)
    checklist_mode = carousel.get("format", "").lower() in ("checklist", "quick-win checklist", "steal-this")
    for i, body in enumerate(body_slides, start=1):
        slide_num = i + 2
        # Show swipe indicator on body slides 1, 4, and second-to-last
        show_swipe = (i == 1) or (i == 4) or (i == len(body_slides) - 1)
        p = render_numbered_slide(i, body, niche, slide_num, total_slides,
                                   os.path.join(out_dir, f"slide_{slide_num:02d}.jpg"),
                                   checklist_mode=checklist_mode, show_swipe=show_swipe)
        paths.append(p)

    # Slide 9: Recap (second-to-last)
    recap_lines = carousel.get("recap_slide", body_slides)
    if isinstance(recap_lines, str):
     recap_lines = [line.strip() for line in recap_lines.split("\n") if line.strip()]
    if not recap_lines:
        recap_lines = body_slides
    last_body = total_slides - 1
    p = render_recap_slide(recap_lines, niche, last_body, total_slides,
                            os.path.join(out_dir, f"slide_{last_body:02d}.jpg"))
    paths.append(p)

    # Slide 10: CTA (final)
    last = total_slides
    cta_word = carousel.get("cta_word", "TIPS")
    cta_promise = carousel.get("cta_promise", "the checklist")
    p = render_cta_slide(carousel.get("cta_slide", ""), cta_word, cta_promise,
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
        "caption": "Save this 7-point Google Ads audit checklist ↓ Most business owners don’t know their ads are burning budget on the wrong searches. #googleads #smallbusiness #marketingtips #ppc #businessowner"
    }
    out = render_carousel(sample, "2026-07-19", "/tmp/sample_carousel")
    print(out)
