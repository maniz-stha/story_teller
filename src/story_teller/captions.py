import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class CaptionCue:
    text: str
    start: float
    end: float


def validate_transcript(script: str, transcript: str) -> None:
    expected = re.findall(r"\w+(?:'\w+)*", script.lower().replace("’", "'"))
    actual = re.findall(r"\w+(?:'\w+)*", transcript.lower().replace("’", "'"))
    comparison = SequenceMatcher(None, expected, actual)
    if comparison.ratio() < 0.97 or any(max(end - start, actual_end - actual_start) > 3 for tag, start, end, actual_start, actual_end in comparison.get_opcodes() if tag != "equal"):
        raise ValueError("Narration transcript differs materially from script")


def time_words(audio: Path, script: str) -> list[TimedWord]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), word_timestamps=True)
    words = [TimedWord(word.word.strip(), word.start, word.end) for segment in segments for word in (segment.words or [])]
    validate_transcript(script, " ".join(word.text for word in words))
    return words


def group_cues(words: list[TimedWord], audio_duration: float) -> list[CaptionCue]:
    cues: list[CaptionCue] = []
    current: list[TimedWord] = []
    for word in words:
        if word.end > audio_duration + 0.05:
            raise ValueError("Caption exceeds audio duration")
        current.append(word)
        if len(current) >= 6 or (len(current) >= 4 and word.text.endswith((".", "?", "!"))):
            cues.append(CaptionCue(" ".join(w.text for w in current), current[0].start, min(audio_duration, current[-1].end)))
            current = []
    if current:
        cues.append(CaptionCue(" ".join(w.text for w in current), current[0].start, min(audio_duration, current[-1].end)))
    return cues
