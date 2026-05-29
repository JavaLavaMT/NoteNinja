# NoteNinja

Local AI meeting note-taker. Records in-person meetings (mic) or phone/Teams calls (BlackHole), transcribes with OpenAI Whisper, and generates structured notes with Claude. Optionally identifies who said what with speaker diarization (runs locally, no extra API cost).

---

## What you need before setup

### Required accounts

| Account | Cost | Used for |
|---|---|---|
| [Anthropic](https://console.anthropic.com) | Pay-per-use (~$0.01/meeting) | Generating structured notes |
| [OpenAI](https://platform.openai.com) | Pay-per-use (~$0.006/min audio) | Transcribing audio with Whisper |

### Optional — speaker diarization (identifies who said what)

| Account | Cost | Used for |
|---|---|---|
| [HuggingFace](https://huggingface.co) | Free | Downloading the pyannote diarization model |

HuggingFace setup (one-time, ~5 min):
1. Create a free account at huggingface.co
2. Go to huggingface.co/pyannote/speaker-diarization-3.1 → click **Agree and access repository**
3. Go to huggingface.co/pyannote/segmentation-3.0 → click **Agree and access repository**
4. Go to huggingface.co/settings/tokens → create a token (read-only is fine)
5. Add it to your `.env` file (see below)

The model downloads once (~1 GB) on first use, then runs entirely on your Mac — no audio is uploaded anywhere.

---

## Installation

### 1. Install BlackHole (for recording Teams/phone calls)

```bash
brew install blackhole-2ch
```

Reboot your Mac after it installs.

### 2. Configure Audio MIDI Setup (one-time)

Open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup")

**Create an Aggregate Device** (captures both sides of a call):
- Click **+** → Create Aggregate Device
- Check: **BlackHole 2ch**, **MacBook Pro Microphone**, **Microsoft Teams Audio**
- Set Clock Source to **BlackHole 2ch**
- Enable Drift Correction on **MacBook Pro Microphone**

![Aggregate Device setup](aggregate-device-setup.png)

**Create a Multi-Output Device** (so you can still hear the call):
- Click **+** → Create Multi-Output Device
- Check: **MacBook Pro Speakers**, **BlackHole 2ch**
- Set Primary Device to **MacBook Pro Speakers**
- Enable Drift Correction on **MacBook Pro Speakers**

![Multi-Output Device setup](multi-output-device-setup.png)

**Before each Teams call:**
- In Teams → Settings → Devices → set Speaker to **Multi-Output Device**
- Switch back to your normal speakers/AirPods when done

### 3. Install NoteNinja

```bash
cd ~/Desktop/GitHub/projects/NoteNinja
./setup.sh
```

This creates a Python virtual environment and installs all dependencies.

### 4. Add your API keys

The app will ask for your keys on first run and save them to `.env`. Or create the file manually:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
HUGGINGFACE_TOKEN=hf_...   # optional, for speaker diarization
```

---

## Usage

```bash
./run
```

| Option | Description |
|---|---|
| **[1] In-person** | Records from your microphone |
| **[2] Teams / phone call** | Records from the BlackHole Aggregate Device (both sides) |
| **[3] Choose device manually** | Pick any input device from a list |
| **[4] Generate notes from transcript** | Re-run note generation on an existing transcript file |
| **[5] Exit** | Quit |

**While recording:**
- `p` + Enter → pause
- `r` + Enter → resume
- Enter → stop and generate notes

Notes and transcripts are saved to `~/meeting-notes/`.

---

## How it works

```
Mic / BlackHole Aggregate Device
        ↓
  NoteNinja records audio
        ↓
  Live preview: Whisper transcribes every 30s and prints to terminal
        ↓
  Final transcription:
    • With HuggingFace token → pyannote diarization + Whisper word timestamps
                                (labels Speaker A, Speaker B, etc.)
    • Without token → Whisper only (no speaker labels)
        ↓
  Claude generates structured notes
        ↓
  Saved to ~/meeting-notes/MeetingName_timestamp_notes.md
```
