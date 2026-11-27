from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .story import Ollama, OpenAI, StoryDraft


class PostingCopy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=3, max_length=100)
    caption: str = Field(min_length=3, max_length=2200)
    hashtags: list[Annotated[str, Field(min_length=2, max_length=50, pattern=r"^#[A-Za-z0-9_]+$")]] = Field(min_length=1, max_length=10)
    pinned_comment: str = Field(default="", max_length=300)


class GeneratedPostingCopy(PostingCopy):
    pinned_comment: str = Field(min_length=3, max_length=300)


def generate_posting_copy(story: StoryDraft, llm: Ollama | OpenAI) -> PostingCopy:
    return llm.structured(
        "Create one short title, caption, relevant hashtags, and a pinned comment for manual posting on short-video platforms. "
        "Keep the caption spoiler-free and end it with one story-specific invitation to respond. "
        "Write the first pinned comment as one concrete question that names a concrete detail, "
        "choice, or consequence unique to this story; "
        "do not repeat the caption verbatim. Avoid generic engagement bait, requests for likes or follows, "
        "spoilers, and false claims. Each hashtag starts with # and contains no spaces. Return JSON only. "
        f"Story: {story.script}",
        GeneratedPostingCopy,
    )
