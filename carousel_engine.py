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
# Typography aligned with reel_engine (2026-08-09): the reels moved to
# all-sans Inter while carousel hooks stayed Liberation Serif, so the profile
# grid read as two different accounts -- the mismatch the rebrand was meant to
# close. Same mechanism as the reels: Inter arrives via `apt-get install
# fonts-inter` in the workflows, Liberation Sans is the fallback if that step
# ever fails, and INTER_FONT_DIR overrides for local testing without root.
# Degrading is allowed; stopping is not.
INTER_DIRS = [
    os.environ.get("INTER_FONT_DIR", ""),
    "/usr/share/fonts/opentype/inter",
    "/usr/share/fonts/truetype/inter",
]

def _sans_family():
    for d in INTER_DIRS:
        if d and os.path.exists(os.path.join(d, "Inter-Regular.otf")):
            return (os.path.join(d, "Inter-Bold.otf"), os.path.join(d, "Inter-Regular.otf"),
                    os.path.join(d, "Inter-SemiBold.otf"))
    return (os.path.join(SYS_DIR, "LiberationSans-Bold.ttf"),
            os.path.join(SYS_DIR, "LiberationSans-Regular.ttf"),
            os.path.join(SYS_DIR, "LiberationSans-Bold.ttf"))

F_SANS_BOLD, F_SANS_REG, F_SEMI = _sans_family()
# Display face for hooks, bridges, mega stats/phrases, recap headers and
# before/after values. Was LiberationSerif-Bold until 2026-08-09.
F_DISPLAY = F_SANS_BOLD

# ---------------------------------------------------------------------------
# Supersampled rendering (2026-08-09). Slides draw onto a 2x canvas and are
# LANCZOS-downscaled to 1080x1350 at save time, which anti-aliases every
# primitive PIL draws hard-edged at 1x -- polygon diagonals, circles, pill
# corners -- and tightens the type. All layout math stays in 1x coordinates:
# _SSDraw scales geometry at draw time and measures text with the caller's
# own 1x font, so wrapping, centering and fitting are bit-for-bit the
# decisions the 1x engine made. Saves also moved to quality=95 with
# subsampling=0: PIL's default 4:2:0 chroma subsampling smears the edges of
# coloured type on dark ground, which reads as blur on a phone.
# ---------------------------------------------------------------------------
SS = 2

class _SSDraw:
    def __init__(self, img):
        self._d = ImageDraw.Draw(img)
        self._fonts = {}

    def _xy(self, xy):
        return [tuple(v * SS for v in p) if isinstance(p, (tuple, list)) else p * SS
                for p in xy]

    def _font2x(self, font):
        key = (font.path, font.size)
        f = self._fonts.get(key)
        if f is None:
            f = ImageFont.truetype(font.path, font.size * SS)
            self._fonts[key] = f
        return f

    def textlength(self, text, font=None):
        return self._d.textlength(text, font=font)  # 1x font, 1x answer

    def text(self, xy, text, font=None, fill=None):
        x, y = xy
        self._d.text((x * SS, y * SS), text, font=self._font2x(font), fill=fill)

    def rectangle(self, xy, **kw):
        self._d.rectangle(self._xy(xy), **kw)

    def rounded_rectangle(self, xy, radius=0, width=1, **kw):
        self._d.rounded_rectangle(self._xy(xy), radius=radius * SS, width=width * SS, **kw)

    def ellipse(self, xy, **kw):
        if "width" in kw:
            kw["width"] = kw["width"] * SS
        self._d.ellipse(self._xy(xy), **kw)

    def line(self, xy, fill=None, width=1, joint=None):
        self._d.line(self._xy(xy), fill=fill, width=width * SS, joint=joint)

    def polygon(self, xy, **kw):
        self._d.polygon(self._xy(xy), **kw)


def new_slide():
    """2x canvas + scaling draw proxy. Pair with save_slide()."""
    img = Image.new("RGB", (W * SS, H * SS), BG)
    return img, _SSDraw(img)


def save_slide(img, out_path):
    img.resize((W, H), Image.LANCZOS).save(out_path, "JPEG", quality=95, subsampling=0)

AGENCY_HANDLE = "@rd.marketing0"

# Palette lifted from marketing-rd.com's own CSS custom properties so the
# carousels and the site read as one brand.
#   --bg #0a0a0d  --bg-alt #0d0e12  --bg-raised #15161c
#   --ink #f4f5f7 --dim #9a9ca6     --accent #6ea8ff
BG = (10, 10, 13)            # --bg
BG_ALT = (13, 14, 18)        # --bg-alt, for vertical gradients
BG_RAISED = (21, 22, 28)     # --bg-raised, card fills
DOT_COLOR = (58, 60, 68)     # unlit constellation nodes
HAIRLINE = (36, 37, 44)      # --line rgba(255,255,255,0.09) over --bg
TEXT = (244, 245, 247)       # --ink
GRAY = (154, 156, 166)       # --dim
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
SHADOW = (6, 6, 8)           # depth shade, now one tone BELOW bg not above

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

# One brand blue, three tonal positions around it. Google Ads sits on the
# true brand hue from marketing-rd.com, Meta pushes violet, Email pushes
# cyan -- close enough to read as one system, far enough apart to tell the
# topics apart at a glance. Keys stay accent/dark/light so every existing
# call site keeps working; on a dark canvas "dark" is the deep tone and
# "light" is the raised-card tone, which is why they look inverted.
TOPIC_COLORS = {
    "google ads": {"accent": (110, 168, 255), "dark": (30, 52, 92), "light": (22, 30, 46)},
    "meta": {"accent": (146, 154, 255), "dark": (44, 46, 96), "light": (27, 28, 48)},
    "instagram": {"accent": (146, 154, 255), "dark": (44, 46, 96), "light": (27, 28, 48)},
    "email": {"accent": (94, 199, 240), "dark": (24, 62, 84), "light": (19, 33, 43)},
}
DEFAULT_COLORS = {"accent": (110, 168, 255), "dark": (30, 52, 92), "light": (22, 30, 46)}


def colors_for(niche):
    n = (niche or "").lower()
    for key, colors in TOPIC_COLORS.items():
        if key in n:
            return colors
    return DEFAULT_COLORS


def split_overlong(draw, word, font, max_width):
    """Break a single token that is wider than the line it has to live on.

    Added 2026-08-09. wrap_text used to hand any such token back as its own line
    and fit_text_shrink_only would shrink until it gave up, then render it anyway
    -- centred, so it ran off BOTH edges. Nothing raised and nothing looked wrong
    in a manifest, so it only showed up once the smoke test started reading pixels
    at the canvas edge. Real copy hits this: DMARC records, tracking URLs, long
    hyphenated compounds.

    Break at punctuation a reader already parses as a seam before resorting to
    mid-character splits, and keep the separator on the leading fragment so the
    line ends on the hyphen rather than starting with one.
    """
    if draw.textlength(word, font=font) <= max_width:
        return [word]

    for sep in ("-", "/", "@", "_", ".", ":", ";", "="):
        if sep in word[1:-1]:
            parts, out, cur = word.split(sep), [], ""
            for i, p in enumerate(parts):
                piece = p + (sep if i < len(parts) - 1 else "")
                if cur and draw.textlength(cur + piece, font=font) > max_width:
                    out.append(cur)
                    cur = piece
                else:
                    cur += piece
            if cur:
                out.append(cur)
            if all(draw.textlength(o, font=font) <= max_width for o in out):
                return out

    # No seam to use -- split by character. Ugly, but legible beats off-canvas.
    out, cur = [], ""
    for ch in word:
        if cur and draw.textlength(cur + ch, font=font) > max_width:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def wrap_text(draw, text, font, max_width):
    lines, cur = [], ""
    for w in text.split():
        for piece in split_overlong(draw, w, font, max_width):
            test = (cur + " " + piece).strip()
            if draw.textlength(test, font=font) <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = piece
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


def draw_dot_grid(draw, spacing=48, radius=2, colors=None, seed=1):
    """Constellation background, matching marketing-rd.com's hero canvas.

    Scattered nodes with hairline links between near neighbours and roughly
    one node in seven lit in the niche accent. `spacing` and `radius` are
    kept in the signature for compatibility with experiment_loop.py, which
    may still reference them, but are no longer used.
    """
    import math, random
    accent = (colors or DEFAULT_COLORS)["accent"]
    rng = random.Random(seed * 7919)
    nodes = [(rng.uniform(-40, W + 40), rng.uniform(-40, H + 40)) for _ in range(34)]

    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d < 300:
                v = int(46 * (1 - d / 300.0))
                draw.line([a, b], fill=(v + 10, v + 11, v + 14), width=1)

    for idx, (x, y) in enumerate(nodes):
        if idx % 7 == 0:
            draw.ellipse([x - 3.5, y - 3.5, x + 3.5, y + 3.5], fill=accent)
        else:
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=DOT_COLOR)


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
            fill = (40, 42, 50)
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
    f_val = ImageFont.truetype(F_DISPLAY, size)
    f_arrow_gap = 70
    while size > min_size:
        before_w = draw.textlength(before_val, font=f_val)
        after_w = draw.textlength(after_val, font=f_val)
        total_w = before_w + f_arrow_gap + after_w
        if total_w <= max_width:
            break
        size -= 4
        f_val = ImageFont.truetype(F_DISPLAY, size)
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
    f_val = ImageFont.truetype(F_DISPLAY, size)
    badge_gap = 90  # space reserved for the VS badge between the two sides
    while size > min_size:
        a_w = draw.textlength(side_a, font=f_val)
        b_w = draw.textlength(side_b, font=f_val)
        total_w = a_w + badge_gap + b_w
        if total_w <= max_width:
            break
        size -= 4
        f_val = ImageFont.truetype(F_DISPLAY, size)
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


def draw_text_highlighted_v2(draw, x, y, line, font, highlight, text_color, marker_color, deep_color=None):
    """Highlight treatment reworked 2026-08-09. The marker used to be the raw
    accent with the line's near-white ink running straight over it: 1.9-2.4:1
    depending on topic -- the same class of bug as the navy mega-phrase, on the
    keyword of nearly every slide. Tried flipping the span's ink dark first;
    descenders poking below the marker vanished into the canvas and the span
    went muddy. The reels already solved this: copy never sits ON the accent
    there -- body text lives on a dark raised panel with a thin accent bar at
    its edge. Same move here: the marker fills with the topic's deep tone
    (near-white on it measures 8-12:1 on all three palettes), a slim accent
    rule runs along its bottom edge to keep the bright signature, and the ink
    never changes so descenders stay legible wherever they land."""
    if not highlight or highlight not in line:
        draw.text((x, y), line, font=font, fill=text_color)
        return
    before, _, after = line.partition(highlight)
    cx = x
    if before:
        cx += draw.textlength(before, font=font)
    hw = draw.textlength(highlight, font=font)
    ascent, _ = font.getmetrics()
    hx, hy, hh = cx, y + ascent * 0.06, ascent * 0.88
    fill = deep_color if deep_color is not None else marker_color
    pts = [(hx - 8, hy + hh * 0.12), (hx + hw + 10, hy - hh * 0.10),
           (hx + hw + 8, hy + hh * 0.98), (hx - 10, hy + hh * 1.08)]
    draw.polygon(pts, fill=fill)
    if deep_color is not None:
        # Accent rule along the marker's skewed bottom edge.
        bar = 7
        draw.polygon([pts[3], pts[2],
                      (pts[2][0], pts[2][1] + bar), (pts[3][0], pts[3][1] + bar)],
                     fill=marker_color)
    draw.text((x, y), line, font=font, fill=text_color)


def draw_text_highlighted_centered(draw, y, line, font, highlight, text_color, marker_color, deep_color=None):
    """Same as draw_text_highlighted_v2, but centers this line horizontally
    on the page instead of drawing from a fixed left x. Used everywhere the
    design should read as centered rather than left-aligned."""
    lw = draw.textlength(line, font=font)
    x = (W - lw) / 2
    draw_text_highlighted_v2(draw, x, y, line, font, highlight, text_color, marker_color, deep_color)


# ============================================================
# VECTOR ICONS — hand-drawn with PIL primitives only (no photos, no
# custom fonts/images needed, works on the GitHub Actions free tier).
# These give every hook/bridge/CTA slide a real graphic element beyond
# text + geometric accent bars, without touching any external asset.
# Each icon function draws centered at (cx, cy) at roughly `size` px
# tall/wide, in the given fill color(s) — callers handle badge/background.
# ============================================================

def draw_icon_bullseye(draw, cx, cy, size, ring_color, dot_color):
    """Google Ads — precision targeting."""
    r = size / 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ring_color)
    r2 = r * 0.66
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=dot_color)
    r3 = r * 0.32
    draw.ellipse([cx - r3, cy - r3, cx + r3, cy + r3], fill=ring_color)


def draw_icon_megaphone(draw, cx, cy, size, color):
    """Meta/Instagram Ads — broadcasting to an audience."""
    w, h = size, size * 0.72
    x0 = cx - w / 2
    # cone body (widening trapezoid pointing right)
    draw.polygon([
        (x0, cy - h * 0.22), (x0, cy + h * 0.22),
        (x0 + w * 0.55, cy + h * 0.5), (x0 + w * 0.55, cy - h * 0.5),
    ], fill=color)
    # handle
    draw.rectangle([x0 - w * 0.12, cy - h * 0.14, x0, cy + h * 0.14], fill=color)
    # bell/opening
    draw.polygon([
        (x0 + w * 0.55, cy - h * 0.5), (x0 + w * 0.55, cy + h * 0.5),
        (x0 + w * 0.78, cy + h * 0.62), (x0 + w * 0.78, cy - h * 0.62),
    ], fill=color)
    # sound lines
    lw = max(3, int(size * 0.05))
    for i, dy in enumerate((-0.28, 0, 0.28)):
        yy = cy + h * dy
        draw.line([(x0 + w * 0.9, yy), (x0 + w * 1.05, yy)], fill=color, width=lw)


def draw_icon_envelope(draw, cx, cy, size, color, bg):
    """Email marketing."""
    w, h = size, size * 0.68
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=size * 0.08, fill=color)
    lw = max(3, int(size * 0.06))
    draw.line([(x0 + lw, y0 + lw), (cx, cy + h * 0.12), (x1 - lw, y0 + lw)], fill=bg, width=lw, joint="curve")


def draw_icon_bookmark(draw, cx, cy, size, color):
    """Save action — used right next to the save CTA line."""
    w, h = size * 0.66, size
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    notch = h * 0.28
    draw.polygon([
        (x0, y0), (x1, y0), (x1, y1),
        (cx, y1 - notch), (x0, y1),
    ], fill=color)


def draw_icon_chat_bubble(draw, cx, cy, size, color):
    """Comment action — used right next to the comment CTA line."""
    w, h = size, size * 0.78
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=h * 0.28, fill=color)
    draw.polygon([
        (cx - w * 0.18, y1 - 2), (cx + w * 0.02, y1 - 2), (cx - w * 0.12, y1 + h * 0.24),
    ], fill=color)


def draw_icon_lightbulb(draw, cx, cy, size, color):
    """Realization / idea angle."""
    r = size * 0.42
    draw.ellipse([cx - r, cy - r * 1.1, cx + r, cy + r * 0.9], fill=color)
    base_w = r * 0.9
    draw.rectangle([cx - base_w / 2, cy + r * 0.55, cx + base_w / 2, cy + r * 1.05], fill=color)
    lw = max(3, int(size * 0.05))
    for i in range(2):
        yy = cy + r * 1.15 + i * (lw + 3)
        draw.line([(cx - base_w * 0.4, yy), (cx + base_w * 0.4, yy)], fill=color, width=lw)


NICHE_ICON_BUILDERS = {}


def draw_niche_icon(draw, cx, cy, size, niche, colors, bg=BG):
    """Dispatch to the right icon for this niche's badge, so every hook
    and bridge slide gets a real graphic mark, not just colored text."""
    n = (niche or "").lower()
    if "google" in n:
        draw_icon_bullseye(draw, cx, cy, size, colors["accent"], colors["dark"])
    elif "meta" in n or "instagram" in n:
        draw_icon_megaphone(draw, cx, cy, size, colors["dark"])
    elif "email" in n:
        draw_icon_envelope(draw, cx, cy, size, colors["dark"], bg)
    else:
        draw_icon_lightbulb(draw, cx, cy, size, colors["dark"])


def draw_icon_badge(draw, cx, cy, r, niche, colors, bg=BG):
    """Circular badge behind the niche icon, with the same flat drop-shadow
    depth treatment used everywhere else in this file (number badges,
    mega-stat text) so it reads as part of the same design system."""
    shadow_off = max(3, r // 14)
    draw.ellipse([cx - r + shadow_off, cy - r + shadow_off, cx + r + shadow_off, cy + r + shadow_off], fill=SHADOW)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colors["light"])
    draw_niche_icon(draw, cx, cy, r * 1.05, niche, colors, bg=colors["light"])


def draw_corner_flag(draw, colors):
    """
    UPGRADE 2 — bold diagonal accent wedge in the top-right corner.
    A consistent, non-photo, no-extra-font brand mark on every single slide.
    Sits under the slide counter, which is drawn on top of it afterward.
    """
    size = 130
    draw.polygon([(W, 0), (W, size), (W - size, 0)], fill=colors["accent"])


def draw_mega_stat(draw, text, y, colors, max_width, font_path=F_DISPLAY, target=170, min_size=110):
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
    # Accent, not "dark": on the old cream canvas "dark" was the ink, but after
    # the 004ec02 rebrand it sat at 1.57-1.78:1 against the near-black bg --
    # slide 1 of every carousel shipping with an invisible hero. Accent reads
    # 7.8-8.2:1 here and matches the reel hook's accent figure. (2026-08-09)
    draw.text((x, y), line, font=font, fill=colors["accent"])
    ascent, descent = font.getmetrics()
    return y + int((ascent + descent) * 0.92), size


def draw_mega_phrase(draw, text, y, colors, max_width, font_path=F_DISPLAY, target=130, min_size=76):
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
        # Accent for the same reason as draw_mega_stat: "dark" ink died in the
        # rebrand. See the comment there. (2026-08-09)
        draw.text((x, y), display_line, font=font, fill=colors["accent"])
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
    f_quote = ImageFont.truetype(F_DISPLAY, 120)
    draw.text((MARGIN - 10, y), "“", font=f_quote, fill=colors["light"])
    draw.text((W - MARGIN - 50, y + 200), "”", font=f_quote, fill=colors["light"])


def draw_vertical_accent_line(draw, x, y0, y1, colors):
    """Vertical accent line for visual interest."""
    draw.rectangle([x, y0, x + 4, y1], fill=colors["accent"])


def draw_bottom_accent_block(draw, y, height, colors):
    """Large accent color block at bottom to fill space."""
    draw.rectangle([0, y, W, y + height], fill=colors["light"])

# ---------------------------------------------------------------------------
# Mixed-weight text (2026-08-09). The reel hook sets its sentence in Regular
# with the emphasis token in Bold accent, and Ryan picked that frame out as
# the design to build on. These helpers bring the same treatment to the
# carousel: words inside the emphasis span measure and draw in the bold face
# and the accent colour, everything else in the base face and ink. Wrapping
# is computed against each word's own font so a bold span can't overflow a
# line that was measured regular.
# ---------------------------------------------------------------------------

def _span_words(text, span):
    """Per-word bold flags: a word is bold if it overlaps `span` in `text`."""
    i = text.find(span) if span else -1
    rng = (i, i + len(span)) if i >= 0 else None
    out, pos = [], 0
    for w in text.split():
        j = text.index(w, pos)
        pos = j + len(w)
        bold = rng is not None and j < rng[1] and (j + len(w)) > rng[0]
        out.append((w, bold))
    return out


def layout_mixed(draw, text, span, f_reg, f_bold, max_w):
    words = _span_words(text, span)
    sp = draw.textlength(" ", font=f_reg)
    lines, cur, cw = [], [], 0.0
    for w, b in words:
        ww = draw.textlength(w, font=f_bold if b else f_reg)
        add = ww if not cur else ww + sp
        if cur and cw + add > max_w:
            lines.append(cur)
            cur, cw = [(w, b)], ww
        else:
            cur.append((w, b))
            cw += add
    if cur:
        lines.append(cur)
    return lines


def fit_mixed(draw, text, span, max_w, max_lines, target, min_size, reg_path, bold_path):
    """Shrink-only, same contract as fit_text_shrink_only."""
    for size in range(target, min_size - 1, -4):
        f_reg = ImageFont.truetype(reg_path, size)
        f_bold = ImageFont.truetype(bold_path, size)
        lines = layout_mixed(draw, text, span, f_reg, f_bold, max_w)
        widths_ok = all(
            sum(draw.textlength(w, font=f_bold if b else f_reg) for w, b in ln)
            + draw.textlength(" ", font=f_reg) * (len(ln) - 1) <= max_w
            for ln in lines)
        if len(lines) <= max_lines and widths_ok:
            return f_reg, f_bold, lines, size
    f_reg = ImageFont.truetype(reg_path, min_size)
    f_bold = ImageFont.truetype(bold_path, min_size)
    return f_reg, f_bold, layout_mixed(draw, text, span, f_reg, f_bold, max_w), min_size


def draw_mixed_lines(draw, lines, x, y, f_reg, f_bold, line_h, ink, accent):
    sp = draw.textlength(" ", font=f_reg)
    for ln in lines:
        cx = x
        for w, b in ln:
            f = f_bold if b else f_reg
            draw.text((cx, y), w, font=f, fill=accent if b else ink)
            cx += draw.textlength(w, font=f) + sp
        y += line_h
    return y


# ============================================================
# HOOK SLIDE — fixed size, designed fill
# ============================================================

def render_hook_slide_fixed(headline, niche, slide_num, total_slides, out_path, pop_phrase=None):
    """Restyled 2026-08-09 into the reel hook's design language, at Ryan's
    call after he picked the reel frames out as the look to build on: copy
    set left-aligned in Regular with the emphasis span in Bold accent, a
    short accent rule above the block, and negative space doing the work.
    The old centered stack -- mega phrase up top, icon circle, full-width
    accent bars, marker block -- repeated the emphasis twice and filled
    every quiet part of the frame; this says it once, larger than life,
    and lets the constellation breathe. Emphasis is colour+weight inline,
    the same call Ryan already made for the reels (block highlight
    rejected), so the grid finally speaks one language."""
    colors = colors_for(niche)
    img, draw = new_slide()
    draw_dot_grid(draw)
    draw_corner_flag(draw, colors)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    max_w = W - 2 * MARGIN
    span = pop_phrase if (pop_phrase and pop_phrase in headline) else find_highlight_word(headline)
    f_reg, f_bold, lines, size = fit_mixed(draw, headline, span, max_w, 4,
                                           HOOK_FONT_SIZE, 52, F_SANS_REG, F_SANS_BOLD)
    line_h = int(size * 1.14)
    total_h = line_h * len(lines)

    # Upper-third anchor, like the reel hook: the block sits high with air
    # underneath, not dead-centered.
    top, bottom = 250, H - 210
    ty = top + max(0, int((bottom - top - total_h) * 0.34))

    # The reel hook's mark: one short accent rule above the copy.
    draw.rectangle([MARGIN, ty - 58, MARGIN + 64, ty - 50], fill=colors["accent"])

    draw_mixed_lines(draw, lines, MARGIN, ty, f_reg, f_bold, line_h, TEXT, colors["accent"])

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    save_slide(img, out_path)
    return out_path


def render_bridge_slide_fixed(headline, niche, slide_num, total_slides, out_path, pop_phrase=None):
    """Same reel-language restyle as the hook (2026-08-09) and the same
    visual weight, per the re-hook rule -- the bridge must stop a swipe on
    its own. Differentiated by its mark: a vertical accent bar down the
    block's left edge (the treatment the original design spec reserved for
    bridge slides) instead of the hook's rule above."""
    colors = colors_for(niche)
    img, draw = new_slide()
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    bar_w, bar_gap = 10, 34
    max_w = W - 2 * MARGIN - bar_w - bar_gap
    span = pop_phrase if (pop_phrase and pop_phrase in headline) else find_highlight_word(headline)
    f_reg, f_bold, lines, size = fit_mixed(draw, headline, span, max_w, 4,
                                           BRIDGE_FONT_SIZE, 48, F_SANS_REG, F_SANS_BOLD)
    line_h = int(size * 1.14)
    total_h = line_h * len(lines)

    top, bottom = 250, H - 210
    ty = top + max(0, int((bottom - top - total_h) * 0.34))

    draw.rectangle([MARGIN, ty + 6, MARGIN + bar_w, ty + total_h - int(line_h * 0.14)],
                   fill=colors["accent"])
    draw_mixed_lines(draw, lines, MARGIN + bar_w + bar_gap, ty, f_reg, f_bold,
                     line_h, TEXT, colors["accent"])

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    save_slide(img, out_path)
    return out_path


# ============================================================

def render_numbered_slide_fixed(number, full_text, niche, slide_num, total_slides, out_path,
                                checklist_mode=False, show_swipe=False):
    before_val, after_val = slide_before_after(full_text)
    side_a, side_b = slide_comparison(full_text)
    full_text, explicit_keyword = slide_text_and_keyword(full_text)
    colors = colors_for(niche)
    img, draw = new_slide()
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
    span = explicit_keyword or find_highlight_word(full_text)
    f_reg, f_bold, lines, size = fit_mixed(draw, full_text, span, max_w, 4,
                                           BODY_FONT_SIZE, 44, F_SEMI, F_SANS_BOLD)
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

    # Chip sits on the panel's left edge, in line with the left-aligned copy
    # below it, instead of floating centered above a left-aligned block.
    badge_x = MARGIN + 4
    badge_y = top_y
    block_y = badge_y + badge_size + gap_below_badge
    block_h = card_pad_y * 2 + strip_h + total_h
    block_x0 = MARGIN
    block_x1 = W - MARGIN

    # UPGRADE 3: accent block renders behind EVERY body slide, not just
    # short-text ones — this is what was making some slides look designed
    # and others look plain within the same carousel.
    # Reel body treatment (2026-08-09): raised panel with an accent bar down
    # its left edge -- the frame Ryan pointed at. The accent never sits
    # under copy, it marks the panel's edge.
    draw.rounded_rectangle([block_x0, block_y, block_x1, block_y + block_h],
                          radius=14, fill=BG_RAISED)
    draw.rectangle([block_x0, block_y + 10, block_x0 + 7, block_y + block_h - 10],
                   fill=colors["accent"])

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

    ty = block_y + card_pad_y
    if has_before_after:
        strip_used = draw_before_after_strip(draw, before_val, after_val, colors, ty, max_w)
        ty += max(strip_used, strip_h)
    elif has_comparison:
        strip_used = draw_comparison_strip(draw, side_a, side_b, colors, ty, max_w)
        ty += max(strip_used, strip_h)
    # Left-aligned mixed-weight copy, keyword in accent bold -- colour+weight
    # emphasis, same call as the hook and the reels. (2026-08-09)
    draw_mixed_lines(draw, lines, block_x0 + card_pad_x, ty, f_reg, f_bold,
                     line_h, TEXT, colors["accent"])

    if show_swipe:
        draw_swipe_arrow(draw, colors)

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    save_slide(img, out_path)
    return out_path


# ============================================================
# AESTHETIC RECAP SLIDE — card based (already good, keep it)
# ============================================================

def render_recap_slide_aesthetic(recap_lines, niche, slide_num, total_slides, out_path):
    colors = colors_for(niche)
    img, draw = new_slide()
    draw_dot_grid(draw)
    draw_header_v2(draw, niche, slide_num, total_slides, colors)

    # "Save This" badge
    f_save_big = ImageFont.truetype(F_DISPLAY, RECAP_HEADER_SIZE)
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

    save_slide(img, out_path)
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
    # Moved onto the dark canvas 2026-08-09. This slide was rebuilt on
    # 2026-07-28, BEFORE the 004ec02 rebrand, and the rebrand missed it: it
    # kept building its own white-to-light-blue gradient locally while every
    # other slide went near-black -- one glowing light slide closing every
    # otherwise-dark carousel on the grid. It even set its context line in
    # the near-white TEXT token, i.e. white-on-white. The gradient now runs
    # BG down into the topic veil tone, echoing how the reel CTA wipes to
    # the topic colour without leaving the dark system.
    colors = colors_for(niche)
    img, draw = new_slide()
    for row in range(H):
        t = row / H
        color = tuple(int(BG[i] + (colors["light"][i] - BG[i]) * t) for i in range(3))
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

    # SAVE ask — a bookmark icon sits right in the pill next to the word
    # "Save," visually reinforcing the exact action being asked for instead
    # of relying on the word alone.
    tw = draw.textlength(save_text, font=f_save)
    pad_x = 24
    icon_w = 34
    icon_gap = 14
    pill_w = tw + pad_x * 2 + icon_w + icon_gap
    px = (W - pill_w) / 2
    draw.rounded_rectangle([px, ty, px + pill_w, ty + pill_h], radius=pill_h // 2, fill=colors["dark"])
    draw_icon_bookmark(draw, px + pad_x + icon_w / 2, ty + pill_h / 2, icon_w, WHITE)
    draw.text((px + pad_x + icon_w + icon_gap, ty + 12), save_text, font=f_save, fill=WHITE)
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
    chat_icon_w = 46
    chat_gap = 16
    total_cta_w = chat_icon_w + chat_gap + tw
    cta_x = (W - total_cta_w) / 2 + chat_icon_w + chat_gap
    # Chat-bubble icon next to "Comment", same purpose as the bookmark next
    # to "Save" above — the icon visually names the action, the giant text
    # still carries the actual keyword.
    draw_icon_chat_bubble(draw, (W - total_cta_w) / 2 + chat_icon_w / 2, ty + cta_h * 0.42, chat_icon_w, colors["accent"])
    # Shadow/ink flipped for the dark canvas: was accent shadow under BLACK
    # text, which is the light-canvas treatment. Now the same SHADOW-offset +
    # accent ink the hook and bridge mega text use. (2026-08-09)
    draw.text((cta_x + cta_shadow_off, ty + cta_shadow_off), cta_text, font=f_cta, fill=SHADOW)
    draw.text((cta_x, ty), cta_text, font=f_cta, fill=colors["accent"])
    ty += cta_h
    draw_accent_bar(draw, ty, colors, width=180)
    ty += bar_gap + cta_gap

    # Promise
    if promise_text:
        tw = draw.textlength(promise_text, font=f_promise)
        draw.text(((W - tw) / 2, ty), promise_text, font=f_promise, fill=TEXT)
        ty += CTA_PROMISE_SIZE + promise_gap

    # Support — short urgency/context line from the content brain, e.g.
    # "No cost, just the checklist" — never the raw caption anymore.
    if support_lines:
        ty += 30
        for line in support_lines:
            tw = draw.textlength(line, font=f_support)
            draw.text(((W - tw) / 2, ty), line, font=f_support, fill=GRAY)
            ty += support_line_h

    draw_follow_pill(draw, colors)
    draw_progress_bar(draw, slide_num, total_slides, colors["accent"], colors["dark"])

    save_slide(img, out_path)
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
