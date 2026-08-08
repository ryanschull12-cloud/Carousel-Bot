# Reel background music

`reel_engine.py` picks one track from this folder per reel and rotates deterministically
by date, so two reels rendered the same day don't share a bed and re-rendering a given
day always produces the same pairing.

**If this folder is empty, reels still render — with a silent audio track.** Nothing
breaks. Silent reels just underperform.

## What to put here

5–10 files, `.mp3` / `.m4a` / `.wav`. Anything 20 seconds or longer is fine — shorter
tracks are looped automatically to fill the reel.

Levels don't matter. Tracks are loudness-normalised to −26 LUFS at encode time, so a
quiet track and a mastered-loud one end up at the same level under the type. Pick on
feel, not volume.

## Where to get them

- **YouTube Audio Library** (studio.youtube.com → Audio Library) — free, and the filter
  for "no attribution required" is the one to use.
- **Pixabay Music** — Pixabay Content Licence, commercial use, no attribution.
- **Uppbeat** — free tier is good but **requires crediting the artist in the caption**,
  which the caption generator doesn't do. Only use these if you'll add the credit yourself.

## Read this before you drop files in

Check the licence covers **commercial social media use**. This is a business account
posting marketing content, which is commercial use — plenty of "free for personal use"
tracks do not cover it.

Also worth knowing: API-published reels cannot use Instagram's licensed trending audio
(Meta: *"Music tagging is only available for original audio"*). That's why the track is
mixed into the MP4 rather than attached in-app. The trade-off is real — no "use this
sound" loop — but a reel with a bed still beats a silent one, and both beat a carousel
that reaches three people.

## credits.json — required for every track

`credits.json` maps each filename to the attribution line that gets appended to the
caption of any reel using it:

```json
{
  "my-track.mp3": "Track Name — Artist (CC BY) youtube.com/@artist"
}
```

Most "no copyright" music is really Creative Commons Attribution: you have a licence
**provided** you credit the artist. Crediting is the licence condition, not a courtesy.
An uncredited CC BY track is an unlicensed track, and a business account posting
commercial content with unlicensed audio gets muted or pulled.

Two rules the code enforces:

- A track with **no entry** in credits.json still plays, but publishes with no credit and
  prints a warning. Fine for genuinely attribution-free music, a licence breach otherwise.
- A track whose credit starts with **`TODO`** is dropped from rotation entirely. It will
  never be used until you replace the placeholder with a real credit — safer than
  publishing "TODO" into a live caption or running the track uncredited.

Crediting does **not** unlock music you have no licence for. It satisfies a condition on
a licence you already hold. Trending/chart audio has no such licence for a business
account, so no amount of crediting makes it usable.

## Naming

Filenames are only used for sorting. Something like `01-calm-piano.mp3`,
`02-upbeat-synth.mp3` makes the rotation order predictable.
