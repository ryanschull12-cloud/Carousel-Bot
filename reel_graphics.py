"""
reel_graphics.py -- the two graphic beat renderers for reel_engine.py.

WHY THIS IS A SEPARATE MODULE (2026-08-12): reel_engine.py is already 1400 lines
and every beat painter lives inside one render() closure, which is fine for four
type beats and unmanageable at six. These two are also the only painters that draw
structures rather than words, so they have their own vocabulary -- cards, rows,
radio marks, bars -- that nothing else needs.

Every function here is PURE. Nothing imports reel_engine, so there is no cycle:
the caller passes a ctx dict carrying the palette, the fonts and the geometry it
already has. That also makes them testable on their own, which is how the timing
below was checked.

WHY THESE BEATS EXIST AT ALL. The reels were all type on a background. A viewer who
does not already know what "location targeting" looks like has to take the claim on
faith, and a claim taken on faith is worth nothing -- which is what "boring by slide
three" actually means. These draw the thing being talked about.

TIMING. Entrances are 300-420ms and never longer. Material puts larger mobile
transitions in that band and calls anything past 500ms sluggish; a 1.7s wipe reads as
lag, not as weight. Reading time is bought by HOLDING the finished frame, never by
slowing the transition that puts it there. Distance scales duration: short fades use
ease-out cubic, long travel uses ease-out quintic so it leaves fast and settles soft.

MECHANISM LINE IS MANDATORY. Both painters end on a line that says what the thing
actually DOES, not what to do about it. "Change this one setting" over a screenshot
teaches nobody anything. The renderer will draw whatever it is given, so the contract
has to hold upstream in the content brain -- a graphic beat with no mechanism line is
decoration and should be rejected before it reaches here.
"""
from PIL import Image, ImageDraw

ENTER      = 0.34      # standard element entrance
ENTER_BIG  = 0.42      # larger travel earns a longer, softer settle
STAGGER    = 0.12      # between sibling rows


def _cubic(t):  return 1 - (1 - t) ** 3
def _quint(t):  return 1 - (1 - t) ** 5


def enter(i, fps, t0, dur=ENTER, curve=_cubic):
    """Progress 0..1 for an element due to start at t0 seconds."""
    t = (i / float(fps) - t0) / dur
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    return curve(t)


def lerp(a, b, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


def _wrap(d, text, font, maxw):
    out, cur = [], ""
    for w in text.split():
        s = (cur + " " + w).strip()
        if d.textlength(s, font=font) <= maxw:
            cur = s
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def _fit(d, text, path, start, floor, maxw, maxlines, F):
    s = start
    while s > floor:
        f = F(path, s)
        ls = _wrap(d, text, f, maxw)
        if len(ls) <= maxlines:
            return f, ls
        s -= 4
    f = F(path, floor)
    return f, _wrap(d, text, f, maxw)


# ---------------------------------------------------------------------------
# CHART BEAT
# ---------------------------------------------------------------------------
def paint_chart(fr, ctx, data, i, fps):
    """A single number falling, with the two bars that explain it.

    ONE STORY, ONE DIRECTION. The first version resolved the headline figure to its
    final value and only then drew before/after bars, so the beat told the same thing
    twice and the second telling was redundant. The number and the after-bar now move
    together: the figure counts down while the bar shortens under it, and the colour
    travels from the dead grey of the "before" state to the accent as it lands. On a
    muted feed the colour change carries the meaning by itself.

    data: {label, before, after, unit, caption}
    """
    W, H, M = ctx["W"], ctx["H"], ctx["M"]
    F, SB = ctx["F"], ctx["F_SANS"]
    BG, INK, DIM = ctx["BG"], ctx["INK"], ctx["DIM"]
    WAS, SHADOW = ctx["BAR_WAS"], ctx["SHADOW"]
    c = ctx["c"]

    d = ImageDraw.Draw(fr)
    unit = data.get("unit", "")
    before, after = float(data["before"]), float(data["after"])

    d.text((M, 430), data["label"].upper(), font=F(SB, 52), fill=DIM)

    p = enter(i, fps, 0.50, 1.25, _quint)          # the fall is the beat, so it gets room
    val = int(round(before - (before - after) * p))
    fn = F(SB, 300)
    s = "%s%d" % (unit, val)
    d.text((M + 4, 504), s, font=fn, fill=SHADOW)
    d.text((M, 500), s, font=fn, fill=lerp(WAS, c["accent"], p))

    bw = W - 2 * M
    by = 900
    d.text((M, by - 54), "BEFORE", font=F(SB, 38), fill=WAS)
    g = enter(i, fps, 0.10, ENTER_BIG, _quint)
    d.rounded_rectangle([M, by, M + int(bw * g), by + 58], radius=8, fill=WAS)

    ay = by + 126
    d.text((M, ay - 54), "AFTER", font=F(SB, 38), fill=c["deep"] if p > 0 else WAS)
    if p > 0:
        ratio = max(0.06, after / before if before else 1.0)
        d.rounded_rectangle([M, ay, M + int(bw * (1 - (1 - ratio) * p)), ay + 58],
                            radius=8, fill=c["accent"])

    cap = data.get("caption")
    if cap:
        q = enter(i, fps, 2.00)
        if q > 0:
            f, ls = _fit(d, cap, SB, 60, 44, W - 2 * M, 2, F)
            for k, ln in enumerate(ls):
                d.text((M, ay + 140 + k * int(f.size * 1.3) + int(12 * (1 - q))),
                       ln, font=f, fill=lerp(BG, INK, q))
    return fr


# ---------------------------------------------------------------------------
# SCREEN BEAT
# ---------------------------------------------------------------------------
def paint_screen(fr, ctx, data, i, fps):
    """The actual setting, with the wrong state named before it changes.

    NAMING THE FAULT FIRST IS THE WHOLE POINT. An earlier cut moved the selection from
    one option to the other with nothing marking the first as wrong, so the switch
    looked arbitrary -- a thing happening rather than a thing being fixed. The current
    option now carries a CURRENTLY ON tag and holds for a beat before anything moves.
    Fault, then fix, in that order, or the viewer has no reason to care about the fix.

    data: {title, panel_label, options[(name, sub)], wrong, right, mechanism}
    """
    W, H, M = ctx["W"], ctx["H"], ctx["M"]
    F, SB, SR = ctx["F"], ctx["F_SANS"], ctx["F_SANSR"]
    BG, INK, DIM = ctx["BG"], ctx["INK"], ctx["DIM"]
    WAS = ctx["BAR_WAS"]
    c = ctx["c"]
    SWITCH = data.get("switch_at", 2.60)

    d = ImageDraw.Draw(fr)
    f, ls = _fit(d, data["title"], SB, 96, 72, W - 2 * M, 2, F)
    lh = int(f.size * 1.16)
    y = 286
    for ln in ls:
        d.text((M, y), ln, font=f, fill=INK)
        y += lh
    g = enter(i, fps, 0.30, ENTER_BIG, _quint)
    if g > 0:
        d.rectangle([M, y + 20, M + int(d.textlength(ls[0], font=f) * g), y + 30],
                    fill=c["accent"])

    opts = data["options"][:2]
    px, py, pw = M, y + 86, W - 2 * M
    ph = 84 + 162 * len(opts)
    cp = enter(i, fps, 0.85, ENTER_BIG)
    if cp <= 0:
        return fr

    card = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(
        [0, 0, pw - 1, ph - 1], radius=20,
        outline=(220, 218, 210, int(255 * cp)), width=2,
        fill=(255, 255, 255, int(255 * cp)))
    fr.paste(card, (px, py + int(28 * (1 - cp))), card)

    d = ImageDraw.Draw(fr)
    off = int(28 * (1 - cp))
    d.text((px + 36, py + 26 + off), data.get("panel_label", "").upper(),
           font=F(SB, 28), fill=DIM)

    switched = (i / float(fps)) >= SWITCH
    wrong, right = data.get("wrong", 0), data.get("right", 1)
    oy = py + 84 + off
    for k, (name, sub) in enumerate(opts):
        if enter(i, fps, 1.35 + k * STAGGER) <= 0:
            oy += 162
            continue
        on = (k == right) if switched else (k == wrong)
        if k == wrong and not switched:
            w = enter(i, fps, 2.45)
            d.rounded_rectangle([px + 22, oy - 14, px + pw - 22, oy + 134],
                                radius=12, fill=(242, 240, 235))
            if w > 0:
                d.rectangle([px + 22, oy - 14, px + 30, oy + 134],
                            fill=lerp((242, 240, 235), WAS, w))
                ft = F(SB, 24)
                tag = "CURRENTLY ON"
                d.text((px + pw - 56 - d.textlength(tag, font=ft), oy + 2),
                       tag, font=ft, fill=lerp(BG, WAS, w))
        if k == right and switched:
            s = enter(i, fps, SWITCH)
            d.rounded_rectangle([px + 22, oy - 14, px + pw - 22, oy + 134],
                                radius=12, fill=lerp(BG, c["veil"], s))
            d.rectangle([px + 22, oy - 14, px + 30, oy + 134],
                        fill=lerp(BG, c["accent"], s))
        rr, cx, cy = 20, px + 54, oy + 24
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                  outline=c["deep"] if on else (188, 186, 178), width=4)
        if on:
            s = enter(i, fps, SWITCH) if k == right else 1.0
            r2 = int(10 * s)
            if r2 > 0:
                d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
                          fill=c["accent"] if k == right else WAS)
        d.text((px + 96, oy - 4), name, font=F(SB, 44), fill=INK if on else DIM)
        d.text((px + 96, oy + 54), sub, font=F(SR, 29), fill=DIM)
        oy += 162

    mech = data.get("mechanism")
    if mech:
        fx, lines = _fit(d, mech, SB, 46, 34, W - 2 * M, 3, F)
        for k, ln in enumerate(lines):
            e = enter(i, fps, SWITCH + 0.70 + k * STAGGER)
            if e > 0:
                d.text((M, py + ph + 52 + k * int(fx.size * 1.34) + int(12 * (1 - e))),
                       ln, font=fx, fill=lerp(BG, INK, e))
    return fr


# A graphic beat that runs long is a budget problem, not a rendering one: the reel
# has a fixed ceiling and trim_to_budget pays for an overrun by DELETING a later
# beat. So these compute the honest duration -- a viewer who cannot finish reading
# the line is worse than a long beat -- and shout when the copy is the reason.
# The fix for a warning here is always shorter copy upstream, never a shorter hold.
MAX_GRAPHIC_S = 9.0
CPS_SUPPORT   = 17.0   # supporting lines read faster: the context is already set


def chart_duration(data, floor=3.6):
    """0.5s lead-in, 1.25s fall, then time to read the caption."""
    cap = data.get("caption") or ""
    d = max(floor, 0.50 + 1.25 + 0.40 + len(cap) / CPS_SUPPORT)
    if d > MAX_GRAPHIC_S:
        print("WARNING: chart beat needs %.1fs -- caption is %d chars. Cap is ~90."
              % (d, len(cap)))
    return d


def screen_duration(data, floor=5.5):
    mech = data.get("mechanism") or ""
    switch = data.get("switch_at", 2.60)
    d = max(floor, switch + 0.70 + 0.40 + len(mech) / CPS_SUPPORT)
    if d > MAX_GRAPHIC_S:
        print("WARNING: screen beat needs %.1fs -- mechanism is %d chars. Cap is ~90."
              % (d, len(mech)))
    return d
