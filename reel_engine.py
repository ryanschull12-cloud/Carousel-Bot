"""
reel_engine.py — renders a carousel's reel_beats into a 1080x1920 Instagram Reel.

WHY THIS EXISTS (2026-08-08): carousels were reaching 2-3 accounts per post. Carousels
are distributed to followers plus hashtag search; with almost no followers that is
almost nobody. Reels are the only format Instagram pushes into cold Explore/Reels
feeds, so this renders the same day's content as a vertical video instead.

NOT A CAROUSEL CONVERTER. The first attempt padded the 1080x1350 slides into a 9:16
frame and cut between them -- it looked like a PDF with a timer. This composes natively
at 1080x1920 with its own layout, type scale and motion. It shares carousel_engine.py's
palette, fonts and badge language so the grid still reads as one account, but nothing
else is reused.

INSTAGRAM SAFE ZONES: the Reels UI covers roughly the bottom 320px (caption, username,
action buttons) and ~180px down the right edge. All copy is anchored inside
SAFE_TOP..SAFE_BOT and the follow pill sits at y=1500, well clear of the overlay. Do not
move content below y=1600 -- it will be invisible in the app even though it looks fine
in a preview.

BEAT TYPES, each with its own layout and motion:
  hook  - serif, word-by-word cascade. The only thing deciding whether the rest is watched.
  stat  - a single number at 380px counting up from zero, rule wiping beneath it.
          This is the thumb-stopper; every reel should have exactly one.
  body  - sans bold, left aligned, accent block hugging the longest line.
  cta   - background wipes to the topic's dark colour, keyword lands in cream.

AUDIO: tracks are read from assets/audio/*.mp3 and rotated by date so consecutive reels
do not share one. API-published reels CANNOT use Instagram's licensed trending audio
(Meta: "Music tagging is only available for original audio"), so the track is mixed into
the MP4 itself. If assets/audio/ is empty the reel renders with a silent AAC track rather
than failing -- silent is worse but shipping beats blocking.
"""
import os, math, random, re
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 24
MARGIN = 96
SYS = "/usr/share/fonts/truetype/liberation"

# Where apt drops fonts-inter, plus an override so the family can be pointed at an
# unpacked copy without root when testing locally.
INTER_DIRS = [
    os.environ.get("INTER_FONT_DIR", ""),
    "/usr/share/fonts/opentype/inter",
    "/usr/share/fonts/truetype/inter",
]

def _family():
    """Prefer Inter, fall back to Liberation Sans.

    Inter is installed by the workflows with `apt-get install fonts-inter` -- a
    Debian package, the same mechanism already used for ffmpeg, not an uploaded
    font file. Chosen for a larger x-height and more open apertures, which is what
    survives being watched at roughly 400px on a phone, and for having nine weights
    where Liberation has two.

    The fallback is the point of doing it this way. If the apt step ever fails on a
    runner, the reel renders in Liberation and posts exactly as it did before,
    rather than a scheduled post dying on a missing font file. Degrading is
    allowed; stopping is not.
    """
    for d in INTER_DIRS:
        if d and os.path.exists(os.path.join(d, "Inter-Regular.otf")):
            return (f"{d}/Inter-Bold.otf", f"{d}/Inter-Regular.otf",
                    f"{d}/Inter-SemiBold.otf", "Inter")
    return (f"{SYS}/LiberationSans-Bold.ttf", f"{SYS}/LiberationSans-Regular.ttf",
            f"{SYS}/LiberationSans-Bold.ttf", "Liberation Sans")

F_SANS, F_SANSR, F_SEMI, FONT_FAMILY = _family()
F_SERIF = f"{SYS}/LiberationSerif-Bold.ttf"   # kept for callers; unused since the rebrand

# --- theme -------------------------------------------------------------------
# Rebranded 2026-08-09 to the site palette, matching carousel_engine.py.
# Until now the reels rendered on cream (240,239,234) with mint/salmon/lilac topic
# colours while the carousels had already moved to near-black with tonal blues.
# On a profile grid the two formats read as two different accounts, which wastes
# the only thing a small account has going for it: looking deliberate.
BG        = (10, 10, 13)      # --bg
BG_ALT    = (13, 14, 18)      # --bg-alt, bottom of the vertical gradient
BG_RAISED = (21, 22, 28)      # --bg-raised, body panels
INK       = (244, 245, 247)   # --ink
DIM       = (154, 156, 166)   # --dim

HANDLE = "@rd.marketing0"

# Keys unchanged -- colors_for() matches on substring and the content brain's
# niche strings have not moved.
TOPIC = {
 "google ads": {"accent": (110, 168, 255), "deep": (30, 52, 92), "veil": (22, 30, 46)},
 "meta":       {"accent": (146, 154, 255), "deep": (44, 46, 96), "veil": (27, 28, 48)},
 "instagram":  {"accent": (146, 154, 255), "deep": (44, 46, 96), "veil": (27, 28, 48)},
 "email":      {"accent": (94, 199, 240),  "deep": (24, 62, 84), "veil": (19, 33, 43)},
}
DEF = {"accent": (110, 168, 255), "deep": (30, 52, 92), "veil": (22, 30, 46)}

def colors_for(n):
    n=(n or "").lower()
    for k,v in TOPIC.items():
        if k in n: return v
    return DEF

F=lambda p,s: ImageFont.truetype(p,s)
ease=lambda t: 1-(1-t)**3
def clamp(v,a=0.0,b=1.0): return max(a,min(b,v))

def split_overlong(d,w,f,mw):
    """Break a token wider than the line. Same failure as carousel_engine had:
    an unbreakable string was returned as its own line and drawn off-canvas.
    Added 2026-08-09."""
    if d.textlength(w,font=f)<=mw: return [w]
    for sep in ("-","/","@","_",".",":",";","="):
        if sep in w[1:-1]:
            parts,out,cur=w.split(sep),[],""
            for i,p in enumerate(parts):
                piece=p+(sep if i<len(parts)-1 else "")
                if cur and d.textlength(cur+piece,font=f)>mw: out.append(cur); cur=piece
                else: cur+=piece
            if cur: out.append(cur)
            if all(d.textlength(o,font=f)<=mw for o in out): return out
    out,cur=[],""
    for ch in w:
        if cur and d.textlength(cur+ch,font=f)>mw: out.append(cur); cur=ch
        else: cur+=ch
    if cur: out.append(cur)
    return out

def wrap(d,t,f,mw):
    out,cur=[],""
    for w in t.split():
        for piece in split_overlong(d,w,f,mw):
            s=(cur+" "+piece).strip()
            if d.textlength(s,font=f)<=mw: cur=s
            else:
                if cur: out.append(cur)
                cur=piece
    if cur: out.append(cur)
    return out

def fit(d,t,path,start,mn,mw,maxl):
    s=start
    while s>mn:
        f=F(path,s); ls=wrap(d,t,f,mw)
        if len(ls)<=maxl: return f,ls
        s-=4
    f=F(path,mn); return f,wrap(d,t,f,mw)

def layer(text,fnt,color):
    d0=ImageDraw.Draw(Image.new("RGB",(4,4)))
    bb=d0.textbbox((0,0),text,font=fnt)
    im=Image.new("RGBA",(bb[2]-bb[0]+10,bb[3]-bb[1]+22),(0,0,0,0))
    ImageDraw.Draw(im).text((5-bb[0],11-bb[1]),text,font=fnt,fill=color+(255,))
    return im

def layer_tracked(text,fnt,color,track=0.0):
    """layer() with letter-spacing. Pillow has no tracking, so it is set one
    character at a time, which loses kerning pairs -- fine at label sizes, and the
    reason the big hook is left at zero where kerning actually shows."""
    if not track: return layer(text,fnt,color)
    d0=ImageDraw.Draw(Image.new("RGB",(4,4)))
    adv=[fnt.getlength(c) for c in text]
    w=int(sum(adv)+track*max(0,len(text)-1))+12
    bb=d0.textbbox((0,0),text or "x",font=fnt)
    im=Image.new("RGBA",(max(w,4),bb[3]-bb[1]+22),(0,0,0,0)); d=ImageDraw.Draw(im)
    x=5.0
    for i,ch in enumerate(text):
        d.text((x,11-bb[1]),ch,font=fnt,fill=color+(255,))
        x+=adv[i]+track
    return im

def fade(lay,a):
    if a>=255: return lay
    l=lay.copy(); l.putalpha(l.getchannel("A").point(lambda v: v*a//255)); return l


# --- background --------------------------------------------------------------
TAU = 2*math.pi

def base_gradient():
    """Vertical BG -> BG_ALT wash. Drawn once and copied per frame."""
    im=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(im)
    for y in range(H):
        k=y/(H-1)
        d.line([(0,y),(W,y)],fill=tuple(int(BG[i]+(BG_ALT[i]-BG[i])*k) for i in range(3)))
    return im

def node_field(seed=7, count=46):
    """The constellation from the site's hero canvas, as drifting nodes.

    Each node orbits its home position on a sine with a WHOLE number of cycles
    across the clip. That is the whole trick behind the seamless loop: at t=1
    every node is exactly where it was at t=0, so the last frame lands back on the
    first and Instagram's replay is invisible. Loops compound watch time, which is
    the single strongest ranking signal available to a faceless account.
    """
    rng=random.Random(seed)
    out=[]
    for _ in range(count):
        out.append({
            "x": rng.uniform(-40, W+40),
            "y": rng.uniform(-40, H+40),
            "ax": rng.uniform(8, 26), "ay": rng.uniform(8, 26),
            "kx": rng.choice((1,1,2)), "ky": rng.choice((1,2,2)),
            "px": rng.random(), "py": rng.random(),
            "hot": rng.random() < 0.13,
        })
    return out

LINK_DIST = 300

def draw_constellation(im, c, t, nodes):
    d=ImageDraw.Draw(im)
    pts=[(n["x"]+n["ax"]*math.sin(TAU*(n["kx"]*t+n["px"])),
          n["y"]+n["ay"]*math.cos(TAU*(n["ky"]*t+n["py"])),
          n["hot"]) for n in nodes]
    edge=tuple(int(BG[i]+(c["accent"][i]-BG[i])*0.16) for i in range(3))
    for i in range(len(pts)):
        xi,yi,_=pts[i]
        for j in range(i+1,len(pts)):
            xj,yj,_=pts[j]
            dx,dy=xi-xj,yi-yj
            dsq=dx*dx+dy*dy
            if dsq<LINK_DIST*LINK_DIST:
                # fade the link out as the pair separates, so the field breathes
                a=1.0-(dsq**0.5)/LINK_DIST
                col=tuple(int(BG[k]+(edge[k]-BG[k])*a) for k in range(3))
                d.line([(xi,yi),(xj,yj)],fill=col,width=1)
    for x,y,hot in pts:
        r=3 if hot else 2
        d.ellipse([x-r,y-r,x+r,y+r],fill=c["accent"] if hot else (58,60,70))

def chrome(im,c,badge):
    """Badge, handle and follow pill. Drawn last on every frame so nothing can
    cover them, and always in the same colours -- the old build swapped to a light
    treatment on the CTA and the two versions never quite matched."""
    d=ImageDraw.Draw(im)
    fb=F(F_SANS,32); tw=d.textlength(badge,font=fb)
    d.rounded_rectangle([MARGIN,104,MARGIN+tw+56,104+66],radius=33,fill=c["accent"])
    d.text((MARGIN+28,104+17),badge,font=fb,fill=BG)
    fh=F(F_SANSR,30)
    d.text((W-MARGIN-40-d.textlength(HANDLE,font=fh),120),HANDLE,font=fh,fill=DIM)
    fp=F(F_SANS,30); p="Follow for more"; pw=d.textlength(p,font=fp)
    d.rounded_rectangle([MARGIN,1500,MARGIN+pw+68,1500+64],radius=32,outline=DIM,width=3)
    d.text((MARGIN+34,1518),p,font=fp,fill=INK)
    return im

SAFE_TOP, SAFE_BOT = 250, 1430   # bottom ~320px is covered by IG caption/buttons
def anchor(blockh):
    """Optically centre a block in the safe area, biased slightly high."""
    return int(SAFE_TOP + max(0,(SAFE_BOT - SAFE_TOP - blockh)) * 0.40)


# --- timing -------------------------------------------------------------------
# Beat durations used to be hardcoded: 2.9s hook, 2.8s stat, 2.2s per body line,
# 3.2s CTA, regardless of how much copy was on screen. Measured against Netflix's
# 20 characters-per-second reading ceiling, six of twenty-one beats across the
# three niches were too short to physically finish -- the worst was a 58-character
# stat label with 2.8s to read it, needing 3.25s -- while the CTA sat for 3.2
# seconds displaying five characters. The reel was simultaneously too fast to read
# and wasting two and a half seconds.
#
# Duration is now derived from the copy. Netflix allows 20 CPS for adult content
# and 17 for children's; BBC uses ~15 because broadcast audiences include elderly
# and low-literacy viewers. This audience is fluent adults choosing to watch on a
# phone, so 20 is the right ceiling -- but it IS a ceiling, not a target, which is
# why ORIENT is added on top: after the frame changes a viewer needs a moment to
# find the new copy before reading starts.
#
# BEAT_MAX is not a stylistic choice. Static shots past about four seconds are
# where viewers scroll. The drifting constellation buys some slack -- nothing here
# is ever truly still -- but not unlimited slack.
CPS        = 20.0   # characters per second, reading ceiling
ORIENT     = 0.35   # seconds to find the new copy after a cut
BEAT_MIN   = 1.6
BEAT_MAX   = 4.0
REEL_MAX_S = 24.0   # past this, drop a beat rather than speed any of them up

def read_time(text, cps=CPS, lo=BEAT_MIN, hi=BEAT_MAX, orient=ORIENT):
    return round(clamp(orient + len(text or "")/cps, lo, hi), 2)


class Beat:
    def __init__(self,kind,text,dur,sub=None,num=None,pair=None):
        self.kind,self.text,self.dur,self.sub,self.num=kind,text,dur,sub,num
        self.pair=pair   # ("€45/lead", "€15/lead") for the proof beat


def number_parts(word):
    """'30%' -> ('', '30', '%'); '€400' -> ('€', '400', ''); 'Gmail' -> (w, None, '')."""
    m=re.match(r"^(\D*?)(\d+)(\D*)$", word)
    return (m.group(1),m.group(2),m.group(3)) if m else (word,None,"")


def fit_hook(d,text,emph,maxw,start,mn,maxl):
    """Wrap the hook measuring each word in the weight it will actually be set in.

    Bold is wider than Regular, so wrapping the whole line in one font and then
    setting the figure in Bold pushed the longest line past the margin. Returns
    (regular, bold, lines-as-word-lists)."""
    size=start
    while True:
        fr_=F(F_SANSR,size); fb=F(F_SANS,size)
        sp=d.textlength(" ",font=fr_)
        def wid(ws):
            t=0.0
            for i,x in enumerate(ws):
                t+=d.textlength(x,font=fb if (emph and x.strip(".,!?:;")==emph) else fr_)
                if i: t+=sp
            return t
        lines,cur=[],[]
        for w in text.split():
            if cur and wid(cur+[w])>maxw:
                lines.append(cur); cur=[w]
            else:
                cur.append(w)
        if cur: lines.append(cur)
        if (len(lines)<=maxl and all(wid(l)<=maxw for l in lines)) or size<=mn:
            return fr_,fb,lines
        size-=4


def emphasis_token(text):
    """The one word in the hook worth a highlight: a figure. The content rules
    require a number, a named setting or a concrete claim in every hook, and the
    number is the part the eye should land on first."""
    for w in (text or "").split():
        if any(ch.isdigit() for ch in w) or "%" in w or "€" in w:
            return w.strip(".,!?:;")
    return None


# Letter-spacing as a fraction of size, so it scales with the type. Small copy
# opens up; the display hook stays at zero, where added tracking just reads loose
# and where losing kerning pairs would actually show.
LABEL_TRACK = 0.02

# The "before" bar on the proof beat: dim enough to read as the past, light enough
# to actually be seen against the background.
BAR_WAS = (92, 95, 108)

# 0.55s to resolve the counting figure. Long enough to register as motion, short
# enough to be finished well before the scroll decision lands.
# 19 frames = 0.79s (was 13/0.55s, slowed 2026-08-09 at Ryan's call after
# watching the renders: the resolves read as UI-snappy rather than as video
# weight. Entrances across every beat moved from the 200-300ms Material band
# to 330-420ms in the same pass. Hypothesis until reel scores land -- if
# retention drops at the new pacing, this is the constant to walk back.
TICK_FRAMES = 19.0

TAIL_S = 0.6   # crossfade back to the hook so the loop closes

def push_in(fr, p, amount=0.022):
    """Slow camera move across a beat (2026-08-09). Content-only -- chrome is
    drawn after this, so the UI stays pinned while the frame drifts. The push
    resets at every hard cut, where the content change masks it, and the hook
    starts at exactly 1.0 so frame 0 and the loop tail's target still match.
    2.2%% over a 2-4s beat is sub-pixel per frame: it reads as production
    camera drift, not as a zoom effect. Encode moved to PNG intermediates and
    crf 18 in the same change so H.264 has the bits to keep the moving type
    sharp -- the risk the research brief flags for exactly this feature."""
    z = 1.0 + amount * p
    zw, zh = int(W * z), int(H * z)
    big = fr.resize((zw, zh), Image.LANCZOS)
    x, y = (zw - W) // 2, (zh - H) // 2
    return big.crop((x, y, x + W, y + H))


def render(niche,beats,outdir,badge):
    """Frames for one reel.

    TYPE (2026-08-09): all sans. The hook used to be set in Liberation Serif while
    the site and every other surface are sans; on a 1080-wide frame at arm's length
    the serif read as a different brand rather than as emphasis. Hierarchy now comes
    from size, weight and the accent colour, which survive compression better than
    stroke contrast does.

    MOTION: the hook is FULLY SET ON FRAME 0. The old build cascaded it in word by
    word over about 1.1s; measured, frame 0 carried 26% of the copy it ended on.
    Roughly half of viewers leave inside 3s and the continue-or-scroll decision
    lands around 1.7s, so an entrance animation spends the entire decision window
    withholding the one thing that decision is based on. Movement now comes from
    the drifting constellation behind the type, the counting stat, the body panels
    and the CTA wipe -- none of which delay comprehension.

    LOOP: every frame is a function of t = frame/total, and the node field runs a
    whole number of cycles over that range, so t=1 reproduces t=0. A short tail
    crossfades the CTA back to the hook, landing the final frame on the first.
    """
    c=colors_for(niche); os.makedirs(outdir,exist_ok=True)
    probe=ImageDraw.Draw(Image.new("RGB",(4,4))); mw=W-2*MARGIN
    grad=base_gradient(); nodes=node_field()

    counts=[int(b.dur*FPS) for b in beats]
    hook=next((b for b in beats if b.kind=="hook"), None)
    tail=int(TAIL_S*FPS) if hook else 0
    total=sum(counts)+tail

    # ---- layout, computed once ----
    L={}
    if hook:
        emph=emphasis_token(hook.text)
        f_reg,f_bold,ls=fit_hook(probe,hook.text,emph,mw,150,84,4)
        L["hook"]=(f_reg,f_bold,ls,int(f_reg.size*1.20),emph)
        L["hook_y"]=anchor(int(f_reg.size*1.20)*len(ls))

    def bg(t):
        fr=grad.copy(); draw_constellation(fr,c,t,nodes); return fr

    def paint_hook(fr, prog=1.0, fi=0):
        """Regular sentence, bold accent figure, no highlight block.

        The block was clean but it fenced the number off from the sentence; weight
        and colour keep it inside the line while still being the first thing the
        eye lands on. The figure also counts up over 0.55s -- a counting number is
        the cheapest genuine pattern interrupt there is, and putting it in the hook
        rather than only in the stat beat lands that interrupt inside the 1.7s
        window where the scroll decision is actually made. The sentence around it
        is fully set on frame 0 the whole time, so nothing is being withheld.

        The digits are right-aligned into a slot sized for the FINAL value, so the
        line never reflows and the suffix never shifts while it counts -- the way
        an odometer reads rather than a jittering label.
        """
        f_reg,f_bold,ls,lh,emph=L["hook"]; y0=L["hook_y"]
        d=ImageDraw.Draw(fr)
        d.rectangle([MARGIN,y0-46,MARGIN+150,y0-38],fill=c["accent"])
        for li,line in enumerate(ls):
            y=y0+li*lh; x=MARGIN
            for w in line:
                if emph and w.strip(".,!?:;")==emph:
                    if "hook_emph_box" not in L:
                        ww=d.textlength(w,font=f_bold)
                        L["hook_emph_box"]=(x, x+ww, y+int(f_bold.size*1.06))
                    pre,dig,suf=number_parts(w)
                    if dig is not None:
                        wpre=d.textlength(pre,font=f_bold)
                        wdig=d.textlength(dig,font=f_bold)
                        shown=str(int(round(int(dig)*prog)))
                        d.text((x,y),pre,font=f_bold,fill=c["accent"])
                        d.text((x+wpre+wdig-d.textlength(shown,font=f_bold),y),
                               shown,font=f_bold,fill=c["accent"])
                        d.text((x+wpre+wdig,y),suf,font=f_bold,fill=c["accent"])
                        x+=wpre+wdig+d.textlength(suf,font=f_bold)
                    else:
                        d.text((x,y),w,font=f_bold,fill=c["accent"])
                        x+=d.textlength(w,font=f_bold)
                else:
                    d.text((x,y),w,font=f_reg,fill=INK)
                    x+=d.textlength(w,font=f_reg)
                x+=d.textlength(" ",font=f_reg)
        # Reinforcement, not reveal (2026-08-09): a rule sweeps under the accent
        # token starting ~0.4s in, well after the whole hook is readable. Motion
        # lands inside the 1.7s decision window without withholding a word --
        # the faceless-reel research consistently ties retention to text motion
        # that reinforces what is already on screen.
        if fi > 10 and L.get("hook_emph_box"):
            ex0, ex1, ey = L["hook_emph_box"]
            sw = ease(clamp((fi - 10) / 14.0))
            if sw > 0:
                d.rectangle([ex0, ey, ex0 + (ex1 - ex0) * sw, ey + 7], fill=c["accent"])

    def hook_frame(t):
        fr=bg(t); paint_hook(fr,0.0); return chrome(fr,c,badge)

    def paint_stat(fr,b,fi):
        d=ImageDraw.Draw(fr)
        fnum=F(F_SANS,360)
        labf,labls=fit(probe,b.sub,F_SANS,72,46,mw,3)
        # Resolve in ~0.55s. A counting number is the cheapest genuine pattern
        # interrupt available, but only while it is still counting -- drag it out
        # and it stops being a hook and starts being a delay.
        p=ease(clamp(fi/19.0))
        s=f"{int(round(b.num*p))}%"
        nl=layer(s,fnum,c["accent"])
        y0=anchor(nl.height+180)
        fr.paste(nl,(MARGIN,y0-40),nl)
        yy=y0-40+nl.height+8
        d.rectangle([MARGIN,yy,MARGIN+int(mw*ease(clamp((fi-13)/16.0))),yy+8],fill=c["accent"])
        for li,line in enumerate(labls):
            # 1 frame of stagger is ~42ms, inside the 40-60ms window where each
            # unit is legible before the next lands. It used to be 3 frames, slow
            # enough to register as an effect rather than as reading.
            q=ease(clamp((fi-19-li*2)/11.0))
            if q>0:
                lay=layer_tracked(line,labf,INK,LABEL_TRACK*labf.size)
                fr.paste(fade(lay,int(255*q)),(MARGIN,yy+38+li*int(labf.size*1.24)+int(22*(1-q))),
                         fade(lay,int(255*q)))

    def paint_body(fr,b,fi):
        d=ImageDraw.Draw(fr)
        # SemiBold, not Bold. Inter Bold at 132px is heavier than Liberation Bold
        # and closes up the counters; SemiBold matches the old weight impression.
        f,ls=fit(probe,b.text,F_SEMI,132,70,mw-72,4); lh=int(f.size*1.26)
        lays=[layer(l,f,INK) for l in ls]
        blockh=lh*len(lays)
        # Clamp the panel to the safe margin. Inter sets wider, and an unclamped
        # hug-the-longest-line panel ran within a few px of the right edge.
        blockw=min(max(l.width for l in lays)+72, W-MARGIN+34)
        y0=anchor(blockh)
        grow=ease(clamp(fi/10.0))
        bw=int(blockw*grow)
        if bw>0:
            d.rounded_rectangle([MARGIN-34,y0-30,MARGIN-34+bw,y0+blockh+26],radius=10,fill=BG_RAISED)
            d.rectangle([MARGIN-34,y0-30,MARGIN-28,y0+blockh+26],fill=c["accent"])
        for li,lay in enumerate(lays):
            p=ease(clamp((fi-li*2)/10.0))
            if p>0:
                fr.paste(fade(lay,int(255*p)),(MARGIN+int(22*(1-p)),y0+li*lh),fade(lay,int(255*p)))

    def paint_proof(fr,b,fi):
        """Before and after, with a directional arrow and bars in proportion.

        Added 2026-08-09. The carousel's before-after format already carries real
        figures -- "€45/lead" to "€15/lead" -- and the reel was throwing them away.
        This is the only frame in the reel that looks like evidence rather than
        advice, which makes it the one worth screenshotting, and saves are the
        second most weighted signal after sends.

        The bars carry the argument. Two numbers alone ask the viewer to do
        arithmetic while the frame is moving; two bars of obviously different
        length do the arithmetic for them before either figure has been read. The
        after figure counts down (or up) from the before figure rather than
        appearing, so the change is something they watch happen.
        """
        before,after=b.pair
        d=ImageDraw.Draw(fr)
        S_BEF,S_AFT,S_LAB = 112, 188, 44
        f_bef=F(F_SANS,S_BEF); f_aft=F(F_SANS,S_AFT); f_lab=F(F_SANSR,S_LAB)
        bp,bd,bs=number_parts(before); ap,ad,asf=number_parts(after)
        bv=int(bd) if bd else None; av=int(ad) if ad else None

        GAP_ARROW=96
        h_lab=(S_LAB+30) if b.sub else 0
        blockh=h_lab+int(S_BEF*1.10)+GAP_ARROW+int(S_AFT*1.05)
        y=anchor(blockh)

        if b.sub:
            lay=layer_tracked(b.sub,f_lab,DIM,LABEL_TRACK*S_LAB)
            fr.paste(lay,(MARGIN,y),lay)
            y+=h_lab

        bar_x=MARGIN+430; bar_w=W-MARGIN-bar_x
        peak=max(bv or 1, av or 1)

        def bar(cy,frac,grow,col,thick):
            wpx=int(bar_w*frac*grow)
            if wpx>4:
                d.rounded_rectangle([bar_x,cy-thick//2,bar_x+wpx,cy+thick//2],
                                    radius=thick//3,fill=col)

        # before -- dim, the number they are leaving behind
        d.text((MARGIN,y),before,font=f_bef,fill=DIM)
        if bv is not None:
            # The "before" bar has to recede without disappearing. At (52,54,64)
            # it measured 1.65:1 against the background -- the element carrying
            # half the comparison was almost invisible.
            bar(y+int(S_BEF*0.55),bv/peak,ease(clamp(fi/9.0)),BAR_WAS,42)
        y_arrow=y+int(S_BEF*1.10)

        # the arrow -- direction is the claim, so it is drawn rather than typed
        q=ease(clamp((fi-11)/12.0))
        if q>0:
            down = (av is not None and bv is not None and av<bv)
            cx=MARGIN+40; top=y_arrow+8; span=GAP_ARROW-26
            ln=int(span*q)
            d.line([(cx,top),(cx,top+ln)] if down else [(cx,top+span),(cx,top+span-ln)],
                   fill=c["accent"],width=8)
            head=int(24*q)
            if head>3:
                tip = top+ln if down else top+span-ln
                pts=([(cx,tip+head),(cx-head,tip),(cx+head,tip)] if down
                     else [(cx,tip-head),(cx-head,tip),(cx+head,tip)])
                d.polygon(pts,fill=c["accent"])

        # after -- accent, larger, counting across from the old figure
        y2=y_arrow+GAP_ARROW
        p=ease(clamp((fi-14)/18.0))
        shown=after
        if av is not None and bv is not None:
            shown=f"{ap}{int(round(bv+(av-bv)*p))}{asf}"
        d.text((MARGIN,y2),shown,font=f_aft,fill=c["accent"])
        if av is not None:
            bar(y2+int(S_AFT*0.55),av/peak,ease(clamp((fi-9)/11.0)),c["accent"],58)

    def paint_cta(fr,b,fi):
        f,ls=fit(probe,b.text,F_SANS,200,110,mw,2); lh=int(f.size*1.16)
        sf,sls=fit(probe,b.sub or "",F_SANS,60,42,mw,3); slh=int(sf.size*1.26)
        ay=anchor(lh*len(ls)+slh*len(sls)+34)
        p=ease(clamp(fi/16.0))
        cut=int(H*p)
        if cut>0:
            veil=Image.new("RGB",(W,cut),c["deep"])
            fr.paste(Image.blend(fr.crop((0,H-cut,W,H)),veil,0.90),(0,H-cut))
        # The keyword used to wait for the wipe to be 55% done and then start a
        # 10-frame fade, so the CTA opened with about half a second of almost empty
        # screen -- dead air immediately after the last instruction, in a reel that
        # is only fifteen seconds long. It now rides in with the wipe, the same way
        # body copy rides in with its panel.
        if p>0.20:
            q=ease(clamp((fi-6)/12.0))
            for li,line in enumerate(ls):
                lay=layer(line,f,c["accent"])
                fr.paste(fade(lay,int(255*q)),(MARGIN,ay+li*lh+int(26*(1-q))),fade(lay,int(255*q)))
            for li,line in enumerate(sls):
                r=ease(clamp((fi-15-li*2)/11.0))
                if r>0:
                    lay=layer_tracked(line,sf,INK,LABEL_TRACK*sf.size)
                    fr.paste(fade(lay,int(255*r)),(MARGIN,ay+len(ls)*lh+34+li*slh),fade(lay,int(255*r)))

    def paint_brand(fr, fi):
        """Typographic end-card (2026-08-09, Ryan's ask). No logo asset exists
        in the repo, so the wordmark is set live in the same type system as
        everything else: R&D in bold accent, MARKETING tracked out in ink, the
        site line in dim. Centered deliberately -- every other beat is
        left-aligned copy, so the one centered lockup reads as a seal, not a
        sentence. It matters most off-Instagram: the same MP4 goes to YouTube
        Shorts and TikTok, where nothing else on screen says who made it.
        Sits BEFORE the loop tail, so the crossfade back to the hook still
        lands the final frame on the first."""
        d=ImageDraw.Draw(fr)
        f_rd=F(F_SANS,170); f_mk=F(F_SANSR,58); f_site=F(F_SANSR,34)
        w_rd=d.textlength("R&D",font=f_rd)
        blockh=int(170*1.02)+26+8+26+58+40+34
        y0=anchor(blockh)
        p1=ease(clamp(fi/10.0))
        if p1>0:
            lay=layer("R&D",f_rd,c["accent"])
            fr.paste(fade(lay,int(255*p1)),(int((W-w_rd)/2),y0+int(20*(1-p1))),fade(lay,int(255*p1)))
        y=y0+int(170*1.02)+26
        sw=ease(clamp((fi-8)/12.0))
        if sw>0:
            half=int(150*sw)
            d.rectangle([W//2-half,y,W//2+half,y+8],fill=c["accent"])
        y+=8+26
        p2=ease(clamp((fi-14)/11.0))
        if p2>0:
            lay=layer_tracked("MARKETING",f_mk,INK,0.32*58)
            fr.paste(fade(lay,int(255*p2)),(int((W-lay.width)/2),y+int(16*(1-p2))),fade(lay,int(255*p2)))
        y+=58+40
        p3=ease(clamp((fi-22)/11.0))
        if p3>0:
            lay=layer("marketing-rd.com",f_site,DIM)
            fr.paste(fade(lay,int(255*p3)),(int((W-lay.width)/2),y),fade(lay,int(255*p3)))

    # ---- frames ----
    n=0
    body_i=0
    for bi,b in enumerate(beats):
        for fi in range(counts[bi]):
            t=n/total
            fr=bg(t)
            if b.kind=="hook":   paint_hook(fr,ease(clamp(fi/TICK_FRAMES)),fi)
            elif b.kind=="stat": paint_stat(fr,b,fi)
            elif b.kind=="proof":paint_proof(fr,b,fi)
            elif b.kind=="cta":  paint_cta(fr,b,fi)
            elif b.kind=="brand":paint_brand(fr,fi)
            else:                paint_body(fr,b,fi)
            fr=push_in(fr, fi/max(counts[bi]-1,1))
            chrome(fr,c,badge)
            # PNG, not JPEG: these are intermediates for x264. Saving them at
            # JPEG q88 was a second lossy pass before the encoder's own -- the
            # frames arrived pre-softened. (2026-08-09)
            fr.save(f"{outdir}/f{n:05d}.png"); n+=1

    # ---- tail: return to the hook so the loop closes ----
    if tail:
        last=Image.open(f"{outdir}/f{n-1:05d}.png").convert("RGB")
        for i in range(tail):
            t=n/total
            fr=Image.blend(last,hook_frame(t),ease((i+1)/tail))
            fr.save(f"{outdir}/f{n:05d}.png"); n+=1

    return n,n/FPS


# ---------------------------------------------------------------------------
# Beat construction from the content brain's reel_beats block
# ---------------------------------------------------------------------------

def proof_pair(carousel):
    """Find a before/after to build the proof beat from.

    Prefers an explicit reel_beats.proof block. Falls back to the first body slide
    carrying before/after, which the before-after carousel format already produces
    and which the reel has been discarding since it was written."""
    rb = carousel.get("reel_beats") or {}
    p = rb.get("proof") or {}
    if p.get("before") and p.get("after"):
        return (str(p["before"]), str(p["after"]), (p.get("label") or "").strip())
    for body in carousel.get("body_slides") or []:
        if isinstance(body, dict) and body.get("before") and body.get("after"):
            return (str(body["before"]), str(body["after"]), "")
    return None


def trim_to_budget(beats, budget=REEL_MAX_S):
    """Keep the reel inside its budget by dropping beats, never by speeding them up.

    Every duration here is already the minimum a person needs to read the copy, so
    compressing to hit a target would just produce a reel nobody can follow --
    which is the failure this whole model exists to remove. Body beats go first and
    from the end, since the content brain front-loads the strongest action."""
    while sum(b.dur for b in beats) > budget:
        idx = max((i for i, b in enumerate(beats) if b.kind == "body"), default=None)
        if idx is None:
            break
        beats.pop(idx)
    return beats


def beats_from_carousel(carousel):
    """Turn a carousel dict's reel_beats into Beat objects.

    Falls back to slicing the carousel copy if reel_beats is missing, so a manifest
    generated before the content-brain change still renders something rather than
    crashing the whole evening run. The fallback reads as checklist items, not video
    lines -- it is a safety net, not the intended path.
    """
    rb = carousel.get("reel_beats") or {}
    if rb.get("hook") and rb.get("body"):
        # The hook is read at a slightly higher rate and floored a little tighter
        # than the body. Copy that is marginally too long to finish in one pass is
        # what earns the replay, and the loop tail brings the hook back around for
        # a second look anyway. That trade is wrong for the body: a viewer who
        # cannot finish an instruction has not been teased, they have been failed.
        out = [Beat("hook", rb["hook"], read_time(rb["hook"], cps=22.0, lo=2.0, hi=3.4))]
        if rb.get("stat_number") is not None and rb.get("stat_label"):
            # 0.55s of that is the number counting up before the label matters.
            out.append(Beat("stat", None,
                            read_time(rb["stat_label"], lo=2.2, hi=4.2, orient=0.90),
                            sub=rb["stat_label"], num=int(rb["stat_number"])))
        for line in rb["body"][:4]:
            if isinstance(line, dict):
                line = (line.get("text") or "").strip()
            if line:
                out.append(Beat("body", line, read_time(line)))
        pr = proof_pair(carousel)
        if pr:
            out.append(Beat("proof", None,
                            read_time(pr[2], lo=2.4, hi=3.6, orient=1.60),
                            sub=pr[2], pair=(pr[0], pr[1])))
        cta_sub = rb.get("cta_line") or carousel.get("cta_promise", "")
        out.append(Beat("cta", carousel.get("cta_word", "AUDIT"),
                        read_time(cta_sub, lo=2.0, hi=3.2, orient=1.20), sub=cta_sub))
        # Brand seal before the loop tail. 1.5s: enough for the lockup to land
        # and hold a beat, not enough to read as an outro card overstaying.
        out.append(Beat("brand", None, 1.5))
        return trim_to_budget(out)

    # --- fallback: no reel_beats on this manifest ---
    # body_slides entries are dicts ({"text": ..., "keyword": ...}), not strings.
    # This passed them straight into Beat.text, and render() died on .split() the
    # moment it tried to wrap them -- so the safety net for a pre-reel_beats
    # manifest has never once worked. Caught 2026-08-09 by the smoke test's
    # missing-fields fixture.
    def _line(b):
        return (b.get("text") or "").strip() if isinstance(b, dict) else str(b or "").strip()

    hook = _line(carousel.get("hook_slide") or carousel.get("hook") or "")
    body = [t for t in (_line(b) for b in (carousel.get("body_slides") or [])) if t][:4]
    if not (hook and body):
        return []
    sub = carousel.get("cta_promise", "")
    out = ([Beat("hook", hook, read_time(hook, cps=22.0, lo=2.0, hi=3.4))]
           + [Beat("body", b, read_time(b)) for b in body])
    out.append(Beat("cta", carousel.get("cta_word", "AUDIT"),
                    read_time(sub, lo=2.0, hi=3.2, orient=1.20), sub=sub))
    out.append(Beat("brand", None, 1.5))
    return trim_to_budget(out)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

AUDIO_DIR = "assets/audio"
CREDITS_PATH = "assets/audio/credits.json"


def credit_for(track, credits_path=CREDITS_PATH):
    """Return the attribution line for a track, or None.

    Most "no copyright" music is actually Creative Commons Attribution: you have a
    licence PROVIDED you credit the artist. Crediting is the licence condition, not a
    courtesy -- an uncredited CC BY track is an unlicensed track, and an Instagram
    business account posting commercial content with unlicensed audio gets muted or
    pulled. So the credit rides with whichever track the reel actually used.

    A track with no entry in credits.json returns None and prints a warning rather than
    guessing at an artist name. Silence is safer than a wrong credit.
    """
    if not track:
        return None
    import json as _json
    try:
        credits = _json.load(open(credits_path))
    except Exception:
        print(f"WARNING: {credits_path} missing or unreadable — reel will publish with "
              f"no music credit. If the track needs attribution, that is a licence breach.")
        return None
    name = os.path.basename(track)
    line = credits.get(name)
    if not line:
        print(f"WARNING: no credit entry for {name!r} in {credits_path}. Publishing "
              f"without attribution — add an entry if this track is CC BY.")
        return None
    return line

def pick_track(batch_date, index, audio_dir=AUDIO_DIR):
    """Rotate deterministically over whatever tracks exist, so two reels rendered on
    the same day get different beds and the same reel always re-renders identically."""
    if not os.path.isdir(audio_dir):
        return None
    tracks = sorted(f for f in os.listdir(audio_dir)
                    if f.lower().endswith((".mp3", ".m4a", ".wav", ".aac")))
    # A track whose credit is still a TODO is not usable: it would either publish the
    # placeholder text into a real caption, or run uncredited. Drop it from rotation
    # until credits.json is filled in.
    usable = []
    for t in tracks:
        line = credit_for(os.path.join(audio_dir, t))
        if line and line.strip().upper().startswith("TODO"):
            print(f"Skipping {t!r} — credit still marked TODO in credits.json.")
            continue
        usable.append(t)
    tracks = usable
    if not tracks:
        return None
    seed = sum(ord(ch) for ch in str(batch_date)) + int(index)
    return os.path.join(audio_dir, tracks[seed % len(tracks)])


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------

def encode(frames_dir, out_mp4, duration, track=None, music_lufs=-26.0):
    """Frames -> Reels-spec MP4.

    Spec compliance is deliberate and was verified with ffprobe against Meta's published
    Reel requirements: H.264 high/4.0, yuv420p (4:2:0), progressive, closed GOP, 24fps,
    AAC 48kHz stereo 128k, moov atom at the front (+faststart -- without this Instagram
    has to download the whole file before it can read the header).

    music_lufs: tracks are loudness-normalised rather than given a fixed gain, because
    Ryan supplies the MP3s and their levels vary by 20dB+ between sources. -26 LUFS puts
    the bed clearly under the type -- present, not competing with the reading. A fixed
    volume= filter was tried first and produced a barely-audible bed on a quiet source.
    """
    import subprocess, json as _json
    fade_out_at = max(0.0, duration - 1.6)

    # Skip the track's intro. Most beds open with a quiet build; the reel needs the
    # track already moving under the hook. Seek 25% in (capped at 30s), but never so
    # far that less than `duration` of audio remains before looping.
    seek = 0.0
    if track:
        try:
            pr = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                                 "-of","csv=p=0",track], capture_output=True, text=True, check=True)
            tdur = float(pr.stdout.strip())
            seek = min(30.0, tdur * 0.25) if tdur > duration * 2 else 0.0
        except Exception:
            seek = 0.0
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f%05d.png")]
    if track:
        cmd += ["-stream_loop", "-1", "-ss", f"{seek:.2f}", "-i", track,
                "-filter_complex",
                f"[1:a]atrim=0:{duration:.3f},afade=t=in:st=0:d=0.6,"
                f"afade=t=out:st={fade_out_at:.3f}:d=1.6,"
                f"loudnorm=I={music_lufs}:TP=-2.0:LRA=11,aresample=48000[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-f", "lavfi", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest"]
    # preset slow + crf 18 (was veryfast/21, 2026-08-09): text is the whole
    # frame here, and the camera push means every pixel moves every frame --
    # veryfast at 21 visibly softened glyph edges. Encode time roughly
    # doubles and stays well inside the workflow budget.
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
            "-x264-params", "keyint=48:min-keyint=48:scenecut=0:open-gop=0",
            "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-t", f"{duration:.3f}",
            "-movflags", "+faststart", out_mp4]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_mp4


def render_reel(carousel, batch_date, index, out_mp4, workdir, audio_dir=AUDIO_DIR):
    """Full pipeline for one carousel: beats -> frames -> MP4. Returns (path, seconds)
    or (None, 0, None) when the carousel has no usable copy. The third value is the
    music attribution line, which the caller must append to the caption."""
    import shutil
    beats = beats_from_carousel(carousel)
    if not beats:
        return None, 0.0, None
    badge = (carousel.get("niche") or "").upper()[:18] or "MARKETING"
    if os.path.isdir(workdir):
        shutil.rmtree(workdir)
    n, dur = render(carousel.get("niche", ""), beats, workdir, badge)
    track = pick_track(batch_date, index, audio_dir)
    encode(workdir, out_mp4, dur, track)
    shutil.rmtree(workdir, ignore_errors=True)
    return out_mp4, dur, credit_for(track)
