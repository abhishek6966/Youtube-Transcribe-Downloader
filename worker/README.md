# Helper worker (optional, free, one-time setup)

The GitHub Pages site is only a web page. A web page cannot pull the sound
out of a YouTube video, and Groq / OpenAI block direct calls from browsers.
This tiny Cloudflare Worker does those two server-side jobs so visitors
need nothing installed:

- `GET /api/captions?url=<YouTube link>&lang=<code>` — fetches the video's
  captions from YouTube and returns timed lines.
- `POST /api/transcribe` — forwards a visitor's sound file + their own API
  key to Groq / OpenAI Whisper and returns the timed transcript.
- `POST /api/transcribe_link` — the fix for videos with no captions: it
  asks YouTube's own player API for the video's audio stream, downloads
  it (capped at ~25 MB, the provider's upload limit), and sends it to
  Groq / OpenAI Whisper — or to Google Gemini (Files API + generateContent,
  which returns the words as [MM:SS] stamped lines). Body:
  `{url, provider, api_key, model?, language?, title?}` where provider is
  `groq`, `openai` or `gemini`.
  Some videos hide their audio behind a signature and return a clear
  error instead — for those, the listening panel or the computer pack is
  the way. It is not real-time and not perfect: the audio is downloaded,
  then transcribed, and sung words can still be misheard.

A visitor's API key is never stored or logged — it is only forwarded to the
provider it belongs to, for that one request.

## Deploy (once, free)

**Easiest way — one click:** after pushing this project to GitHub, open this link (replace `YOUR-USERNAME` and `YOUR-REPO` with yours):

`https://deploy.workers.cloudflare.com/?url=https://github.com/YOUR-USERNAME/YOUR-REPO/tree/main/worker`

That deploys the worker straight from your repo. Then copy your worker address (like `https://yt-transcribe-helper.<your-name>.workers.dev`) into the `WORKER_URL` setting at the top of `index.html`, and push to GitHub.

**Or by hand:** make a free account at https://dash.cloudflare.com and install
Node.js, then run: `npm install -g wrangler`
2. In this `worker/` folder, run: `wrangler login` then `wrangler deploy`
3. Copy your worker address (like
   `https://yt-transcribe-helper.<your-name>.workers.dev`) into the
   `WORKER_URL` setting at the top of `index.html`, and push to GitHub.

Visitors then use the site with no install at all.

## Honest limits

- This code could not be tested live from the machine that wrote it
  (outside calls are blocked there), so deploy it and try one captioned
  video first before telling visitors it works.
- YouTube sometimes blocks requests from datacentre addresses. If captions
  fail through the worker, the offline pack (`server.py` / `start_html.bat`)
  still works from your own computer.
- A video with no captions still needs its sound: the visitor uploads the
  sound/video file on the page, or uses the offline pack. No web page or
  worker can pull audio out of a YouTube video on its own.
