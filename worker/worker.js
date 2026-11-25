// YouTube Transcribe Downloader — tiny free helper (Cloudflare Worker).
// Why this exists: a plain web page (GitHub Pages) cannot pull the sound
// out of a YouTube video, and Groq / OpenAI block direct browser calls.
// This worker does the two server-side jobs, and nothing else:
//   1. GET  /api/captions?url=<youtube link>&lang=<code>
//      Fetches the video's captions from YouTube (server-side) and
//      returns them as timed lines.
//   2. POST /api/transcribe  (multipart: file, provider, api_key, model?)
//      Forwards the visitor's audio file to Groq / OpenAI Whisper and
//      returns the timed transcript.
//   3. POST /api/transcribe_link  (JSON: url, provider, api_key, model?, language?, title?)
//      Fetches the video's sound server-side (YouTube player API) and
//      transcribes it with the visitor's provider: Groq / OpenAI Whisper,
//      or Google Gemini (Files API + generateContent, [MM:SS] lines).
// The visitor's API key is NEVER stored or logged — it is only forwarded
// to the provider it belongs to, for that one request.
// Deploy (once, free): see worker/README.md in this folder.

const PROVIDERS = {
  groq: "https://api.groq.com/openai/v1/audio/transcriptions",
  openai: "https://api.openai.com/v1/audio/transcriptions",
};

// Gemini does not have a Whisper-style audio endpoint: it transcribes
// through generateContent, with the sound uploaded first (Files API)
// and the words asked for as [MM:SS] stamped lines.
const GEMINI_FILES = "https://generativelanguage.googleapis.com/upload/v1beta/files";
const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";
const GEMINI_DEFAULT_MODEL = "gemini-2.5-flash";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, authorization",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

// Sound-description cues — same lists as the web page, the Python pack
// and the MCP server. A transcript holds only sung or spoken words;
// [music], [संगीत], [गाना गाने की आवाज़], [हांफने की आवाज़] and the
// rest are cleaned off at every step. A real sung line is never
// touched, even if it mentions music: only bracketed marks and
// cue-only lines are removed. (The worker has no romanizer: Devanagari
// cues are caught by RAW_CUES below, Latin cue words match directly.)
const CUE_WORDS = new Set(("music musica musik musique muzyka pauza eumak " +
  "sangeet sangeeta sangeeth sangit dhun dhuna taal taaliyaan taaliyan hansee hansi " +
  "viraama gaayana vaadya myoosik myoosika gaanaa gaane aavaaza haanphane shora " +
  "pause tune applause laughter laughing cheering cheers singing humming instrumental " +
  "interlude intro outro silence silent noise beep beeping clapping whispering murmuring " +
  "chatter gasp gasping sigh sighing coughing crying sobbing shouting screaming ringing alarm " +
  "footsteps thunder melody beat beats rhythm song songs blankaudio nospeech speech inaudible " +
  "unintelligible crosstalk").split(" "));
const CUE_FILLER = new Set(("soft loud background playing plays play played dramatic upbeat gentle " +
  "slow melodic cheerful tense suspenseful rhythmic traditional continues continuing fades fading " +
  "distant muffled echoing theme and the a an of in on no kee").split(" "));
const RAW_CUES = ["संगीत", "धुन", "तालियाँ", "तालियां", "ताली", "हँसी", "हंसी", "विराम", "वाद्य",
  "म्यूसिक", "म्यूज़िक", "गाना गाने की आवाज़", "हांफने की आवाज़", "शोर",
  "موسيقى", "الموسيقى", "音楽", "음악", "音乐", "音樂", "blank_audio"];
function isCueText(s) {
  const raw = String(s || "").trim().toLowerCase();
  if (!raw) return false;
  if (raw.split(/\s+/).filter(Boolean).length <= 4) {
    for (const r of RAW_CUES) if (raw.indexOf(r) >= 0) return true;
  }
  const words = raw.split(/\s+/).filter(Boolean);
  let hasCue = false;
  for (const w of words) {
    if (CUE_WORDS.has(w)) hasCue = true;
    else if (!CUE_FILLER.has(w)) return false;
  }
  return hasCue;
}
function stripCueMarks(text) {
  let t = String(text || "").replace(/[♪♫]/g, " ");
  t = t.replace(/\[([^\]]*)\]|\(([^)]*)\)/g, (m, b, p) =>
    isCueText(b !== undefined ? b : p) ? " " : m);
  // Split brackets: a cue cut across seconds leaves fragments like
  // "[गाना" or "आवाज़]" — drop one only when its bracket-free text
  // is itself a sound description.
  const kept = [];
  for (const tok of t.split(/\s+/)) {
    if (!tok) continue;
    if (/[\[\]]/.test(tok)) {
      const inner = tok.replace(/[\[\]()]/g, "").trim();
      if (inner && isCueText(inner)) continue;
    }
    kept.push(tok);
  }
  return kept.join(" ").replace(/\s+/g, " ").trim();
}
function stripLabels(text) {
  const t = stripCueMarks(text);
  return (t && isCueText(t)) ? "" : t;
}

function videoId(url) {
  try {
    const u = new URL(url);
    if (u.hostname.includes("youtu.be")) return u.pathname.slice(1);
    return u.searchParams.get("v") || "";
  } catch {
    return "";
  }
}

async function captions(url, lang) {
  const id = videoId(url);
  if (!id) return json({ ok: false, error: "That does not look like a YouTube link." }, 400);
  const page = await fetch(`https://www.youtube.com/watch?v=${id}`, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9",
    },
  });
  if (!page.ok) {
    return json({ ok: false, error: "YouTube did not answer. Try again, or use the offline pack." }, 502);
  }
  const html = await page.text();
  const m = html.match(/"captionTracks":(\[.*?\])/);
  if (!m) {
    return json({ ok: false, error: "This video has no captions to fetch.", hasCaptions: false });
  }
  const tracks = JSON.parse(m[1]);
  const track =
    tracks.find((t) => t.languageCode === lang) ||
    tracks.find((t) => t.languageCode === (lang || "").split("-")[0]) ||
    tracks.find((t) => t.languageCode === "en") ||
    tracks[0];
  const timed = await fetch(track.baseUrl + "&fmt=json3", {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  const data = await timed.json();
  const lines = [];
  for (const ev of data.events || []) {
    if (!ev.segs) continue;
    const text = stripLabels(ev.segs.map((s) => s.utf8 || "").join("").replace(/\n/g, " ").trim());
    if (text) lines.push({ start: (ev.tStartMs || 0) / 1000, text });
  }
  return json({ ok: true, language: track.languageCode, kind: track.kind || "standard", lines });
}

async function transcribe(request) {
  const form = await request.formData();
  const provider = (form.get("provider") || "").toString();
  const key = (form.get("api_key") || "").toString();
  const file = form.get("file");
  if (!PROVIDERS[provider]) return json({ ok: false, error: "Provider must be groq or openai." }, 400);
  if (!key || !file) return json({ ok: false, error: "An API key and a sound file are needed." }, 400);
  return forwardToWhisper(provider, key, file, file.name || "audio.webm",
    (form.get("model") || "").toString(), (form.get("language") || "").toString());
}

async function forwardToWhisper(provider, key, audio, filename, model, lang) {
  const out = new FormData();
  out.append("file", audio, filename);
  out.append("model", model || (provider === "groq" ? "whisper-large-v3-turbo" : "whisper-1"));
  out.append("response_format", "verbose_json");
  out.append("timestamp_granularities[]", "word");
  if (lang) out.append("language", lang);
  const res = await fetch(PROVIDERS[provider], {
    method: "POST",
    headers: { Authorization: `Bearer ${key}` },
    body: out,
  });
  const data = await res.json();
  if (!res.ok) {
    return json({ ok: false, error: data?.error?.message || `The provider said no (${res.status}).` }, res.status);
  }
  return json({ ok: true, provider, ...data });
}

// The YouTube player API needs an API key, but we NEVER hard-code one
// in this repo — GitGuardian / GitHub push protection rightly flag any
// key-shaped string in code. Instead, fetch YouTube's own public web
// key from its homepage at runtime (the same key YouTube's own website
// ships to every visitor) and cache it for this worker instance.
let _innertubeKey = null;
async function innertubeKey() {
  if (_innertubeKey) return _innertubeKey;
  const home = await fetch("https://www.youtube.com/", {
    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" },
  });
  const html = await home.text();
  const m = html.match(/"INNERTUBE_API_KEY":"([^"]+)"/);
  if (!m) throw new Error("Could not read YouTube's player key.");
  _innertubeKey = m[1];
  return _innertubeKey;
}
// A web page cannot pull audio out of YouTube — YouTube blocks it.
// A server CAN ask YouTube's own player API (the Android client) for the
// audio stream, download it, and send it to the provider's Whisper.
// That is what this endpoint does. Limits, stated plainly:
//  - Audio is capped at ~25 MB (the provider's upload limit) — long
//    videos are cut to roughly the first 25 MB.
//  - Some videos hide their audio behind a signature YouTube will not
//    give this way; those return a clear error, and the listening panel
//    or the computer pack is the way for them.
//  - It is not real-time and not perfect: the audio is downloaded, then
//    transcribed, and sung words can still be misheard.
// Gemini transcription for a downloaded audio file. The sound is
// uploaded once (Files API — no base64 blow-up), then generateContent is
// asked for the words as [MM:SS] stamped lines, words only, never a
// translation. The stamped lines come back as segments the page renders
// exactly like Whisper segments. If Gemini will not stamp the lines,
// the plain words come back as text and the page shows them as one block.
// The uploaded file is deleted afterwards on a best-effort basis.
function parseStampedLines(text) {
  const segs = [];
  for (const raw of String(text || "").split(/\r?\n/)) {
    const m = raw.match(/^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*(.+)$/);
    if (!m) continue;
    const start = m[3] !== undefined
      ? (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3])
      : (+m[1]) * 60 + (+m[2]);
    const line = stripLabels(m[4].replace(/\s+/g, " ").trim());
    if (line) segs.push({ start, text: line });
  }
  return segs;
}

async function transcribeWithGemini(key, file, model, lang, title) {
  const useModel = (model || "").trim() || GEMINI_DEFAULT_MODEL;
  const promptBits = [];
  if (title) promptBits.push(`The video is titled "${title}". Use it for names of people, places and songs.`);
  promptBits.push(
    "Transcribe every word in this audio exactly as heard — names, fast lines and sung words included. " +
    "Do not add words that are not sung or spoken. Never write sound descriptions like [music], [pause], [संगीत], [गाना गाने की आवाज़] or [हांफने की आवाज़] — words only, " +
    "in the language they are sung or spoken in, never translated. " +
    "Write one line per few seconds, each line starting with its time as [MM:SS], for example [00:07] the words here."
  );
  if (lang) promptBits.push(`The language is ${lang}; keep the words in that language.`);
  const prompt = promptBits.join(" ");

  // 1. Upload the sound (Files API, multipart).
  const upForm = new FormData();
  upForm.append("metadata", new Blob([JSON.stringify({ file: { displayName: file.name || "audio" } })], { type: "application/json" }));
  upForm.append("file", file);
  const upRes = await fetch(`${GEMINI_FILES}?uploadType=multipart`, {
    method: "POST",
    headers: { "x-goog-api-key": key },
    body: upForm,
  });
  const upData = await upRes.json().catch(() => ({}));
  const fileUri = upData?.file?.uri;
  const fileMime = upData?.file?.mimeType || file.type || "audio/webm";
  if (!upRes.ok || !fileUri) {
    return json({ ok: false, error: upData?.error?.message || `Gemini would not take the sound (${upRes.status}).` }, upRes.status || 502);
  }

  // 2. Ask for the stamped words.
  let text = "";
  try {
    const genRes = await fetch(`${GEMINI_BASE}/models/${encodeURIComponent(useModel)}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": key },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }, { fileData: { mimeType: fileMime, fileUri } }] }],
        generationConfig: { temperature: 0 },
      }),
    });
    const genData = await genRes.json().catch(() => ({}));
    if (!genRes.ok) {
      return json({ ok: false, error: genData?.error?.message || `Gemini said no (${genRes.status}).` }, genRes.status);
    }
    const parts = genData?.candidates?.[0]?.content?.parts || [];
    text = parts.map((p) => p.text || "").join("");
  } finally {
    // 3. Best-effort delete of the uploaded sound — never fail the answer over it.
    const name = String(fileUri).split("/").pop();
    if (name) {
      await fetch(`${GEMINI_BASE}/files/${encodeURIComponent(name)}`, {
        method: "DELETE",
        headers: { "x-goog-api-key": key },
      }).catch(() => {});
    }
  }
  // Strip any bracketed sound-description lines Gemini slipped in anyway.
  const clean = String(text || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !/^\[(music|song|sangeet|instrumental|applause|laughter|silence|pause)\]/i.test(l))
    .join("\n");
  const segments = parseStampedLines(clean);
  if (segments.length) return json({ ok: true, provider: "gemini", language: lang || "", segments });
  if (clean) return json({ ok: true, provider: "gemini", language: lang || "", text: clean });
  return json({ ok: false, error: "Gemini listened but wrote no words. Try again, or use the listening panel." }, 502);
}

async function transcribeLink(request) {
  const body = await request.json().catch(() => ({}));
  const provider = (body.provider || "").toString();
  const key = (body.api_key || "").toString();
  const lang = (body.language || "").toString();
  const title = (body.title || "").toString();
  const id = videoId(body.url || "");
  if (!id) return json({ ok: false, error: "That does not look like a YouTube link." }, 400);
  if (provider !== "gemini" && !PROVIDERS[provider]) return json({ ok: false, error: "Provider must be groq, openai or gemini." }, 400);
  if (!key) return json({ ok: false, error: "An API key is needed." }, 400);

  // Ask YouTube's player API (Android client) for this video's streams.
  // The player key is YouTube's own public web key, read from its
  // homepage at runtime by innertubeKey() — never hard-coded, and never
  // the visitor's provider key.
  const ytKey = await innertubeKey();
  const player = await fetch(
    `https://www.youtube.com/youtubei/v1/player?key=${encodeURIComponent(ytKey)}&prettyPrint=false`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
        Origin: "https://www.youtube.com",
      },
      body: JSON.stringify({
        context: {
          client: {
            clientName: "ANDROID", clientVersion: "19.09.37",
            deviceMake: "Google", deviceModel: "Pixel 7",
            osName: "Android", osVersion: "13", androidSdkVersion: 33,
          },
        },
        videoId: id, racyCheckOk: true, contentCheckOk: true,
      }),
    });
  if (!player.ok) {
    return json({ ok: false, error: "YouTube did not answer. Try again, or use the listening panel or the computer pack." }, 502);
  }
  const pdata = await player.json();
  const formats = [...(pdata.streamingData?.adaptiveFormats || []), ...(pdata.streamingData?.formats || [])];
  // Audio-only streams, with a direct URL (no signature to unscramble).
  const audioFmt = formats
    .filter((f) => (f.mimeType || "").startsWith("audio/") && f.url)
    .sort((a, b) => (a.bitrate || 0) - (b.bitrate || 0))[0];
  if (!audioFmt) {
    return json({ ok: false, error: "YouTube would not give this video's audio to a server. Use the listening panel (upload the sound file) or the computer pack." }, 502);
  }
  const audioRes = await fetch(audioFmt.url, {
    headers: { Range: "bytes=0-26214399", "User-Agent": "Mozilla/5.0" },
  });
  if (!audioRes.ok && audioRes.status !== 206) {
    return json({ ok: false, error: "Could not download this video's audio. Use the listening panel or the computer pack." }, 502);
  }
  const buf = await audioRes.arrayBuffer();
  const ext = (audioFmt.mimeType || "").includes("webm") ? "webm" : "m4a";
  const file = new File([buf], `audio.${ext}`, { type: `audio/${ext}` });
  // Gemini transcribes through generateContent, not a Whisper endpoint.
  if (provider === "gemini") {
    return transcribeWithGemini(key, file, (body.model || "").toString(), lang, title);
  }
  const out = new FormData();
  out.append("file", file);
  out.append("model", (body.model || (provider === "groq" ? "whisper-large-v3-turbo" : "whisper-1")).toString());
  out.append("response_format", "verbose_json");
  out.append("timestamp_granularities[]", "word");
  if (title) out.append("prompt", title);
  if (lang) out.append("language", lang);
  const res = await fetch(PROVIDERS[provider], {
    method: "POST",
    headers: { Authorization: `Bearer ${key}` },
    body: out,
  });
  const data = await res.json();
  if (!res.ok) {
    return json({ ok: false, error: data?.error?.message || `The provider said no (${res.status}).` }, res.status);
  }
  return json({ ok: true, provider, ...data });
}

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    const url = new URL(request.url);
    try {
      if (url.pathname === "/api/captions" && request.method === "GET") {
        return captions(url.searchParams.get("url") || "", url.searchParams.get("lang") || "");
      }
      if (url.pathname === "/api/transcribe" && request.method === "POST") {
        return transcribe(request);
      }
      if (url.pathname === "/api/transcribe_link" && request.method === "POST") {
        return transcribeLink(request);
      }
      if (url.pathname === "/api/health") return json({ ok: true });
      return json({ ok: false, error: "Unknown address." }, 404);
    } catch (e) {
      return json({ ok: false, error: String(e?.message || e) }, 500);
    }
  },
};
