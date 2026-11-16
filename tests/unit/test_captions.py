import sys
from types import SimpleNamespace

import pytest

from story_teller.captions import TimedWord, group_cues, time_words, validate_transcript


def test_groups_about_six_words_without_exceeding_audio():
    words = [TimedWord(text=f"word{i}", start=i * .3, end=(i + 1) * .3) for i in range(13)]
    cues = group_cues(words, audio_duration=3.9)
    assert [len(c.text.split()) for c in cues] == [6, 6, 1]
    assert cues[-1].end <= 3.9


def test_missing_transcribed_words_stop_render():
    with pytest.raises(ValueError):
        validate_transcript("I found the locked drawer", "I found drawer")


def test_curly_quotes_and_contractions_match_recognized_speech():
    validate_transcript("I’d seen her. 'Don’t tell anyone.' She’d left.", "I'd seen her. Don't tell anyone. She'd left.")


def test_spoken_price_matches_asr_currency_notation():
    validate_transcript("I sold the piano for twenty four hundred dollars.",
                        "I sold the piano for $2 ,400.")
    with pytest.raises(ValueError):
        validate_transcript("I sold the piano for twenty four hundred dollars.",
                            "I sold the piano for $2 ,500.")


def test_close_asr_wording_does_not_hide_a_different_passage():
    before = " ".join(f"on word{i}" for i in range(100))
    after = " ".join(f"on tail{i}" for i in range(100))
    validate_transcript(f"{before} drying on every one {after}",
                        f"{before} drawing on everyone {after}")
    with pytest.raises(ValueError):
        validate_transcript(f"{before} I found the signed contract in the drawer {after}",
                            f"{before} I hid our last payment from the client {after}")


def test_contiguous_missing_sentence_stops_render_even_when_total_similarity_is_high():
    words = [f"word{i}" for i in range(270)]
    script = " ".join(words)
    transcript = " ".join(words[:100] + words[110:])
    with pytest.raises(ValueError):
        validate_transcript(script, transcript)


def test_timing_does_not_lose_spoken_words_to_previous_transcription_context(tmp_path, monkeypatch):
    script = "I opened the case history on my laptop. The system kept every status change."

    class WhisperModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, audio, **kwargs):
            spoken = script if kwargs.get("condition_on_previous_text") is False else "I opened the status change."
            words = [SimpleNamespace(word=word, start=i, end=i + 1) for i, word in enumerate(spoken.split())]
            return [SimpleNamespace(words=words)], None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=WhisperModel))
    assert len(time_words(tmp_path / "narration.wav", script)) == len(script.split())
