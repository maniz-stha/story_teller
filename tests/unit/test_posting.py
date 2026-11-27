import pytest
from pydantic import ValidationError

from story_teller.posting import PostingCopy, generate_posting_copy
from story_teller.story import StoryDraft


class FakeLLM:
    calls = 0

    def structured(self, prompt, schema):
        assert issubclass(schema, PostingCopy)
        assert "manual posting" in prompt
        assert "story-specific" in prompt
        assert "pinned comment" in prompt
        assert "I found a message" in prompt
        self.calls += 1
        return schema(title="A strange message", caption="I never expected this. Would you have opened it?", hashtags=["#story"], pinned_comment="What would you have done with the message?")


def test_one_shared_copy_generated():
    story = StoryDraft(script="I found a message. " * 20, summary="A strange message appeared", narrator="female")
    llm = FakeLLM()
    copy = generate_posting_copy(story, llm)
    assert copy.title == "A strange message"
    assert copy.pinned_comment == "What would you have done with the message?"
    assert llm.calls == 1


def test_malformed_hashtag_is_rejected():
    from pydantic import ValidationError

    try:
        PostingCopy(title="Some title", caption="Some caption", hashtags=["not a hashtag"])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected invalid hashtag to be rejected")


def test_older_copy_without_pinned_comment_remains_valid():
    copy = PostingCopy(title="Some title", caption="Some caption", hashtags=["#story"])
    assert copy.pinned_comment == ""


def test_generated_copy_requires_a_pinned_comment():
    story = StoryDraft(script="I found a message. " * 20, summary="A strange message appeared", narrator="female")

    class MissingCommentLLM:
        def structured(self, prompt, schema):
            assert "concrete detail" in prompt
            return schema.model_validate({"title": "A strange message", "caption": "Would you open it?", "hashtags": ["#story"]})

    with pytest.raises(ValidationError):
        generate_posting_copy(story, MissingCommentLLM())
