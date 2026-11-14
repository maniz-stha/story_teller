#!/usr/bin/env python3
"""Create short, timed SRT captions locally from narration audio.

Setup (a separate Python 3.11 environment is recommended):
    python -m pip install faster-whisper
Usage:
    python audio_to_srt.py story_audio_1.5x.wav
    python audio_to_srt.py narration.wav --words 4 --model small.en

The first run downloads the model; transcription then runs locally on CPU.
SRT stores text and timing, not fonts, animation, or word highlighting.
"""

import argparse
from pathlib import Path


def timestamp(milliseconds):
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def build_srt(words, max_words=5):
    """Group timestamped words at pauses, sentence endings, or size limits."""
    groups = []
    group = []
    for word in words:
        if not word.word.strip():
            continue
        if group and (
            word.start - group[-1].end > 0.45
            or word.end - group[0].start > 2.5
            or len(" ".join(w.word.strip() for w in group + [word])) > 42
        ):
            groups.append(group)
            group = []
        group.append(word)
        if len(group) >= max_words or word.word.rstrip().endswith(
            (".", "?", "!", '."', '?"', '!"', ".”", "?”", "!”")
        ):
            groups.append(group)
            group = []
    if group:
        groups.append(group)

    blocks = []
    previous_end = 0
    for index, group in enumerate(groups, 1):
        start = max(previous_end, round(group[0].start * 1000), 0)
        end = max(start + 1, round(group[-1].end * 1000))
        text = " ".join(word.word.strip() for word in group)
        blocks.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n")
        previous_end = end
    return "\n".join(blocks) + ("\n" if blocks else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path, help="Final audio, after speed changes")
    parser.add_argument("-o", "--output", type=Path, help="Default: audio filename with .srt")
    parser.add_argument("--model", default="small.en", help="Default: small.en; try base.en for speed")
    parser.add_argument("--language", default="en", help="Language code; default: en")
    parser.add_argument("--words", type=int, default=5, help="Maximum words per caption; default: 5")
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error(f"Audio file not found: {args.audio}")
    if args.words < 1:
        parser.error("--words must be at least 1")
    output = args.output or args.audio.with_suffix(".srt")
    if output.resolve() == args.audio.resolve():
        parser.error("Output must differ from the input audio")
    if output.exists():
        parser.error(f"Output already exists: {output}; choose another path with -o")
    if not output.parent.is_dir():
        parser.error(f"Output directory does not exist: {output.parent}")

    from faster_whisper import WhisperModel

    print(f"Loading {args.model} on CPU (int8)...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(args.audio), language=args.language, word_timestamps=True,
        vad_filter=True, condition_on_previous_text=False,
    )
    words = []
    for segment in segments:
        words.extend(segment.words or [])
        print(f"Transcribed through {segment.end:.1f}s", flush=True)
    srt = build_srt(words, args.words)
    if not srt:
        raise SystemExit("No speech detected; no SRT written.")
    with output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(srt)
    print(f"Saved: {output.resolve()}")


if __name__ == "__main__":
    main()
