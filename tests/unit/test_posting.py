from story_teller.posting import PostingCopy, generate_posting_copy
from story_teller.story import StoryDraft


class FakeLLM:
    def structured(self, prompt, schema):
        assert schema is PostingCopy
        return PostingCopy(title="A strange message", caption="I never expected this.", hashtags=["#story"])


def test_copy_generated_only_for_selected_platforms():
    story = StoryDraft(script="I found a message. " * 20, summary="A strange message appeared", narrator="female")
    assert list(generate_posting_copy(story, ["youtube", "tiktok"], FakeLLM())) == ["youtube", "tiktok"]


def test_malformed_hashtag_is_rejected():
    from pydantic import ValidationError

    try:
        PostingCopy(title="Some title", caption="Some caption", hashtags=["not a hashtag"])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected invalid hashtag to be rejected")
