import subprocess
from pathlib import Path

from story_teller.speech import adjust_duration, audio_duration, managed_voice, voice_reference


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
