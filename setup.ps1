# NoteNinja Windows Setup
# Run this once in PowerShell: .\setup.ps1

$ErrorActionPreference = "Stop"
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $DIR

Write-Host ""
Write-Host "Setting up NoteNinja..."
Write-Host ""

# Require Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install from https://python.org (check 'Add to PATH')"
    exit 1
}

# Create virtual environment
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    Write-Host "Virtual environment created."
}

# Install dependencies
Write-Host "Installing dependencies (first run installs torch ~2 GB, may take a few minutes)..."
.venv\Scripts\pip install -q --upgrade pip
.venv\Scripts\pip install -q -r requirements.txt
.venv\Scripts\pip install -q -r requirements-dev.txt
Write-Host "Dependencies installed."

Write-Host ""
Write-Host "================================================"
Write-Host "  Setup complete!"
Write-Host "================================================"
Write-Host ""
Write-Host "  Start NoteNinja:"
Write-Host "    .\run.bat"
Write-Host ""
Write-Host "  Watch for Teams calls automatically:"
Write-Host "    .\run.bat watch"
Write-Host ""
Write-Host "  Run tests:"
Write-Host "    .\run.bat pytest tests/ -v"
Write-Host ""
Write-Host "  -- VB-Audio setup (for Teams / phone calls) --"
Write-Host ""
Write-Host "  1. Download and install VB-Audio Virtual Cable (free):"
Write-Host "       https://vb-audio.com/Cable"
Write-Host "     Then REBOOT your PC."
Write-Host ""
Write-Host "  2. Set Teams to output audio through the cable:"
Write-Host "       Teams -> Settings -> Devices -> Speaker: CABLE Input (VB-Audio Virtual Cable)"
Write-Host ""
Write-Host "  3. To hear the call while recording, enable Listen:"
Write-Host "       Windows Settings -> Sound -> More sound settings"
Write-Host "       Recording tab -> CABLE Output -> Properties"
Write-Host "       Listen tab -> check 'Listen to this device'"
Write-Host "       Playback through: your speakers or headphones"
Write-Host ""
Write-Host "  4. In NoteNinja, choose [2] Teams call"
Write-Host "       It will auto-detect CABLE Output (VB-Audio Virtual Cable)"
Write-Host ""
Write-Host "  -- Optional: Speaker diarization (who said what) --"
Write-Host ""
Write-Host "  1. Create a free account at https://huggingface.co"
Write-Host "  2. Accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1"
Write-Host "  3. Accept terms at https://huggingface.co/pyannote/segmentation-3.0"
Write-Host "  4. Get a token at https://huggingface.co/settings/tokens"
Write-Host "  5. Add to .env:  HUGGINGFACE_TOKEN=hf_..."
Write-Host "     (model downloads ~1 GB on first use)"
Write-Host ""
