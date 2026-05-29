import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import notes_generator


def make_mock_claude(response_text="# Meeting Notes"):
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = msg
    return client


class TestHasSpeakersDetection:
    def test_detects_speaker_labels(self):
        transcript = "Speaker A: Hello\nSpeaker B: Hi there"
        has = any(line.startswith("Speaker ") for line in transcript.splitlines()[:20])
        assert has is True

    def test_no_labels_in_plain_transcript(self):
        transcript = "Hello, how are you doing today? I'm doing well thanks."
        has = any(line.startswith("Speaker ") for line in transcript.splitlines()[:20])
        assert has is False

    def test_speaker_label_must_be_at_line_start(self):
        transcript = "I said to Speaker A that the meeting was good"
        has = any(line.startswith("Speaker ") for line in transcript.splitlines()[:20])
        assert has is False


class TestGenerate:
    def test_returns_claude_response(self):
        client = make_mock_claude("# My Notes\nSome content")
        result = notes_generator.generate("transcript text", "Test Meeting", client)
        assert result == "# My Notes\nSome content"

    def test_calls_claude_with_transcript(self):
        client = make_mock_claude()
        notes_generator.generate("the transcript content", "Meeting", client)
        call_args = client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "the transcript content" in prompt

    def test_includes_meeting_name_in_prompt(self):
        client = make_mock_claude()
        notes_generator.generate("transcript", "Q3 Planning", client)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Q3 Planning" in prompt

    def test_speaker_prompt_added_when_labels_present(self):
        client = make_mock_claude()
        transcript = "Speaker A: Let's do X\nSpeaker B: Agreed"
        notes_generator.generate(transcript, "Meeting", client)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "speaker labels" in prompt.lower()

    def test_no_speaker_prompt_without_labels(self):
        client = make_mock_claude()
        transcript = "Let's make sure we finish this by Friday"
        notes_generator.generate(transcript, "Meeting", client)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        # The phrase "the transcript includes speaker labels" only appears when diarization is on
        assert "the transcript includes speaker labels" not in prompt.lower()

    def test_action_item_instruction_always_present(self):
        client = make_mock_claude()
        notes_generator.generate("some transcript", "Meeting", client)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "action items" in prompt.lower()

    def test_uses_correct_model(self):
        client = make_mock_claude()
        notes_generator.generate("transcript", "Meeting", client)
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
