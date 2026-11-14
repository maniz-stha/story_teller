import os
import re
from pathlib import Path
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field


class StoryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    script: str = Field(min_length=100, max_length=5000)
    summary: str = Field(min_length=10, max_length=400)
    narrator: Literal["female", "male"]
    title: str | None = Field(default=None, min_length=3, max_length=120)


class StoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=3, max_length=120)
    narration: str = Field(min_length=100, max_length=5000)
    word_count: int = Field(gt=0)
    estimated_duration_seconds: float = Field(gt=0)
    continuity_note: str = Field(min_length=10, max_length=400)
    narrator: Literal["female", "male"]


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    passed: bool = Field(alias="pass")
    hook: int = Field(ge=1, le=5)
    coherence: int = Field(ge=1, le=5)
    ending: int = Field(ge=1, le=5)
    resolved: bool
    reasons: list[str] = Field(max_length=5)


T = TypeVar("T", bound=BaseModel)


class Ollama:
    def __init__(self, model: str = "qwen3:4b-instruct", base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url

    def structured(self, prompt: str, schema: type[T]) -> T:
        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = httpx.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "stream": False, "think": False, "format": schema.model_json_schema(), "messages": [{"role": "user", "content": prompt}]},
                    timeout=240,
                )
                response.raise_for_status()
                return schema.model_validate_json(response.json()["message"]["content"])
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
        raise ValueError(f"Ollama did not return valid {schema.__name__}: {last_error}")


def openai_api_key() -> str | None:
    if key := os.environ.get("OPENAI_API_KEY", "").strip():
        return key
    for dotenv in (Path(__file__).resolve().parents[2] / ".env", Path.cwd() / ".env"):
        if dotenv.is_file():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "OPENAI_API_KEY":
                    return value.strip().strip('"\'') or None
    return None


class OpenAI:
    def __init__(self, model: str):
        self.model = model

    def structured(self, prompt: str, schema: type[T]) -> T:
        key = openai_api_key()
        if not key:
            raise ValueError("OPENAI_API_KEY is required for the selected OpenAI model; set it in .env")
        # OpenAI strict schemas omit Pydantic's validation keywords; Pydantic checks the result.
        def strict_shape(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: strict_shape(v) for k, v in value.items() if k not in {
                    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
                    "exclusiveMaximum", "minItems", "maxItems", "pattern", "default",
                }}
            if isinstance(value, list):
                return [strict_shape(item) for item in value]
            return value

        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = httpx.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": self.model, "input": prompt, "store": False,
                        "text": {"format": {"type": "json_schema", "name": schema.__name__.lower(),
                                            "schema": strict_shape(schema.model_json_schema()), "strict": True}},
                    },
                    timeout=240,
                )
                response.raise_for_status()
                body = response.json()
                if body["status"] != "completed":
                    raise ValueError(f"OpenAI response status: {body['status']}")
                content = [item for output in body["output"] if output.get("type") == "message"
                           for item in output["content"] if item.get("type") == "output_text"]
                if not content:
                    raise ValueError("OpenAI returned no structured text (possibly refused)")
                return schema.model_validate_json(content[0]["text"])
            except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
                last_error = exc
        raise ValueError(f"OpenAI did not return valid {schema.__name__}: {last_error}")


def validate_story(draft: StoryDraft, target_words: int, recent: list[str]) -> None:
    words = draft.script.split()
    if not 0.9 * target_words <= len(words) <= 1.1 * target_words:
        raise ValueError(f"Story has {len(words)} words; target is {target_words}")
    if not re.search(r"\b(I|me|my|mine|we|our)\b", draft.script, re.IGNORECASE):
        raise ValueError("Story must be first person")
    normalized = set(re.findall(r"\w+", draft.summary.lower()))
    for previous in recent:
        other = set(re.findall(r"\w+", previous.lower()))
        if len(normalized & other) >= 6 and len(normalized & other) / max(1, len(normalized | other)) > 0.6:
            raise ValueError("Story repeats a recent plot")


def generate_story(inputs: dict[str, Any], recent: list[str], llm: Ollama | OpenAI, note: str | None = None, feedback: str | None = None) -> StoryDraft:
    target_words = round(int(inputs["target_duration"]) * int(inputs["narration_speed"]) / 60)
    prompt = (Path(__file__).with_name("story_prompt.txt").read_text(encoding="utf-8").format(
        theme=inputs.get("theme", "random"),
        target_duration=inputs["target_duration"],
        narration_speed=inputs["narration_speed"],
        tone=inputs.get("tone") or "suspenseful, believable, emotionally engaging",
        perspective=inputs.get("perspective", "first person"),
        audience=inputs.get("audience", "general adult audience"),
        language=inputs.get("language", "English"),
        premise=inputs.get("premise") or "none; invent an original idea",
        recent="; ".join(recent) or "none",
        avoid=inputs.get("avoid") or "none",
        note=note or "none",
        feedback=feedback or "none",
        target_words=target_words,
    ))
    result = llm.structured(prompt, StoryOutput)
    return StoryDraft(script=result.narration, summary=result.continuity_note, narrator=result.narrator, title=result.title)


def evaluate_story(draft: StoryDraft, inputs: dict[str, object], llm: Ollama | OpenAI) -> Evaluation:
    prompt = (
        "Evaluate this short story against the requested theme and the natural six-beat shape: "
        "specific hook, setup with personal stakes, connected escalation, consequential choice "
        "with a credible cost, earned payoff using a planted detail, and a closing line tied "
        "to the opening without a generic moral. Check believable motives, clear character "
        "relationships, emotional engagement, and easy-to-follow narration. Rate hook, coherence, "
        "and ending from 1 to 5. Identify the central question raised by the setup. Set "
        "resolved=false if the ending does not answer it, if the protagonist's choice does not "
        "affect the outcome, or if the payoff relies on a coincidence or sudden rescuer. Pass "
        "only if all scores are at least 3, resolved=true, and all beats are present. "
        "Give concrete reasons. "
        f"Inputs: {inputs}. Story: {draft.script}. Summary: {draft.summary}. Return only JSON."
    )
    result = llm.structured(prompt, Evaluation)
    if min(result.hook, result.coherence, result.ending) < 3 or not result.resolved:
        result.passed = False
    return result
