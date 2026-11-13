import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .captions import CaptionCue
from .speech import audio_duration

CaptionPlacement = str
POSITIONS = {"lower_middle": 2, "middle": 5, "upper_middle": 8}


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    duration: float
    width: int
    height: int
    audio_streams: int


def _stamp(seconds: float) -> str:
    hundredths = round(seconds * 100)
    hours, rem = divmod(hundredths, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def _write_ass(path: Path, cues: list[CaptionCue], placement: str, width: int, height: int) -> None:
    if placement not in POSITIONS:
        raise ValueError("Invalid caption placement")
    size = round(width * .075)
    margin = round(height * .2) if placement != "middle" else 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,{POSITIONS[placement]},40,40,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for cue in cues:
        safe = cue.text.replace("{", "").replace("}", "").replace("\\", "")
        lines.append(f"Dialogue: 0,{_stamp(cue.start)},{_stamp(cue.end)},Default,,0,0,0,,{safe}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def render_video(clip: Path, audio: Path, cues: list[CaptionCue], placement: CaptionPlacement, output: Path, width: int = 1080, height: int = 1920) -> VideoInfo:
    if not cues:
        raise ValueError("At least one caption is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = audio_duration(audio)
    ass = output.with_suffix(".ass")
    _write_ass(ass, cues, placement, width, height)
    temporary = output.with_name(output.stem + ".tmp.mp4")
    escaped = str(ass).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},ass='{escaped}'"
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(clip), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-vf", vf, "-t", f"{duration:.6f}", "-r", "30", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(temporary)], check=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", str(temporary)], capture_output=True, text=True, check=True)
        data = json.loads(probe.stdout)
        video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
        audio_streams = sum(stream["codec_type"] == "audio" for stream in data["streams"])
        output_duration = float(data["format"]["duration"])
        if video["width"] != width or video["height"] != height or audio_streams != 1 or abs(output_duration - duration) > .1:
            raise ValueError("Rendered media failed duration or stream validation")
        temporary.replace(output)
        return VideoInfo(output, output_duration, width, height, audio_streams)
    finally:
        temporary.unlink(missing_ok=True)
