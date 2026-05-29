import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main


def make_device(dev_id, name, channels):
    info = {"max_input_channels": channels}
    return (dev_id, name), info


class TestFindAggregateDevice:
    def _mock_devices(self, specs):
        """specs: list of (id, name, channels)"""
        devices = [(dev_id, name) for dev_id, name, _ in specs]
        channel_map = {dev_id: ch for dev_id, _, ch in specs}

        def mock_query(dev_id, **kwargs):
            return {"max_input_channels": channel_map.get(dev_id, 2)}

        return devices, mock_query

    def test_prefers_aggregate_over_blackhole(self):
        devices, mock_query = self._mock_devices([
            (0, "BlackHole 2ch", 2),
            (1, "Aggregate Device", 4),
        ])
        with patch("main.sd.query_devices", side_effect=mock_query):
            result = main.find_aggregate_device(devices)
        assert result[1] == "Aggregate Device"

    def test_prefers_more_channels_among_same_priority(self):
        devices, mock_query = self._mock_devices([
            (0, "Aggregate Device A", 2),
            (1, "Aggregate Device B", 4),
        ])
        with patch("main.sd.query_devices", side_effect=mock_query):
            result = main.find_aggregate_device(devices)
        assert result[0] == 1  # device with 4 channels

    def test_returns_none_when_no_match(self):
        devices = [(0, "MacBook Pro Microphone"), (1, "MacBook Pro Speakers")]
        with patch("main.sd.query_devices", return_value={"max_input_channels": 1}):
            result = main.find_aggregate_device(devices)
        assert result is None

    def test_matches_multi_output(self):
        devices, mock_query = self._mock_devices([
            (0, "Multi-Output Device", 2),
        ])
        with patch("main.sd.query_devices", side_effect=mock_query):
            result = main.find_aggregate_device(devices)
        assert result is not None

    def test_matches_blackhole_when_only_option(self):
        devices, mock_query = self._mock_devices([
            (0, "BlackHole 2ch", 2),
        ])
        with patch("main.sd.query_devices", side_effect=mock_query):
            result = main.find_aggregate_device(devices)
        assert result is not None


class TestTeamsIsRunning:
    def test_returns_true_when_pgrep_finds_teams(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("main.subprocess.run", return_value=mock_result):
            assert main.teams_is_running() is True

    def test_returns_false_when_teams_not_found(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("main.subprocess.run", return_value=mock_result):
            assert main.teams_is_running() is False

    def test_calls_pgrep_with_teams(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("main.subprocess.run", return_value=mock_result) as mock_run:
            main.teams_is_running()
            args = mock_run.call_args[0][0]
            assert "teams" in " ".join(args).lower()


class TestAudioLevel:
    def test_returns_zero_on_exception(self):
        with patch("main.sd.InputStream", side_effect=Exception("no device")):
            level = main.audio_level(device_id=99)
        assert level == 0.0

    def test_returns_float(self):
        import numpy as np

        captured = []

        class FakeStream:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]

            def __enter__(self):
                # Feed some audio to the callback
                data = np.ones((1024, 1), dtype=np.int16) * 1000
                self.callback(data, 1024, None, None)
                return self

            def __exit__(self, *args):
                return False

        with patch("main.sd.InputStream", FakeStream):
            with patch("main.time.sleep"):
                level = main.audio_level(device_id=0, sample_secs=0)

        assert isinstance(level, float)
        assert level >= 0
