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
import os, math
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 24
MARGIN = 96
SYS = "/usr/share/fonts/truetype/liberation"
F_SERIF = f"{SYS}/LiberationSerif-Bold.ttf"
F_SANS  = f"{SYS}/LiberationSans-Bold.ttf"
F_SANSR = f"{SYS}/LiberationSans-Regular.ttf"

BG, DOT, TEXT, GRAY = (240,239,234), (225,223,216), (20,20,20), (130,130,130)
HANDLE = "@rd.marketing0"
TOPIC = {
 "google ads": {"accent":(161,214,191),"dark":(30,90,65),"light":(200,240,220)},
 "meta":       {"accent":(240,172,168),"dark":(140,45,45),"light":(255,220,215)},
 "instagram":  {"accent":(240,172,168),"dark":(140,45,45),"light":(255,220,215)},
 "email":      {"accent":(196,176,226),"dark":(80,55,120),"light":(225,210,245)},
}
DEF = {"accent":(161,214,191),"dark":(30,90,65),"light":(200,240,220)}

def colors_for(n):
    n=(n or "").lower()
    for k,v in TOPIC.items():
        if k in n: return v
    return DEF

F=lambda p,s: ImageFont.truetype(p,s)
ease=lambda t: 1-(1-t)**3
def clamp(v,a=0.0,b=1.0): return max(a,min(b,v))

def wrap(d,t,f,mw):
    out,cur=[],""
    for w in t.split():
        s=(cur+" "+w).strip()
        if d.textlength(s,font=f)<=mw: cur=s
        else:
            if cur: out.append(cur)
            cur=w
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

def fade(lay,a):
    if a>=255: return lay
    l=lay.copy(); l.putalpha(l.getchannel("A").point(lambda v: v*a//255)); return l

def make_bg(c,dark=False):
    base=c["dark"] if dark else BG
    im=Image.new("RGB",(W,H),base); d=ImageDraw.Draw(im)
    if not dark:
        for y in range(0,H,46):
            for x in range(0,W,46): d.ellipse([x-2,y-2,x+2,y+2],fill=DOT)
        d.polygon([(W-200,0),(W,0),(W,200)],fill=c["light"])
    d.rectangle([0,0,W,12],fill=c["accent"]); d.rectangle([0,H-12,W,H],fill=c["accent"])
    return im

def chrome(im,c,badge,dark=False):
    d=ImageDraw.Draw(im)
    fg = BG if dark else c["dark"]
    pill = c["accent"] if not dark else c["light"]
    fb=F(F_SANS,32); tw=d.textlength(badge,font=fb)
    d.rounded_rectangle([MARGIN,104,MARGIN+tw+56,104+66],radius=33,fill=pill)
    d.text((MARGIN+28,104+17),badge,font=fb,fill=c["dark"])
    fh=F(F_SANSR,30); d.text((W-MARGIN-40-d.textlength(HANDLE,font=fh),120),HANDLE,font=fh,
                             fill=(200,215,205) if dark else GRAY)
    fp=F(F_SANS,30); p="Follow for more"; pw=d.textlength(p,font=fp)
    d.rounded_rectangle([MARGIN,1500,MARGIN+pw+68,1500+64],radius=32,outline=fg,width=3)
    d.text((MARGIN+34,1518),p,font=fp,fill=fg)
    return im

SAFE_TOP, SAFE_BOT = 250, 1430   # bottom ~320px is covered by IG caption/buttons          # between the badge row and the follow pill
def anchor(blockh):
    """Optically centre a block in the safe area, biased slightly high."""
    return int(SAFE_TOP + max(0,(SAFE_BOT - SAFE_TOP - blockh)) * 0.40)
TOP = 600

class Beat:
    def __init__(self,kind,text,dur,sub=None,num=None):
        self.kind,self.text,self.dur,self.sub,self.num=kind,text,dur,sub,num

def render(niche,beats,outdir,badge):
    c=colors_for(niche); os.makedirs(outdir,exist_ok=True)
    light=chrome(make_bg(c),c,badge); darkbg=chrome(make_bg(c,True),c,badge,True)
    probe=ImageDraw.Draw(Image.new("RGB",(4,4))); mw=W-2*MARGIN
    n=0
    for b in beats:
        nf=int(b.dur*FPS)
        if b.kind=="hook":
            f,ls=fit(probe,b.text,F_SERIF,152,84,mw,4); lh=int(f.size*1.14)
            words=[[layer(w,f,c["dark"]) for w in l.split()] for l in ls]
            y0=anchor(lh*len(ls))
            sp=probe.textlength(" ",font=f)
            for fi in range(nf):
                fr=light.copy(); k=0
                for li,ws in enumerate(words):
                    x=MARGIN
                    for lay in ws:
                        p=ease(clamp((fi-k*2)/9.0)); k+=1
                        if p>0:
                            fr.paste(fade(lay,int(255*p)),(x,y0+li*lh+int(38*(1-p))),fade(lay,int(255*p)))
                        x+=lay.width+int(sp)-8
                fr.save(f"{outdir}/f{n:05d}.jpg",quality=88); n+=1

        elif b.kind=="stat":
            fnum=F(F_SERIF,380); flab=F(F_SANS,62)
            labf,labls=fit(probe,b.sub,F_SANS,78,48,mw,3)
            labl=[layer(l,labf,TEXT) for l in labls]
            target=b.num
            for fi in range(nf):
                fr=light.copy(); d=ImageDraw.Draw(fr)
                p=ease(clamp(fi/14.0))
                val=int(round(target*p))
                s=f"{val}%"
                nl=layer(s,fnum,c["dark"])
                sc=0.92+0.08*p
                nl2=nl.resize((int(nl.width*sc),int(nl.height*sc)))
                y0=anchor(nl2.height+150)
                fr.paste(nl2,(MARGIN,y0-60),nl2)
                yy=y0-60+nl2.height+18
                d.rectangle([MARGIN,yy,MARGIN+int(mw*ease(clamp((fi-10)/12.0))),yy+9],fill=c["accent"])
                for li,lay in enumerate(labl):
                    q=ease(clamp((fi-14-li*3)/10.0))
                    if q>0: fr.paste(fade(lay,int(255*q)),(MARGIN,yy+42+li*int(labf.size*1.22)+int(26*(1-q))),fade(lay,int(255*q)))
                fr.save(f"{outdir}/f{n:05d}.jpg",quality=88); n+=1

        elif b.kind=="cta":
            f,ls=fit(probe,b.text,F_SANS,210,110,mw,2); lh=int(f.size*1.16)
            keyl=[layer(l,f,BG) for l in ls]
            sf,sls=fit(probe,b.sub,F_SANS,64,42,mw,3); slh=int(sf.size*1.26)
            subl=[layer(l,sf,c["light"]) for l in sls]
            ay=anchor(lh*len(keyl)+slh*len(subl)+34)
            for fi in range(nf):
                p=ease(clamp(fi/12.0))
                fr=light.copy()
                cut=int(H*p)
                if cut>0: fr.paste(darkbg.crop((0,H-cut,W,H)),(0,H-cut))
                if p>0.55:
                    q=ease(clamp((fi-13)/10.0))
                    for li,lay in enumerate(keyl):
                        fr.paste(fade(lay,int(255*q)),(MARGIN,ay+li*lh+int(30*(1-q))),fade(lay,int(255*q)))
                    for li,lay in enumerate(subl):
                        r=ease(clamp((fi-20-li*3)/10.0))
                        if r>0: fr.paste(fade(lay,int(255*r)),(MARGIN,ay+len(keyl)*lh+34+li*slh),fade(lay,int(255*r)))
                fr.save(f"{outdir}/f{n:05d}.jpg",quality=88); n+=1

        else:  # body
            f,ls=fit(probe,b.text,F_SANS,138,72,mw-56,4); lh=int(f.size*1.24)
            lays=[layer(l,f,TEXT) for l in ls]
            blockh=lh*len(lays)
            blockw=max(l.width for l in lays)+56          # bar hugs the longest line
            y0=anchor(blockh)
            for fi in range(nf):
                fr=light.copy(); d=ImageDraw.Draw(fr)
                grow=ease(clamp(fi/6.0))
                bw=int(blockw*grow)
                if bw>0:
                    bar=Image.new("RGBA",(bw,blockh+52),c["light"]+(175,))
                    fr.paste(bar,(MARGIN-28,y0-26),bar)
                    d.rectangle([MARGIN-28,y0-26,MARGIN-28+10,y0-26+blockh+52],fill=c["dark"])
                for li,lay in enumerate(lays):
                    # text rides in with the bar, not after it
                    p=ease(clamp((fi-li*3)/9.0))
                    if p>0: fr.paste(fade(lay,int(255*p)),(MARGIN+int(26*(1-p)),y0+li*lh),fade(lay,int(255*p)))
                fr.save(f"{outdir}/f{n:05d}.jpg",quality=88); n+=1
    return n,n/FPS


# ---------------------------------------------------------------------------
# Beat construction from the content brain's reel_beats block
# ---------------------------------------------------------------------------

def beats_from_carousel(carousel):
    """Turn a carousel dict's reel_beats into Beat objects.

    Falls back to slicing the carousel copy if reel_beats is missing, so a manifest
    generated before the content-brain change still renders something rather than
    crashing the whole evening run. The fallback reads as checklist items, not video
    lines -- it is a safety net, not the intended path.
    """
    rb = carousel.get("reel_beats") or {}
    if rb.get("hook") and rb.get("body"):
        out = [Beat("hook", rb["hook"], 2.9)]
        if rb.get("stat_number") is not None and rb.get("stat_label"):
            out.append(Beat("stat", None, 2.8, sub=rb["stat_label"], num=int(rb["stat_number"])))
        for line in rb["body"][:4]:
            out.append(Beat("body", line, 2.2))
        out.append(Beat("cta", carousel.get("cta_word", "AUDIT"), 3.2,
                        sub=rb.get("cta_line") or carousel.get("cta_promise", "")))
        return out

    # --- fallback: no reel_beats on this manifest ---
    hook = carousel.get("hook_slide") or carousel.get("hook") or ""
    body = [b for b in (carousel.get("body_slides") or [])][:4]
    if not (hook and body):
        return []
    out = [Beat("hook", hook, 2.9)] + [Beat("body", b, 2.2) for b in body]
    out.append(Beat("cta", carousel.get("cta_word", "AUDIT"), 3.2,
                    sub=carousel.get("cta_promise", "")))
    return out


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
           "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f%05d.jpg")]
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
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
