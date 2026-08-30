"""A small OpenRouter client for the scene agent.

Deliberately not a framework dependency. This is a tool that produces twin assets, so it lives in
`scripts/` and talks to one endpoint with `urllib`. Nothing here imports an OpenSDL package and
nothing in OpenSDL imports this.

The model this was built for is `z-ai/glm-5.3-flash`, chosen because it accepts images. A render
loop whose critic cannot see the render is a loop that argues with itself about text.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

#: 1.3M context, accepts text, image and video, and costs $0.075/$0.25 per million tokens. The
#: cheapness matters: an iterative loop that reruns twenty times is a rounding error at this price
#: and a real decision at a frontier model's.
DEFAULT_MODEL = "z-ai/glm-5.3-flash"

#: Two models, because the two jobs need different things. Writing a scene needs no eyes, and
#: GLM 4.6 does it reliably in 17-116s on every brief measured. Judging a render needs eyes, and
#: GLM 5.3 Flash is the cheap model that has them. Measured on the same base brief, 4.6 answered
#: four prompt variants out of four; 5.3 Flash exhausted its budget on all of them.
GENERATOR_MODEL = "z-ai/glm-4.6"
CRITIC_MODEL = "z-ai/glm-5.3-flash"

#: GLM 5.3 Flash does not stop reasoning on its own. Left alone it spends the whole completion
#: budget thinking and returns `finish_reason="length"` with zero content, which reads as the model
#: having nothing to say. Measured on one Blender brief: plain, 143s and 6000 tokens of reasoning
#: for 0 bytes of answer; with this flag, 34s and 2181 bytes. It still reasons — the flag excludes
#: the trace from the response — but it now yields an answer. `{"enabled": false}` is rejected by
#: the provider outright.
REASONING = {"exclude": True}


class MissingCredential(RuntimeError):
    """Raised when no key is configured, with the two ways to supply one."""


@dataclass(frozen=True)
class Reply:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        """What this exchange cost, at the published GLM 5.3 Flash rates."""

        return self.prompt_tokens * 0.075e-6 + self.completion_tokens * 0.25e-6


def api_key(explicit: str | None = None) -> str:
    """The key, from the argument, the environment, or a file, in that order."""

    if explicit:
        return explicit
    from_env = os.environ.get("OPENROUTER_API_KEY")
    if from_env:
        return from_env
    for candidate in (
        Path.home() / ".secrets" / "openrouter",
        Path.home() / ".config" / "openrouter" / "key",
    ):
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8").strip()
            if content:
                return content
    raise MissingCredential(
        "no OpenRouter key. Set OPENROUTER_API_KEY, or write the key to ~/.secrets/openrouter. "
        "Get one at https://openrouter.ai/keys."
    )


def image_part(path: Path) -> dict[str, object]:
    """One image, inlined as a data URL, in the shape the chat API expects."""

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{encoded}"},
    }


class NoContent(RuntimeError):
    """The model spent its budget reasoning and said nothing. Usually worth another attempt."""


def ask_retrying(
    messages: list[dict[str, object]],
    *,
    attempts: int = 3,
    max_tokens: int = 12000,
    model: str = DEFAULT_MODEL,
    key: str | None = None,
    temperature: float = 0.2,
) -> Reply:
    """`ask`, but a model that says nothing gets asked again with more room to answer.

    An empty reply killed a whole five-stage build once: the exception escaped the per-stage retry
    loop, so one transient failure at stage three threw away two stages that had already passed.
    Transport trouble belongs to the caller of the model, not to the thing being built.

    Each attempt raises the budget, since the failure mode is a reasoning trace that ran long.
    """
    budget = max_tokens
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return ask(
                messages,
                model=model,
                key=key,
                temperature=temperature,
                max_tokens=budget,
            )
        except NoContent as exc:
            last = exc
            budget = int(budget * 1.6)
        except RuntimeError as exc:
            last = exc
            time.sleep(2.0 * (attempt + 1))
    raise last if last is not None else RuntimeError("no attempt was made")


def ask(
    messages: list[dict[str, object]],
    *,
    model: str = DEFAULT_MODEL,
    key: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 12000,
    timeout: float = 240.0,
) -> Reply:
    """One completion. Raises on transport failure so the caller decides whether to retry."""

    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning": REASONING,
        }
    ).encode("utf-8")

    request = urllib.request.Request(  # noqa: S310
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key(key)}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/fl-sean03/OpenSDL",
            "X-Title": "OpenSDL scene agent",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenRouter returned {exc.code}: {detail}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {json.dumps(payload)[:400]}")
    usage = payload.get("usage") or {}
    message = choices[0].get("message") or {}
    text = message.get("content")
    if not text:
        # GLM 5.3 Flash reasons before it answers, and reasoning is billed as completion tokens.
        # An exhausted budget therefore returns content=None with a full reasoning trace, which
        # looks like a silent empty reply unless it is named.
        reason = choices[0].get("finish_reason")
        thought = (message.get("reasoning") or "")[:300]
        raise NoContent(
            f"the model returned no content (finish_reason={reason!r}). This usually means "
            f"max_tokens was spent on reasoning before any answer began. Reasoning began: "
            f"{thought!r}"
        )
    return Reply(
        text=text,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
    )


def fenced_python(text: str) -> str:
    """The largest Python block in a reply, or the whole reply if it is bare code.

    Models fence inconsistently and sometimes explain first. Taking the largest block rather than
    the first avoids picking up a two-line illustration in the preamble.
    """

    blocks: list[str] = []
    marker = "```"
    parts = text.split(marker)
    for index in range(1, len(parts), 2):
        block = parts[index]
        first_newline = block.find("\n")
        if first_newline == -1:
            continue
        language = block[:first_newline].strip().lower()
        code = block[first_newline + 1 :]
        if language in {"", "python", "py"}:
            blocks.append(code)
    if blocks:
        return max(blocks, key=len).strip()
    return text.strip()
