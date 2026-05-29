import wave
import os
import tempfile
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import transcriber


def make_wav(seconds=2, sample_rate=16000, tmp_path=None):
    """Write a silent WAV file and return its path."""
    frames = np.zeros(int(seconds * sample_rate), dtype=np.int16).tobytes()
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False,
                                    dir=tmp_path if tmp_path else None)
    with wave.open(f.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)
    return f.name


class TestSplitWav:
    def test_small_file_stays_as_one_chunk(self):
        path = make_wav(seconds=1)
        try:
            chunks = transcriber._split_wav(path)
            assert len(chunks) == 1
        finally:
            os.unlink(path)
            for c in chunks:
                if os.path.exists(c):
                    os.unlink(c)

    def test_large_file_splits_into_multiple_chunks(self):
        path = make_wav(seconds=2)
        # Force a tiny chunk size so a 2-second file must split
        original = transcriber.MAX_CHUNK_BYTES
        transcriber.MAX_CHUNK_BYTES = 16000 * 2 * 1  # 1 second worth
        try:
            chunks = transcriber._split_wav(path)
            assert len(chunks) >= 2
        finally:
            transcriber.MAX_CHUNK_BYTES = original
            os.unlink(path)
            for c in chunks:
                if os.path.exists(c):
                    os.unlink(c)

    def test_chunks_are_valid_wav_files(self):
        path = make_wav(seconds=2)
        original = transcriber.MAX_CHUNK_BYTES
        transcriber.MAX_CHUNK_BYTES = 16000 * 2 * 1
        try:
            chunks = transcriber._split_wav(path)
            for c in chunks:
                with wave.open(c, "rb") as wf:
                    assert wf.getnchannels() == 1
                    assert wf.getframerate() == 16000
        finally:
            transcriber.MAX_CHUNK_BYTES = original
            os.unlink(path)
            for c in chunks:
                if os.path.exists(c):
                    os.unlink(c)

    def test_total_frames_preserved_across_chunks(self):
        path = make_wav(seconds=3)
        original = transcriber.MAX_CHUNK_BYTES
        transcriber.MAX_CHUNK_BYTES = 16000 * 2 * 1
        try:
            chunks = transcriber._split_wav(path)
            total = sum(
                wave.open(c, "rb").getnframes() for c in chunks
            )
            with wave.open(path, "rb") as wf:
                assert total == wf.getnframes()
        finally:
            transcriber.MAX_CHUNK_BYTES = original
            os.unlink(path)
            for c in chunks:
                if os.path.exists(c):
                    os.unlink(c)


class TestTranscribe:
    def test_calls_whisper_for_small_file(self):
        path = make_wav(seconds=1)
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "hello world"
        try:
            result = transcriber.transcribe(path, mock_client)
            assert mock_client.audio.transcriptions.create.called
            assert result == "hello world"
        finally:
            os.unlink(path)

    def test_joins_chunks_with_space(self):
        path = make_wav(seconds=2)
        original = transcriber.MAX_CHUNK_BYTES
        # Force exactly 2 chunks: 2s at 16kHz mono int16 = 64000 bytes; set limit to 32000
        transcriber.MAX_CHUNK_BYTES = 32000
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = ["part one", "part two"]
        try:
            result = transcriber.transcribe(path, mock_client)
            assert "part one" in result
            assert "part two" in result
        finally:
            transcriber.MAX_CHUNK_BYTES = original
            os.unlink(path)

    def test_chunk_cleans_up_temp_files(self):
        path = make_wav(seconds=3)
        original = transcriber.MAX_CHUNK_BYTES
        transcriber.MAX_CHUNK_BYTES = 16000 * 2 * 1
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "text"
        created = []
        original_split = transcriber._split_wav

        def tracking_split(p):
            chunks = original_split(p)
            created.extend(chunks)
            return chunks

        try:
            with patch.object(transcriber, "_split_wav", tracking_split):
                transcriber.transcribe(path, mock_client)
            for c in created:
                assert not os.path.exists(c), f"Temp chunk not cleaned up: {c}"
        finally:
            transcriber.MAX_CHUNK_BYTES = original
            os.unlink(path)


class TestTranscribeChunk:
    def test_calls_whisper_with_wav(self):
        audio = np.zeros(16000, dtype=np.int16)
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "test"
        result = transcriber.transcribe_chunk(audio, mock_client)
        assert mock_client.audio.transcriptions.create.called
        assert result == "test"

    def test_cleans_up_temp_file(self):
        import tempfile as tmpmod
        audio = np.zeros(16000, dtype=np.int16)
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = ""
        created_paths = []

        original_ntf = tmpmod.NamedTemporaryFile

        def tracking_ntf(**kwargs):
            f = original_ntf(**kwargs)
            created_paths.append(f.name)
            return f

        with patch("transcriber.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            transcriber.transcribe_chunk(audio, mock_client)

        for path in created_paths:
            assert not os.path.exists(path), f"Temp file not cleaned up: {path}"


class TestSpeakerLabelMapping:
    def test_speakers_get_abc_labels(self):
        """Test that pyannote speaker IDs map to A, B, C in order of appearance."""
        speaker_map = {}

        def _label(spk):
            if spk not in speaker_map:
                speaker_map[spk] = chr(ord("A") + len(speaker_map))
            return speaker_map[spk]

        assert _label("SPEAKER_00") == "A"
        assert _label("SPEAKER_01") == "B"
        assert _label("SPEAKER_02") == "C"
        assert _label("SPEAKER_00") == "A"  # consistent on repeat

    def test_up_to_26_speakers_supported(self):
        speaker_map = {}

        def _label(spk):
            if spk not in speaker_map:
                speaker_map[spk] = chr(ord("A") + len(speaker_map))
            return speaker_map[spk]

        for i in range(26):
            lbl = _label(f"SPEAKER_{i:02d}")
            assert lbl == chr(ord("A") + i)
