#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$HOME/Applications/NoteNinja.app"

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
    # tkinter support for the settings window
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if ! brew list python-tk@$PY_VER &>/dev/null 2>&1; then
        echo "Installing python-tk@$PY_VER (required for settings window)..."
        brew install python-tk@$PY_VER
    fi
else
    echo "WARNING: Homebrew not found. If setup fails, install portaudio and python-tk manually."
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
pip install -q -r "$DIR/requirements-dev.txt"
echo "Dependencies installed."

# Make scripts executable
chmod +x "$DIR/nj"
chmod +x "$DIR/nj-remove"

# Optionally add NoteNinja to PATH so "nj" works from anywhere
SHELL_RC="$HOME/.zshrc"
[ -n "$BASH_VERSION" ] && SHELL_RC="$HOME/.bashrc"
if ! grep -qF "$DIR" "$SHELL_RC" 2>/dev/null; then
    echo ""
    read -r -p "  Add 'nj' as a global command so you can run it from anywhere? [Y/n] " add_path
    if [[ "$add_path" != "n" && "$add_path" != "N" ]]; then
        echo "" >> "$SHELL_RC"
        echo "export PATH=\"$DIR:\$PATH\"  # NoteNinja" >> "$SHELL_RC"
        echo "  Added. Run 'source $SHELL_RC' after setup to activate."
    else
        echo "  Skipped — you can still run NoteNinja with ./nj from this directory."
    fi
fi

# Set up menu bar icon as a login item
echo ""
echo "Setting up 🥷 menu bar icon on login..."

osacompile -o "$APP_PATH" - <<APPLESCRIPT
on run
    set ninjaDir to "$DIR"
    do shell script "cd " & quoted form of ninjaDir & " && ./nj menubar > /dev/null 2>&1 &"
end run
APPLESCRIPT

osascript <<LOGINSCRIPT
tell application "System Events"
    if login item "NoteNinja" exists then
        delete login item "NoteNinja"
    end if
    make new login item at end of login items with properties {path:"$APP_PATH", hidden:false}
end tell
LOGINSCRIPT

echo "Done — NoteNinja.app added to Login Items."

# Apply ninja icon
python "$DIR/generate_icon.py"

# Launch the menu bar icon right now — no need to wait for next login
"$DIR/nj" menubar &

echo ""
echo "================================================"
echo "  Setup complete!"
echo "================================================"
echo ""
echo "  The 🥷 icon is now running in your menu bar."
echo ""
echo "  To remove the login item:"
echo "    ./nj-remove"
echo ""
echo "  Run tests:"
echo "    ./nj pytest tests/ -v"
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
