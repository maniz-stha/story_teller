import pytest

from story_teller.captions import TimedWord, group_cues, validate_transcript


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


def test_contiguous_missing_sentence_stops_render_even_when_total_similarity_is_high():
    words = [f"word{i}" for i in range(270)]
    script = " ".join(words)
    transcript = " ".join(words[:100] + words[110:])
    with pytest.raises(ValueError):
        validate_transcript(script, transcript)
