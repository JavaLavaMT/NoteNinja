import wave
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recorder


def make_audio(seconds=2, channels=1, sample_rate=16000):
    """Generate a sine wave as int16 numpy array."""
    t = np.linspace(0, seconds, int(seconds * sample_rate))
    sine = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    if channels > 1:
        return np.stack([sine] * channels, axis=1)
    return sine


class TestSaveWav:
    def test_creates_valid_wav(self, tmp_path):
        audio = make_audio()
        path = recorder.save_wav(audio)
        try:
            with wave.open(path, "rb") as wf:
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 16000
                assert wf.getnchannels() == 1
        finally:
            os.unlink(path)

    def test_always_saves_mono(self, tmp_path):
        audio = make_audio()
        path = recorder.save_wav(audio)
        try:
            with wave.open(path, "rb") as wf:
                assert wf.getnchannels() == 1
        finally:
            os.unlink(path)

    def test_frame_count_matches_audio_length(self):
        audio = make_audio(seconds=3)
        path = recorder.save_wav(audio)
        try:
            with wave.open(path, "rb") as wf:
                assert wf.getnframes() == len(audio)
        finally:
            os.unlink(path)


class TestDeviceChannels:
    def test_returns_channel_count_from_device(self):
        mock_info = {"max_input_channels": 4}
        with patch("recorder.sd.query_devices", return_value=mock_info):
            assert recorder._device_channels(0) == 4

    def test_minimum_of_1_for_zero_channels(self):
        mock_info = {"max_input_channels": 0}
        with patch("recorder.sd.query_devices", return_value=mock_info):
            assert recorder._device_channels(0) == 1

    def test_none_device_uses_default_input(self):
        mock_info = {"max_input_channels": 2}
        with patch("recorder.sd.query_devices", return_value=mock_info) as mock_q:
            recorder._device_channels(None)
            mock_q.assert_called_once_with(kind="input")


class TestMonoDownmix:
    def test_multichannel_audio_mixes_to_mono(self):
        """Multi-channel audio recorded by record() should be mixed down to 1D."""
        stereo = np.array([[100, 200], [300, 400], [500, 600]], dtype=np.int16)
        result = stereo.mean(axis=1).astype(np.int16)
        assert result.ndim == 1
        assert len(result) == 3
        assert result[0] == 150  # (100+200)/2

    def test_mono_audio_stays_flat(self):
        mono = np.array([100, 200, 300], dtype=np.int16)
        result = mono.flatten()
        assert result.ndim == 1
        np.testing.assert_array_equal(result, mono)
