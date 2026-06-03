"""
NoteNinja local API server — run with: python server.py
The npm SDK starts this automatically; you can also run it standalone.
"""
import argparse
import os
import threading
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from dotenv import load_dotenv
load_dotenv()

import warnings
warnings.filterwarnings("ignore", message="torchcodec")

app = FastAPI(title="NoteNinja", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # local only — safe
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path.home() / "meeting-notes"

# ── Recording state ──────────────────────────────────────────────────────────

_state = {
    "status": "idle",       # idle | recording | processing | done | error
    "session_id": None,
    "meeting_name": None,
    "started_at": None,
    "result": None,         # { transcript, notes, transcript_path, notes_path }
    "error": None,
    "stop_event": None,
}
_state_lock = threading.Lock()


# ── Models ───────────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    meeting_name: Optional[str] = None
    device_id: Optional[int] = None

class StopRequest(BaseModel):
    session_id: str
    extra_context: Optional[str] = ""

class NotesRequest(BaseModel):
    transcript: str
    meeting_name: Optional[str] = "Meeting"
    extra_context: Optional[str] = ""


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "version": "0.1.0"}


@app.get("/api/devices")
def list_devices():
    import recorder
    devices = recorder.list_input_devices()
    return {"devices": [{"id": i, "name": name} for i, name in devices]}


@app.post("/api/record/start")
def start_recording(req: StartRequest):
    with _state_lock:
        if _state["status"] == "recording":
            raise HTTPException(400, "Already recording")

        session_id = str(uuid.uuid4())
        meeting_name = req.meeting_name or f"Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        stop_event = threading.Event()

        _state.update({
            "status": "recording",
            "session_id": session_id,
            "meeting_name": meeting_name,
            "started_at": datetime.now().isoformat(),
            "result": None,
            "error": None,
            "stop_event": stop_event,
        })

    threading.Thread(
        target=_recording_worker,
        args=(session_id, meeting_name, req.device_id, stop_event),
        daemon=True,
    ).start()

    return {"session_id": session_id, "status": "recording", "meeting_name": meeting_name}


@app.post("/api/record/stop")
def stop_recording(req: StopRequest):
    with _state_lock:
        if _state["session_id"] != req.session_id:
            raise HTTPException(404, "Session not found")
        if _state["status"] != "recording":
            raise HTTPException(400, f"Not recording (status: {_state['status']})")
        _state["status"] = "processing"
        _state["extra_context"] = req.extra_context or ""
        stop_event = _state["stop_event"]

    stop_event.set()
    return {"status": "processing"}


@app.get("/api/record/status")
def recording_status():
    with _state_lock:
        return {
            "status": _state["status"],
            "session_id": _state["session_id"],
            "meeting_name": _state["meeting_name"],
            "started_at": _state["started_at"],
            "result": _state["result"],
            "error": _state["error"],
        }


@app.post("/api/notes")
def generate_notes(req: NotesRequest):
    """Generate notes from an existing transcript string."""
    import notes_generator
    from anthropic import Anthropic
    claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    notes = notes_generator.generate(req.transcript, req.meeting_name, claude, req.extra_context or "")
    return {"notes": notes}


# ── Recording worker (runs in background thread) ─────────────────────────────

def _recording_worker(session_id, meeting_name, device_id, stop_event):
    try:
        import recorder
        import transcriber
        import notes_generator
        from anthropic import Anthropic
        from openai import OpenAI

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        hf_token = os.environ.get("HUGGINGFACE_TOKEN", "")

        claude = Anthropic(api_key=anthropic_key)
        openai_client = OpenAI(api_key=openai_key)
        diarization = bool(hf_token)

        OUTPUT_DIR.mkdir(exist_ok=True)

        all_chunks = []
        import numpy as np
        import sounddevice as sd
        from recorder import SAMPLE_RATE

        channels = 1
        if device_id is not None:
            info = sd.query_devices(device_id)
            channels = max(1, int(info["max_input_channels"]))

        def callback(indata, frames, time_info, status):
            if not stop_event.is_set():
                all_chunks.append(indata.copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=channels,
            dtype="int16",
            device=device_id,
            callback=callback,
        ):
            stop_event.wait()

        if not all_chunks:
            with _state_lock:
                _state.update({"status": "error", "error": "No audio captured"})
            return

        audio = np.concatenate(all_chunks, axis=0)
        if audio.ndim > 1 and audio.shape[1] > 1:
            audio = audio.mean(axis=1).astype(np.int16)
        else:
            audio = audio.flatten()

        duration = len(audio) / SAMPLE_RATE

        with _state_lock:
            extra_context = _state.get("extra_context", "")

        wav_path = recorder.save_wav(audio)
        safe_name = meeting_name.replace(" ", "_").replace("/", "-")[:40]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        import shutil
        saved_wav = OUTPUT_DIR / f"{safe_name}_{ts}_audio.wav"

        try:
            if diarization:
                transcript = transcriber.transcribe_diarized_local(wav_path, openai_client, hf_token)
            else:
                transcript = transcriber.transcribe(wav_path, openai_client)
        finally:
            shutil.move(wav_path, saved_wav)

        transcript_path = OUTPUT_DIR / f"{safe_name}_{ts}_transcript.txt"
        transcript_path.write_text(transcript)

        notes = notes_generator.generate(transcript, meeting_name, claude, extra_context)
        notes_path = OUTPUT_DIR / f"{safe_name}_{ts}_notes.md"
        notes_path.write_text(notes)

        with _state_lock:
            _state.update({
                "status": "done",
                "result": {
                    "transcript": transcript,
                    "notes": notes,
                    "transcript_path": str(transcript_path),
                    "notes_path": str(notes_path),
                    "audio_path": str(saved_wav),
                    "duration_seconds": round(duration),
                },
            })

    except Exception as e:
        with _state_lock:
            _state.update({"status": "error", "error": str(e)})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7627)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    print(f"  NoteNinja API → http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
