import logging
import os
import time
import platform
import subprocess
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

SYSTEM = platform.system()  # "Darwin" = macOS, "Windows" = Windows

LOG_PATH = Path.home() / ".noteninja.log"

def _setup_logging():
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

_setup_logging()
log = logging.getLogger("noteninja")

import numpy as np
from dotenv import load_dotenv
from anthropic import Anthropic
from openai import OpenAI

import sounddevice as sd

import recorder
import transcriber
import notes_generator

load_dotenv()

OUTPUT_DIR = Path.home() / "meeting-notes"

# How loud the Aggregate Device must be (0–32768) to count as an active call
CALL_AUDIO_THRESHOLD = 300
# Seconds between polls when watching for a call
WATCH_POLL_INTERVAL = 10
# Don't re-prompt within this many seconds after the user says no
ALERT_COOLDOWN = 60


def _load_key_config():
    config_path = Path(__file__).parent / "config.json"
    defaults = {"ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY":    "OPENAI_API_KEY",
                "HUGGINGFACE_TOKEN": "HUGGINGFACE_TOKEN",
                "env_file":          str(Path(__file__).parent / ".env")}
    if config_path.exists():
        import json
        try:
            return {**defaults, **json.loads(config_path.read_text())}
        except Exception:
            pass
    return defaults


def get_api_keys():
    cfg      = _load_key_config()
    env_path = Path(cfg["env_file"]).expanduser()
    load_dotenv(env_path)
    anthropic_key = os.environ.get(cfg["ANTHROPIC_API_KEY"], "")
    openai_key    = os.environ.get(cfg["OPENAI_API_KEY"], "")
    hf_token      = os.environ.get(cfg["HUGGINGFACE_TOKEN"], "")

    if anthropic_key and openai_key:
        return anthropic_key, openai_key, hf_token

    print("\n  First-time setup — enter your API keys (saved to .env)\n")

    if not anthropic_key:
        anthropic_key = input("  Anthropic API key:   ").strip()
    if not openai_key:
        openai_key = input("  OpenAI API key:      ").strip()
    if not hf_token:
        print("\n  Speaker diarization uses a free local model (pyannote.audio).")
        print("  One-time setup required:")
        print("    1. Create a free account at https://huggingface.co")
        print("    2. Accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1")
        print("    3. Accept terms at https://huggingface.co/pyannote/segmentation-3.0")
        print("    4. Get your token at https://huggingface.co/settings/tokens")
        hf_token = input("\n  HuggingFace token (Enter to skip): ").strip()

    with env_path.open("w") as f:
        f.write(f"ANTHROPIC_API_KEY={anthropic_key}\n")
        f.write(f"OPENAI_API_KEY={openai_key}\n")
        if hf_token:
            f.write(f"HUGGINGFACE_TOKEN={hf_token}\n")

    print(f"\n  Keys saved to {env_path}\n")
    return anthropic_key, openai_key, hf_token


def pick_device(devices):
    for i, (dev_id, name) in enumerate(devices):
        print(f"    [{i + 1}] {name}")
    while True:
        raw = input("\n  Select number: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(devices):
                return devices[idx][0]
        except ValueError:
            pass
        print("  Invalid — try again.")


def find_aggregate_device(devices):
    """Return (device_id, name) of the best aggregate/BlackHole/VB-Audio device, or None."""
    priority = ("aggregate", "multi-output", "loopback", "blackhole", "cable output", "vb-audio")
    matches = [d for d in devices if any(k in d[1].lower() for k in priority)]

    def _rank(d):
        name = d[1].lower()
        order = next((i for i, k in enumerate(priority) if k in name), 99)
        info = sd.query_devices(d[0])
        return (order, -int(info["max_input_channels"]))

    matches.sort(key=_rank)
    return matches[0] if matches else None


def make_preview_callback(openai_client):
    def on_chunk(audio):
        try:
            text = transcriber.transcribe_chunk(audio, openai_client)
            if text.strip():
                print(f"\n\n  [Live transcript]\n  {text.strip()}\n")
        except Exception as e:
            print(f"\n  [Preview error: {e}]")
    return on_chunk


def process_audio(audio, duration, meeting_name, openai_client, claude, hf_token, diarization):
    """Transcribe audio and generate notes. Returns (transcript_path, notes_path)."""
    print(f"\n  Captured {duration:.0f}s ({duration / 60:.1f} min)")
    log.info(f"Recording finished: '{meeting_name}' — {duration:.0f}s ({duration/60:.1f} min)")
    wav_path = recorder.save_wav(audio)

    try:
        log.info("Transcribing...")
        if diarization:
            transcript = transcriber.transcribe_diarized_local(wav_path, openai_client, hf_token)
        else:
            transcript = transcriber.transcribe(wav_path, openai_client)
    finally:
        os.unlink(wav_path)

    if not transcript.strip():
        print("  No speech detected in recording.")
        log.warning("No speech detected in recording.")
        return None, None

    safe_name = meeting_name.replace(" ", "_").replace("/", "-")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    transcript_path = OUTPUT_DIR / f"{safe_name}_{ts}_transcript.txt"
    transcript_path.write_text(transcript)
    print(f"  Transcript: {transcript_path}")
    log.info(f"Transcript saved: {transcript_path}")

    log.info("Generating notes...")
    notes = notes_generator.generate(transcript, meeting_name, claude)
    notes_path = OUTPUT_DIR / f"{safe_name}_{ts}_notes.md"
    notes_path.write_text(notes)
    print(f"  Notes:      {notes_path}\n")
    log.info(f"Notes saved: {notes_path}")

    print("-" * 60)
    print(notes)
    print("-" * 60)

    return transcript_path, notes_path


def notify(title, message):
    """Send a desktop notification (works even when terminal is minimized)."""
    try:
        if SYSTEM == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}" sound name "Glass"'],
                capture_output=True
            )
        else:
            from plyer import notification
            notification.notify(title=title, message=message, app_name="NoteNinja", timeout=10)
    except Exception:
        pass


def teams_is_running():
    try:
        return any("teams" in (p.name() or "").lower() for p in psutil.process_iter(["name"]))
    except Exception:
        r = subprocess.run(["pgrep", "-fi", "teams"], capture_output=True)
        return r.returncode == 0


def audio_level(device_id, sample_secs=1.5):
    """Return mean audio level (0–32768) on a device over sample_secs seconds."""
    levels = []

    def cb(indata, frames, time_info, status):
        levels.append(float(np.abs(indata.astype(np.float32)).mean()))

    try:
        channels = recorder._device_channels(device_id)
        with sd.InputStream(device=device_id, channels=channels, dtype="int16", callback=cb):
            time.sleep(sample_secs)
    except Exception:
        return 0.0

    return sum(levels) / len(levels) if levels else 0.0


def watch_for_teams(openai_client, claude, hf_token, diarization):
    """Poll for an active Teams call and prompt to record when one is detected."""
    devices = recorder.list_input_devices()
    agg = find_aggregate_device(devices)

    if not agg:
        if SYSTEM == "Darwin":
            print("\n  BlackHole Aggregate Device not found.")
            print("  Set it up in Audio MIDI Setup first (see README).")
        else:
            print("\n  VB-Audio Virtual Cable not found.")
            print("  Install it from vb-audio.com/Cable and set Teams output to CABLE Input (see README).")
        return

    device_id, device_name = agg
    print(f"\n  Watching for Teams calls via: {device_name}")
    print("  Press Ctrl+C to stop.\n")
    log.info(f"Watch mode started via: {device_name}")

    last_alerted = 0

    def _start_recording(device, meeting_name_default):
        meeting_name = input(f"  Meeting name (Enter for '{meeting_name_default}'): ").strip()
        if not meeting_name:
            meeting_name = meeting_name_default
        preview_cb = make_preview_callback(openai_client)
        audio, duration = recorder.record(device_id=device, on_preview_chunk=preview_cb)
        if audio is not None and duration >= 1:
            process_audio(audio, duration, meeting_name, openai_client, claude, hf_token, diarization)

    try:
        while True:
            # Auto-detect Teams call
            if teams_is_running():
                level = audio_level(device_id)
                now = time.time()
                if level > CALL_AUDIO_THRESHOLD and (now - last_alerted) > ALERT_COOLDOWN:
                    print(f"\n  Teams call detected!")
                    log.info(f"Teams call detected (audio level: {level:.0f})")
                    notify("NoteNinja", "Teams call detected — open NoteNinja to start recording")
                    answer = input("  Start recording? [Y/n]: ").strip().lower()
                    last_alerted = time.time()
                    if answer != "n":
                        _start_recording(device_id, f"Teams Call {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                        print("\n  Back to watching for Teams calls...")
                        last_alerted = time.time()
            else:
                print(f"\r  Watching — [m + Enter] for in-person recording...", end="", flush=True)

            time.sleep(WATCH_POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n  Stopped watching.\n")


def do_recording(choice, devices, openai_client):
    device_id = None

    if choice == "2":
        agg = find_aggregate_device(devices)
        if agg:
            device_id, name = agg
            ch = int(sd.query_devices(device_id)["max_input_channels"])
            print(f"\n  Using: {name}  ({ch} input channels)")
        else:
            print("\n  BlackHole Aggregate Device not found — falling back to manual selection.\n")
            device_id = pick_device(devices)
    elif choice == "3":
        print("\n  Available input devices:")
        device_id = pick_device(devices)

    preview_cb = make_preview_callback(openai_client)
    return recorder.record(device_id=device_id, on_preview_chunk=preview_cb)


def main():
    anthropic_key, openai_key, hf_token = get_api_keys()
    claude = Anthropic(api_key=anthropic_key)
    openai_client = OpenAI(api_key=openai_key)
    OUTPUT_DIR.mkdir(exist_ok=True)

    diarization = bool(hf_token)
    log.info(f"NoteNinja started — diarization={'ON' if diarization else 'OFF'}")

    print("\n===========================")
    print("         NoteNinja")
    print("===========================")
    print(f"\n  Notes saved to: {OUTPUT_DIR}")
    print(f"  Speaker diarization: {'ON (local pyannote)' if diarization else 'OFF — add HUGGINGFACE_TOKEN to .env to enable'}")

    while True:
        print("\n  What kind of meeting?")
        print("  [1] In-person  (microphone)")
        print("  [2] Teams / phone call  (BlackHole aggregate device)")
        print("  [3] Choose audio device manually")
        print("  [4] Generate notes from existing transcript")
        print("  [5] Exit")

        choice = input("\n> ").strip()

        if choice == "5":
            print("\n  Goodbye!\n")
            break

        if choice == "4":
            transcript_input = input("\n  Path to transcript file: ").strip().strip("'\"")
            transcript_path = Path(transcript_input).expanduser()
            if not transcript_path.exists():
                print(f"  File not found: {transcript_path}")
                continue

            meeting_name = input("  Meeting name (Enter to skip): ").strip()
            if not meeting_name:
                meeting_name = transcript_path.stem.replace("_transcript", "").replace("_", " ")

            transcript = transcript_path.read_text()
            notes = notes_generator.generate(transcript, meeting_name, claude)

            notes_path = transcript_path.parent / transcript_path.name.replace("_transcript.txt", "_notes.md")
            if notes_path == transcript_path:
                notes_path = transcript_path.with_suffix("_notes.md")
            notes_path.write_text(notes)
            print(f"  Notes: {notes_path}\n")
            print("-" * 60)
            print(notes)
            print("-" * 60)
            continue

        if choice not in ("1", "2", "3"):
            print("  Invalid option.")
            continue

        meeting_name = input("\n  Meeting name (Enter to skip): ").strip()
        if not meeting_name:
            meeting_name = f"Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        devices = recorder.list_input_devices()
        audio, duration = do_recording(choice, devices, openai_client)

        if audio is None or duration < 1:
            print("\n  No audio captured.")
            continue

        process_audio(audio, duration, meeting_name, openai_client, claude, hf_token, diarization)

        if input("\n  Record another meeting? [y/N] ").strip().lower() != "y":
            print("\n  Goodbye!\n")
            break


def quick_record(mode):
    """Skip the menu and go straight to recording. Used by the menu bar app."""
    anthropic_key, openai_key, hf_token = get_api_keys()
    claude = Anthropic(api_key=anthropic_key)
    openai_client = OpenAI(api_key=openai_key)
    OUTPUT_DIR.mkdir(exist_ok=True)
    diarization = bool(hf_token)

    devices = recorder.list_input_devices()

    if mode == "mic":
        device_id = None
        default_name = f"In-Person Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    else:  # teams
        agg = find_aggregate_device(devices)
        if not agg:
            print("\n  Aggregate device not found. Set up BlackHole first (see README).")
            return
        device_id, name = agg
        ch = int(sd.query_devices(device_id)["max_input_channels"])
        print(f"\n  Using: {name}  ({ch} input channels)")
        default_name = f"Teams Call {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    meeting_name = input(f"\n  Meeting name (Enter for '{default_name}'): ").strip()
    if not meeting_name:
        meeting_name = default_name

    preview_cb = make_preview_callback(openai_client)
    audio, duration = recorder.record(device_id=device_id, on_preview_chunk=preview_cb)

    if audio is not None and duration >= 1:
        process_audio(audio, duration, meeting_name, openai_client, claude, hf_token, diarization)


if __name__ == "__main__":
    try:
        import sys
        arg = sys.argv[1] if len(sys.argv) > 1 else None
        if arg == "watch":
            anthropic_key, openai_key, hf_token = get_api_keys()
            claude = Anthropic(api_key=anthropic_key)
            openai_client = OpenAI(api_key=openai_key)
            OUTPUT_DIR.mkdir(exist_ok=True)
            watch_for_teams(openai_client, claude, hf_token, bool(hf_token))
        elif arg in ("mic", "teams"):
            quick_record(arg)
        else:
            main()
    except KeyboardInterrupt:
        print("\n\n  Goodbye!\n")
