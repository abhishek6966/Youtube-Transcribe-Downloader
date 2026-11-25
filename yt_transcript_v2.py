#!/usr/bin/env python3
"""
YouTube lyrics / transcript v2 — FAST + more accurate.
Fixes vs v1:
  1. CAPTIONS FIRST: if YouTube already has captions, use them — seconds,
     not minutes, and exact when the uploader supplied them.
  2. MODEL large-v3-turbo instead of large-v3: ~5-6x faster on CPU,
     almost the same accuracy. large-v3 is the slowest Whisper model.
  3. Language detect: 1 short listen instead of 5x 30s — that alone
     saved minutes in v1. Give the language code if you know it to skip it.
  4. beam_size=1 (greedy): lyrics gain almost nothing from beam 5, it costs a lot.
  5. cpu_threads=4 so all cores are used.

Honest limit: no speech model gives "exact true pronunciation" for sung
lyrics. Whisper hears words over music and sometimes mishears them — the
romanizer can only spell what Whisper heard. Captions (step 1) are the
only exact source; Whisper is the fallback when there are no captions.
Run:  double-click run_transcript_v2.bat   (or: python yt_transcript_v2.py "VIDEO_LINK")
"""

# =====================================================================
#  SETTINGS
# =====================================================================
VIDEO_LINKS = [
    "https://www.youtube.com/watch?v=PASTE_LINK_HERE",   # only used without the .bat
]

LANGUAGE = None          # None = auto-detect (the .bat can override). e.g. "es", "hi", "ja"
MODEL = "large-v3-turbo" # was "large-v3" — turbo is ~5-6x faster on CPU, near-same accuracy.
                         # Even faster draft: "medium" (much faster, a bit less accurate).
                         # Do NOT go back to "large-v3" unless turbo mishears a language badly.
DEVICE = "cpu"
CPU_THREADS = 4          # use all cores; set to your PC's core count if you know it
BEAM_SIZE = 5             # accuracy first: beam 5 + temperature 0 picks the
                          # model's most confident words (fast lines, singing).
                          # Slower than greedy (1), but far fewer mistakes.
WORD_TIMESTAMPS = True   # True = one line per WORD with start --> end in milliseconds
ENGLISH_LETTERS = True   # main output written in English (Latin) letters
OUTPUT_FOLDER = "transcripts"
# =====================================================================

import glob
import os
import re
import sys
import tempfile
import unicodedata

_kks = None

# ---------------------------------------------------------------------
#  Hindi / Devanagari -> English letters (handles the hidden "a" sound)
# ---------------------------------------------------------------------
_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "ऩ": "n", "ऱ": "r", "ऴ": "zh",
}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f"}
_INDEP = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
          "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e"}
_MATRA = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
          "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
          "ॆ": "e", "ॊ": "o"}
_LABIAL = set("पफबभम")


def _deva_word(w, schwa=True):
    w = "".join(unicodedata.normalize("NFD", ch) if "\u0958" <= ch <= "\u095F" else ch for ch in w)
    syl = []   # each: [consonant, vowel, inherent(bool), nasal]
    i = 0
    while i < len(w):
        c = w[i]
        if c in _CONS:
            cons = _CONS[c]
            if i + 1 < len(w) and w[i + 1] == "़":
                cons = _NUKTA.get(c, cons)
                i += 1
            nxt = w[i + 1] if i + 1 < len(w) else ""
            if nxt in _MATRA:
                syl.append([cons, _MATRA[nxt], False, ""]); i += 2
            elif nxt == "्":
                syl.append([cons, "", False, ""]); i += 2
            else:
                syl.append([cons, "a", True, ""]); i += 1
        elif c in _INDEP:
            syl.append(["", _INDEP[c], False, ""]); i += 1
        elif c in "ंँ":
            if syl:
                syl[-1][3] = "n"
            i += 1
        elif c == "ः":
            if syl:
                syl[-1][3] = "h"
            i += 1
        elif c == "।":
            syl.append(["", ".", False, ""]); i += 1
        else:
            syl.append(["", c, False, ""]); i += 1

    n = len(syl)
    for k in range(n if schwa else 0):
        cons, vow, inherent, nasal = syl[k]
        if not inherent or n == 1:
            continue
        if k == n - 1 and not nasal:                       # word-final: "par", not "para"
            syl[k][1] = ""
        elif (0 < k < n - 1 and not nasal and syl[k - 1][1] != "" and not syl[k - 1][3]
              and syl[k + 1][1] not in ("",)):             # middle: "samjhaa", not "samajhaa"
            syl[k][1] = ""
    out = []
    for k, (cons, vow, _, nasal) in enumerate(syl):
        out.append(cons + vow)
        if nasal == "n":
            nxt = syl[k + 1][0][:1] if k + 1 < n else ""
            out.append("m" if (not schwa or (nxt and nxt in "pbm")) else "n")
        elif nasal:
            out.append(nasal)
    s = "".join(out).replace("jny", "gy")
    return s


# Indian scripts share one layout (ISCII), so each is mapped onto Devanagari
# and read with the same rules. True = hidden "a" is dropped at word end.
_BLOCKS = {0x0900: True, 0x0980: True, 0x0A00: True, 0x0A80: True, 0x0B00: True,
           0x0B80: False, 0x0C00: False, 0x0C80: False, 0x0D00: False}


def indic_to_latin(text):
    text = unicodedata.normalize("NFC", text).replace("\u0A70", "\u0A02")  # Punjabi tippi

    def conv(m):
        run = m.group(0)
        base = (ord(run[0]) // 0x80) * 0x80
        dev = "".join(chr(ord(c) - base + 0x0900) if base <= ord(c) < base + 0x80 else c
                      for c in run)
        return _deva_word(dev, _BLOCKS.get(base, True))

    return re.sub(r"[\u0900-\u0D7F]+", conv, text)


def romanize(text, lang):
    """Original-language text -> English letters, as it sounds."""
    global _kks
    try:
        if re.search(r"[\u0900-\u0D7F]", text):            # Hindi, Bengali, Tamil, Telugu...
            return indic_to_latin(text)
        if lang == "ja":
            import pykakasi
            _kks = _kks or pykakasi.kakasi()
            return " ".join(i["hepburn"] for i in _kks.convert(text))
        if lang in ("zh", "yue"):
            from pypinyin import lazy_pinyin
            return " ".join(lazy_pinyin(text))
        if lang == "ko":
            from korean_romanizer.romanizer import Romanizer
            return Romanizer(text).romanize()
    except Exception:
        pass
    from unidecode import unidecode
    return unidecode(text)


# ---------------------------------------------------------------------
def ts(seconds):
    """Seconds only, no milliseconds. Whisper timing is not accurate
    to the millisecond anyway, so .123 is false precision and clutter."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def group_by_second(items):
    """Sec by sec: one line per second, words spoken in that second joined.
    items are (start, end, text). Returns [(second_start, joined_text)]."""
    buckets = {}
    order = []
    for a, b, t in items:
        sec = int(a)
        if sec not in buckets:
            buckets[sec] = []
            order.append(sec)
        buckets[sec].append(t)
    return [(sec, " ".join(buckets[sec])) for sec in order]


def detect_language(model, path):
    """Accuracy first: listen at TWO points (first 15s + middle 15s).
    If both agree, trust it. If they disagree, take the higher confidence.
    Sung music fools a single short listen, so one sample is not enough."""
    from faster_whisper import decode_audio

    audio = decode_audio(path, sampling_rate=16000)
    n, win = len(audio), 15 * 16000
    samples = [audio[0:win], audio[max(0, (n - win) // 2):max(0, (n - win) // 2) + win]]
    results = []
    for sample in samples:
        try:
            _, _, probs = model.detect_language(sample)
        except Exception:
            continue
        probs = probs.items() if isinstance(probs, dict) else probs
        best, p = max(probs, key=lambda kv: kv[1])
        results.append((best, p))
    if not results:
        return None, 0.0
    if len(results) == 2 and results[0][0] == results[1][0]:
        return results[0][0], max(r[1] for r in results)
    return max(results, key=lambda r: r[1])


def try_captions(url, language):
    """Step 1 — YouTube's own captions. Returns (lang, items) or None.
    Instant (seconds) and exact when the uploader supplied captions.
    Auto-captions are also returned, but labelled as auto — they can be
    wrong on sung lyrics too, just faster than re-transcribing."""
    import re as _re
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.formatters import TextFormatter  # noqa: F401 (kept for reference)

    m = _re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", url)
    if not m:
        return None
    vid = m.group(1)
    api = YouTubeTranscriptApi()
    try:
        listing = api.list(vid)
    except Exception as e:
        print(f"  No captions available ({type(e).__name__}), will transcribe audio instead.")
        return None
    # Prefer manually created captions in the requested language, then any manual, then auto.
    langs = [language] if language else ["en", "hi"]
    chosen = None
    for want in (langs + [None]):
        try:
            chosen = listing.find_transcript(langs) if want else None
        except Exception:
            chosen = None
        if chosen:
            break
    if not chosen:
        try:
            chosen = next(iter(listing))
        except Exception:
            return None
    try:
        fetched = chosen.fetch()
    except Exception as e:
        print(f"  Captions listed but could not be fetched ({e}), will transcribe audio instead.")
        return None
    items = [(s.start, s.start + s.duration, s.text.strip())
             for s in fetched if s.text.strip()]
    if not items:
        return None
    kind = "manual (exact)" if not chosen.is_generated else "auto-generated (may mishear lyrics)"
    print(f"  Captions found: {chosen.language} — {kind}, {len(items)} lines. No audio download needed.")
    return chosen.language_code, kind, items


def transcribe(url, model, language, names_hint=None):
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        opts = {"format": "bestaudio/best",
                "outtmpl": os.path.join(tmp, "audio.%(ext)s"), "quiet": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
        path = glob.glob(os.path.join(tmp, "audio.*"))[0]

        prob = None
        if not language:
            print("  Detecting spoken language...")
            language, prob = detect_language(model, path)
            print(f"  Detected: {language} ({prob:.0%})")

        # Accuracy settings (slower than greedy, but far fewer mistakes):
        # beam_size=5 + temperature=0 = the model picks its most confident
        # words, which matters most on fast lines and singing.
        # initial_prompt = the video title + any names the user gave us,
        # so proper names are heard correctly instead of guessed.
        # No VAD filter: it throws away singing over loud music.
        # task="transcribe" = keep the spoken language, never translate.
        prompt = title
        if names_hint:
            prompt += f". Names and words in this video: {names_hint}."
        segments, det = model.transcribe(
            path,
            language=language,
            task="transcribe",
            word_timestamps=True,
            beam_size=5,
            temperature=0.0,
            initial_prompt=prompt,
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,   # skip text invented over silence
            compression_ratio_threshold=2.4,
        )
        items = []  # (start, end, text)
        for seg in segments:
            print(f"\r  Transcribed up to {ts(seg.end)[:8]} ...", end="", flush=True)
            if WORD_TIMESTAMPS and seg.words:
                for w in seg.words:
                    word = w.word.strip()
                    if word:
                        items.append((w.start, w.end, word))
            else:
                items.append((seg.start, seg.end, seg.text.strip()))
        print()
        return title, det.language, prob, items


def main():
    import time
    from faster_whisper import WhisperModel

    forced = os.environ.get("YT_LANG", "").strip().lower() or LANGUAGE
    names_hint = os.environ.get("YT_NAMES", "").strip() or None
    # Optional: pass names after the URL, e.g.
    #   run_transcript_v2.bat <url> --names "Arijit Singh, Shah Rukh Khan"
    argv = [a for a in sys.argv[1:] if not a.startswith("--names")]
    if "--names" in sys.argv:
        i = sys.argv.index("--names")
        names_hint = sys.argv[i + 1] if i + 1 < len(sys.argv) else names_hint
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for url in (argv or VIDEO_LINKS):
        print(f"\nProcessing: {url}")
        t0 = time.time()
        # --- Step 1: captions first (seconds, exact if manual) ---
        cap = try_captions(url, forced)
        if cap:
            lang, kind, items = cap
            note = f"YouTube captions — {kind}"
            title = "video"
            try:
                import yt_dlp
                with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                    title = ydl.extract_info(url, download=False).get("title", "video")
            except Exception:
                pass
            _save(title, lang, note, items)
            print(f"  Done in {time.time() - t0:.0f}s (captions, no transcription).")
            continue
        # --- Step 2: no captions — transcribe audio with turbo ---
        print(f"Loading model '{MODEL}' (first run downloads ~800 MB, once only)...")
        model = WhisperModel(MODEL, device=DEVICE, compute_type="int8", cpu_threads=CPU_THREADS)
        try:
            title, lang, prob, items = transcribe(url, model, forced, names_hint)
        except Exception as e:
            print(f"  Failed: {e}")
            continue
        note = "forced by you" if forced else f"auto-detected, confidence {prob:.0%}"
        _save(title, lang, note, items)
        print(f"  Done in {time.time() - t0:.0f}s total.")
        print(f"  Tip: if lyrics still mishear, give the language code next time —")
        print(f"  auto-detect on sung music is the weakest link.")


def _save(title, lang, note, items):
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        def render(fn=lambda x: x):
            # Sec by sec: [00:00:01] words in that second
            return "\n".join(f"[{ts(sec)}] {fn(text)}" for sec, text in group_by_second(items))

        original = render()
        latin = render(lambda t: romanize(t, lang)) if ENGLISH_LETTERS else None
        name = re.sub(r"[^\w\- ]", "", title).strip()[:80] or "video"
        # File 1: original language, its own script.
        path1 = os.path.join(OUTPUT_FOLDER, f"{name}.txt")
        with open(path1, "w", encoding="utf-8") as f:
            f.write(f"{title}\nSpoken language: {lang} ({note})\n\n{original}\n")
        print(f"  Spoken language: {lang} ({note})\n  Saved file 1 (original): {path1}")
        # File 2: same words, same order, English letters as pronounced.
        if latin is not None and latin != original:
            path2 = os.path.join(OUTPUT_FOLDER, f"{name} - English letters.txt")
            with open(path2, "w", encoding="utf-8") as f:
                f.write(f"{title}\nSpoken language: {lang} ({note})\nPronunciation in English letters\n\n{latin}\n")
            print(f"  Saved file 2 (English letters): {path2}")
        print()
        print(original)


if __name__ == "__main__":
    main()
