import time
import wave
import tempfile
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
PREVIEW_INTERVAL = 30  # seconds between live preview transcriptions


def list_input_devices():
    devices = sd.query_devices()
    return [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]


def _device_channels(device_id):
    info = sd.query_devices(device_id) if device_id is not None else sd.query_devices(kind="input")
    return max(1, int(info["max_input_channels"]))


def record(device_id=None, on_preview_chunk=None):
    channels = _device_channels(device_id)
    print(f"\n  Recording... ({channels} input channels)")
    print("  [Enter]=stop   [p + Enter]=pause   [r + Enter]=resume\n")

    all_chunks = []
    preview_chunks = []
    all_lock = threading.Lock()
    preview_lock = threading.Lock()
    paused = threading.Event()
    stop_event = threading.Event()
    start_time = time.time()

    def show_timer():
        while not stop_event.is_set():
            elapsed = time.time() - start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            status = "PAUSED" if paused.is_set() else "●"
            print(f"\r  {status} {mins:02d}:{secs:02d}", end="", flush=True)
            time.sleep(1)

    def preview_worker():
        while not stop_event.is_set():
            time.sleep(PREVIEW_INTERVAL)
            if on_preview_chunk is None or stop_event.is_set():
                continue
            with preview_lock:
                if not preview_chunks:
                    continue
                chunk = np.concatenate(preview_chunks, axis=0)
                preview_chunks.clear()
            if chunk.ndim > 1 and chunk.shape[1] > 1:
                chunk = chunk.mean(axis=1).astype(np.int16)
            else:
                chunk = chunk.flatten()
            on_preview_chunk(chunk)

    def callback(indata, frames, time_info, status):
        if not paused.is_set():
            data = indata.copy()
            with all_lock:
                all_chunks.append(data)
            with preview_lock:
                preview_chunks.append(data)

    timer_thread = threading.Thread(target=show_timer, daemon=True)
    timer_thread.start()

    if on_preview_chunk:
        preview_thread = threading.Thread(target=preview_worker, daemon=True)
        preview_thread.start()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=channels,
            dtype="int16",
            device=device_id,
            callback=callback,
        ):
            while True:
                cmd = input().strip().lower()
                if cmd == "p":
                    paused.set()
                    print("\n  Paused. Type r + Enter to resume, or Enter alone to stop.")
                elif cmd == "r":
                    paused.clear()
                    print("\n  Resumed.")
                elif cmd == "":
                    break
    finally:
        stop_event.set()
        timer_thread.join(timeout=2)
        print()

    with all_lock:
        if not all_chunks:
            return None, 0
        audio = np.concatenate(all_chunks, axis=0)

    if audio.ndim > 1 and audio.shape[1] > 1:
        audio = audio.mean(axis=1).astype(np.int16)
    else:
        audio = audio.flatten()

    duration = len(audio) / SAMPLE_RATE
    return audio, duration


def save_wav(audio):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return tmp.name
