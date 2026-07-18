"""
Carousel image engine — clean "basic template" style: solid cream
background with a subtle dot-grid texture, bold text, per-topic accent
colors, highlighter-marker emphasis. No photos, no custom font uploads.
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

# Per-topic accent colors — each niche gets its own consistent color
# identity instead of a visible text label.
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
    draw.text((W - MARGIN - cw - 18, 60), counter, font=f_counter, fill=(255, 255, 255))


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
    pts = [(x - 6, y + h * 0.15), (x + w + 8, y - h * 0.08),
           (x + w + 6, y + h * 0.95), (x - 8, y + h * 1.05)]
    draw.polygon(pts, fill=color)


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


def render_hook_slide(headline, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    max_w = W - 2 * MARGIN
    font, lines, size = fit_text(draw, headline, max_w, 5, 92, 46, F_SERIF_BOLD)
    line_h = int(size * 1.2)
    highlight = find_highlight_word(headline)

    total_h = line_h * len(lines)
    ty = max(300, (H - total_h) // 2 - 40)
    for line in lines:
        draw_text_highlighted(draw, MARGIN, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_numbered_slide(number, full_text, niche, slide_num, total_slides, out_path):
    """Uses the FULL sentence as the headline, dynamically sized to fill
    the space properly — no more arbitrary word-count splitting that
    left some slides with an empty, sparse body."""
    colors = colors_for(niche)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    badge_size = 68
    badge_x = MARGIN
    text_x = badge_x + badge_size + 28
    max_w = W - MARGIN - text_x

    highlight = find_highlight_word(full_text)
    font, lines, size = fit_text(draw, full_text, max_w, 6, 62, 36, F_SANS_BOLD)
    line_h = int(size * 1.28)

    total_h = line_h * len(lines)
    badge_y = max(280, (H - total_h) // 2 - 20)

    if number is not None:
        draw_number_badge(draw, badge_x, badge_y, badge_size, number, colors["accent"], TEXT)

    ty = badge_y - 2
    for line in lines:
        draw_text_highlighted(draw, text_x, ty, line, font, highlight, TEXT, colors["accent"])
        ty += line_h

    img.save(out_path, "JPEG", quality=92)
    return out_path


def render_cta_slide(headline, cta_word, support_text, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    bg_bottom = tuple(min(255, int(c * 0.5 + 255 * 0.5)) for c in colors["accent"])
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for row in range(H):
        t = row / H
        color = tuple(int(255 + (bg_bottom[i] - 255) * t) for i in range(3))
        draw.line([(0, row), (W, row)], fill=color)
    draw_dot_grid(draw)
    draw_header(draw, slide_num, total_slides, colors["dark"])

    max_w = W - 2 * MARGIN
    f_head, head_lines, head_size = fit_text(draw, headline, max_w, 4, 46, 30, F_SANS_REG)
    line_h = int(head_size * 1.35)

    ty = 400
    for line in head_lines:
        tw = draw.textlength(line, font=f_head)
        draw.text(((W - tw) / 2, ty), line, font=f_head, fill=TEXT)
        ty += line_h

    ty += 50
    f_cta = ImageFont.truetype(F_SANS_BOLD, 58)
    cta_text = f"Comment '{cta_word}'"
    tw = draw.textlength(cta_text, font=f_cta)
    cta_x = (W - tw) / 2
    draw.text((cta_x, ty), cta_text, font=f_cta, fill=colors["dark"])
    draw.line([(cta_x, ty + 70), (cta_x + tw, ty + 70)], fill=colors["dark"], width=4)

    ty += 105
    if support_text:
        f_support = ImageFont.truetype(F_SANS_REG, 32)
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
    total_slides = 3 + len(body_slides)

    p = render_hook_slide(carousel["hook_slide"], niche, 1, total_slides,
                           os.path.join(out_dir, "slide_01.jpg"))
    paths.append(p)

    bridge = carousel.get("bridge_slide") or f"Here's exactly what that means, step by step."
    p = render_hook_slide(bridge, niche, 2, total_slides,
                           os.path.join(out_dir, "slide_02.jpg"))
    paths.append(p)

    for i, body in enumerate(body_slides, start=1):
        slide_num = i + 2
        p = render_numbered_slide(i, body, niche, slide_num, total_slides,
                                   os.path.join(out_dir, f"slide_{slide_num:02d}.jpg"))
        paths.append(p)

    last = total_slides
    cta_word = carousel.get("cta_word", "TIPS")
    p = render_cta_slide(carousel["cta_slide"], cta_word, carousel.get("caption", ""),
                          niche, last, total_slides, os.path.join(out_dir, f"slide_{last:02d}.jpg"))
    paths.append(p)

    return paths
