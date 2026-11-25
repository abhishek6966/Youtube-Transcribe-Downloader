# YouTube Transcribe Downloader — MCP server

Use the transcriber from **any AI assistant or any project**: paste a
YouTube link, get the words second by second — in the original language
**and** in English letters, spelled the way they sound.

```text
[00:26] तू अगर मेरी ये हवाएं तेरी
[00:26] too agara meree ye havaaen teree
```

No installs beyond Python 3.10+. No accounts. The server is one file,
`server.py`, pure Python standard library — it speaks MCP (newline-delimited
JSON-RPC over stdio) and nothing else.

## What it does

| Tool | What it does |
|---|---|
| `transcribe_youtube(url, lang="auto")` | Captions-first, same chain as the web page: public Invidious mirrors raced in parallel → Piped → YouTube legacy timedtext. Free, no key. |
| `transcribe_audio(audio_path_or_url, api_key, provider="groq")` | Sends an audio/video file (or its URL) to Groq or OpenAI Whisper. For videos with no captions. Needs a key. |

Both tools return two timed versions: the words in the original language,
and the same words in English letters (romanized pronunciation — never a
translation). Sound descriptions (`[music]`, `[Sangeet]`, `[म्यूसिक]`,
`[BLANK_AUDIO]`, `(pause)`, `♪ tune ♪` …) are stripped everywhere, and
words are never invented: if a video has no captions and no key is given,
the tool says so plainly.

**Honest limits:** a video with no captions cannot be done from the link
alone (a web page — and this server — cannot pull YouTube audio); audio
files over 25 MB are refused; sung words can still be misheard.

## Quick test (no setup)

```bash
cd mcp-server
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"transcribe_youtube","arguments":{"url":"https://youtu.be/GVizJ_jpUnw"}}}' \
  | python3 server.py
```

## Setup

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "youtube-transcribe-downloader": {
      "command": "python3",
      "args": ["/absolute/path/to/youtube-transcribe-downloader/mcp-server/server.py"]
    }
  }
}
```

Restart Claude Desktop. The two tools appear in the tools list.

### Cursor

Settings → MCP → Add new global MCP server (or edit
`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "youtube-transcribe-downloader": {
      "command": "python3",
      "args": ["/absolute/path/to/youtube-transcribe-downloader/mcp-server/server.py"]
    }
  }
}
```

### VS Code (Copilot / MCP extension)

In `.vscode/mcp.json` (workspace) or your user `mcp.json`:

```json
{
  "servers": {
    "youtube-transcribe-downloader": {
      "command": "python3",
      "args": ["/absolute/path/to/youtube-transcribe-downloader/mcp-server/server.py"]
    }
  }
}
```

### Claude Code / Muse

```bash
claude mcp add youtube-transcribe-downloader \
  -- python3 /absolute/path/to/youtube-transcribe-downloader/mcp-server/server.py
```

Or add it to `~/.claude.json` under `mcpServers` with the same
`command` / `args` as above.

> On Windows, use `python` instead of `python3` if that is what your
> install is called, and use the full path with forward slashes
> (`C:/path/to/mcp-server/server.py`).

## API keys (only for `transcribe_audio`)

No key is needed for `transcribe_youtube`. For `transcribe_audio` the
user supplies their own key per call — Groq (`gsk_…`) or OpenAI
(`sk-…`). The server never stores or logs a key; it is sent only to
its own provider, for that one request. Never commit a key, and never
paste one into a shared document.

## How it works

- **Captions** are fetched the same way the web page does: Invidious
  mirrors and Piped servers are raced in parallel (one quiet retry on a
  temporary 5xx/timeout), legacy `timedtext` last. A positive "no
  captions" answer is only believed when every route agrees.
- **Word times** are kept when the caption file carries them
  (`<00:00:01.200>` tags) or when Whisper returns per-word timestamps,
  so each word lands on its real second; otherwise words are spread
  evenly across the line.
- **Romanization** is ported from the web page: Indic scripts, Hangul,
  kana, Cyrillic, Greek, Arabic, Hebrew and Latin accents, word by word.
- **Whisper** uses the provider's verbose JSON with word timestamps and
  steps down its model chain on failure (`whisper-large-v3-turbo` →
  `whisper-large-v3` on Groq; `whisper-1` → `gpt-4o-transcribe` →
  `gpt-4o-mini-transcribe` on OpenAI).
