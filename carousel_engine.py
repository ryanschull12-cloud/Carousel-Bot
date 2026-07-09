"""
Carousel image engine — matches the uploaded terracotta template style,
adapted to 1080x1920 vertical (TikTok/Instagram) instead of the original
landscape layout, since that's the established posting format.

Takes the JSON output from the content-brain prompt and renders each
slide as a branded PNG.
"""

from PIL import Image, ImageDraw, ImageFont
import json
import os

# --- Brand constants (sampled from uploaded reference) ---
BG_COLOR = (208, 90, 58)       # terracotta background
WHITE = (255, 255, 255)
LIGHT = (255, 235, 227)        # slightly warm off-white for body text
PILL_BG = (255, 255, 255)
PILL_TEXT = (150, 60, 35)

W, H = 1080, 1920
MARGIN = 72

FONT_DIR = "/usr/share/fonts/truetype/liberation"
F_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
F_REG = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")


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


def render_slide(eyebrow_left, eyebrow_right, headline, body_lines,
                  show_swipe=False, cta_text=None, out_path="slide.png"):
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    f_eyebrow = ImageFont.truetype(F_REG, 30)
    f_headline = ImageFont.truetype(F_BOLD, 76)
    f_body = ImageFont.truetype(F_REG, 40)
    f_pill = ImageFont.truetype(F_BOLD, 32)
    f_swipe = ImageFont.truetype(F_BOLD, 34)

    # Top row: eyebrow left / right
    draw.text((MARGIN, 70), eyebrow_left, font=f_eyebrow, fill=LIGHT)
    rw = draw.textlength(eyebrow_right, font=f_eyebrow)
    draw.text((W - MARGIN - rw, 70), eyebrow_right, font=f_eyebrow, fill=LIGHT)

    # Headline
    max_w = W - 2 * MARGIN
    lines = wrap_text(draw, headline, f_headline, max_w)
    y = 260
    for line in lines:
        draw.text((MARGIN, y), line, font=f_headline, fill=WHITE)
        y += 92
    y += 30

    # Body
    for para in body_lines:
        wrapped = wrap_text(draw, para, f_body, max_w)
        for line in wrapped:
            draw.text((MARGIN, y), line, font=f_body, fill=LIGHT)
            y += 54
        y += 30

    # CTA pill
    if cta_text:
        pad_x, pad_y = 40, 24
        tw = draw.textlength(cta_text, font=f_pill)
        pill_w, pill_h = tw + pad_x * 2, 68 + pad_y - 24
        px0, py0 = MARGIN, H - 220
        px1, py1 = px0 + pill_w, py0 + pill_h
        draw.rounded_rectangle([px0, py0, px1, py1], radius=pill_h // 2, fill=PILL_BG)
        draw.text((px0 + pad_x, py0 + (pill_h - 32) // 2), cta_text, font=f_pill, fill=PILL_TEXT)

    # Swipe indicator
    if show_swipe:
        draw.text((MARGIN, H - 120), "Swipe  \u2192", font=f_swipe, fill=WHITE)

    img.save(out_path)
    return out_path


def render_carousel(carousel, batch_date, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    niche = carousel["niche"]
    paths = []

    total_slides = 2 + len(carousel["body_slides"])  # hook + body + cta

    # Slide 1: Hook
    p = render_slide(
        eyebrow_left=f"\u00a92026 \u00b7 {niche}",
        eyebrow_right=f"01/{total_slides:02d}",
        headline=carousel["hook_slide"],
        body_lines=[],
        show_swipe=True,
        out_path=os.path.join(out_dir, "slide_01.png"),
    )
    paths.append(p)

    # Body slides
    for i, body in enumerate(carousel["body_slides"], start=2):
        # use first ~6 words as a mini headline, rest as body
        words = body.split()
        headline = " ".join(words[:6])
        rest = " ".join(words[6:]) if len(words) > 6 else ""
        p = render_slide(
            eyebrow_left=carousel["angle"],
            eyebrow_right=f"{i:02d}/{total_slides:02d}",
            headline=headline,
            body_lines=[rest] if rest else [],
            out_path=os.path.join(out_dir, f"slide_{i:02d}.png"),
        )
        paths.append(p)

    # CTA slide
    last = total_slides
    p = render_slide(
        eyebrow_left="Follow for more",
        eyebrow_right=f"{last:02d}/{total_slides:02d}",
        headline=carousel["cta_slide"],
        body_lines=[carousel["caption"][:120]],
        cta_text="Follow @youragency",
        out_path=os.path.join(out_dir, f"slide_{last:02d}.png"),
    )
    paths.append(p)

    return paths


if __name__ == "__main__":
    sample = {
        "niche": "Cosmetic Clinics",
        "angle": "Mistake/myth-busting",
        "hook_slide": "Your clinic's Google Ads are probably paying for people who were never going to book",
        "body_slides": [
            "Broad match keywords burn budget on people just browsing, not booking a consultation",
            "Check your search terms report weekly, not just your campaign dashboard",
            "Add the exact filters that cut wasted spend within the first week",
            "A good cost-per-lead for aesthetics sits far lower than most clinics assume"
        ],
        "cta_slide": "Comment AUDIT and I'll tell you what to check first",
        "caption": "Most clinics don't have a Google Ads problem, they have a search terms problem"
    }
    out = render_carousel(sample, "2026-07-09", "/home/claude/sample_carousel")
    print(out)
