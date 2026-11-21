import subprocess
from pathlib import Path

import pytest
import torch

from story_teller import speech
from story_teller.speech import (
    adjust_duration,
    audio_duration,
    managed_voice,
    synthesize,
    voice_reference,
)
from story_teller.story import StoryDraft


def test_voice_selection_and_actual_duration(tmp_path: Path):
    assert voice_reference("male").name == "male_voice_reference.mp3"
    assert voice_reference("female").name == "female_voice_reference.mp3"
    source = tmp_path / "source.wav"
    target = tmp_path / "target.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", str(source)], check=True)
    adjust_duration(source, target, 1.5)
    assert abs(audio_duration(target) - 1.5) < .05


def test_voice_copy_records_checksum(tmp_path: Path):
    copied = managed_voice(tmp_path, "female")
    assert copied.is_file()
    assert copied.with_suffix(".sha256").read_text().strip() == "2efc0418b12521134dcc23f6705ef1a5a3304ae30a7992551f4268b6c8437245"


def test_existing_reference_without_checksum_is_registered(tmp_path: Path):
    target = tmp_path / "voices" / "female_voice_reference.mp3"
    target.parent.mkdir()
    target.write_bytes(voice_reference("female").read_bytes())
    assert managed_voice(tmp_path, "female") == target
    assert target.with_suffix(".sha256").is_file()


@pytest.mark.parametrize("oom_at", ["load", "generate"])
def test_mps_out_of_memory_retries_narration_on_cpu(tmp_path: Path, monkeypatch, oom_at: str):
    from chatterbox.tts import ChatterboxTTS

    devices = []
    cleared = []

    class FakeModel:
        sr = 24000

        def __init__(self, device):
            self.device = device

        def prepare_conditionals(self, *args, **kwargs):
            pass

        def generate(self, *args, **kwargs):
            if self.device == "mps" and oom_at == "generate":
                raise RuntimeError("MPS backend out of memory")
            return torch.zeros((1, 24000))

    def load_model(device):
        devices.append(device)
        if device == "mps" and oom_at == "load":
            raise RuntimeError("MPS backend out of memory")
        return FakeModel(device)

    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    monkeypatch.setattr(torch.mps, "empty_cache", lambda: cleared.append(True))
    monkeypatch.setattr(ChatterboxTTS, "from_pretrained", load_model)
    monkeypatch.setattr(speech, "adjust_duration", lambda source, output, target: output.write_bytes(source.read_bytes()))
    monkeypatch.setattr(speech, "audio_duration", lambda path: 1.0)
    story = StoryDraft(script="A safe short sentence. " * 6, summary="A short safe story.", narrator="female")

    result = synthesize(story, tmp_path / "voice.mp3", tmp_path / "narration.wav", 1.0)

    assert devices == ["mps", "cpu"]
    assert cleared == [True]
    assert result.path.is_file()


def test_unrelated_mps_error_does_not_fall_back(tmp_path: Path, monkeypatch):
    from chatterbox.tts import ChatterboxTTS

    devices = []

    def load_model(device):
        devices.append(device)
        raise RuntimeError("Model checkpoint is missing")

    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    monkeypatch.setattr(ChatterboxTTS, "from_pretrained", load_model)
    story = StoryDraft(script="A safe short sentence. " * 6, summary="A short safe story.", narrator="female")

    with pytest.raises(RuntimeError, match="Model checkpoint is missing"):
        synthesize(story, tmp_path / "voice.mp3", tmp_path / "narration.wav", 1.0)
    assert devices == ["mps"]
