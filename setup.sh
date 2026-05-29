#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "Setting up NoteNinja..."
echo ""

# Require python3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install from python.org or via 'brew install python'"
    exit 1
fi

# Require Homebrew portaudio (sounddevice dependency on macOS)
if command -v brew &>/dev/null; then
    if ! brew list portaudio &>/dev/null 2>&1; then
        echo "Installing portaudio (required for audio capture)..."
        brew install portaudio
    fi
else
    echo "WARNING: Homebrew not found. If setup fails, install portaudio manually."
fi

# Create virtual environment
if [ ! -d "$DIR/.venv" ]; then
    python3 -m venv "$DIR/.venv"
    echo "Virtual environment created."
fi

# Install dependencies
source "$DIR/.venv/bin/activate"
pip install -q --upgrade pip

echo "Installing dependencies (first run installs torch ~2 GB, may take a few minutes)..."
pip install -q -r "$DIR/requirements.txt"
echo "Dependencies installed."

# Install dev dependencies
pip install -q -r "$DIR/requirements-dev.txt"

# Make scripts executable
chmod +x "$DIR/run"

echo ""
echo "================================================"
echo "  Setup complete!"
echo "================================================"
echo ""
echo "  Start NoteNinja:"
echo "    ./run"
echo ""
echo "  Watch for Teams calls automatically:"
echo "    ./run watch"
echo ""
echo "  Run tests:"
echo "    ./run pytest tests/ -v"
echo ""
echo "  ── BlackHole setup (for Teams / phone calls) ──"
echo ""
echo "  1. Install BlackHole (free, no account):"
echo "       brew install blackhole-2ch"
echo "     Then REBOOT your Mac."
echo ""
echo "  2. Open 'Audio MIDI Setup' (Spotlight -> Audio MIDI Setup)"
echo ""
echo "  3. Create an Aggregate Device (captures both sides of a call):"
echo "       Click '+' -> Create Aggregate Device"
echo "       Check: BlackHole 2ch, MacBook Pro Microphone, Microsoft Teams Audio"
echo "       Set Clock Source to: BlackHole 2ch"
echo "       Enable Drift Correction on: MacBook Pro Microphone"
echo ""
echo "  4. Create a Multi-Output Device (so you can still hear the call):"
echo "       Click '+' -> Create Multi-Output Device"
echo "       Check: MacBook Pro Speakers, BlackHole 2ch"
echo "       Set Primary Device to: MacBook Pro Speakers"
echo "       Enable Drift Correction on: MacBook Pro Speakers"
echo ""
echo "  5. Before each Teams call:"
echo "       Teams -> Settings -> Devices -> Speaker: Multi-Output Device"
echo ""
echo "  ── Optional: Speaker diarization (who said what) ──"
echo ""
echo "  1. Create a free account at https://huggingface.co"
echo "  2. Accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1"
echo "  3. Accept terms at https://huggingface.co/pyannote/segmentation-3.0"
echo "  4. Get a token at https://huggingface.co/settings/tokens"
echo "  5. Add to .env:  HUGGINGFACE_TOKEN=hf_..."
echo "     (model downloads ~1 GB on first use)"
echo ""
