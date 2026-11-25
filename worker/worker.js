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
// The visitor's API key is NEVER stored or logged — it is only forwarded
// to the provider it belongs to, for that one request.
// Deploy (once, free): see worker/README.md in this folder.

const PROVIDERS = {
  groq: "https://api.groq.com/openai/v1/audio/transcriptions",
  openai: "https://api.openai.com/v1/audio/transcriptions",
};

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
    const text = ev.segs.map((s) => s.utf8 || "").join("").replace(/\n/g, " ").trim();
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
async function transcribeLink(request) {
  const body = await request.json().catch(() => ({}));
  const provider = (body.provider || "").toString();
  const key = (body.api_key || "").toString();
  const lang = (body.language || "").toString();
  const title = (body.title || "").toString();
  const id = videoId(body.url || "");
  if (!id) return json({ ok: false, error: "That does not look like a YouTube link." }, 400);
  if (!PROVIDERS[provider]) return json({ ok: false, error: "Provider must be groq or openai." }, 400);
  if (!key) return json({ ok: false, error: "An API key is needed." }, 400);

  // Ask YouTube's player API (Android client) for this video's streams.
  const player = await fetch(
    "`https://www.youtube.com/youtubei/v1/player?key=${encodeURIComponent(key)}&prettyPrint=false`",
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
