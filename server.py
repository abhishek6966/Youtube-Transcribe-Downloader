#!/usr/bin/env python3
"""YouTube Transcribe Downloader — HTML version (one click).

Double-click start_html.bat: it starts this server and opens the nice
HTML page in your browser. Paste a link, click Get Transcript.

How it works:
  1. Captions first (seconds, exact if manual) — via youtube-transcript-api,
     running on YOUR PC, so YouTube sees your IP, not a shared server.
  2. If no captions, click "Transcribe audio" — Whisper large-v3-turbo
     runs locally (slow on CPU, first run downloads ~800 MB model once).
No video is downloaded for captions. Audio is downloaded only for step 2.
"""
import json
import os
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765

# Reuse v2's captions + romanization code (no duplication).
import yt_transcript_v2 as v2
import universal_server as studio

# API-key providers (in memory only — the key is NEVER written to disk,
# never logged, and never sent to Muse. It lives only in this server
# process on the user's own PC, and is sent only to the provider it
# belongs to, to list models / transcribe audio.)
# Honest limits: only Groq and OpenAI have a real audio-transcription
# endpoint that can do this job fast. DeepSeek / Anthropic / NVIDIA
# are text-only or have no simple audio endpoint, so a key for those
# is detected and reported, but cannot transcribe audio here.
# "100+ providers" is not possible from one key alone — keys have no
# standard label saying which company they belong to, so detection
# uses the key's prefix, then confirms with that provider's own
# /models check. No key is ever tried against a provider it does
# not look like it belongs to, except sk- (OpenAI or DeepSeek).
import http.client
import ssl

_api = {"provider": None, "model": None, "key": None, "models": []}

PROVIDERS = {
    "groq": {
        "models_url": ("api.groq.com", "/openai/v1/models"),
        "transcribe_url": ("api.groq.com", "/openai/v1/audio/transcriptions"),
        # Fallback chain, in order — if the first is decommissioned or
        # fails, the next working one is used. Never a hard-coded single model.
        "transcribe_models": ["whisper-large-v3", "whisper-large-v3-turbo"],
    },
    "openai": {
        "models_url": ("api.openai.com", "/v1/models"),
        "transcribe_url": ("api.openai.com", "/v1/audio/transcriptions"),
        "transcribe_models": ["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"],
    },
    "gemini": {
        "models_url": None,  # key goes in the query string, handled separately
        "transcribe_url": None,
        "transcribe_models": [],
    },
    "deepseek": {
        "models_url": ("api.deepseek.com", "/v1/models"),
        "transcribe_url": None,
        "transcribe_models": [],
    },
}


def _https_json(host, path, key, method="GET", body=None, headers=None):
    conn = http.client.HTTPSConnection(host, timeout=20,
                                       context=ssl.create_default_context())
    h = {"Authorization": f"Bearer {key}"}
    if headers:
        h.update(headers)
    conn.request(method, path, body=body, headers=h)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data or b"{}")


def detect_provider(key):
    """Prefix only — never guess by trying the key everywhere."""
    k = (key or "").strip()
    if k.startswith("gsk_"):
        return "groq"
    if k.startswith("AIza") or k.startswith("AQ."):
        # Gemini keys: old shape AIza..., new shape AQ.... (2026 AI Studio keys)
        return "gemini"
    if k.startswith("nvapi-"):
        return "nvidia"
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("sk-proj-"):
        return "openai"
    if k.startswith("sk-"):
        return "openai-or-deepseek"
    return None

_jobs = {}  # job_id -> {status, progress, result, error}


def srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(items):
    out = []
    for i, (a, b, t) in enumerate(items, 1):
        out.append(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n")
    return "\n".join(out)


def payload(lang, source, items):
    # Sec by sec, seconds only — group words/captions by whole second.
    # SRT keeps milliseconds because the SRT format requires them.
    grouped = v2.group_by_second(items)
    grouped_latin = [(sec, v2.romanize(text, lang)) for sec, text in grouped]
    plain = "\n".join(f"[{v2.ts(sec)}] {text}" for sec, text in grouped)
    plain_latin = "\n".join(f"[{v2.ts(sec)}] {text}" for sec, text in grouped_latin)
    latin = [(a, b, v2.romanize(t, lang)) for a, b, t in items]
    return {
        "language": lang,
        "source": source,
        "count": len(grouped),
        "timed_items": [{"start": a, "end": b, "text": t} for a, b, t in items],
        "segments": [{"start": sec, "end": sec + 1, "text": text} for sec, text in grouped],
        "segments_latin": [{"start": sec, "end": sec + 1, "text": text} for sec, text in grouped_latin],
        "plain": plain,
        "plain_latin": plain_latin,
        "srt": to_srt(items),
        "srt_latin": to_srt(latin),
    }


def captions_result(url, lang):
    cap = v2.try_captions(url, lang or None)
    if not cap:
        return None
    lang_code, kind, items = cap
    p = payload(lang_code, f"YouTube captions — {kind}", items)
    p["note"] = "Uploader captions — not audio verified" if "manual" in kind else "Auto captions — may mishear sung lyrics"
    return p


def transcribe_job(job_id, url, lang):
    """Background Whisper job. Loads the model only when needed."""
    from faster_whisper import WhisperModel

    try:
        _jobs[job_id]["status"] = "loading model (first run downloads ~800 MB once)..."
        model = WhisperModel(v2.MODEL, device=v2.DEVICE, compute_type="int8",
                             cpu_threads=v2.CPU_THREADS)
        _jobs[job_id]["status"] = "transcribing audio..."
        title, detected, prob, items = v2.transcribe(url, model, lang or None)
        note = "forced by you" if lang else f"auto-detected, confidence {prob:.0%}"
        p = payload(detected, f"Whisper {v2.MODEL} — {title} ({note})", items)
        p["note"] = "Transcribed from audio — sung words can be misheard"
        _jobs[job_id]["result"] = p
        _jobs[job_id]["status"] = "done"
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)


def connect_api_key(key):
    """Detect provider from the key, confirm it with that provider's
    own /models list, pick its transcription model. Returns a dict
    safe to show the user (never includes the key)."""
    provider = detect_provider(key)
    if provider is None:
        return {"ok": False,
                "error": "Could not tell which provider this key is for. "
                         "Groq keys start with gsk_, Gemini with AIza, OpenAI with sk-."}
    if provider == "openai-or-deepseek":
        for cand in ("openai", "deepseek"):
            host, path = PROVIDERS[cand]["models_url"]
            try:
                status, data = _https_json(host, path, key)
            except Exception as e:
                return {"ok": False, "error": f"Could not reach {cand}: {e}"}
            if status == 200:
                provider = cand
                break
        else:
            return {"ok": False, "error": "Key was not accepted by OpenAI or DeepSeek. Check the key and try again."}
    if provider in ("nvidia", "anthropic"):
        return {"ok": False,
                "error": f"{provider} key detected, but {provider} has no audio transcription here. Use a Groq or OpenAI key for transcribing."}
    if provider == "gemini":
        try:
            conn = http.client.HTTPSConnection("generativelanguage.googleapis.com", timeout=20,
                                               context=ssl.create_default_context())
            conn.request("GET", f"/v1beta/models?key={urllib.parse.quote(key)}")
            resp = conn.getresponse()
            data = json.loads(resp.read() or b"{}")
            conn.close()
            if resp.status != 200:
                return {"ok": False, "error": "Gemini did not accept this key. Check the key and try again."}
            models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
        except Exception as e:
            return {"ok": False, "error": f"Could not reach Gemini: {e}"}
        return {"ok": False, "provider": "gemini", "models": models,
                "error": "Gemini key connected, but Gemini audio transcription is not built in this version. Use a Groq or OpenAI key for transcribing."}
    host, path = PROVIDERS[provider]["models_url"]
    try:
        status, data = _https_json(host, path, key)
    except Exception as e:
        return {"ok": False, "error": f"Could not reach {provider}: {e}"}
    if status != 200:
        return {"ok": False, "error": f"{provider} did not accept this key. Check the key and try again."}
    models = sorted({m.get("id", "") for m in data.get("data", []) if m.get("id")})
    # The list comes live from the provider each time, so a model the
    # provider decommissioned is simply not in it and can never be picked.
    # Pick the first working transcription model from the fallback chain
    # that is still in the live list.
    chain = PROVIDERS[provider]["transcribe_models"]
    model = next((m for m in chain if m in models), None)
    if provider == "deepseek":
        return {"ok": False, "provider": "deepseek", "models": models,
                "error": "DeepSeek key connected, but DeepSeek is text-only — it cannot transcribe audio. Use a Groq or OpenAI key for transcribing."}
    if not model:
        return {"ok": False, "provider": provider, "models": models,
                "error": f"{provider} accepted the key, but none of its transcription models are available right now. Try again later."}
    _api.update({"provider": provider, "model": model, "key": key, "models": models})
    return {"ok": True, "provider": provider, "model": model, "models": models,
            "message": f"Connected to {provider} — using {model} for transcribing."}


def transcribe_with_api(job_id, url, lang):
    """Download audio once, send it to the connected provider's
    Whisper endpoint, build sec-by-sec items from its word timestamps."""
    import glob
    import tempfile
    import uuid

    import yt_dlp

    try:
        if not _api.get("key"):
            raise RuntimeError("No API key connected yet. Paste a key and tap Fetch and Connect first.")
        provider = _api["provider"]
        host, path = PROVIDERS[provider]["transcribe_url"]
        # Fallback chain: try each transcription model in order until one
        # works. A model that fails (decommissioned, removed, error) is
        # skipped, never retried in this run.
        chain = [_api["model"]] + [m for m in PROVIDERS[provider]["transcribe_models"]
                                   if m != _api["model"] and m in _api.get("models", [])]
        _jobs[job_id]["status"] = "downloading audio..."
        with tempfile.TemporaryDirectory() as tmp:
            opts = {"format": "bestaudio/best",
                    "outtmpl": os.path.join(tmp, "audio.%(ext)s"), "quiet": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "video")
            audio_path = glob.glob(os.path.join(tmp, "audio.*"))[0]
            _jobs[job_id]["status"] = f"sending audio to {provider}..."
            boundary = uuid.uuid4().hex
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            ext = os.path.splitext(audio_path)[1].lstrip(".") or "webm"
            parts = []
            def field(name, value):
                return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
            last_error = None
            data = None
            used_model = None
            for model in chain:
                body = field("model", model)
                body += field("response_format", "verbose_json")
                body += field("timestamp_granularities[]", "word")
                body += field("timestamp_granularities[]", "segment")
                body += field("temperature", "0")
                # Accuracy: give Whisper the video title as a prompt, so names
                # and fast lines are heard correctly instead of guessed.
                body += field("prompt", title)
                if lang:
                    body += field("language", lang)
                body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                         f"filename=\"audio.{ext}\"\r\nContent-Type: audio/{ext}\r\n\r\n").encode()
                body += audio_bytes + f"\r\n--{boundary}--\r\n".encode()
                status, data = _https_json(
                    host, path, _api["key"], method="POST", body=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
                if status == 200:
                    used_model = model
                    break
                last_error = f"{provider} ({model}) said: {data.get('error', {}).get('message', status)}"
            if not used_model:
                raise RuntimeError(last_error or f"{provider} did not answer.")
            model = used_model
            items = []
            for w in (data.get("words") or []):
                if (w.get("word") or "").strip():
                    items.append((float(w["start"]), float(w["end"]), w["word"].strip()))
            if not items:
                for seg in data.get("segments", []):
                    if (seg.get("text") or "").strip():
                        items.append((float(seg["start"]), float(seg["end"]), seg["text"].strip()))
            detected = lang or data.get("language") or "en"
            p = payload(detected, f"{provider} {model} — {title}", items)
            p["note"] = "Transcribed with your connected API key — sung words can still be misheard"
            _jobs[job_id]["result"] = p
            _jobs[job_id]["status"] = "done"
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _trusted(self):
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin')
        if host not in ('127.0.0.1:8765','localhost:8765') or (origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765')) or self.headers.get('Sec-Fetch-Site')=='cross-site':
            self._send({'error':'Local service accepts only same-origin loopback requests.'},403)
            return False
        return True

    def do_GET(self):
        if not self._trusted():return
        parsed = urllib.parse.urlparse(self.path)
        if studio.dispatch(self,parsed.path,'GET'):return
        assets={'/':'index.html','/index.html':'index.html','/Transcript.html':'Transcript.html','/studio.js':'studio.js','/studio.css':'studio.css','/offline-pack.zip':'offline-pack.zip'}
        if parsed.path in assets:
            name=assets[parsed.path];ctype={'html':'text/html; charset=utf-8','js':'application/javascript; charset=utf-8','css':'text/css; charset=utf-8','zip':'application/zip'}[name.rsplit('.',1)[-1]]
            with open(os.path.join(HERE,name),'rb') as f:self._send(f.read(),ctype=ctype)
            return
        if parsed.path == "/api/transcript":
            q = urllib.parse.parse_qs(parsed.query)
            url = (q.get("url") or [""])[0].strip()
            lang = (q.get("lang") or [""])[0].strip().lower() or None
            if not url:
                self._send({"error": "Paste a YouTube link first."}, 400)
                return
            try:
                result = captions_result(url, lang)
            except Exception as e:
                self._send({"error": f"Captions check failed: {e}"}, 500)
                return
            if result:
                self._send(result)
            else:
                self._send({"error": "no_captions",
                            "message": "This video has no captions. Use Transcribe audio below — it is slower."})
            return
        if parsed.path == "/api/status":
            self._send({"provider": _api.get("provider"), "model": _api.get("model"),
                        "connected": bool(_api.get("key"))})
            return
        if parsed.path == "/api/job":
            q = urllib.parse.parse_qs(parsed.query)
            job = _jobs.get((q.get("id") or [""])[0])
            if not job:
                self._send({"error": "Unknown job."}, 404)
                return
            self._send(job)
            return
        self.send_error(404)

    def do_POST(self):
        if not self._trusted():return
        parsed = urllib.parse.urlparse(self.path)
        if studio.dispatch(self,parsed.path,'POST'):return
        if parsed.path == "/api/connect":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            key = (body.get("api_key") or "").strip()
            if not key:
                self._send({"ok": False, "error": "Paste an API key first."}, 400)
                return
            self._send(connect_api_key(key))
            return
        if parsed.path == "/api/transcribe_api":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            url = (body.get("url") or "").strip()
            lang = (body.get("lang") or "").strip().lower() or None
            if not url:
                self._send({"error": "Paste a YouTube link first."}, 400)
                return
            if not _api.get("key"):
                self._send({"error": "No API key connected yet. Paste a key and tap Fetch and Connect first."}, 400)
                return
            job_id = f"job-{int(time.time() * 1000)}"
            _jobs[job_id] = {"status": "starting...", "result": None, "error": None}
            threading.Thread(target=transcribe_with_api, args=(job_id, url, lang),
                             daemon=True).start()
            self._send({"job_id": job_id})
            return
        if parsed.path == "/api/transcribe":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            url = (body.get("url") or "").strip()
            lang = (body.get("lang") or "").strip().lower() or None
            if not url:
                self._send({"error": "Paste a YouTube link first."}, 400)
                return
            job_id = f"job-{int(time.time() * 1000)}"
            _jobs[job_id] = {"status": "starting...", "result": None, "error": None}
            threading.Thread(target=transcribe_job, args=(job_id, url, lang),
                             daemon=True).start()
            self._send({"job_id": job_id})
            return
        self.send_error(404)


if __name__ == "__main__":
    print(f"YouTube Transcribe Downloader — open http://127.0.0.1:{PORT} in your browser")
    print("Close this window to stop it.")
    httpd=ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    if "--open" in __import__("sys").argv:
        import webbrowser
        threading.Timer(.3,lambda:webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    httpd.serve_forever()
