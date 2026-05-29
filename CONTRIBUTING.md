# Contributing to NoteNinja

Thanks for your interest! Here's everything you need to know.

---

## Reporting a bug

Open an issue on GitHub and include:
- Your OS and version (macOS 14.x / Windows 11, etc.)
- What you expected to happen
- What actually happened
- Any error output from the terminal or `nj logs`

---

## Suggesting a feature

Open an issue with the **enhancement** label. Describe the use case, not just the feature — it helps us understand whether it fits the project.

---

## Making a change

1. **Fork** the repo and create a branch from `main`
2. **Install dependencies:**
   ```bash
   nj          # macOS — runs setup on first launch
   nj.bat      # Windows
   ```
3. **Make your changes**
4. **Run the tests** — all must pass before submitting:
   ```bash
   nj pytest tests/ -v
   ```
5. **Open a pull request** against `main` with a clear description of what changed and why

---

## Project structure

| File | Purpose |
|---|---|
| `main.py` | CLI entry point, menu, recording pipeline |
| `recorder.py` | Audio capture (sounddevice) |
| `transcriber.py` | Whisper transcription + pyannote diarization |
| `notes_generator.py` | Claude prompt + notes formatting |
| `menubar.py` | macOS menu bar / Windows system tray app |
| `settings_window.py` | tkinter settings UI |
| `generate_icon.py` | Builds NoteNinja.icns from icon.png |
| `tests/` | pytest test suite |

---

## Adding tests

Tests live in `tests/`. We use `unittest.mock` to avoid hitting real APIs or audio hardware — keep it that way. See existing tests for patterns.

---

## Code style

- No comments unless the *why* is non-obvious
- No unused imports or dead code
- Keep functions small and focused
- Run existing tests before opening a PR — CI will catch failures but it's faster to check locally first
