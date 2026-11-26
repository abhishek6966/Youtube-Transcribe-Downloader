# Regression tests

- `python tests/test_universal.py`: local engine, consensus, timing, repeated words, benchmark and checkpoint tests.
- `python tests/test_local_service.py`: loopback HTTP integration, mocked ASR and cross-origin rejection.
- `python tests/test_timeline_browser.py`: Classic caption processing, simulated karaoke clock, timing and SRT export.
- `python tests/test_classic_sequence.py`: sequence preservation with deliberately conflicting offsets, corroborated boundary recovery, real WAV decoding and three simulated audio observations, audit and viewport.

- `python tests/test_dense_timing.py`: dense caption ranges, rolling snapshots, multilingual word segmentation, timing corroboration, real-word anchor preservation, millisecond export, simulated playback/seek, and worker/Python parity.

These are software tests, not live ASR accuracy benchmarks. Install Playwright and Chromium for browser tests.

`python tests/test_phonetic_fullscreen.py` — validates synthetic mishearing, rejects unsupported substitutions, tests cropped recognition with simulated providers and real WAV decoding, vocabulary hint isolation and fixed viewport layout. No live speech accuracy measurement.

`python tests/test_spotlight_responsive.py` — shared word rows, matching scroll and active index in both scripts, uncertain range handling, tab changes, fixed frame and control reachability across nine simulated browser viewport sizes.

`python tests/test_shared_range_spotlight.py` — approximate per-word playback for shared caption ranges, preservation of later timing anchors, simultaneous bilingual highlights, click-to-seek, silence, and unchanged subtitle evidence. Uses a simulated clock, not live song audio.

`python tests/test_gemini_video_routing.py` — browser test of live-catalog mock, compatible video model selection, bounded HTTP 400 failover, Interactions and legacy request formats, escaped provider diagnostics, and no retry on quota/access/content rejection. No live API access.
