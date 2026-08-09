"""
render_qa.py -- image analysis used by smoke_test_render.py.

WHY THIS EXISTS (2026-08-09): the old smoke test only asked "did it raise?".
It passed cleanly through the entire dark-palette rebrand while shipping a hook
pop-phrase drawn in (30,52,92) navy on a (10,10,13) background -- the largest
element on the most important slide, effectively invisible -- and body slides
with the top half empty. Green ticks for a week, nobody looked.

These checks are deliberately engine-agnostic. They read pixels, not layout
constants, so they keep working when the design changes and they cannot drift
out of sync with carousel_engine.py the way a hard-coded bounding box would.

THE THREE THINGS PIXELS CAN CATCH THAT AN EXCEPTION CANNOT:
  contrast  -- something was drawn but you cannot read it
  balance   -- something was drawn but it is all in one corner
  clipping  -- something was drawn past the edge of the canvas

Thresholds are tuned in daylight against known-bad output (the navy pop phrase,
the dark-on-dark follow pill) and known-good output (white headline on black).
Retune by running with --debug, which dumps the per-cell contrast map.
"""
import numpy as np
from PIL import Image, ImageFilter

# --- tuning -----------------------------------------------------------------
CELL = 90              # px; ~one cap-height of body copy at 56px
MIN_CONTRAST = 3.0     # WCAG AA for large text. All our text is large.

# Ink fraction is what separates "a headline nobody can read" from "the decorative
# constellation, which is supposed to be faint". Measured on the live engine:
# constellation lines and text drop-shadows top out around 0.14 of a cell; set copy
# at 96px or larger fills 0.4-0.9. Anything in between is chrome -- the badge shadow,
# the progress bar, the follow pill -- which is worth saying once, not ninety times.
INK_DECORATION = 0.16  # below this, it is decoration; ignore
INK_COPY = 0.35        # at or above this, it is set copy; a finding here is serious
INK_HIGHPASS = 10      # gray levels above local blur before a pixel counts as ink
BLUR_R = 12
DEAD_ROW_INK = 0.0025  # row is "empty" below this ink fraction
DEAD_RUN_FRAC = 0.34   # flag a dead band longer than this fraction of content
EDGE_PX = 3


def _srgb_to_lum(arr):
    """Relative luminance per WCAG 2.1. arr is HxWx3 uint8."""
    c = arr.astype(np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def _ratio(hi, lo):
    return (hi + 0.05) / (lo + 0.05)


def ink_mask(im):
    """High-pass the image so text and hard shapes survive and smooth gradients
    do not. The constellation background is a real design element but it is drawn
    at very low amplitude, so it falls below INK_HIGHPASS and does not pollute the
    balance reading -- which is what we want: we are measuring *copy* placement."""
    g = im.convert("L")
    hp = np.abs(np.asarray(g, dtype=np.int16)
                - np.asarray(g.filter(ImageFilter.GaussianBlur(BLUR_R)), dtype=np.int16))
    return hp > INK_HIGHPASS


def _otsu_split(vals):
    """Split a cell's luminances into figure and ground.

    Replaces an earlier approach that took the ink mask as the figure and
    everything else as the ground. That works for text on a flat field and fails
    completely on a filled shape: a badge pill fills most of its cell, the mask
    saturates at 98%, and the leftover 2% "background" is unrepresentative, so a
    perfectly legible dark-on-accent badge measured 1.77:1. Otsu makes no
    assumption about which is which -- it just finds the threshold that best
    separates two populations, which is the actual question being asked.
    """
    hist, edges = np.histogram(vals, bins=64, range=(0.0, 1.0))
    total = hist.sum()
    if total == 0:
        return None
    centres = (edges[:-1] + edges[1:]) / 2.0
    w0 = np.cumsum(hist)
    w1 = total - w0
    valid = (w0 > 0) & (w1 > 0)
    if not valid.any():
        return None
    csum = np.cumsum(hist * centres)
    m0 = np.where(w0 > 0, csum / np.maximum(w0, 1), 0)
    m1 = np.where(w1 > 0, (csum[-1] - csum) / np.maximum(w1, 1), 0)
    between = w0 * w1 * (m0 - m1) ** 2
    between[~valid] = -1
    thr = centres[int(np.argmax(between))]
    lo_px, hi_px = vals[vals <= thr], vals[vals > thr]
    if lo_px.size < 20 or hi_px.size < 20:
        return None
    return float(np.percentile(hi_px, 85)), float(np.percentile(lo_px, 15))


def contrast_findings(im, min_ink=INK_DECORATION):
    """Walk the image in cells and, in each one, separate what was drawn from what
    it was drawn on, then measure the WCAG ratio between them.

    An earlier version took percentiles over the whole cell. That silently passed
    everything: a headline covers well under 8% of its cell's area, so the 92nd
    percentile was still background and every ratio came back 1.0:1. Ink has to be
    isolated by mask first -- the point of this check is precisely the case where
    ink and background are close together, so any method that treats the cell as
    one population cannot see it.

    Returns (x, y, ratio, ink_fraction) worst-first.
    """
    arr = np.asarray(im.convert("RGB"))
    L = _srgb_to_lum(arr)
    mask = ink_mask(im)
    h, w = L.shape
    out = []
    for y in range(0, h - CELL + 1, CELL):
        for x in range(0, w - CELL + 1, CELL):
            m = mask[y:y + CELL, x:x + CELL]
            frac = float(m.mean())
            if frac < min_ink:
                continue                      # nothing meaningful drawn here
            split = _otsu_split(L[y:y + CELL, x:x + CELL].ravel())
            if split is None:
                continue
            hi, lo = split
            r = _ratio(hi, lo)
            if r < MIN_CONTRAST:
                out.append((x, y, round(r, 2), round(frac, 3)))
    out.sort(key=lambda t: t[2])
    return out


def merge_contrast(cells):
    """Collapse adjacent flagged cells into one region.

    A 130px number spans eight cells. Reporting it eight times buries the one line
    that matters under seven that repeat it, and a report nobody finishes reading is
    the same as the old test nobody looked at. Returns dicts with the region box, its
    worst ratio, its peak ink fraction, and a copy/chrome verdict.
    """
    if not cells:
        return []
    idx = {(x, y): (r, f) for x, y, r, f in cells}
    seen, regions = set(), []
    for key in idx:
        if key in seen:
            continue
        stack, group = [key], []
        seen.add(key)
        while stack:
            cx, cy = stack.pop()
            group.append((cx, cy))
            for dx, dy in ((CELL, 0), (-CELL, 0), (0, CELL), (0, -CELL)):
                n = (cx + dx, cy + dy)
                if n in idx and n not in seen:
                    seen.add(n)
                    stack.append(n)
        xs = [g[0] for g in group]
        ys = [g[1] for g in group]
        ratios = [idx[g][0] for g in group]
        fracs = [idx[g][1] for g in group]
        regions.append({
            "box": (min(xs), min(ys), max(xs) + CELL, max(ys) + CELL),
            "ratio": min(ratios),
            "ink": max(fracs),
            "cells": len(group),
            "kind": "copy" if max(fracs) >= INK_COPY else "chrome",
        })
    regions.sort(key=lambda r: (r["kind"] != "copy", r["ratio"]))
    return regions


def balance_findings(im, top_chrome=150, bottom_chrome=95):
    """Longest vertical band of the content area with essentially nothing in it.
    Catches the 'copy sits in the bottom third and the top half is void' failure
    that the rebrand introduced and nobody saw."""
    mask = ink_mask(im)
    h = mask.shape[0]
    rows = mask[top_chrome:h - bottom_chrome].mean(axis=1)
    n = len(rows)
    best_run, run, best_start, start = 0, 0, 0, 0
    for i, v in enumerate(rows):
        if v < DEAD_ROW_INK:
            if run == 0:
                start = i
            run += 1
            if run > best_run:
                best_run, best_start = run, start
        else:
            run = 0
    frac = best_run / float(n)
    centroid = float((rows * np.arange(n)).sum() / max(rows.sum(), 1e-9) / n)
    return {
        "dead_frac": round(frac, 3),
        "dead_from": top_chrome + best_start,
        "dead_to": top_chrome + best_start + best_run,
        "centroid": round(centroid, 3),
        "flag": frac > DEAD_RUN_FRAC,
    }


def clip_findings(im, mid_band=(0.12, 0.88)):
    """Ink touching the left/right edge in the middle band means a line ran off the
    canvas. Corners are excluded because the corner triangle and the progress bar
    bleed on purpose."""
    mask = ink_mask(im)
    h, w = mask.shape
    a, b = int(h * mid_band[0]), int(h * mid_band[1])
    left = mask[a:b, :EDGE_PX].any()
    right = mask[a:b, w - EDGE_PX:].any()
    return {"left": bool(left), "right": bool(right), "flag": bool(left or right)}


def analyse(path, top_chrome=150, bottom_chrome=95):
    im = Image.open(path).convert("RGB")
    return {
        "path": path,
        "size": im.size,
        "contrast": merge_contrast(contrast_findings(im)),
        "balance": balance_findings(im, top_chrome, bottom_chrome),
        "clip": clip_findings(im),
    }


def ink_mass(path_or_im):
    im = Image.open(path_or_im) if isinstance(path_or_im, str) else path_or_im
    return float(ink_mask(im.convert("RGB")).mean())


def frame_rms(p1, p2):
    a = np.asarray(Image.open(p1).convert("RGB"), dtype=np.float64)
    b = np.asarray(Image.open(p2).convert("RGB"), dtype=np.float64)
    return float(np.sqrt(((a - b) ** 2).mean()))


def contact_sheet(paths, out_path, cols=5, thumb_w=300, label=None):
    """A human still has to look. This makes looking cost one click instead of ten."""
    from PIL import ImageDraw
    ims = [Image.open(p).convert("RGB") for p in paths]
    if not ims:
        return None
    ar = ims[0].height / ims[0].width
    tw, th = thumb_w, int(thumb_w * ar)
    rows = (len(ims) + cols - 1) // cols
    pad, head = 8, (34 if label else 0)
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad) + pad + head), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    if label:
        d.text((pad + 2, 10), label, fill=(235, 235, 240))
    for i, im in enumerate(ims):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((tw, th), Image.LANCZOS),
                    (pad + c * (tw + pad), head + pad + r * (th + pad)))
    sheet.save(out_path, quality=90)
    return out_path
