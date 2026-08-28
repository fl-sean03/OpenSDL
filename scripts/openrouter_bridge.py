"""Serve the Anthropic Messages API on top of OpenRouter, so any model can run in this harness.

Claude Code speaks one protocol and honours `ANTHROPIC_BASE_URL`, which was verified by pointing it
at a listener and watching it POST `/v1/messages?beta=true`. OpenRouter speaks OpenAI chat
completions. This is the translation between them, in the standard library, so it starts with
`python3 scripts/openrouter_bridge.py` and nothing else.

    OPENROUTER_API_KEY=... python3 scripts/openrouter_bridge.py --model z-ai/glm-5.3-flash
    ANTHROPIC_BASE_URL=http://127.0.0.1:8899 ANTHROPIC_API_KEY=unused claude -p "..."

**Upstream calls are not streamed, downstream responses are.** Claude Code wants server-sent events;
OpenRouter is asked for a whole response and the events are synthesised from it. That trades first
token latency for not having to reassemble partial tool-call JSON across chunk boundaries, which is
where this class of bridge usually breaks. For an agent loop, where the next action waits on the
whole message anyway, that is the right side of the trade.

What is deliberately not handled: prompt caching hints, thinking blocks, and citations. They are
dropped rather than faked, because a bridge that silently invents a capability is worse than one
that plainly lacks it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: Overridable so the bridge can be tested against a local fake without a live key.
UPSTREAM = os.environ.get(
    "OPENROUTER_COMPLETIONS_URL", "https://openrouter.ai/api/v1/chat/completions"
)

#: Anthropic stop reasons keyed by the OpenAI finish reason that means the same thing.
STOP_REASONS = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "end_turn",
}


# --------------------------------------------------------------------------- request translation


def _system_text(system: Any) -> str:
    """Anthropic allows a bare string or a list of blocks. OpenAI wants one string."""

    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n\n".join(
            str(block.get("text", "")) for block in system if isinstance(block, dict)
        )
    return ""


def _content_parts(content: Any) -> list[dict[str, Any]]:
    """Text and image blocks, in OpenAI's shape. Other block types are handled by the caller."""

    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    parts: list[dict[str, Any]] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append({"type": "text", "text": block.get("text", "")})
        elif kind == "image":
            source = block.get("source") or {}
            if source.get("type") == "base64":
                media = source.get("media_type", "image/png")
                data = source.get("data", "")
                parts.append(
                    {"type": "image_url", "image_url": {"url": f"data:{media};base64,{data}"}}
                )
            elif source.get("type") == "url":
                parts.append({"type": "image_url", "image_url": {"url": source.get("url", "")}})
    return parts


def to_openai(payload: dict[str, Any], model: str) -> dict[str, Any]:
    """One Anthropic Messages request, as an OpenAI chat completion request."""

    messages: list[dict[str, Any]] = []
    system = _system_text(payload.get("system"))
    if system:
        messages.append({"role": "system", "content": system})

    for message in payload.get("messages", []):
        role = message.get("role", "user")
        content = message.get("content")

        # A user turn carrying tool results becomes one OpenAI `tool` message per result.
        if isinstance(content, list):
            tool_results = [
                b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"
            ]
            for result in tool_results:
                body = result.get("content")
                if isinstance(body, list):
                    body = "\n".join(
                        str(part.get("text", "")) for part in body if isinstance(part, dict)
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.get("tool_use_id", ""),
                        "content": str(body if body is not None else ""),
                    }
                )

            tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            parts = _content_parts(
                [b for b in content if b not in tool_results and b not in tool_uses]
            )

            if tool_uses:
                messages.append(
                    {
                        "role": "assistant",
                        "content": "".join(p["text"] for p in parts if p.get("type") == "text")
                        or None,
                        "tool_calls": [
                            {
                                "id": use.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                "type": "function",
                                "function": {
                                    "name": use.get("name", ""),
                                    "arguments": json.dumps(use.get("input") or {}),
                                },
                            }
                            for use in tool_uses
                        ],
                    }
                )
            elif parts:
                messages.append({"role": role, "content": parts})
        elif content:
            messages.append({"role": role, "content": content})

    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": payload.get("max_tokens", 8192),
    }
    if "temperature" in payload:
        request["temperature"] = payload["temperature"]

    tools = payload.get("tools") or []
    translated = [
        {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", "")[:1024],
                "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
        if isinstance(tool, dict) and tool.get("name")
    ]
    if translated:
        request["tools"] = translated
        request["tool_choice"] = "auto"
    return request


# -------------------------------------------------------------------------- response translation


def to_anthropic_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    """An OpenAI assistant message, as Anthropic content blocks."""

    blocks: list[dict[str, Any]] = []
    text = message.get("content")
    if isinstance(text, str) and text.strip():
        blocks.append({"type": "text", "text": text})
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw = function.get("arguments") or "{}"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            parsed = {"_unparsed_arguments": raw}
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or f"toolu_{uuid.uuid4().hex[:16]}",
                "name": function.get("name", ""),
                "input": parsed if isinstance(parsed, dict) else {"value": parsed},
            }
        )
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    return blocks


def sse_events(blocks: list[dict[str, Any]], stop_reason: str, usage: dict[str, Any], model: str):
    """The Anthropic stream, synthesised whole. Each yielded item is one `event:`/`data:` pair."""

    message_id = f"msg_{uuid.uuid4().hex[:24]}"

    def event(name: str, body: dict[str, Any]) -> str:
        return f"event: {name}\ndata: {json.dumps(body)}\n\n"

    yield event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": int(usage.get("prompt_tokens", 0)),
                    "output_tokens": 0,
                },
            },
        },
    )

    for index, block in enumerate(blocks):
        if block["type"] == "text":
            yield event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            if block["text"]:
                yield event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "text_delta", "text": block["text"]},
                    },
                )
        else:
            yield event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": {},
                    },
                },
            )
            yield event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block["input"]),
                    },
                },
            )
        yield event("content_block_stop", {"type": "content_block_stop", "index": index})

    yield event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": int(usage.get("completion_tokens", 0))},
        },
    )
    yield event("message_stop", {"type": "message_stop"})


# ------------------------------------------------------------------------------------ the server


class Handler(BaseHTTPRequestHandler):
    model = "z-ai/glm-5.3-flash"
    key = ""
    verbose = False

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Quiet unless asked. The default handler writes a line per request to stderr."""

        if self.verbose:
            sys.stderr.write((format % args if args else format) + "\n")

    def _fail(self, status: int, message: str) -> None:
        body = json.dumps({"type": "error", "error": {"type": "api_error", "message": message}})
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _health(self) -> None:
        """Claude Code probes `/api/hello` before it starts. A 501 there is noise in the log."""

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b"{}")

    def do_HEAD(self) -> None:  # noqa: N802
        self._health()

    def do_GET(self) -> None:  # noqa: N802
        self._health()

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/v1/messages"):
            self._fail(404, f"no route for {self.path}")
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            self._fail(400, f"unparseable request: {exc}")
            return

        upstream = to_openai(payload, self.model)
        if self.verbose:
            sys.stderr.write(
                f"-> {len(upstream['messages'])} messages, {len(upstream.get('tools', []))} tools\n"
            )

        try:
            request = urllib.request.Request(  # noqa: S310
                UPSTREAM,
                data=json.dumps(upstream).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/fl-sean03/OpenSDL",
                    "X-Title": "OpenSDL bridge",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
                completion = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:600]
            self._fail(exc.code if 400 <= exc.code < 600 else 502, f"openrouter: {detail}")
            return
        except Exception as exc:  # noqa: BLE001
            self._fail(502, f"openrouter unreachable: {exc}")
            return

        choices = completion.get("choices") or []
        if not choices:
            self._fail(502, f"openrouter returned no choices: {json.dumps(completion)[:300]}")
            return

        choice = choices[0]
        blocks = to_anthropic_blocks(choice.get("message") or {})
        stop = STOP_REASONS.get(choice.get("finish_reason") or "stop", "end_turn")
        if any(b["type"] == "tool_use" for b in blocks):
            stop = "tool_use"
        usage = completion.get("usage") or {}

        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in sse_events(blocks, stop, usage, self.model):
                raw = chunk.encode("utf-8")
                self.wfile.write(f"{len(raw):X}\r\n".encode())
                self.wfile.write(raw)
                self.wfile.write(b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return

        body = json.dumps(
            {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": self.model,
                "content": blocks,
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": int(usage.get("prompt_tokens", 0)),
                    "output_tokens": int(usage.get("completion_tokens", 0)),
                },
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="z-ai/glm-5.3-flash")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        from pathlib import Path

        candidate = Path.home() / ".secrets" / "openrouter"
        if candidate.is_file():
            key = candidate.read_text(encoding="utf-8").strip()
    if not key:
        sys.stderr.write(
            "no OpenRouter key. Set OPENROUTER_API_KEY or write it to ~/.secrets/openrouter.\n"
        )
        return 2

    Handler.model = args.model
    Handler.key = key
    Handler.verbose = args.verbose

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write(
        f"bridging {args.model} on http://{args.host}:{args.port}\n"
        f"  ANTHROPIC_BASE_URL=http://{args.host}:{args.port} ANTHROPIC_API_KEY=unused claude ...\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
