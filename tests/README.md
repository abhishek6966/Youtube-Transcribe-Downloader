# Regression tests

- `python tests/test_universal.py`: local engine, consensus, timing, repeated words, benchmark and checkpoint tests.
- `python tests/test_local_service.py`: loopback HTTP integration, mocked ASR and cross-origin rejection.
- `python tests/test_timeline_browser.py`: Classic caption processing, simulated karaoke clock, timing and SRT export.
- `python tests/test_classic_sequence.py`: sequence preservation with deliberately conflicting offsets, corroborated boundary recovery, real WAV decoding and three simulated audio observations, audit and viewport.

These are software tests, not live ASR accuracy benchmarks. Install Playwright and Chromium for browser tests.
