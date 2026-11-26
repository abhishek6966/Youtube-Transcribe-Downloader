# Regression tests

- `python tests/test_universal.py`: 8 tests for chronology, repeated words, boundary omissions, substitution, coverage, source validation, cache recovery and benchmark calculations.
- `python tests/test_local_service.py`: real loopback HTTP integration; mocked ASR.
- `python tests/test_studio_browser.py`: Playwright browser test; mocked cloud responses, real WAV decode, dual-column timing, edit/undo, audit export and mobile width.
- `python tests/test_timeline_browser.py`: legacy karaoke/timing regression; simulated player.

These are software tests, not real ASR accuracy benchmarks. Optional Demucs/WhisperX and live provider calls are not exercised. Install Playwright and Chromium to run browser tests.

- `python tests/test_wizard_browser.py`: simulated provider discovery and responsive wizard.
- `python tests/test_classic_handoff.py`: simulated classic receiver; external network resources blocked.
- `python tests/test_restored_workspace.py`: preview metadata mock, Maximum recheck, clear, SRT import, progress, viewport.
