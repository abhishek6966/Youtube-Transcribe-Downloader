# YouTube Transcribe Downloader — agent skill

## When to use this skill

Use the `youtube-transcribe-downloader` MCP tools whenever someone asks for
the **words of a YouTube video** — lyrics, a transcript, what was said —
especially when they want them **second by second** and **in English
letters so they can be read aloud**. Also use them when a project needs
transcription built in (a bot, a notes app, a study tool, a lyrics site).

## The tools (from the `mcp-server` in this repo)

| Tool | Use it when |
|---|---|
| `transcribe_youtube(url, lang="auto")` | The video has captions (most music and popular videos do). Free, no key needed. |
| `transcribe_audio(audio_path_or_url, api_key, provider="groq")` | The video has **no captions**, or the captions are wrong — send the sound file to Groq / OpenAI Whisper instead. Needs an API key. |

## What comes back

Every successful call returns **two timed versions, line for line**:

```
[00:26] तू अगर मेरी ये हवाएं तेरी
[00:27] मेरी ये हवाएं
```

and, underneath, the same lines in English letters (romanized
pronunciation — **never a translation**):

```
[00:26] too agara meree ye havaaen teree
[00:27] meree ye havaaen
```

## Rules the tools already follow (do not work around them)

- **Captions first.** `transcribe_youtube` tries public Invidious mirrors
  raced in parallel, then Piped, then YouTube's legacy timedtext. Manual
  captions are exact; auto captions are labelled as such.
- **Words only.** Sound descriptions are stripped everywhere:
  `[music]`, `(pause)`, `[Sangeet]` / `[संगीत]`, `[म्यूसिक]`,
  `[BLANK_AUDIO]`, `♪ tune ♪`, bare `Sangeet` / `dhun` lines. A real sung
  line is never touched, even if it mentions music.
- **Never invent words.** If a video has no captions and no key is given,
  the tool says so plainly. Offer `transcribe_audio` with a key, or the
  offline computer pack in this repo — never guess the lyrics.
- **No perfect-transcription promises.** Sung words can be misheard by
  auto captions and by Whisper, and no checker can recover a word that
  was never heard correctly. Say that when it matters.
- **Keys stay private.** An API key is sent only to its own provider, for
  that one request. Never paste a key into chat, a file, or a screenshot,
  and never store one.

## How to ask the user for what you need

- A YouTube link is enough for `transcribe_youtube` — no key, no setup.
- For `transcribe_audio`, you need **the sound file** (or its URL) and
  **the user's own Groq (`gsk_…`) or OpenAI (`sk-…`) key**. The user
  pastes the key to their own assistant, never into a shared document.
- If the user wants a specific language, pass its code (`lang="hi"`,
  `"en"`, `"es"` …). Leave it on `"auto"` otherwise.

## Limits, stated plainly

- A video with **no captions** cannot be done from the link alone — the
  page, and this server, cannot pull YouTube audio. That is the
  `transcribe_audio` case (or the repo's offline pack).
- Some videos hide their audio behind a signature even from a server;
  those fail with a clear error.
- Audio files over 25 MB are refused (the provider's upload limit).
- It is not real-time, and sung words can still be misheard.
