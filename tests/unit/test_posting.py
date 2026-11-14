from story_teller.posting import PostingCopy, generate_posting_copy
from story_teller.story import StoryDraft


class FakeLLM:
    calls = 0

    def structured(self, prompt, schema):
        assert schema is PostingCopy
        assert "manual posting" in prompt
        self.calls += 1
        return PostingCopy(title="A strange message", caption="I never expected this.", hashtags=["#story"])


def test_one_shared_copy_generated():
    story = StoryDraft(script="I found a message. " * 20, summary="A strange message appeared", narrator="female")
    llm = FakeLLM()
    assert generate_posting_copy(story, llm).title == "A strange message"
    assert llm.calls == 1


def test_malformed_hashtag_is_rejected():
    from pydantic import ValidationError

    try:
        PostingCopy(title="Some title", caption="Some caption", hashtags=["not a hashtag"])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected invalid hashtag to be rejected")
