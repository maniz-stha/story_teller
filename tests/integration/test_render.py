import subprocess
from pathlib import Path

import pytest

from story_teller.captions import CaptionCue
from story_teller.render import render_video
from story_teller.service import inspect_video


@pytest.mark.parametrize("clip_seconds", [0.4, 2.0])
def test_video_matches_audio_for_short_and_long_clips(tmp_path: Path, clip_seconds: float):
    clip, audio, output = (tmp_path / name for name in ("clip.mp4", "voice.wav", "out.mp4"))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={clip_seconds}", "-f", "lavfi", "-i", f"sine=frequency=220:duration={clip_seconds}", "-shortest", "-y", str(clip)], check=True)
    assert abs(inspect_video(clip)[0] - clip_seconds) < .08
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", str(audio)], check=True)
    result = render_video(clip, audio, [CaptionCue("I found it", 0, .8)], "lower_middle", output, width=360, height=640)
    assert result.width == 360 and result.height == 640
    assert abs(result.duration - 1) < .08
    assert result.audio_streams == 1
