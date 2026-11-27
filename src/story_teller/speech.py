import gc
import hashlib
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .story import StoryDraft


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration: float


def audio_duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def voice_reference(narrator: str) -> Path:
    if narrator not in ("female", "male"):
        raise ValueError("Invalid narrator")
    return Path(__file__).resolve().parents[2] / "samples" / f"{narrator}_voice_reference.mp3"


def managed_voice(root: Path, narrator: str) -> Path:
    source = voice_reference(narrator)
    if not source.is_file():
        raise FileNotFoundError(source)
    target = root / "voices" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    checksum = target.with_suffix(".sha256")
    if not target.exists():
        if audio_duration(source) <= 0:
            raise ValueError("Voice reference is not decodable")
        shutil.copy2(source, target)
        checksum.write_text(hashlib.sha256(target.read_bytes()).hexdigest() + "\n")
    elif not checksum.exists() and hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest():
        checksum.write_text(hashlib.sha256(target.read_bytes()).hexdigest() + "\n")
    if not checksum.exists() or checksum.read_text().strip() != hashlib.sha256(target.read_bytes()).hexdigest():
        raise ValueError("Managed voice reference checksum mismatch")
    return target


def adjust_duration(source: Path, output: Path, target_seconds: float) -> None:
    ratio = audio_duration(source) / target_seconds
    if not 0.5 <= ratio <= 2:
        raise ValueError("Required narration speed adjustment is too large")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-af", f"atempo={ratio:.6f}", str(output)], check=True)


def synthesize(story: StoryDraft, voice_ref: Path, output: Path, target_seconds: float) -> AudioInfo:
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    if device == "mps":
        try:
            return _synthesize_on_device(story, voice_ref, output, target_seconds, device)
        except RuntimeError as exc:
            if "MPS backend out of memory" not in str(exc):
                raise
        logging.getLogger(__name__).warning("MPS ran out of memory; retrying narration on CPU")
        gc.collect()
        torch.mps.empty_cache()
    return _synthesize_on_device(story, voice_ref, output, target_seconds, "cpu")


def _synthesize_on_device(story: StoryDraft, voice_ref: Path, output: Path, target_seconds: float, device: str) -> AudioInfo:
    import soundfile as sf
    import torch
    from chatterbox.tts import ChatterboxTTS

    model = ChatterboxTTS.from_pretrained(device=device)
    model.prepare_conditionals(str(voice_ref), exaggeration=0.8)
    sentences = re.split(r"(?<=[.!?])\s+", story.script.strip())
    chunks: list[str] = []
    for sentence in sentences:
        if chunks and len((chunks[-1] + " " + sentence).split()) <= 45:
            chunks[-1] += " " + sentence
        else:
            chunks.append(sentence)
    parts: list[torch.Tensor] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        wav = model.generate(chunk, exaggeration=0.8, cfg_weight=0.5).detach().cpu()
        if wav.ndim != 2 or wav.shape[-1] == 0:
            raise ValueError("Narration model returned empty audio")
        if parts:
            parts.append(wav.new_zeros((wav.shape[0], int(model.sr * .15))))
        parts.append(wav)
    if not parts:
        raise ValueError("Story has no spoken text")
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = output.with_name("raw.wav")
    sf.write(str(raw), torch.cat(parts, dim=-1).float().numpy().T, model.sr, subtype="PCM_16")
    adjust_duration(raw, output, target_seconds)
    raw.unlink()
    duration = audio_duration(output)
    if abs(duration - target_seconds) > 10:
        raise ValueError(f"Narration duration {duration:.1f}s is outside target")
    return AudioInfo(output, duration)
