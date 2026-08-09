"""
Render smoke test -- design QA, not just a crash check.

WHAT CHANGED (2026-08-09) AND WHY:
The previous version rendered five synthetic carousels with placeholder copy and
exited zero if nothing raised. It did its job -- it never let a broken paren reach
the 7:37am cron -- but it was blind to everything that actually went wrong. It
passed every day through the dark-palette rebrand while shipping hook slides whose
largest element was navy-on-black, body slides with an empty top half, and a follow
pill drawn dark-on-dark. Seventeen days of green ticks, nobody looked at an image.

So this now does four things the old one did not:

  1. RENDERS REAL COPY. Fixtures are written to the content brain's own rules,
     with currency symbols, curly quotes, em dashes and numbers, at the lengths
     Mistral actually returns -- plus hostile cases (longest plausible hook, a
     one-word hook, an unbreakable 48-character token, a manifest missing every
     optional field) because the fitter only breaks at the extremes.

  2. READS THE PIXELS. Contrast, vertical balance and edge clipping are measured
     on the rendered image (see render_qa.py). These are the three failures that
     an exception can never catch: drawn but unreadable, drawn but badly placed,
     drawn but off-canvas.

  3. COVERS REELS. Reels are where the reach is, and reel_engine.py had no test at
     all. Checks the hook is fully legible at frame 0 (the scroll decision lands
     around 1.7s -- animating the hook in spends the whole window on a transition),
     that the loop closes, that duration sits in the retention band, and that the
     MP4 matches Meta's published Reel spec via ffprobe.

  4. LEAVES SOMETHING TO LOOK AT. The old test called shutil.rmtree on its own
     output, which is the single reason nobody had seen a slide since the rebrand.
     This writes contact sheets and an HTML report to --out and the workflow
     uploads them as an artifact.

EXIT CODES. Hard failures (crash, wrong slide count, clipped text, broken loop,
off-spec MP4) exit 1 and turn the commit red. Design findings (low contrast, dead
bands) print and land in the report but exit 0, because they are judgement calls
and a permanently-red CI is a CI nobody reads. Run with --strict to fail on those
too; that is what you want once the current findings are cleared.

Usage:
  python smoke_test_render.py                  carousels + one reel, report to ./smoke_out
  python smoke_test_render.py --no-reel        skip video (fast, no ffmpeg needed)
  python smoke_test_render.py --all-reels      render a reel for every niche
  python smoke_test_render.py --strict         design findings fail the build
  python smoke_test_render.py --out DIR        where to write the report
"""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import traceback

import carousel_engine as ce
import render_qa as qa
import smoke_test_fixtures as fx

DEFAULT_OUT = "smoke_out"

# Reel retention band. 7-15s holds 60-80%, 15-30s holds 40-60%, 45s+ rarely clears
# 30%, and 2026 benchmarks put a good view-through rate above 65% for reels under
# 15s against above 50% for under 30s.
#
# The floor was 15s on the assumption that ~20s was the target. That was backwards.
# Once beat durations came from reading speed the reels settled at 14-15s with every
# line still fully readable, which is the better end of the trade in both directions:
# shorter AND finishable. The floor now only catches a reel so short it cannot be
# carrying four body beats -- i.e. something upstream dropped copy.
REEL_MIN_S, REEL_MAX_S = 12.0, 26.0

# Frame 0 must already carry the hook. If the first frame has less than this
# fraction of the ink the hook ends on, the hook is animating in.
HOOK_FRAME0_INK = 0.85

# A seamless loop compounds watch time. Sinusoidal motion with a whole number of
# cycles should land the last frame on the first. Allow a little JPEG noise.
LOOP_RMS_MAX = 2.0

# A low-contrast region that shows up on one slide only is almost always the
# constellation background clustering by chance. A systematic one -- the badge
# shadow, the follow pill -- shows up on every slide it is drawn on. Three is the
# line between an accident and a decision.
MIN_CHROME_SLIDES = 3


class Findings:
    def __init__(self):
        self.hard = []
        self.soft = []
        self.notes = []
        # Chrome-level contrast repeats on every slide by construction -- the badge
        # shadow and the progress bar are drawn identically ten times. Collapse them
        # to one line each with a count, so the report stays readable.
        self._chrome = {}

    def fail(self, case, msg):
        self.hard.append((case, msg))

    def warn(self, case, msg):
        self.soft.append((case, msg))

    def note(self, case, msg):
        self.notes.append((case, msg))

    def chrome(self, case, box, ratio):
        # Keyed on position only, not case. These are fixed elements drawn at fixed
        # coordinates on every slide of every carousel; keying per case turned one
        # design problem into fifty identical lines.
        cur = self._chrome.get(box)
        if cur:
            self._chrome[box] = (min(cur[0], ratio), cur[1] + 1, cur[2] | {case})
        else:
            self._chrome[box] = (ratio, 1, {case})

    def settle(self):
        for box, (ratio, n, cases) in sorted(self._chrome.items(),
                                             key=lambda kv: kv[1][0]):
            if n < MIN_CHROME_SLIDES:
                continue
            x0, y0, x1, y1 = box
            self.soft.append(("chrome", f"({x0},{y0})-({x1},{y1}) sits at {ratio}:1 "
                                        f"-- {n} slides across {len(cases)} carousels"))
        self._chrome.clear()


# ---------------------------------------------------------------------------
# Carousels
# ---------------------------------------------------------------------------
def check_carousel(name, carousel, out_dir, f, sheets):
    slide_dir = os.path.join(out_dir, "carousels", name)
    os.makedirs(slide_dir, exist_ok=True)
    try:
        paths = ce.render_carousel(carousel, "2026-08-09", slide_dir)
    except Exception as e:
        f.fail(name, f"{type(e).__name__}: {e}")
        f.note(name, traceback.format_exc(limit=4))
        return

    expected = 4 + len(carousel["body_slides"])
    if not paths or len(paths) != expected:
        f.fail(name, f"expected {expected} slides, got {len(paths) if paths else 0}")
        return

    for p in paths:
        n = os.path.basename(p)
        try:
            r = qa.analyse(p)
        except Exception as e:
            f.fail(name, f"{n}: analysis failed: {type(e).__name__}: {e}")
            continue

        if r["size"] != (ce.W, ce.H):
            f.fail(name, f"{n}: canvas is {r['size']}, engine says {(ce.W, ce.H)}")

        if r["clip"]["flag"]:
            side = "left" if r["clip"]["left"] else "right"
            f.fail(name, f"{n}: copy runs off the {side} edge")

        for reg in r["contrast"]:
            x0, y0, x1, y1 = reg["box"]
            if reg["kind"] == "copy":
                f.warn(name, f"{n}: set copy is unreadable -- {reg['ratio']}:1 at "
                             f"({x0},{y0})-({x1},{y1}), {int(reg['ink'] * 100)}% ink. "
                             f"AA needs {qa.MIN_CONTRAST}:1 for large text.")
            else:
                f.chrome(name, (x0, y0, x1, y1), reg["ratio"])

        b = r["balance"]
        if b["flag"]:
            f.warn(name, f"{n}: {int(b['dead_frac'] * 100)}% dead band, "
                         f"y={b['dead_from']}-{b['dead_to']} (centroid {b['centroid']})")

    sheet = os.path.join(out_dir, "sheets", f"carousel_{name}.jpg")
    os.makedirs(os.path.dirname(sheet), exist_ok=True)
    qa.contact_sheet(paths, sheet, cols=5, label=f"{name} / {carousel.get('niche','')}")
    sheets.append((f"carousel: {name}", sheet))


# ---------------------------------------------------------------------------
# Reels
# ---------------------------------------------------------------------------
def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check_reel(name, carousel, out_dir, f, sheets, audio_dir):
    try:
        import reel_engine as re_
    except Exception as e:
        f.fail(name, f"reel_engine import failed: {type(e).__name__}: {e}")
        return

    work = os.path.join(out_dir, "reelframes", name)
    mp4 = os.path.join(out_dir, "reels", f"{name}.mp4")
    os.makedirs(os.path.dirname(mp4), exist_ok=True)
    if os.path.isdir(work):
        shutil.rmtree(work)

    beats = re_.beats_from_carousel(carousel)
    if not beats:
        f.fail(name, "beats_from_carousel returned nothing -- reel would be skipped")
        return

    try:
        # Called directly rather than via render_reel so the frames survive for
        # inspection; render_reel rmtrees its workdir, which is exactly the habit
        # that kept anyone from ever looking at one.
        n, dur = re_.render(carousel.get("niche", ""), beats, work,
                            (carousel.get("niche") or "").upper()[:18] or "MARKETING")
    except Exception as e:
        f.fail(name, f"frame render failed: {type(e).__name__}: {e}")
        f.note(name, traceback.format_exc(limit=4))
        return

    # Reel frames moved from JPEG to PNG intermediates (2026-08-09); accept
    # both so this keeps working against either engine generation.
    frames = sorted(os.path.join(work, x) for x in os.listdir(work)
                    if x.endswith((".jpg", ".png")))
    if len(frames) < 2:
        f.fail(name, f"only {len(frames)} frames rendered")
        return

    # --- every beat must be on screen long enough to read ---
    # Netflix allows 20 CPS for adult content; add time to find the copy after the
    # frame changes. The hook is exempt: it is deliberately set a touch tight, and
    # the loop tail brings it back for a second pass.
    for b in beats:
        copy = b.text if b.kind not in ("stat", "proof") else (b.sub or "")
        if not copy or b.kind == "hook":
            continue
        # Reads the engine's own constants rather than restating them. This check
        # silently stopped meaning anything the moment CPS moved from 20 to 15
        # (2026-08-09) -- it was still measuring against a ceiling the renderer no
        # longer used, so every beat passed by definition.
        need = min(re_.ORIENT + len(copy) / re_.CPS, re_.BEAT_MAX)
        if b.dur + 0.01 < need:
            f.warn(name, f"{b.kind} beat is {b.dur:.2f}s for {len(copy)} characters -- "
                         f"needs {need:.2f}s at {re_.CPS:.0f} CPS. Nobody can finish "
                         f"reading it.")
    # The content brain's own contract: body lines 65-95 characters, written as
    # sentences. Rewritten 2026-08-09 when the contract inverted -- it used to cap
    # lines at 34 characters and 6 words, which is what produced beats like
    # "Personalize first half": too short to carry a cause, and unshufflable only
    # by accident. Both bounds matter now. Under 65 is a telegram again; over 95
    # does not fit the 5.6s a beat gets inside a 30s reel, so it renders at a rate
    # nobody reads at.
    for b in beats:
        if b.kind == "proof" and b.pair:
            for v in b.pair:
                if not any(ch.isdigit() for ch in v):
                    f.warn(name, f"proof figure {v!r} has no number in it")
                if len(v) > 8:
                    f.warn(name, f"proof figure {v!r} is {len(v)} chars, max 8 -- "
                                 f"it sets very large and will shrink the frame's "
                                 f"dominant element")
        if b.kind == "body" and b.text:
            # Emphasis checks. The renderer degrades quietly on all three of these
            # (draws the line flat, or highlights a run so long it stops being a
            # highlight), so nothing else would ever catch them.
            if not b.emph:
                f.warn(name, f"body line has no emphasis phrase -- it renders as a "
                             f"flat wall with nothing for the eye to land on: {b.text!r}")
            else:
                if b.emph.lower() not in b.text.lower():
                    f.fail(name, f"emphasis {b.emph!r} does not appear in its own body "
                                 f"line, so nothing is highlighted: {b.text!r}")
                n_w = len(b.emph.split())
                if n_w > 3:
                    f.warn(name, f"emphasis {b.emph!r} is {n_w} words, max 3 -- past "
                                 f"three it reads as underlining the sentence rather "
                                 f"than pointing at the thing that matters")
            n_ch = len(b.text)
            if n_ch > 95:
                f.warn(name, f"body line is {n_ch} chars, max 95 -- at {re_.CPS:.0f} "
                             f"CPS that needs {re_.ORIENT + n_ch/re_.CPS:.1f}s and the "
                             f"beat caps at {re_.BEAT_MAX}s: {b.text!r}")
            if "," not in b.text and n_ch > 70:
                f.warn(name, f"body line is {n_ch} chars with no comma -- clause_wrap "
                             f"has no seam to break on and will split mid-phrase: "
                             f"{b.text!r}")
            if n_ch < 65:
                f.warn(name, f"body line is {n_ch} chars, min 65 -- too short to carry "
                             f"a cause, which is the telegram failure the contract was "
                             f"rewritten to stop: {b.text!r}")
    # The CTA is the frame the whole reel exists to reach, and it is composed as
    # "COMMENT" / keyword / "and I'll send you <promise>". A promise carrying its own
    # verb produces "and I'll send you I'll DM you the checklist", which is the kind
    # of sentence that only ever gets caught by reading the rendered frame.
    cb = next((b for b in beats if b.kind == "cta"), None)
    if cb:
        if not (cb.sub or "").strip():
            f.fail(name, "CTA has no promise -- the frame asks for a comment and never "
                         "says what the comment gets them")
        else:
            import re as _re
            if _re.match(r"(?i)^(comment|save|i'?ll|dm|send)\b", cb.sub.strip()):
                f.warn(name, f"cta_promise {cb.sub!r} starts with a verb -- it is slotted "
                             f"into \"and I'll send you ...\" and will read as a doubled "
                             f"instruction")
        if not (cb.text or "").strip():
            f.fail(name, "CTA has no keyword -- there is nothing to comment")

    # The hook's highlight. emphasis_token silently returned None for every hook
    # written to the current rules once the "must contain a figure" requirement was
    # dropped, and a hook with no highlight is the most expensive flat frame in the
    # reel. Check the beat actually resolves one, and that it came from the brain
    # rather than from the deliberately-poor fallback.
    hb = next((b for b in beats if b.kind == "hook"), None)
    if hb and hb.text:
        if not hb.emph:
            f.warn(name, "no hook_emphasis on this reel -- the renderer is guessing "
                         "which words to highlight on the frame that matters most")
        elif not re_.mark_phrase(hb.text.split(), hb.emph):
            f.fail(name, f"hook_emphasis {hb.emph!r} does not appear in the hook, so "
                         f"nothing is highlighted: {hb.text!r}")
        elif len(hb.emph.split()) > 3:
            f.warn(name, f"hook_emphasis {hb.emph!r} is {len(hb.emph.split())} words, "
                         f"max 3 -- it stops being a highlight")
        if re_.emphasis_token(hb.text, hb.emph) is None:
            f.fail(name, f"hook resolves no emphasis at all and will render flat: "
                         f"{hb.text!r}")

    # Descender clipping. Rendered body lines are composited as their own layers,
    # and a layer sized off ink rather than font metrics silently chops the tails
    # off g, j, p, q and y -- "guesses" renders as "auesses". Ryan caught it from a
    # screenshot on 2026-08-09; every existing check passed, because clipped copy
    # is still comfortably inside the margins. Probe the layer directly: ink on the
    # bottom row means the glyph ran out of box.
    try:
        from PIL import ImageDraw as _ID, Image as _IM
        _d = _ID.Draw(_IM.new("RGB", (4, 4)))
        probe_text = "gypsy judging quality, propped by heavy typography"
        fr_, fb_, ls_ = re_.fit_body_mixed(_d, probe_text, "judging quality",
                                           1080 - 2 * re_.MARGIN - 40, 112, 58, 6)
        for ln in ls_:
            lay = re_.line_layer(ln, fr_, fb_, (110, 168, 255))
            px = lay.load()
            if any(px[x, lay.height - 1][3] > 0 for x in range(lay.width)):
                f.fail(name, "body line layer has ink on its bottom row -- descenders "
                             "are being clipped (g/y/p/j/q lose their tails)")
                break
        # Mixed weights must share a baseline, or the emphasis phrase floats.
        a_r, d_r = fr_.getmetrics(); a_b, d_b = fb_.getmetrics()
        if abs(a_r - a_b) > 2:
            f.warn(name, f"regular and bold ascents differ by {abs(a_r-a_b)}px -- the "
                         f"emphasis phrase will not sit on the same line as its sentence")
    except Exception as e:
        f.warn(name, f"descender probe could not run: {e}")

    f.note(name, f"{len(beats)} beats, {sum(b.dur for b in beats):.1f}s of copy, "
                 f"type: {getattr(re_, 'FONT_FAMILY', '?')}")

    # --- the hook must be readable at frame 0 -------------------------------
    hook_frames = int(beats[0].dur * re_.FPS)
    ink0 = qa.ink_mass(frames[0])
    ink_end = qa.ink_mass(frames[min(hook_frames - 1, len(frames) - 1)])
    share = ink0 / max(ink_end, 1e-9)
    if share < HOOK_FRAME0_INK:
        f.warn(name, f"hook animates in -- frame 0 carries {int(share * 100)}% of the "
                     f"copy it ends on. The scroll decision lands at ~1.7s; a cascade "
                     f"spends that window on a transition.")
    else:
        f.note(name, f"hook legible at frame 0 ({int(share * 100)}% of final ink)")

    # --- contrast on a frame from each beat ---------------------------------
    probe_at, t = [], 0.0
    for b in beats:
        probe_at.append(min(int((t + b.dur * 0.75) * re_.FPS), len(frames) - 1))
        t += b.dur
    for idx in probe_at:
        r = qa.analyse(frames[idx], top_chrome=190, bottom_chrome=420)
        for reg in r["contrast"]:
            x0, y0, x1, y1 = reg["box"]
            if reg["kind"] == "copy":
                f.warn(name, f"frame {idx}: set copy is unreadable -- {reg['ratio']}:1 "
                             f"at ({x0},{y0})-({x1},{y1})")
            else:
                f.chrome(name, (x0, y0, x1, y1), reg["ratio"])
        if r["size"] != (re_.W, re_.H):
            f.fail(name, f"frame {idx}: {r['size']}, expected {(re_.W, re_.H)}")

    # --- loop closure -------------------------------------------------------
    rms = qa.frame_rms(frames[0], frames[-1])
    if rms > LOOP_RMS_MAX:
        f.warn(name, f"loop does not close -- last frame differs from first by "
                     f"RMS {rms:.1f}. A seamless loop compounds watch time.")
    else:
        f.note(name, f"loop closes (RMS {rms:.2f})")

    # --- duration -----------------------------------------------------------
    if not (REEL_MIN_S <= dur <= REEL_MAX_S):
        f.warn(name, f"duration {dur:.1f}s outside the {REEL_MIN_S:.0f}-{REEL_MAX_S:.0f}s "
                     f"retention band")

    # --- encode and check the container against Meta's spec ------------------
    try:
        track = re_.pick_track("2026-08-09", 0, audio_dir)
        re_.encode(work, mp4, dur, track)
    except Exception as e:
        f.fail(name, f"encode failed: {type(e).__name__}: {e}")
        return

    try:
        meta = ffprobe(mp4)
    except Exception as e:
        f.fail(name, f"ffprobe failed: {type(e).__name__}: {e}")
        return

    v = next((s for s in meta["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        f.fail(name, "no video stream")
    else:
        if (v["width"], v["height"]) != (re_.W, re_.H):
            f.fail(name, f"video is {v['width']}x{v['height']}, Reels needs 1080x1920")
        if v["codec_name"] != "h264":
            f.fail(name, f"codec is {v['codec_name']}, Reels needs h264")
        if v.get("pix_fmt") != "yuv420p":
            f.fail(name, f"pix_fmt is {v.get('pix_fmt')}, Reels needs yuv420p")
    if a is None:
        # Some containers are rejected outright with no audio stream, which is why
        # encode() falls back to silent AAC rather than omitting it.
        f.fail(name, "no audio stream -- Instagram rejects some containers without one")
    elif a["codec_name"] != "aac":
        f.fail(name, f"audio codec is {a['codec_name']}, Reels needs aac")

    d = float(meta["format"]["duration"])
    if abs(d - dur) > 0.4:
        f.warn(name, f"encoded {d:.1f}s but frames say {dur:.1f}s")
    f.note(name, f"{d:.1f}s, {os.path.getsize(mp4) / 1e6:.1f}MB, "
                 f"track: {os.path.basename(track) if track else 'silent'}")

    key = [frames[0]] + [frames[i] for i in probe_at] + [frames[-1]]
    sheet = os.path.join(out_dir, "sheets", f"reel_{name}.jpg")
    os.makedirs(os.path.dirname(sheet), exist_ok=True)
    qa.contact_sheet(key, sheet, cols=len(key), thumb_w=200,
                     label=f"reel {name} -- frame 0, one per beat, last frame")
    sheets.append((f"reel: {name}", sheet))
    shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(out_dir, f, sheets):
    p = os.path.join(out_dir, "report.html")

    def rows(items, cls):
        if not items:
            return '<p class="ok">none</p>'
        return "".join(
            f'<div class="{cls}"><b>{html.escape(c)}</b> {html.escape(m)}</div>'
            for c, m in items)

    imgs = "".join(
        f'<h3>{html.escape(t)}</h3><img src="{html.escape(os.path.relpath(s, out_dir))}">'
        for t, s in sheets)

    with open(p, "w") as fh:
        fh.write(f"""<!doctype html><meta charset="utf-8">
<title>Carousel-Bot render QA</title>
<style>
body{{background:#0a0a0d;color:#f4f5f7;font:15px/1.55 -apple-system,Segoe UI,sans-serif;
max-width:1100px;margin:40px auto;padding:0 24px}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:34px;border-bottom:1px solid #26262e;padding-bottom:6px}}
h3{{font-size:13px;color:#9a9ca6;font-weight:600;margin:22px 0 6px}}
img{{width:100%;border-radius:6px;border:1px solid #26262e}}
.fail{{background:#2a1416;border-left:3px solid #ff6b6b;padding:7px 11px;margin:5px 0;border-radius:0 4px 4px 0}}
.warn{{background:#2a2416;border-left:3px solid #e8c15e;padding:7px 11px;margin:5px 0;border-radius:0 4px 4px 0}}
.note{{color:#9a9ca6;padding:3px 11px}} .ok{{color:#6ea8ff}}
b{{color:#f4f5f7;font-weight:600;margin-right:8px}}
</style>
<h1>Carousel-Bot render QA</h1>
<h2>Hard failures ({len(f.hard)})</h2>{rows(f.hard,'fail')}
<h2>Design findings ({len(f.soft)})</h2>{rows(f.soft,'warn')}
<h2>Notes</h2>{rows(f.notes,'note')}
<h2>Look at the output</h2>{imgs}
""")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-reel", action="store_true")
    ap.add_argument("--all-reels", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--audio-dir", default=None)
    args = ap.parse_args()

    out = args.out
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)

    f, sheets = Findings(), []

    for name, carousel in fx.format_cases():
        check_carousel(name, carousel, out, f, sheets)
    for name, carousel in fx.HOSTILE:
        check_carousel(name, carousel, out, f, sheets)

    if not args.no_reel:
        audio_dir = args.audio_dir
        if audio_dir is None:
            import reel_engine as _re
            audio_dir = _re.AUDIO_DIR
        cases = fx.REALISTIC if args.all_reels else [fx.GOOGLE]
        for c in cases:
            check_reel(c["niche"].split("/")[0].replace(" ", "-").lower(),
                       c, out, f, sheets, audio_dir)
        check_reel("missing-fields", fx.MISSING_FIELDS, out, f, sheets, audio_dir)

    f.settle()
    report = write_report(out, f, sheets)

    print()
    if f.hard:
        print(f"HARD FAILURES ({len(f.hard)}) -- these break the build")
        for c, m in f.hard:
            print(f"  x {c}: {m}")
    if f.soft:
        print(f"\nDESIGN FINDINGS ({len(f.soft)}){' -- failing, --strict' if args.strict else ''}")
        for c, m in f.soft:
            print(f"  ! {c}: {m}")
    if f.notes:
        print("\nNOTES")
        for c, m in f.notes:
            print(f"  - {c}: {m}")
    print(f"\nReport: {report}")

    if f.hard or (args.strict and f.soft):
        sys.exit(1)
    print("No hard failures.")


if __name__ == "__main__":
    main()
