from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .story import Ollama, OpenAI, StoryDraft


class PostingCopy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=3, max_length=100)
    caption: str = Field(min_length=3, max_length=2200)
    hashtags: list[Annotated[str, Field(min_length=2, max_length=50, pattern=r"^#[A-Za-z0-9_]+$")]] = Field(min_length=1, max_length=10)


def generate_posting_copy(story: StoryDraft, llm: Ollama | OpenAI) -> PostingCopy:
    return llm.structured(
        "Create one short title, caption, and relevant hashtags for manual posting on short-video platforms. "
        "Avoid spoilers and false claims. Each hashtag starts with # and contains no spaces. Return JSON only. "
        f"Story: {story.script}",
        PostingCopy,
    )
