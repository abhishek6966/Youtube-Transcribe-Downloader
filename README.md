<div align="center">
  <img src="docs/readme/studio-hero.gif" alt="Every word, in its place — animated audio transcription banner" width="100%" />
  <h1>YouTube Transcribe Downloader</h1>
  <p><strong>Classic Precision Edition</strong> · AI transcription · Multilingual text · Synchronized karaoke</p>
  <p>Transcribe. Compare. Verify. Sing along.</p>
  <p>
    <a href="#accuracy-engine"><img src="docs/readme/badges/release.png" width="134" alt="Edition: Classic" /></a>
    <a href="#computer-package"><img src="docs/readme/badges/python.png" width="126" alt="Python: 3.12" /></a>
    <a href="#deployment"><img src="docs/readme/badges/frontend.png" width="159" alt="Frontend: HTML / JS" /></a>
    <a href="LICENSE"><img src="docs/readme/badges/license.png" width="121" alt="License: MIT" /></a>
    <a href="mcp-server/README.md"><img src="docs/readme/badges/mcp.png" width="110" alt="MCP: Tools" /></a>
  </p>
  <p>
    <a href="https://abhishek6966.github.io/Youtube-Transcribe-Downloader/"><img src="docs/readme/badges/open-app.png" width="252" alt="Open live web app" /></a>
    <a href="offline-pack.zip"><img src="docs/readme/badges/computer.png" width="252" alt="Download computer package" /></a>
  </p>
  <p><strong><a href="https://abhishek6966.github.io/Youtube-Transcribe-Downloader/">Open live application</a></strong> · <a href="#computer-package">Computer setup</a> · <a href="#accuracy-engine">Technical guide</a></p>
  <p><a href="#quick-start">Quick start</a> · <a href="#accuracy-engine">Accuracy engine</a> · <a href="#karaoke">Karaoke</a> · <a href="#deployment">Deployment</a> · <a href="#verification">Verification</a></p>
</div>


> One familiar interface. The original animated three-step Classic website is now the sole user-facing application on GitHub Pages and in the computer package. `index.html` and `Transcript.html` contain identical HTML; old bookmarks still work. No separate advanced dashboard is required.

**Live website:** https://abhishek6966.github.io/Youtube-Transcribe-Downloader/  
**Classic direct link:** https://abhishek6966.github.io/Youtube-Transcribe-Downloader/Transcript.html

## Classic Precision 1.6 — caption fallback, progressive audio recognition and synchronized playback

Step 3 uses the available viewport with more compact controls, a bounded video preview, paired word rows and responsive panels. The document remains fixed; transcripts, panels and dialogs can scroll internally on short displays. Steps 1 and 2 retain their responsive layouts.

<img src="docs/readme/compact-spotlight.webp" width="100%" alt="Compact Classic workspace — synthetic timed-word playback fixture" />

Maximum mode on the browser Groq/Deepgram audio-file route (with a compatible connected chat model) and the computer engine with Groq context review scans even agreed words for plausible phonetic confusions. It checks at most two candidates per chunk using fresh, unprompted recognition of the matching audio crop. A one-word substitution requires two distinct recognition routes, matching adjacent words and compatible word boundaries; unresolved suggestions remain in the audit. This is not a measurement of accuracy. The direct hosted helper and OpenAI Whisper route do not run this cropped context-review loop.

The **Vocabulary** button accepts up to 180 characters of known spellings in the source language. In Maximum mode, supported Groq / OpenAI Whisper audio routes, the trusted helper and local Whisper can run a separate hinted observation. Hinted recognition is deliberately excluded from automatic consensus; inspect the audit and use the editable transcript or authorized reference for confirmed corrections. No remote model weights are modified. Prompts may bias recognition and do not guarantee pronunciation accuracy. Caption-only results cannot verify the actual spoken or sung sound.

## When a video has no captions

The embedded YouTube player does not expose audio samples to this page. A Groq key gives access to recognition models, not to YouTube audio. If caption retrieval fails, the app displays persistent actions rather than an automatically disappearing dead-end warning.

| Route | Behavior |
|---|---|
| Groq / Deepgram + matching authorized audio or video file | Recognize overlapping audio chunks and populate both scripts as chunks finish. |
| Computer + matching authorized recording | Local recognition with progressive job updates; optional installed models improve alignment. |
| Connected Gemini + public YouTube URL | After consent, automatically select a general-purpose video candidate from the live Gemini catalog, excluding audio-only models, and attempt direct video-input recognition. Model-generated word times are explicitly estimated; availability and completeness depend on provider/model. |
| Trusted deployed helper | Existing authorized audio-input route; provider response arrives as a batch. |
| No usable source | Explain the limitation and offer the matching-media picker, provider connection or helper setup. |

For a new file transcript, **Play as words arrive** attempts to play the supplied recording after the first recognized chunk, highlights the available words in both scripts, and pauses at the processed boundary until more audio is recognized. Browser autoplay restrictions may require a manual Play & sing along click. The player uses the supplied media, not a capture of the YouTube embed. Existing transcripts are replaced only after recognition succeeds, rather than progressively overwritten during rechecks. Processing uses bounded chunks, not instantaneous word streaming. If a chunk fails, the audit reports the missing interval; model agreement is not a measured accuracy score. Only process media you have permission to use and where the source/platform permits the processing. No automatic bypass of YouTube media access is added.

```mermaid
flowchart TD
    A[Get transcript] --> B{Captions available?}
    B -->|Yes| C[Caption timings and playback]
    B -->|No| D{Authorized audio source available?}
    D -->|Matching file| E[Overlapping audio chunks]
    D -->|Configured trusted helper| F[Provider audio recognition]
    D -->|Gemini connected| G[Consent and direct video URL input]
    D -->|None| H[Choose matching media or connect provider]
    E --> I[Publish processed word timeline]
    I --> J[Play supplied media up to processed boundary]
    I --> K[Original and romanized text]
    G --> L[Estimated model-generated timings]
    F --> K
    L --> K
    C --> K
```

### Gemini public-video compatibility and diagnostics

- The live model list is checked on connection (up to five catalog pages). The app separates general-purpose video candidates from specialized transcription models; a model name containing `transcribe` does not imply video-input support.
- The no-caption route uses the documented [Interactions API](https://ai.google.dev/gemini-api/docs/video-understanding#youtube) with the public video URI and stateless requests. On compatibility errors (HTTP 400/404), it may try the legacy GenerateContent route and other catalog candidates, with at most four requests per consent. Provider usage and quota may be consumed.
- Temporary server errors (HTTP 500/502/503/504) trigger bounded backoff and automatic switching to another video candidate, with one final retry if the alternatives are exhausted and the four-request budget permits. Long Retry-After cooldowns stop the attempt. Authentication, access, quota and explicit content refusals stop automatic retry. Errors identify attempted model, endpoint, HTTP status and available provider explanation, with credential redaction and HTML escaping.
- All Gemini-generated word times remain estimates; a successful API response does not establish full coverage or acoustic accuracy. Public-video availability, model capability, quota and processing permission are not guaranteed. Use a matching authorized media file for acoustic recognition when link input is unavailable.
- `python tests/test_gemini_video_routing.py` checks the exact compatibility failure path with simulated API responses, including automatic model selection, legacy fallback, and refusal handling.

See [Groq speech-to-text](https://console.groq.com/docs/speech-to-text) and [Gemini video URL input](https://ai.google.dev/gemini-api/docs/video-understanding#youtube). Live Gemini availability has not been verified with credentials in this release; the regression test checks the request and response handling with mock data.

## Quick start

<div align="center"><img src="docs/readme/three-step-tour.gif" alt="Actual Classic UI screenshots in a three-step slideshow; transcript uses a deterministic mock recognition fixture" width="100%" /></div>

| Step | What to do |
|---|---|
| 1 · Welcome | Open the live web app and press Start. |
| 2 · Connect | Paste a recognized provider key, or select its provider if the key format is ambiguous. The app requests the provider's model catalog. Optional Deepgram connection uses a separate key and accessible project/model-list permissions. |
| 3 · Transcribe | Choose the language (or Auto), accuracy mode, and matching file. A trusted deployed HTTPS helper can attempt YouTube audio processing; without audio access, a link returns captions only unless a connected Gemini model accepts the direct video URL. |
| Review | Inspect original text and English-letter pronunciation, listen to the actual recording, and use Check the words for an audio recheck when available. |
| Export | Save TXT or SRT in both scripts, or export the available audit JSON. |

<img src="docs/readme/studio-step-welcome.webp" width="100%" alt="Classic animated landing page" />
<img src="docs/readme/studio-step-connect.webp" width="100%" alt="Classic provider connection screen" />

The welcome and connection screens adapt to desktop, tablet, phone and landscape viewports. Start, Back and Continue stay visible; on short screens or when optional settings expand, only the content region scrolls. The main document remains fixed.
<img src="docs/readme/studio-step-workspace.webp" width="100%" alt="Classic workspace; deterministic mock ASR example, not verified song lyrics" />

## Accuracy engine

<img src="docs/readme/verification-flow.gif" width="100%" alt="Illustrative verification pipeline animation" />

Recognition and timing are separate problems. Sorting individual words by imperfect or overlapping timestamps can corrupt the phrase order. This version preserves provider token sequence, repairs conflicting offsets separately, and labels repaired or inferred word boundaries as **estimated**. It also checks nearby segment-text permutations when the exact same tokens appear in a different order. That comparison is evidence from the same model, not independent proof of the performance.

```mermaid
flowchart TD
    A[Classic source selection] --> B{Audio available?}
    B -->|No| C[Caption-only retrieval]
    B -->|File or authorized link| D[Audio recognition]
    D --> E[Ordered word observations]
    E --> F[Compare bounded alternative sequences]
    F --> G{Additional audio observation corroborates alternate?}
    G -->|Yes| H[Accept supported alternative]
    G -->|No| I[Preserve primary and report dispute]
    C --> J[Remove overlapping caption carry-over]
    H --> K[Sequence-preserving timing repair]
    I --> K
    J --> K
    K --> L[Timed transcript and karaoke]
    K --> M[Audit where available]
```

### Accuracy modes

| Mode | Browser Groq / Deepgram file route | Computer route | Trusted helper |
|---|---|---|---|
| Fast | One available word-timed recognition pass | One available pass | One Whisper pass |
| Advanced | Up to two passes | Multi-model recognition and bounded retries | Up to two Whisper passes |
| Maximum | Up to three observations, plus one targeted retry per disputed chunk | Extra recognition, bounded retries, optional vocal separation and forced alignment | Up to three Whisper observations |

The number of successful passes depends on available models, credentials, audio format, and provider access. Repeated observations from Whisper are **not independent model families**. Deepgram is an optional independent family. Text AI can rank observed alternatives in context; it cannot hear the recording and its suggestions do not automatically rewrite words. OpenAI and Gemini retain their supported direct routes; Gemini times are estimates and its route is not equivalent to the multi-model pipeline.

### Word timing and chunking

```mermaid
flowchart LR
    A[Decode matching file] --> B[35 second audio windows]
    B --> C[5 second overlap]
    C --> D[Word-timed recognition]
    D --> E[Compare alternative ordered sequences]
    E --> F[Keep each window's owned region]
    F --> G[Preserve sequence and repair timing]
    G --> H[Original and transliteration]
```

Browser decoding supports files up to 200 MB and decoded audio up to one hour on the Groq/Deepgram chunk route. Browser codec support varies. The computer service supports files up to 512 MB and recordings up to four hours, with configured limits and optional local models. Other provider routes have smaller file limits. Acoustic alignment is optional in the computer package, not a browser capability. Audio coverage measures processed audio, not word accuracy.

## Karaoke

<img src="docs/readme/karaoke-preview.gif" width="100%" alt="Illustrative synchronized word spotlight animation" />

Play & Sing Along uses the playback clock from the matching uploaded media or the embedded YouTube player. Both transcript columns share one word timeline, lexical row indices, matched row heights and a common scroll position. Changing tabs or resizing remeasures the rows. Clicking a timed word seeks to its start; clicking a shared-range word seeks to its approximate playback position when available, otherwise to the containing caption range. Seeking, pause and playback update the spotlight. Gaps without a timed word are not filled by a fabricated highlight. Each individual word now shows its millisecond timestamp. `~` indicates an estimate, not an audio-verified boundary. Dense or conflicting caption phrases with insufficient timing evidence are shown as separate word rows with the shared caption time range, not as a long line at one second. These rows now receive a sequential, explicitly approximate playback-only spotlight when their shared range has enough room. During playback the row shows an estimated individual start time with a tilde, and its tooltip retains the original range. The estimate stays inside the caption range and does not displace adjacent individually timed words. Very short or conflicting intervals remain range-only. The original timestamp evidence and exports are unchanged. The Improve with audio button starts an audio recheck or opens the matching-media picker in Maximum mode. Real audio recognition and optional acoustic alignment can resolve these passages; a text-only model cannot establish the correct sound timing. TXT and on-screen transcripts use a separate row per timed word, including shared-range labels for unresolved words. SRT uses individual word intervals where available and retains unresolved phrases as ranges to avoid inventing boundaries. Very short rolling WebVTT display snapshots are removed only when an adjacent cue corroborates the same text. The caption fetcher briefly prefers sources with distinct word offsets over coarse cues. In Maximum mode, the browser can recover unresolved word intervals when two additional audio observations agree on the complete word sequence and compatible timing. This is corroboration, not proof of exact alignment. Embedded playback and audio access depend on the video and browser.

```mermaid
sequenceDiagram
    participant P as Actual player
    participant T as Ordered timeline
    participant O as Original words
    participant R as English letters
    P->>T: Current playback time
    T->>T: Find active word by start and end
    T->>O: Highlight and scroll
    T->>R: Highlight same word and scroll
    O->>P: Seek on word click
```

## Computer package

1. Download [offline-pack.zip](offline-pack.zip) and extract it.
2. Install Python 3.12 if needed.
3. Double-click `Open_Transcriber.bat` on Windows. The first run installs dependencies. macOS/Linux users may use `sh start_studio.sh` with a compatible Python environment.
4. The loopback server opens `http://127.0.0.1:8765/` in your browser, showing the same Classic interface.
5. Select the computer/no-key path for local Whisper. A local audio file is recommended; authorized YouTube acquisition may fail due to source availability.
6. For optional Demucs and WhisperX, run `Install_Maximum_Models.bat`. These may require substantial downloads, processing time and compatible hardware.

The local engine retains chunking, optional vocal isolation, optional acoustic alignment, source fingerprinting, bounded retries, quality reports and internal checkpoint support. Classic does not expose every old dashboard configuration: checkpoint opt-in and some detailed model controls remain engine-level settings. API keys are held in the browser tab and sent to a provider or explicitly trusted helper only as needed. Selecting the local no-key route does not send cloud credentials. The helper receives a key only after approval for the link request.

## Deployment

```mermaid
flowchart TD
    A[GitHub Pages: index.html / Transcript.html] --> B[Classic browser]
    B --> C[Provider APIs]
    B -->|Optional trusted HTTPS helper| D[Cloudflare Worker]
    D --> C
    E[Computer launcher] --> F[Loopback HTTP server]
    F --> G[Same Classic HTML]
    F --> H[Local verification engine]
    H --> I[Optional installed models]
```

Upload the complete GitHub package contents to the repository. In GitHub Pages settings publish the repository root from the desired branch. Keep both HTML files identical; the root URL opens Classic directly. Deploy the updated `worker/worker.js` separately if you use the helper, following [worker setup](worker/README.md). The helper uses the new `mode` field and can return an additional `third_words` observation. Use only a helper you control or trust and media you are authorized to process.

## Verification

```mermaid
flowchart LR
    A[Timestamp collision / reversal] --> B[Sequence regression]
    C[WAV fixture] --> D[Mock recognition tests]
    E[Simulated video clock] --> F[Karaoke tests]
    G[Local HTTP requests] --> H[Loopback security tests]
    B --> I[Release checks]
    D --> I
    F --> I
    H --> I
```

Run `python tests/test_universal.py`, `python tests/test_local_service.py`, `python tests/test_timeline_browser.py`, and `python tests/test_classic_sequence.py`. Run `python tests/test_progressive_audio.py` for progressive playback, fallback actions and simulated Gemini link input. Browser tests require Playwright and Chromium. `benchmark.py` measures errors against supplied human-annotated ground truth. The tests exercise sequence preservation, timed repetitions, boundary recovery, timing repair, mock recognition with real WAV decoding, karaoke playback logic, and local service access. They do not establish live recognition accuracy on songs. Optional models and Windows launchers have not been exercised end-to-end in this build environment.

**Accuracy limits:** no ASR model guarantees perfect lyrics for every recording or language. Captions can be inaccurate, recognition models can share mistakes, and estimated timings cannot be represented as acoustic truth. Use the exact authorized recording, Maximum mode, and human review of unresolved words for critical karaoke results. No measured accuracy percentage is claimed without independent ground truth.

## Repository guide

| Path | Purpose |
|---|---|
| `index.html`, `Transcript.html` | Same original Classic user interface and browser engine |
| `universal_engine.py`, `universal_server.py` | Computer processing and local job endpoints |
| `server.py` | Local HTTP server |
| `worker/` | Optional deployed helper |
| `mcp-server/` | Legacy and advanced local audio MCP tools |
| `docs/readme/` | Locally bundled animated graphics and UI captures |
| `tests/` | Deterministic software regression suite |
| `benchmark.py` | Reference-based accuracy metrics |

See [license](LICENSE) and [contribution guide](CONTRIBUTING.md). Animated graphics illustrate the workflow; mock screenshots are not real verified song results.


### Troubleshooting direct Gemini link recognition

If captions are unavailable, **Retry Gemini link** directly retries Google (with your consent) without repeating the caption search. HTTP errors, quota limits, incomplete timed output and network failures have separate diagnostic messages. The URL route requires a supported public video and compatible Gemini model; it does not provide acoustic word alignment. Use matching authorized audio for more precise timing. No credentials or raw provider response bodies are displayed in diagnostics.
