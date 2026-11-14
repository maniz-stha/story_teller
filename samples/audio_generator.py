from pathlib import Path
import re
import subprocess

import torch
import soundfile as sf
from chatterbox.tts import ChatterboxTTS

# Resolve files relative to this script.
base_dir = Path(__file__).resolve().parent
text = (base_dir / "story.txt").read_text(encoding="utf-8").strip()

if not text:
    raise ValueError("story.txt is empty")

if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

print(f"Using device: {device}")

model = ChatterboxTTS.from_pretrained(device=device)
model.prepare_conditionals(
    str(base_dir / "female_voice_reference.mp3"),
    exaggeration=0.8,
)

# Blank lines mark narration sections.
sections = [
    section.strip()
    for section in re.split(r"\n\s*\n", text)
    if section.strip()
]

parts = []

for index, section in enumerate(sections, start=1):
    print(f"Generating section {index}/{len(sections)}")

    audio = model.generate(section, exaggeration=0.8, cfg_weight=0.5).detach().cpu()

    if audio.ndim != 2 or audio.shape[-1] == 0:
        raise RuntimeError(f"Invalid audio for section {index}")

    if parts:
        # A short pause between sections.
        pause = audio.new_zeros(
            (audio.shape[0], int(model.sr * 0.15))
        )
        parts.append(pause)

    parts.append(audio)

audio = torch.cat(parts, dim=-1)
output_path = base_dir / "story_audio.wav"

sf.write(
    str(output_path),
    audio.detach().cpu().float().numpy().T,
    model.sr,
    subtype="PCM_16",
)

fast_output_path = output_path.with_name(
    f"{output_path.stem}_1.5x.wav"
)

subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-i", str(output_path),
        "-af", "atempo=1.5",
        str(fast_output_path),
    ],
    check=True,
)

print(f"Saved faster version: {fast_output_path}")

duration = audio.shape[-1] / model.sr
print(f"Saved: {output_path}")
print(f"Duration: {duration:.1f} seconds")
