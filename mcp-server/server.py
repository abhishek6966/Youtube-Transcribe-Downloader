#!/usr/bin/env python3
"""YouTube Transcribe Downloader — MCP server (pure Python stdlib, no installs).

Exposes the project's real behaviour as tools any MCP client can call
(Claude Desktop, Cursor, VS Code, Claude Code, ...):

  transcribe_youtube(url, lang="auto")
      Captions-first, using the same chain as the web page: public
      Invidious mirrors raced in parallel, then Piped (its /streams
      answer, then the subtitle file), then YouTube's legacy timedtext
      last. Returns timed lines with [MM:SS] stamps in the original
      language PLUS the same lines in English letters (romanized
      pronunciation, never a translation). Sound-description cues
      ([Sangeet]/[sangeet]/[myoosik], [Music], (pause), tune,
      [BLANK_AUDIO], ...) are stripped everywhere. Words are never
      invented: if the video has no captions and no key is given, the
      tool says so plainly instead of guessing.

  transcribe_audio(audio_path_or_url, api_key, provider="groq")
      Sends an audio file (or a URL to one) to Groq / OpenAI Whisper
      and returns the same two timed versions.

Protocol: newline-delimited JSON-RPC 2.0 over stdio. Handles
initialize, ping, tools/list and tools/call. No third-party packages:
only the Python 3.10+ standard library.

Your API key is never stored or logged — it is sent only to the
provider it belongs to, for that one request.
"""

import concurrent.futures
import html
import http.client
import json
import math
import os
import re
import ssl
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ---------------------------------------------------------------------------
# Caption sources — the same two public families the web page races.
# ---------------------------------------------------------------------------
INVIDIOUS_HOSTS = [
    "https://inv.nadeko.net",
    "https://invidious.privacyredirect.com",
    "https://invidious.jing.rocks",
    "https://invidious.reallyaweso.me",
    "https://invidious.0011.lt",
    "https://invidious.fdn.fr",
]
PIPED_HOSTS = [
    "https://api.piped.private.coffee",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi.dmatik.dev",
    "https://pipedapi.syncpundit.io",
]

WHISPER_PROVIDERS = {
    "groq": {
        "host": "api.groq.com",
        "path": "/openai/v1/audio/transcriptions",
        "models": ["whisper-large-v3", "whisper-large-v3-turbo"],
    },
    "openai": {
        "host": "api.openai.com",
        "path": "/v1/audio/transcriptions",
        "models": ["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"],
    },
}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # provider upload limit


# ---------------------------------------------------------------------------
# Romanization — a faithful port of the web page's romanize(): the same
# words in English letters, spelled the way they sound. Never a translation.
# ---------------------------------------------------------------------------
INDIC_BASES = [0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80, 0x0C00, 0x0C80, 0x0D00]
INDIC_VOWELS = {"5": "a", "6": "aa", "7": "i", "8": "ee", "9": "u", "10": "oo",
                "11": "ri", "15": "e", "16": "ai", "19": "o", "20": "au"}
INDIC_MATRAS = {"3e": "aa", "3f": "i", "40": "ee", "41": "u", "42": "oo",
                "43": "ri", "47": "e", "48": "ai", "4b": "o", "4c": "au"}
INDIC_CONS = {"15": "k", "16": "kh", "17": "g", "18": "gh", "19": "ng", "1a": "ch",
              "1b": "chh", "1c": "j", "1d": "jh", "1e": "ny", "1f": "t", "20": "th",
              "21": "d", "22": "dh", "23": "n", "24": "t", "25": "th", "26": "d",
              "27": "dh", "28": "n", "29": "n", "2a": "p", "2b": "ph", "2c": "b",
              "2d": "bh", "2e": "m", "2f": "y", "30": "r", "31": "r", "32": "l",
              "33": "l", "34": "l", "35": "v", "36": "sh", "37": "sh", "38": "s",
              "39": "h", "58": "k", "59": "kh", "5a": "g", "5b": "z", "5c": "d",
              "5d": "dh", "5e": "f", "5f": "y"}
INDIC_NUKTA = {"15": "k", "16": "kh", "17": "g", "1c": "z", "21": "d",
               "22": "dh", "2b": "f"}

CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
       "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
       "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
       "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
       "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}
GRK = {"α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
       "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
       "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
       "φ": "ph", "χ": "kh", "ψ": "ps", "ω": "o", "ά": "a", "έ": "e", "ή": "i",
       "ί": "i", "ό": "o", "ύ": "y", "ώ": "o", "ϊ": "i", "ϋ": "y"}
ARB = {"ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
       "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s",
       "ض": "d", "ط": "t", "ظ": "z", "ع": "'", "غ": "gh", "ف": "f", "ق": "q",
       "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
       "ة": "a", "ى": "a", "أ": "a", "إ": "i", "آ": "aa", "ؤ": "w", "ئ": "y",
       "ء": "'", "َ": "a", "ُ": "u", "ِ": "i", "ً": "", "ٌ": "", "ٍ": "",
       "ّ": "", "ْ": ""}
HEB = {"א": "'", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z",
       "ח": "ch", "ט": "t", "י": "y", "כ": "k", "ך": "kh", "ל": "l", "מ": "m",
       "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "'", "פ": "p", "ף": "f",
       "צ": "ts", "ץ": "ts", "ק": "k", "ר": "r", "ש": "sh", "ת": "t"}
KANA_SRC = ("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめも"
             "やゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ")
KANA_ROM = ["a", "i", "u", "e", "o", "ka", "ki", "ku", "ke", "ko", "sa", "shi",
            "su", "se", "so", "ta", "chi", "tsu", "te", "to", "na", "ni", "nu",
            "ne", "no", "ha", "hi", "fu", "he", "ho", "ma", "mi", "mu", "me",
            "mo", "ya", "yu", "yo", "ra", "ri", "ru", "re", "ro", "wa", "wo",
            "n", "ga", "gi", "gu", "ge", "go", "za", "ji", "zu", "ze", "zo",
            "da", "ji", "zu", "de", "do", "ba", "bi", "bu", "be", "bo", "pa",
            "pi", "pu", "pe", "po"]
KANA = dict(zip(KANA_SRC, KANA_ROM))
KANA_DIGI = {"ki": "ky", "shi": "sh", "chi": "ch", "ni": "ny", "hi": "hy",
             "mi": "my", "ri": "ry", "gi": "gy", "ji": "j", "bi": "by", "pi": "py"}
HG_I = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j",
        "jj", "ch", "k", "t", "p", "h"]
HG_M = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe",
        "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
HG_F = ["", "k", "k", "k", "n", "n", "nh", "t", "l", "l", "l", "l", "l", "l",
        "l", "l", "m", "p", "p", "s", "s", "ng", "j", "ch", "k", "t", "p", "h"]
LATX = {"ñ": "ny", "Ñ": "Ny", "ß": "ss", "æ": "ae", "Æ": "Ae", "œ": "oe",
        "ø": "o", "Ø": "O", "đ": "d", "ł": "l", "þ": "th", "ð": "d",
        "ş": "sh", "ğ": "g", "ı": "i", "ç": "ch"}


def _indic_base(code):
    for base in INDIC_BASES:
        if base <= code < base + 0x80:
            return base
    return 0


def _indic_char(text, i, base):
    off = ord(text[i]) - base
    key = format(off, "x")
    if key in INDIC_CONS:
        out = INDIC_CONS[key]
        i += 1
        if i < len(text) and ord(text[i]) - base == 0x3C:  # nukta
            if key in INDIC_NUKTA:
                out = INDIC_NUKTA[key]
            i += 1
        noff = ord(text[i]) - base if i < len(text) else -1
        nkey = format(noff, "x")
        if noff == 0x4D:  # virama: bare consonant
            return out, i + 1
        if nkey in INDIC_MATRAS:
            return out + INDIC_MATRAS[nkey], i + 1
        return out + "a", i
    # Vowel keys are DECIMAL offsets (the web page looks them up by the
    # plain number, not by hex) — e.g. offset 15 is "e", 16 is "ai".
    if str(off) in INDIC_VOWELS:
        return INDIC_VOWELS[str(off)], i + 1
    if off in (0x01, 0x02):
        return "n", i + 1
    if off == 0x03:
        return "h", i + 1
    if 0x66 <= off <= 0x6F:
        return str(off - 0x66), i + 1
    return "", i + 1


def _kana_of(ch):
    code = ord(ch)
    if 0x30A1 <= code <= 0x30F6:  # katakana -> hiragana
        return chr(code - 0x60)
    return ch


def _kana_at(text, i):
    ch = _kana_of(text[i])
    if ch == "っ":
        nxt = KANA.get(_kana_of(text[i + 1])) if i + 1 < len(text) else None
        if nxt and nxt[0] in "bcdfghjkprstz":
            return nxt[0], i + 1
        return "", i + 1
    rom = KANA.get(ch)
    if rom is None:
        return text[i], i + 1
    if i + 1 < len(text):
        small = _kana_of(text[i + 1])
        if small in ("ゃ", "ゅ", "ょ") and rom in KANA_DIGI:
            return KANA_DIGI[rom] + {"ゃ": "a", "ゅ": "u", "ょ": "o"}[small], i + 2
    return rom, i + 1


def _hangul(ch):
    s = ord(ch) - 0xAC00
    return HG_I[s // 588] + HG_M[(s % 588) // 28] + HG_F[s % 28]


def _cap_like(orig, rom):
    if orig != orig.lower() and rom:
        return rom[0].upper() + rom[1:]
    return rom


def romanize(text):
    """Same words, spelled in English letters the way they sound.

    Pronunciation only — never a translation. Ported from the web page's
    romanize(): Indic scripts (Hindi, Bengali, Tamil, Telugu, ...),
    Hangul, kana, Cyrillic, Greek, Arabic, Hebrew, and Latin accents.
    """
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        code = ord(ch)
        base = _indic_base(code)
        if base:
            r, i = _indic_char(text, i, base)
            out.append(r)
            continue
        if 0xAC00 <= code <= 0xD7A3:
            out.append(_hangul(ch))
            i += 1
            continue
        if ch == "ー":
            m = re.search(r"[aeiou](?=[^aeiou]*$)", "".join(out))
            out.append(m.group(0) if m else "")
            i += 1
            continue
        if 0x3040 <= code <= 0x30FF:
            r, i = _kana_at(text, i)
            out.append(r)
            continue
        low = ch.lower()
        if low in CYR:
            out.append(_cap_like(ch, CYR[low]))
            i += 1
            continue
        if low in GRK:
            out.append(_cap_like(ch, GRK[low]))
            i += 1
            continue
        if ch in ARB:
            out.append(ARB[ch])
            i += 1
            continue
        if ch in HEB:
            out.append(HEB[ch])
            i += 1
            continue
        if ch in LATX:
            out.append(LATX[ch])
            i += 1
            continue
        if 0xC0 <= code <= 0x24F:
            dec = "".join(c for c in unicodedata.normalize("NFD", ch)
                          if not (0x300 <= ord(c) <= 0x36F))
            out.append(dec if dec and dec != ch else ch)
            i += 1
            continue
        if 0x300 <= code <= 0x36F:
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)

# ---------------------------------------------------------------------------
# Sound-description cues — same lists as the web page. A transcript holds
# only the words that are sung or spoken; [music], (pause), [संगीत],
# [म्यूसिक], [BLANK_AUDIO] and the rest are not words and are cleaned off
# at every step. A real sung line is never touched, even if it mentions
# music: only bracketed marks and cue-only lines are removed.
# ---------------------------------------------------------------------------
CUE_WORDS = {
    "music", "musica", "musik", "musique", "muzyka", "pauza", "eumak",
    "sangeet", "sangeeta", "sangeeth", "sangit", "dhun", "dhuna", "taal",
    "taaliyaan", "taaliyan", "hansee", "hansi", "viraama", "gaayana",
    "vaadya", "myoosik", "myoosika", "gaanaa", "gaane", "aavaaza",
    "haanphane", "shora",
    "pause", "tune", "applause", "laughter", "laughing", "cheering", "cheers",
    "singing", "humming", "instrumental", "interlude", "intro", "outro",
    "silence", "silent", "noise", "beep", "beeping", "clapping", "whispering",
    "murmuring", "chatter", "gasp", "gasping", "sigh", "sighing", "coughing",
    "crying", "sobbing", "shouting", "screaming", "ringing", "alarm",
    "footsteps", "thunder", "melody", "beat", "beats", "rhythm", "song",
    "songs", "blankaudio", "nospeech", "speech", "inaudible",
    "unintelligible", "crosstalk",
}
CUE_FILLER = {
    "soft", "loud", "background", "playing", "plays", "play", "played",
    "dramatic", "upbeat", "gentle", "slow", "melodic", "cheerful", "tense",
    "suspenseful", "rhythmic", "traditional", "continues", "continuing",
    "fades", "fading", "distant", "muffled", "echoing", "theme",
    "and", "the", "a", "an", "of", "in", "on", "no", "kee",
}
RAW_CUES = ["संगीत", "धुन", "तालियाँ", "तालियां", "ताली", "हँसी", "हंसी",
            "विराम", "वाद्य", "म्यूसिक", "म्यूज़िक",
            "गाना गाने की आवाज़", "हांफने की आवाज़", "शोर",
            "موسيقى", "الموسيقى", "音楽", "음악", "音乐", "音樂", "blank_audio"]
_BRACKET_RE = re.compile(r"\[([^\]]*)\]|\(([^)]*)\)")


def _cue_norm(s):
    return re.sub(r"\s+", " ", re.sub(
        r"[^a-z]+", " ", romanize(str(s or "").lower().replace("_", "")))).strip()


def is_cue_text(s):
    """True when the whole short text is only a sound description."""
    raw = str(s or "").strip().lower()
    if not raw:
        return False
    if len(raw.split()) <= 4:
        for cue in RAW_CUES:
            if cue in raw:
                return True
    norm = _cue_norm(raw)
    if not norm:
        return False
    words = norm.split(" ")
    has_cue = False
    for w in words:
        if w in CUE_WORDS:
            has_cue = True
        elif w not in CUE_FILLER:
            return False
    return has_cue


def strip_cue_marks(text):
    """Remove bracketed sound marks only — a single real word is never
    dropped by this, even a cue word, because inside a line it may
    truly be sung."""
    t = str(text or "").replace("♪", " ").replace("♫", " ")

    def _sub(m):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        return " " if is_cue_text(inner) else m.group(0)

    t = _BRACKET_RE.sub(_sub, t)
    # Split brackets: a cue that arrives cut across seconds leaves
    # fragments like "[गाना" or "आवाज़]" — drop a bracket-carrying token
    # only when its bracket-free text is itself a sound description.
    kept = []
    for tok in t.split():
        if "[" in tok or "]" in tok:
            inner = tok.replace("[", "").replace("]", "").replace("(", "").replace(")", "").strip()
            if inner and is_cue_text(inner):
                continue
        kept.append(tok)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def collapse_echo(words):
    """Collapse immediate repetition inside ONE per-second line only:
    the same word twice in a row -> once; a phrase of 2+ words that
    appears twice inside the same line -> keep the first occurrence.
    Repetition across different seconds (a real chorus) is untouched."""
    out = []
    for w in words:
        if not out or w != out[-1]:
            out.append(w)
    changed = True
    while changed:
        changed = False
        n = len(out)
        for ln in range(n // 2, 1, -1):
            found = False
            for i in range(0, n - ln + 1):
                for j in range(i + ln, n - ln + 1):
                    if out[i:i + ln] == out[j:j + ln]:
                        del out[j:j + ln]
                        found = True
                        changed = True
                        break
                if found:
                    break
            if found:
                break
    return out


def strip_labels(text):
    return strip_cue_marks(text)


# ---------------------------------------------------------------------------
# Time helpers and subtitle parsing — ports of the web page's parsers.
# ---------------------------------------------------------------------------
def fmt_sec(sec):
    sec = max(0, int(round(sec or 0)))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_time_token(tok):
    """'00:01:02.300', '01:02.5', '62.4' or '1.2s' -> seconds (float)."""
    if tok is None:
        return 0.0
    t = str(tok).strip().rstrip("s")
    if not t:
        return 0.0
    parts = t.split(":")
    try:
        vals = [float(p.replace(",", ".")) for p in parts]
    except ValueError:
        return 0.0
    total = 0.0
    for v in vals:
        total = total * 60 + v
    return total


def parse_subtitle_text(text):
    """WebVTT (and SRT-shaped) text -> [{start, dur, text, wt?}].

    YouTube auto-captions carry the exact time of every word inside the
    line, like <00:00:01.200> — those times are lifted out before the
    tags are stripped, so words can be placed at their real seconds.
    """
    entries = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        ti = next((i for i, ln in enumerate(lines) if "-->" in ln), -1)
        if ti < 0:
            continue
        start_s, end_s = lines[ti].split("-->", 1)
        start = parse_time_token(start_s)
        end = parse_time_token(end_s.strip().split()[0])
        raw_body = " ".join(lines[ti + 1:])
        stamps = []

        def _grab(m):
            stamps.append(parse_time_token(m.group(1)))
            return " "

        marked = re.sub(r"<(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)>", _grab, raw_body)
        body = strip_labels(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", marked)).strip())
        if not body:
            continue
        entry = {"start": start, "dur": max(0.5, end - start), "text": body}
        words = body.split()
        if len(stamps) == len(words):
            entry["wt"] = stamps
        elif len(stamps) == len(words) - 1:
            entry["wt"] = [start] + stamps
        entries.append(entry)
    return entries


def parse_ttml(text):
    """Piped subtitle files that arrive as TTML: <p begin end>line</p>."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    ns = {"tt": "http://www.w3.org/ns/ttml"}
    out = []
    for p in root.iter():
        if p.tag.endswith("}p") or p.tag == "p":
            txt = strip_labels(re.sub(r"\s+", " ", "".join(p.itertext())).strip())
            if not txt:
                continue
            st = parse_time_token(p.get("begin"))
            en = parse_time_token(p.get("end"))
            out.append({"start": st, "dur": max(0.5, (en - st) if en > st else 2.0),
                        "text": txt})
    return out


def parse_subtitle_any(text):
    head = text[:600]
    if "<tt" in head:
        return parse_ttml(text)
    return parse_subtitle_text(text)


def parse_track_list(xml_text):
    """Legacy timedtext ?type=list -> [{lang, kind}]."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    tracks = []
    for t in root.iter("track"):
        tracks.append({"lang": t.get("langCode") or t.get("lang") or "",
                       "kind": t.get("kind") or ""})
    return tracks


def parse_caption_xml(xml_text):
    """Legacy timedtext caption track -> entries."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for t in root.iter("text"):
        txt = strip_labels(re.sub(r"\s+", " ", html.unescape("".join(t.itertext()))).strip())
        if not txt:
            continue
        st = float(t.get("start") or 0)
        dur = float(t.get("dur") or 2)
        out.append({"start": st, "dur": max(0.5, dur), "text": txt})
    return out


# ---------------------------------------------------------------------------
# HTTP helpers (urllib honours the environment proxy, like curl does).
# ---------------------------------------------------------------------------
class FetchError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def fetch_text(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                              "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise FetchError(f"http {e.code}", status=e.code)
    except Exception as e:
        raise FetchError(str(e))


def fetch_json(url, timeout=10):
    return json.loads(fetch_text(url, timeout=timeout))


def retry_transient(fn):
    """One quiet retry for the failures that are usually a server hiccup
    (5xx, dropped connection, timeout). A positive 'no captions' or a
    4xx is an answer, not a hiccup, and is never retried."""
    try:
        return fn()
    except Exception as e:
        msg = str(e)
        if msg in ("notracks", "notrack") or msg.startswith("http 4"):
            raise
        time.sleep(0.9)
        return fn()


class NoTracks(Exception):
    pass


def race_attempts(factories):
    """First success wins; the race only reports 'notracks' when every
    attempt failed AND at least one positively said there are no tracks."""
    saw_no_tracks = False
    last_err = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(factories)) as pool:
        futs = {pool.submit(f): f for f in factories}
        done, _ = concurrent.futures.wait(
            futs, return_when=concurrent.futures.FIRST_COMPLETED)
        # FIRST_COMPLETED returns as soon as one finishes — but a failure
        # is not a success, so keep waiting until one succeeds or all fail.
        pending = set(futs)
        while pending:
            done, pending = concurrent.futures.wait(
                pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in done:
                try:
                    return fut.result()
                except NoTracks:
                    saw_no_tracks = True
                except Exception as e:
                    last_err = e
    if saw_no_tracks:
        raise NoTracks("notracks")
    raise last_err or FetchError("unreachable")


# ---------------------------------------------------------------------------
# Caption chain — same order as the web page.
# ---------------------------------------------------------------------------
def choose_track(tracks, lang):
    """Pick the best caption track. lang is a code like 'hi' or 'auto'."""
    want = (lang or "auto").lower()
    manual = [t for t in tracks if t.get("kind") != "asr"]
    auto = [t for t in tracks if t.get("kind") == "asr"]

    def by_lang(pool, code):
        for t in pool:
            if (t.get("lang") or "").lower() == code:
                return t
        base = code.split("-")[0]
        for t in pool:
            if (t.get("lang") or "").lower().split("-")[0] == base:
                return t
        return None

    if want and want != "auto":
        return by_lang(manual, want) or by_lang(auto, want)
    return (manual[0] if manual else None) or (auto[0] if auto else None)


def _fetch_invidious_track(base, vid, lang):
    def _try():
        data = fetch_json(f"{base}/api/v1/captions/{vid}", timeout=10)
        caps = data.get("captions") or []
        if not caps:
            raise NoTracks("notracks")
        tracks = [{"lang": c.get("languageCode") or "", "name": c.get("label") or "",
                   "kind": "asr" if re.search(r"auto", c.get("label") or "", re.I) else "",
                   "url": (c.get("url") if str(c.get("url") or "").startswith("http")
                           else base + (c.get("url") or ""))}
                  for c in caps]
        track = choose_track(tracks, lang)
        if not track:
            raise NoTracks("notrack")
        text = fetch_text(track["url"], timeout=10)
        entries = parse_subtitle_any(text)
        if not entries:
            raise FetchError("empty")
        return entries, track
    return retry_transient(_try)


def captions_via_invidious(vid, lang):
    return race_attempts([lambda b=b: _fetch_invidious_track(b, vid, lang)
                          for b in INVIDIOUS_HOSTS])


def _fetch_piped_track(base, vid, lang):
    def _try():
        data = fetch_json(f"{base}/streams/{vid}", timeout=10)
        if not data or data.get("error"):
            raise FetchError("unreachable")
        subs = [s for s in (data.get("subtitles") or []) if s and s.get("url")]
        if not subs:
            raise NoTracks("notracks")
        tracks = [{"lang": s.get("code") or "", "name": s.get("name") or "",
                   "kind": "asr" if s.get("autoGenerated") else "",
                   "url": s.get("url")} for s in subs]
        track = choose_track(tracks, lang)
        if not track:
            raise NoTracks("notrack")
        url = track["url"]
        if "fmt=ttml" in url:
            url = url.replace("fmt=ttml", "fmt=vtt")
        elif "fmt=" not in url:
            url += ("&" if "?" in url else "?") + "fmt=vtt"
        text = fetch_text(url, timeout=10)
        entries = parse_subtitle_any(text)
        if not entries:
            raise FetchError("empty")
        return entries, track
    return retry_transient(_try)


def captions_via_piped(vid, lang):
    return race_attempts([lambda b=b: _fetch_piped_track(b, vid, lang)
                          for b in PIPED_HOSTS])


def captions_via_legacy(vid, lang):
    xml = fetch_text(f"https://www.youtube.com/api/timedtext?v={vid}&type=list",
                     timeout=10)
    tracks = parse_track_list(xml)
    if not tracks:
        raise NoTracks("notracks")
    track = choose_track(tracks, lang)
    if not track:
        raise NoTracks("notrack")
    url = (f"https://www.youtube.com/api/timedtext?v={vid}"
           f"&lang={urllib.parse.quote(track['lang'])}")
    if track.get("kind") == "asr":
        url += "&kind=asr"
    entries = parse_caption_xml(fetch_text(url, timeout=10))
    if not entries:
        raise FetchError("empty")
    return entries, track


def get_captions(vid, lang):
    """Invidious + Piped raced together, legacy timedtext last."""
    saw_no_tracks = False

    def _pub():
        try:
            return race_attempts([lambda: captions_via_invidious(vid, lang),
                                  lambda: captions_via_piped(vid, lang)])
        except NoTracks:
            raise
        except Exception as e:
            raise e

    try:
        return _pub()
    except NoTracks:
        saw_no_tracks = True
    except Exception:
        pass
    try:
        return captions_via_legacy(vid, lang)
    except NoTracks:
        saw_no_tracks = True
    except Exception:
        pass
    if saw_no_tracks:
        raise NoTracks("This video has no captions to fetch.")
    raise FetchError("YouTube would not hand this video's captions to a "
                     "server through any route — that is YouTube's block, "
                     "not your internet.")


def video_id(url):
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return ""
    if "youtu.be" in u.netloc:
        return u.path.strip("/").split("/")[0]
    q = urllib.parse.parse_qs(u.query)
    return (q.get("v") or [""])[0]


def video_meta(vid):
    """Title + channel, best effort: oEmbed first, Invidious as backup."""
    try:
        d = fetch_json("https://www.youtube.com/oembed?url=" +
                       urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")
                       + "&format=json", timeout=10)
        if d.get("title"):
            return {"title": d.get("title", ""), "author": d.get("author_name", ""),
                    "author_url": d.get("author_url", "")}
    except Exception:
        pass
    try:
        entries, _ = race_attempts(
            [lambda b=b: (fetch_json(f"{b}/api/v1/videos/{vid}", timeout=10), None)[0]
             for b in INVIDIOUS_HOSTS[:3]])
        if isinstance(entries, dict) and entries.get("title"):
            return {"title": entries.get("title", ""), "author": entries.get("author", ""),
                    "author_url": ("https://www.youtube.com" + entries["authorUrl"])
                    if entries.get("authorUrl") else ""}
    except Exception:
        pass
    return {"title": "", "author": "", "author_url": ""}

# ---------------------------------------------------------------------------
# Second-by-second lines — the single shape both versions share.
# ---------------------------------------------------------------------------
def _norm_vote_word(w):
    w = str(w).lower()
    w = re.sub(r"[.,!?\"'’\";:()\[\]—\-]", "", w)
    w = w.replace("ं", "").replace("ँ", "").replace("़", "")
    return w


def majority_vote(lines):
    """Songs repeat the same line many times and the captions render it
    differently each time. Group lines by their normalised word sequence
    and spell every occurrence the way it most often appears. Only within
    clearly repeated lines: same words in a different order or spelling,
    same length give or take one word. Never merge different lines: when
    one line's words are all inside the other's they are adjacent slices
    of one sung line, not the same line repeated. Each group merges at
    most once, so merges never chain. Only rewrites when the top spelling
    appears at least twice and strictly more than the runner-up; ties and
    single lines stay untouched. Never changes a timestamp.
    lines: [(sec, text)] -> same shape, same order, same seconds."""
    from collections import Counter
    n = len(lines)
    if n < 2:
        return lines
    norm = [[_norm_vote_word(w) for w in text.split()] for _, text in lines]
    norm = [[w for w in ws if w] for ws in norm]
    keys = [" ".join(sorted(ws)) for ws in norm]
    groups = {}
    order = []
    for i, k in enumerate(keys):
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(i)

    def jaccard(a, b):
        ca, cb = Counter(a), Counter(b)
        inter = sum((ca & cb).values())
        uni = sum((ca | cb).values())
        return inter / uni if uni else 0.0

    def is_subset(shorter, longer):
        cs, cl = Counter(shorter), Counter(longer)
        return all(cl[w] >= c for w, c in cs.items())

    def key_words(k):
        return k.split() if k else []

    pairs = []
    for a in range(len(order)):
        for b in range(a + 1, len(order)):
            ka, kb = key_words(order[a]), key_words(order[b])
            if abs(len(ka) - len(kb)) > 1:
                continue
            if jaccard(ka, kb) < 0.8:
                continue
            shorter, longer = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
            if is_subset(shorter, longer):
                continue
            pairs.append((jaccard(ka, kb), order[a], order[b]))
    pairs.sort(key=lambda p: -p[0])
    merged = set()
    for _, ka, kb in pairs:
        if ka in merged or kb in merged:
            continue
        groups[ka] = groups[ka] + groups[kb]
        del groups[kb]
        merged.add(ka)
        merged.add(kb)
    out = list(lines)
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        counts = {}
        for i in idxs:
            counts[lines[i][1]] = counts.get(lines[i][1], 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        best, best_n = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        if best_n >= 2 and best_n > second:
            for i in idxs:
                out[i] = (lines[i][0], best)
    return out


def second_buckets(entries):
    """Chronological words; only overlapping rolling caption suffixes may be removed."""
    tokens = []
    previous = None
    def key(w):
        return ''.join(c for c in w.casefold() if c.isalnum() or '\u0900' <= c <= '\u0d7f')
    for e in sorted(entries, key=lambda e: e['start']):
        words = strip_cue_marks(e['text']).split()
        if not words:
            continue
        start, dur = e['start'], max(.02, e.get('dur') or 1)
        wt = e.get('wt')
        timed = bool(wt and len(wt) == len(words))
        skip = 0
        if previous and start < previous[0] - .025 and not e.get('audio') and not previous[2]:
            old = previous[1]
            for k in range(min(len(old),len(words)), 1, -1):
                if [key(w) for w in old[-k:]] == [key(w) for w in words[:k]]:
                    skip=k
                    break
        for i, word in enumerate(words):
            if i < skip:
                continue
            tm = wt[i] if timed else start+dur*i/len(words)
            if skip and not timed and tokens:
                tm=max(tm,tokens[-1][0]+.02)
            tokens.append((tm,word))
        previous=(start+dur,words,e.get('audio',False))
    buckets={}
    for tm,word in sorted(tokens,key=lambda x:x[0]):
        buckets.setdefault(int(math.floor(tm)),[]).append(word)
    return [(sec,' '.join(buckets[sec])) for sec in sorted(buckets)]


def timed_lines(entries, english=False):
    lines = []
    for sec, words in second_buckets(entries):
        if english:
            words = re.sub(r"\s+", " ", romanize(words)).strip() or words
        lines.append(f"[{fmt_sec(sec)}] {words}")
    return lines


def build_result(title, author, vid, lang, kind, entries, source):
    """The two timed versions, exactly like the project's two files."""
    original = timed_lines(entries, english=False)
    english = timed_lines(entries, english=True)
    header = []
    if title:
        header.append(title)
    if vid:
        header.append(f"https://www.youtube.com/watch?v={vid}")
    header.append(f"Language: {lang or 'auto-detected'}"
                  + (f" ({kind})" if kind else ""))
    header.append(f"Source: {source}")
    head = "\n".join(header)
    return {
        "title": title,
        "author": author,
        "video_id": vid,
        "language": lang,
        "kind": kind,
        "source": source,
        "lines": len(original),
        "original": original,
        "english_letters": english,
        "text": (head + "\n\n--- Words in the original language ---\n"
                 + "\n".join(original)
                 + "\n\n--- The same words in English letters ---\n"
                 + "\n".join(english) + "\n"),
    }


# ---------------------------------------------------------------------------
# transcribe_audio — Groq / OpenAI Whisper, same as the project's server.py.
# ---------------------------------------------------------------------------
def detect_provider(key):
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("sk-proj-") or key.startswith("sk-"):
        return "openai"
    return None


def _https_json(host, path, key, method="GET", body=None, headers=None):
    """HTTPS request that honours the environment proxy (some networks,
    including this sandbox, only reach the internet through one —
    http.client does not read proxy variables on its own, so tunnel
    through it explicitly when one is set)."""
    proxy_url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    ctx = ssl.create_default_context()
    if proxy_url:
        pu = urllib.parse.urlparse(proxy_url)
        conn = http.client.HTTPConnection(pu.hostname, pu.port or 8080,
                                          timeout=120)
        tunnel_headers = {}
        if pu.username:
            import base64
            creds = f"{urllib.parse.unquote(pu.username)}:{urllib.parse.unquote(pu.password or '')}"
            tunnel_headers["Proxy-Authorization"] = (
                "Basic " + base64.b64encode(creds.encode()).decode())
        conn.set_tunnel(host, 443, headers=tunnel_headers)
    else:
        conn = http.client.HTTPSConnection(host, timeout=120, context=ctx)
    hdrs = dict(headers or {})
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    try:
        parsed = json.loads(data or b"{}")
    except json.JSONDecodeError:
        parsed = {}
    return resp.status, parsed


def _read_audio(source):
    """Local file or URL -> (bytes, filename, ext). Capped at ~25 MB."""
    if re.match(r"^https?://", source or "", re.I):
        req = urllib.request.Request(source, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read(MAX_AUDIO_BYTES + 1)
        name = os.path.basename(urllib.parse.urlparse(source).path) or "audio"
        ext = os.path.splitext(name)[1].lstrip(".") or "webm"
        filename = name if "." in name else f"audio.{ext}"
    else:
        path = os.path.expanduser(source)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No audio file at: {source}")
        with open(path, "rb") as f:
            data = f.read(MAX_AUDIO_BYTES + 1)
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lstrip(".") or "webm"
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError("Audio is over 25 MB — the provider refuses files "
                         "that big. Use a shorter clip.")
    if not data:
        raise ValueError("Audio file is empty.")
    return data, filename, ext


def transcribe_audio(source, api_key, provider="groq", lang=""):
    if not api_key:
        raise ValueError("An API key is needed to listen to audio.")
    provider = (provider or "auto").lower()
    if provider in ("auto", ""):
        provider = detect_provider(api_key) or ""
    if provider not in WHISPER_PROVIDERS:
        raise ValueError("Provider must be groq or openai (or a groq "
                         "gsk_ / openai sk- key, which is detected).")
    cfg = WHISPER_PROVIDERS[provider]
    audio, filename, ext = _read_audio(source)
    last_error = None
    for model in cfg["models"]:
        boundary = uuid.uuid4().hex

        def field(name, value):
            return (f"--{boundary}\r\nContent-Disposition: form-data; "
                    f"name=\"{name}\"\r\n\r\n{value}\r\n").encode()

        body = field("model", model)
        body += field("response_format", "verbose_json")
        body += field("timestamp_granularities[]", "word")
        body += field("timestamp_granularities[]", "segment")
        body += field("temperature", "0")
        if lang:
            body += field("language", lang)
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"file\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: audio/{ext}\r\n\r\n").encode()
        body += audio + f"\r\n--{boundary}--\r\n".encode()
        status, data = _https_json(
            cfg["host"], cfg["path"], api_key, method="POST", body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        if status == 200:
            words = []
            for w in data.get("words") or []:
                if (w.get("word") or "").strip():
                    words.append((float(w["start"]), float(w.get("end") or w["start"]),
                                  w["word"].strip()))
            if not words:
                for seg in data.get("segments") or []:
                    if (seg.get("text") or "").strip():
                        words.append((float(seg["start"]), float(seg["end"]),
                                      seg["text"].strip()))
            entries = entries_from_words(words)
            detected = lang or data.get("language") or ""
            return build_result("", "", "", detected, "whisper",
                                entries, f"{provider} {model} (listened)")
        last_error = (data.get("error") or {}).get("message") or f"HTTP {status}"
    raise RuntimeError(f"{provider} said no: {last_error}")


def entries_from_words(words):
    """Group per-word timings into short lines at real pauses, keeping
    each word's exact second — port of the web page's entriesFromWords."""
    entries = []
    cur = None
    cur_end = 0.0
    for st, en, wtext in words:
        wtext = strip_cue_marks(str(wtext).strip())
        if not wtext:
            continue
        en = en if en > st else st + 0.3
        if (not cur or st - cur_end > 0.6 or en - cur["start"] > 3.2
                or len(cur["wt"]) >= 12):
            cur = {"start": st, "dur": max(0.3, en - st), "text": wtext, "wt": [st], "audio": True}
            entries.append(cur)
        else:
            cur["text"] += " " + wtext
            cur["wt"].append(st)
            cur["dur"] = max(cur["dur"], en - cur["start"])
        cur_end = max(cur_end, en)
    return entries


def transcribe_youtube(url, lang="auto"):
    vid = video_id(url)
    if not vid:
        raise ValueError("That does not look like a YouTube link.")
    lang = (lang or "auto").lower()
    meta = video_meta(vid)
    entries, track = get_captions(vid, lang)
    # Clean every entry once more — the parsers already strip cues, but
    # a cue-only line must never survive into the output.
    entries = [dict(e, text=strip_labels(e["text"]))
               for e in entries if strip_labels(e["text"])]
    if not entries:
        raise NoTracks("This video has no captions to fetch.")
    track_lang = (track.get("lang") or "") or (meta.get("title") and "")
    kind = "auto captions" if track.get("kind") == "asr" else "captions"
    return build_result(meta.get("title", ""), meta.get("author", ""), vid,
                        track_lang or lang, kind, entries,
                        "captions (Invidious/Piped/legacy)")


# ---------------------------------------------------------------------------
# MCP over stdio — newline-delimited JSON-RPC 2.0.
# ---------------------------------------------------------------------------
TOOLS = [
    {"name":"verify_local_audio", "description":"Audio-first universal verification for an authorized local media file. Uses installed computer engine; optional Groq and Deepgram keys send audio to those providers. Returns evidence, not a guaranteed accuracy score.", "inputSchema":{"type":"object","properties":{"path":{"type":"string"},"mode":{"type":"string","enum":["fast","advanced","maximum"]},"language":{"type":"string"},"groq":{"type":"string"},"deepgram":{"type":"string"},"local":{"type":"boolean"}},"required":["path"]}},
    {
        "name": "transcribe_youtube",
        "description": (
            "Transcribe a YouTube video. Captions-first: public Invidious "
            "mirrors raced in parallel, then Piped, then YouTube's legacy "
            "timedtext. Returns timed lines with [MM:SS] stamps in the "
            "original language PLUS the same lines in English letters "
            "(romanized pronunciation, never a translation). Sound "
            "descriptions like [music], [Sangeet] or [BLANK_AUDIO] are "
            "removed. If the video has no captions, it says so plainly "
            "instead of guessing — use transcribe_audio with an API key "
            "for those videos."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string",
                        "description": "YouTube watch link or youtu.be link."},
                "lang": {"type": "string", "default": "auto",
                         "description": "Caption language code (e.g. 'hi', "
                                        "'en') or 'auto' to take the best "
                                        "available track."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "transcribe_audio",
        "description": (
            "Transcribe an audio or video file by sending it to Groq or "
            "OpenAI Whisper. Returns the same two timed versions as "
            "transcribe_youtube: [MM:SS] lines in the original language "
            "plus the same lines in English letters. Needs an API key "
            "(Groq gsk_ or OpenAI sk-); the key is sent only to its own "
            "provider. Files over 25 MB are refused."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "audio_path_or_url": {
                    "type": "string",
                    "description": "Local file path, or an http(s) URL to "
                                   "an audio/video file (max 25 MB)."},
                "api_key": {"type": "string",
                            "description": "Groq (gsk_...) or OpenAI "
                                           "(sk-...) API key."},
                "provider": {"type": "string", "default": "groq",
                             "description": "'groq', 'openai', or 'auto' "
                                            "(detected from the key)."},
                "lang": {"type": "string", "default": "",
                         "description": "Optional spoken-language code "
                                        "(e.g. 'hi')."},
            },
            "required": ["audio_path_or_url", "api_key"],
        },
    },
]


def _tool_result(text, is_error=False):
    return {"content": [{"type": "text", "text": text}],
            "isError": is_error}


def _handle(method, params):
    if method == "initialize":
        return {"protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "youtube-transcribe-downloader",
                               "version": VERSION}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = (params or {}).get("name")
        args = (params or {}).get("arguments") or {}
        try:
            if name == "verify_local_audio":
                import pathlib, contextlib
                sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
                import universal_engine, universal_server
                source=pathlib.Path(args.get("path", "")).expanduser()
                if not source.is_file(): return _tool_result("Choose an existing authorized local media file.", True)
                opts=universal_server.settings(args)
                with contextlib.redirect_stdout(sys.stderr):
                    result=universal_engine.run(source,opts)
                return _tool_result(json.dumps(result,ensure_ascii=False))
            if name == "transcribe_youtube":
                result = transcribe_youtube(args.get("url", ""),
                                            args.get("lang") or "auto")
                return _tool_result(result["text"])
            if name == "transcribe_audio":
                result = transcribe_audio(args.get("audio_path_or_url", ""),
                                          args.get("api_key", ""),
                                          args.get("provider") or "groq",
                                          args.get("lang") or "")
                return _tool_result(result["text"])
            return _tool_result(f"Unknown tool: {name}", is_error=True)
        except NoTracks as e:
            return _tool_result(
                "No captions for this video, and no API key was given.\n"
                "This video has no captions to fetch — nothing to "
                "transcribe from. To do it anyway, use transcribe_audio "
                "with a Groq/OpenAI key and the video's sound file, or "
                "the offline computer pack in this project.\n"
                f"(Detail: {e})", is_error=True)
        except Exception as e:
            return _tool_result(f"Could not transcribe: {e}", is_error=True)
    raise ValueError(f"Method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        req_id = msg.get("id")
        # Notifications (no id) need no reply.
        if req_id is None:
            continue
        try:
            result = _handle(method, msg.get("params") or {})
            reply = {"jsonrpc": "2.0", "id": req_id, "result": result}
        except ValueError as e:
            reply = {"jsonrpc": "2.0", "id": req_id,
                     "error": {"code": -32601, "message": str(e)}}
        except Exception as e:
            reply = {"jsonrpc": "2.0", "id": req_id,
                     "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
