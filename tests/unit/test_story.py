import httpx
import pytest
from pydantic import ValidationError

from story_teller.story import (
    Evaluation,
    Ollama,
    StoryDraft,
    StoryOutput,
    evaluate_story,
    generate_story,
    validate_story,
)


def test_story_schema_rejects_missing_and_extra_fields():
    with pytest.raises(ValidationError):
        StoryDraft.model_validate({"script": "I left.", "summary": "Leaving"})
    with pytest.raises(ValidationError):
        StoryDraft.model_validate({"script": "I left.", "summary": "Leaving", "narrator": "female", "surprise": 1})


def test_story_schema_rejects_invalid_narrator_and_rating():
    with pytest.raises(ValidationError):
        StoryDraft.model_validate({"script": "I left.", "summary": "Leaving", "narrator": "unknown"})
    with pytest.raises(ValidationError):
        Evaluation.model_validate({"pass": True, "hook": 6, "coherence": 3, "ending": 3, "reasons": []})


def test_off_target_script_fails_business_validation():
    draft = StoryDraft(script="Someone went home. " * 100, summary="Someone leaves home", narrator="female")
    with pytest.raises(ValueError):
        validate_story(draft, target_words=200, recent=[])


def test_unresolved_central_question_fails_even_with_high_scores():
    draft = StoryDraft(script="I found a secret. " * 50, summary="A secret changes my job.", narrator="female")

    class Evaluator:
        def structured(self, prompt, schema):
            assert "central question" in prompt
            assert "protagonist" in prompt
            assert "final quarter" in prompt
            assert "wholesome" in prompt
            assert "mystery" in prompt
            assert "pass=false" in prompt
            return Evaluation.model_validate({"pass": True, "hook": 5, "coherence": 5, "ending": 5, "resolved": False, "reasons": ["The culprit is never identified"]})

    assert not evaluate_story(draft, {}, Evaluator()).passed


def test_story_length_must_support_requested_speaking_pace():
    draft = StoryDraft(script="I found the missing file. " * 58, summary="I uncover a missing file.", narrator="female")
    with pytest.raises(ValueError, match="target is 390"):
        validate_story(draft, target_words=390, recent=[])


def test_180_second_story_can_exceed_5000_characters():
    narration = "I found the extraordinarily complicated missing file. " * 112
    output = StoryOutput(title="The missing file", narration=narration, word_count=784,
                         estimated_duration_seconds=180, continuity_note="I found the file and resolved the case.", narrator="female")
    draft = StoryDraft(script=output.narration, summary=output.continuity_note, narrator=output.narrator)
    validate_story(draft, target_words=780, recent=[])


def test_story_just_below_requested_pace_is_revised():
    draft = StoryDraft(script="I found the missing file. " * 70, summary="I uncover a missing file.", narrator="female")
    with pytest.raises(ValueError, match="target is 390"):
        validate_story(draft, target_words=390, recent=[])


def test_structured_ollama_call_disables_reasoning_for_json(monkeypatch):
    seen = []

    def post(url, json, timeout):
        seen.append(json)
        content = '{"script":"' + "I found a clue. " * 20 + '","summary":"A clue changes my day.","narrator":"female"}'
        return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))

    monkeypatch.setattr("story_teller.story.httpx.post", post)
    Ollama().structured("Write a story", StoryDraft)
    assert seen[0]["think"] is False


def test_writer_uses_story_structure_and_resolved_inputs():
    class Writer:
        def structured(self, prompt, schema):
            assert schema is StoryOutput
            assert "390 words" in prompt
            assert "within 10%" in prompt
            for beat in ("IMMEDIATE HOOK", "NECESSARY CONTEXT", "CONNECTED SCENES AND ESCALATION", "PROTAGONIST ACTION AND SURPRISING DEVELOPMENT", "CLIMAX", "PAYOFF AND CLOSING"):
                assert beat in prompt
            for detail in ("workplace drama", "260 words per minute", "believable, tense", "first person", "general adult audience", "English", "falsified approvals", "A stolen ledger", "avoid a secret recording", "move the reveal earlier", "ending lacks a choice"):
                assert detail in prompt
            assert "privately" in prompt.lower()
            assert "2–4 sentences" in prompt
            assert "do not add a moral" in prompt.lower()
            assert '"continuity_note":' in prompt
            assert "Wholesome surprise:" in prompt
            assert "Everyday mystery:" in prompt
            assert '"narration":' in prompt
            return StoryOutput(title="The missing approval", narration="I found a clue. " * 98, word_count=392, estimated_duration_seconds=90.5, continuity_note="I found the clue and resolved it.", narrator="female")

    draft = generate_story({"theme": "workplace drama", "target_duration": 90, "narration_speed": 260, "tone": "believable, tense", "perspective": "first person", "audience": "general adult audience", "language": "English", "premise": "falsified approvals", "avoid": "avoid a secret recording"}, ["A stolen ledger"], Writer(), note="move the reveal earlier", feedback="ending lacks a choice")
    assert draft.title == "The missing approval"
    assert draft.summary == "I found the clue and resolved it."


def test_writer_preserves_blank_optional_inputs_for_template_defaults():
    class Writer:
        def structured(self, prompt, schema):
            assert "Tone: \n" in prompt
            assert "Optional premise: \n" in prompt
            return StoryOutput(title="A family promise", narration="I kept the promise. " * 100, word_count=400,
                               estimated_duration_seconds=92, continuity_note="I kept a promise to my family.", narrator="female")

    generate_story({"target_duration": 90, "narration_speed": 260, "tone": "", "premise": ""}, [], Writer())


def test_story_word_count_uses_spoken_words_not_apostrophe_fragments():
    draft = StoryDraft(script=("I don’t know why she left. " * 15).strip(), summary="A colleague suddenly leaves.", narrator="female")
    validate_story(draft, target_words=90, recent=[])
