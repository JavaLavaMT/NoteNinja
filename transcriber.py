import os
import wave
import tempfile

MAX_CHUNK_BYTES = 24 * 1024 * 1024  # 24 MB (Whisper limit is 25 MB)


def _split_wav(wav_path):
    chunks = []
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames_per_chunk = MAX_CHUNK_BYTES // (n_channels * sampwidth)
        while True:
            frames = wf.readframes(frames_per_chunk)
            if not frames:
                break
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            with wave.open(tmp.name, "wb") as out:
                out.setnchannels(n_channels)
                out.setsampwidth(sampwidth)
                out.setframerate(framerate)
                out.writeframes(frames)
            chunks.append(tmp.name)
    return chunks


def transcribe(wav_path, openai_client):
    """Transcribe with Whisper (no speaker labels)."""
    file_size = os.path.getsize(wav_path)
    if file_size <= MAX_CHUNK_BYTES:
        print("  Transcribing...")
        with open(wav_path, "rb") as f:
            return str(openai_client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="text"
            ))

    chunk_paths = _split_wav(wav_path)
    print(f"  Transcribing in {len(chunk_paths)} parts...")
    parts = []
    for i, path in enumerate(chunk_paths, 1):
        print(f"    Part {i}/{len(chunk_paths)}...")
        try:
            with open(path, "rb") as f:
                parts.append(str(openai_client.audio.transcriptions.create(
                    model="whisper-1", file=f, response_format="text"
                )))
        finally:
            os.unlink(path)
    return " ".join(parts)


def transcribe_chunk(audio, openai_client):
    """Quick Whisper transcription of a raw numpy int16 array (for live preview)."""
    import wave, tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
        with open(tmp.name, "rb") as f:
            return str(openai_client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="text"
            ))
    finally:
        os.unlink(tmp.name)


def _transcribe_with_timestamps(wav_path, openai_client):
    """Return a flat list of word objects with correct timestamps, chunking if needed."""
    from types import SimpleNamespace

    def _fetch(path, offset=0.0):
        with open(path, "rb") as f:
            result = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        raw_words = getattr(result, "words", None) or []
        if offset == 0.0:
            return raw_words
        return [
            SimpleNamespace(word=w.word, start=w.start + offset, end=w.end + offset)
            for w in raw_words
        ]

    if os.path.getsize(wav_path) <= MAX_CHUNK_BYTES:
        return _fetch(wav_path)

    # File too large — split, transcribe each chunk, offset timestamps
    all_words = []
    time_offset = 0.0
    for chunk_path in _split_wav(wav_path):
        try:
            with wave.open(chunk_path, "rb") as wf:
                chunk_duration = wf.getnframes() / wf.getframerate()
            all_words.extend(_fetch(chunk_path, offset=time_offset))
            time_offset += chunk_duration
        finally:
            os.unlink(chunk_path)
    return all_words


_pipeline = None


def _load_pipeline(hf_token):
    global _pipeline
    if _pipeline is None:
        from pyannote.audio import Pipeline
        import torch
        print("  Loading speaker diarization model (first run downloads ~1 GB, takes a minute)...")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
        if torch.backends.mps.is_available():
            _pipeline = _pipeline.to(torch.device("mps"))
    return _pipeline


def transcribe_diarized_local(wav_path, openai_client, hf_token):
    """Transcribe with speaker diarization using pyannote (local) + Whisper word timestamps."""
    pipeline = _load_pipeline(hf_token)

    print("  Running speaker diarization...")
    # Preload audio to avoid torchcodec/FFmpeg dependency issues
    import soundfile as sf
    import torch
    waveform, sample_rate = sf.read(wav_path, dtype="float32")
    if waveform.ndim == 1:
        waveform = waveform[None, :]  # (1, time)
    else:
        waveform = waveform.T         # (channels, time)
    audio_input = {"waveform": torch.tensor(waveform), "sample_rate": sample_rate}
    raw = pipeline(audio_input)
    # Unwrap DiarizeOutput — newer pyannote wraps result in a dataclass
    if hasattr(raw, "itertracks"):
        diarization = raw
    elif hasattr(raw, "speaker_diarization"):
        diarization = raw.speaker_diarization
    elif hasattr(raw, "diarization"):
        diarization = raw.diarization
    elif hasattr(raw, "annotation"):
        diarization = raw.annotation
    else:
        diarization = raw

    print("  Transcribing with word timestamps...")
    words = _transcribe_with_timestamps(wav_path, openai_client)

    # Fall back to plain text if Whisper returned no word timestamps
    if not words:
        return transcribe(wav_path, openai_client)

    # Map pyannote speaker IDs (SPEAKER_00, etc.) to A, B, C...
    speaker_map = {}

    def _label(spk):
        if spk not in speaker_map:
            speaker_map[spk] = chr(ord("A") + len(speaker_map))
        return speaker_map[spk]

    def speaker_at(t):
        # Find the closest speaker segment if no exact match (handles brief gaps)
        best_spk = None
        best_dist = float("inf")
        for turn, _, spk in diarization.itertracks(yield_label=True):
            if turn.start <= t <= turn.end:
                return _label(spk)
            dist = min(abs(t - turn.start), abs(t - turn.end))
            if dist < best_dist:
                best_dist = dist
                best_spk = spk
        return _label(best_spk) if best_spk else "A"

    # Group consecutive words with the same speaker into utterances
    lines = []
    current_speaker = None
    current_words = []

    for w in words:
        mid = (w.start + w.end) / 2
        spk = speaker_at(mid)
        if spk != current_speaker:
            if current_words:
                lines.append(f"Speaker {current_speaker}: {' '.join(current_words).strip()}")
            current_speaker = spk
            current_words = [w.word]
        else:
            current_words.append(w.word)

    if current_words and current_speaker:
        lines.append(f"Speaker {current_speaker}: {' '.join(current_words).strip()}")

    return "\n".join(lines)
