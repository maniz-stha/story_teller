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


_NUMBER_WORDS = {word: value for value, word in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
     "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
)}
_NUMBER_WORDS.update(dict(zip(["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"], range(20, 100, 10))))


def _comparison_words(text: str) -> list[str]:
    text = re.sub(r"(?<=\d)\s*,\s*(?=\d{3}\b)", "", text.lower().replace("’", "'"))
    words = re.findall(r"\w+(?:'\w+)*", text)
    result = []
    i = 0
    while i < len(words):
        if words[i] in _NUMBER_WORDS:
            total = group = 0
            previous_unit = False
            while i < len(words):
                word = words[i]
                if word in _NUMBER_WORDS:
                    amount = _NUMBER_WORDS[word]
                    if previous_unit and amount < 20:
                        break
                    group += amount
                    previous_unit = amount < 20
                elif word == "hundred":
                    group = max(group, 1) * 100
                    previous_unit = False
                elif word == "thousand":
                    total += max(group, 1) * 1000
                    group = 0
                    previous_unit = False
                elif word == "and" and (group >= 100 or total) and i + 1 < len(words) and words[i + 1] in _NUMBER_WORDS:
                    pass
                else:
                    break
                i += 1
            result.append(str(total + group))
        elif words[i].isdigit():
            result.append(str(int(words[i])))
            i += 1
        else:
            result.append(words[i])
            i += 1
            continue
        if i < len(words) and words[i] in ("dollar", "dollars", "percent"):
            i += 1
    return result


def validate_transcript(script: str, transcript: str) -> None:
    expected = _comparison_words(script)
    actual = _comparison_words(transcript)
    comparison = SequenceMatcher(None, expected, actual, autojunk=False)
    if comparison.ratio() < 0.97:
        raise ValueError("Narration transcript differs materially from script")
    for tag, start, end, actual_start, actual_end in comparison.get_opcodes():
        if tag == "equal" or max(end - start, actual_end - actual_start) <= 3:
            continue
        raise ValueError("Narration transcript differs materially from script")


def time_words(audio: Path, script: str) -> list[TimedWord]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), word_timestamps=True, condition_on_previous_text=False)
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
