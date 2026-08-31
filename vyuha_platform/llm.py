"""One way to ask Claude anything, for every feature that needs to.

Three features call a model — the business agent, the deck generator, and (in
Roshan's lane) the order parser. Three hand-rolled clients would mean three
different failure modes on a laptop in front of a prospect, so they all come
through ``ask()``.

What that buys, in order of how much it matters on demo day:

* **A disk cache.** Identical question, identical answer, no network. Pre-warm
  it with every scripted question and the live demo never waits on an API.
* **An offline mode.** ``VYUHA_LLM=offline`` refuses to call out at all, so a
  caller with a sensible fallback (the agent has one) still answers when the
  venue wifi does not.
* **Errors as values.** ``ask()`` never raises. A missing key, a rejected key,
  a rate limit and a refusal all come back as an ``Answer`` with ``ok=False``
  and something a human can act on, because every one of them will eventually
  happen while somebody is watching.

The cache is keyed on the whole request — model, system prompt, user prompt and
schema — so changing any of them is a different question and cannot silently
return the previous answer.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "vyuha_data" / "llm_cache"

#: Answers are small; decks are the largest thing we ask for.
MAX_TOKENS = 8000


@dataclass
class Answer:
    ok: bool
    text: str = ""
    #: Parsed object when a schema was supplied, else None.
    data: dict | None = None
    #: "live" | "cache" | "offline" | "error" — shown in the UI, because an
    #: answer replayed from cache and an answer just computed are not the same
    #: claim, and the operator should be able to tell which they are looking at.
    source: str = "live"
    error: str = ""
    needs_action: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def cached(self) -> bool:
        return self.source == "cache"


def offline() -> bool:
    """True when this machine must not make a network call."""
    return os.environ.get("VYUHA_LLM", "").strip().lower() in {"offline", "off", "0"}


# ----------------------------------------------------------------- the cache

def _key(model: str, system: str, prompt: str, schema: dict | None) -> str:
    blob = json.dumps([model, system, prompt, schema], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _cached(key: str) -> Answer | None:
    path = CACHE / f"{key}.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None                       # a corrupt entry is a cache miss
    return Answer(ok=True, text=raw.get("text", ""), data=raw.get("data"),
                  source="cache", notes=raw.get("notes", []))


def _store(key: str, answer: Answer) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        (CACHE / f"{key}.json").write_text(json.dumps({
            "text": answer.text, "data": answer.data, "notes": answer.notes,
        }, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass                              # a cache that cannot write is not an error


def warm(entries: int = 0) -> int:
    """How many answers are already on disk. Used by the console to say so."""
    if not CACHE.exists():
        return 0
    return len(list(CACHE.glob("*.json")))


def clear() -> int:
    """Drop every cached answer. Returns how many went."""
    if not CACHE.exists():
        return 0
    gone = 0
    for f in CACHE.glob("*.json"):
        try:
            f.unlink()
            gone += 1
        except OSError:
            pass
    return gone


# -------------------------------------------------------------------- asking

def ask(prompt: str, settings, system: str = "", schema: dict | None = None,
        model: str = "", use_cache: bool = True) -> Answer:
    """Ask Claude one question. Never raises.

    ``settings`` is a ``config.Settings`` — the key and model live there because
    they are deployment credentials, not per-account preferences.
    """
    model = model or getattr(settings, "vision_model", "") or "claude-opus-5"
    key = _key(model, system, prompt, schema)

    if use_cache:
        hit = _cached(key)
        if hit is not None:
            return hit

    if offline():
        return Answer(False, source="offline",
                      error="Vyuha is running offline, so it did not ask Claude.",
                      needs_action="Unset VYUHA_LLM to allow live answers.")

    if not getattr(settings, "anthropic_key", ""):
        return Answer(False, source="error",
                      error="No Claude API key is configured.",
                      needs_action="Add an Anthropic API key in Settings.")

    try:
        import anthropic
    except ImportError:
        return Answer(False, source="error",
                      error="The anthropic package is not installed.",
                      needs_action="pip install anthropic")

    client = anthropic.Anthropic(api_key=settings.anthropic_key)
    request: dict = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        request["system"] = system
    if schema is not None:
        request["output_config"] = {"format": {"type": "json_schema", "schema": schema}}

    try:
        response = client.messages.create(**request)
    except anthropic.AuthenticationError:
        return Answer(False, source="error", error="The Claude API key was rejected.",
                      needs_action="Check the key in Settings.")
    except anthropic.RateLimitError:
        return Answer(False, source="error", error="Claude is rate-limiting this key.",
                      needs_action="Wait a minute and ask again.")
    except anthropic.APIError as exc:
        return Answer(False, source="error", error=f"Claude could not answer: {exc}")
    except Exception as exc:                        # network down, DNS, proxy
        return Answer(False, source="error", error=f"Could not reach Claude: {exc}",
                      needs_action="Check the connection, or run with VYUHA_LLM=offline.")

    # A refusal is a 200 with no content — check before indexing into it.
    if getattr(response, "stop_reason", "") == "refusal":
        return Answer(False, source="error", error="Claude declined to answer that.")

    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    if not text.strip():
        return Answer(False, source="error", error="Claude returned an empty answer.")

    data = None
    if schema is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return Answer(False, source="error",
                          error="Claude's reply was not readable as structured data.")

    answer = Answer(True, text=text, data=data, source="live")
    if use_cache:
        _store(key, answer)
    return answer


# ------------------------------------------------------------- tool calling

@dataclass
class Call:
    """One tool the model asked for, and what it got back. Shown to the user."""
    name: str
    args: dict
    ok: bool = True
    summary: str = ""


@dataclass
class Conversation:
    ok: bool
    text: str = ""
    calls: list = field(default_factory=list)
    source: str = "live"
    error: str = ""
    needs_action: str = ""
    turns: int = 0


#: A hard ceiling on the loop. The model decides when it is finished; this only
#: exists so a confused model cannot bill for an unbounded conversation. Eight
#: is generous — real questions here resolve in two or three.
MAX_TURNS = 8


def run_tools(prompt: str, settings, tools: list, execute, system: str = "",
              model: str = "", max_turns: int = MAX_TURNS,
              effort: str = "high") -> Conversation:
    """Let Claude call real functions until it can answer. Never raises.

    ``tools`` is a list of Anthropic tool definitions; ``execute(name, args)``
    runs one and returns a JSON-serialisable result. Everything the model learns
    comes back through ``execute``, so the numbers in an answer are computed in
    Python and can be checked — the model chooses *which* questions to ask of the
    data, never what the data says.

    Not cached. A single-shot question with a fixed context is the same question
    every time and caches well; a tool conversation branches on what the first
    call returns, so a cache hit would replay an answer derived from data that
    has since changed. ``ask()`` remains the cached path.
    """
    if offline():
        return Conversation(False, source="offline",
                            error="Vyuha is running offline, so it did not ask Claude.",
                            needs_action="Unset VYUHA_LLM to allow live answers.")
    if not getattr(settings, "anthropic_key", ""):
        return Conversation(False, source="error",
                            error="No Claude API key is configured.",
                            needs_action="Add an Anthropic API key in Settings.")
    try:
        import anthropic
    except ImportError:
        return Conversation(False, source="error",
                            error="The anthropic package is not installed.",
                            needs_action="pip install anthropic")

    client = anthropic.Anthropic(api_key=settings.anthropic_key)
    model = model or getattr(settings, "vision_model", "") or "claude-opus-5"
    messages: list = [{"role": "user", "content": prompt}]
    calls: list[Call] = []

    for turn in range(max_turns):
        request: dict = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "messages": messages,
            "tools": tools,
            # Adaptive thinking, because choosing which figures to pull and how
            # to combine them is exactly the reasoning this is for. budget_tokens
            # is rejected on this model family; effort is the control that works.
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
        if system:
            request["system"] = system

        try:
            response = client.messages.create(**request)
        except anthropic.AuthenticationError:
            return Conversation(False, calls=calls, source="error",
                                error="The Claude API key was rejected.",
                                needs_action="Check the key in Settings.")
        except anthropic.RateLimitError:
            return Conversation(False, calls=calls, source="error",
                                error="Claude is rate-limiting this key.",
                                needs_action="Wait a minute and ask again.")
        except anthropic.APIError as exc:
            return Conversation(False, calls=calls, source="error",
                                error=f"Claude could not answer: {exc}")
        except Exception as exc:                       # network, DNS, proxy
            return Conversation(False, calls=calls, source="error",
                                error=f"Could not reach Claude: {exc}",
                                needs_action="Check the connection, or run with "
                                             "VYUHA_LLM=offline.")

        if getattr(response, "stop_reason", "") == "refusal":
            return Conversation(False, calls=calls, source="error",
                                error="Claude declined to answer that.")

        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content
                           if getattr(b, "type", "") == "text")
            return Conversation(bool(text.strip()), text=text.strip(), calls=calls,
                                source="live", turns=turn + 1,
                                error="" if text.strip() else "Claude returned nothing.")

        # Echo the assistant turn back verbatim -- thinking blocks included, which
        # this model requires when the conversation continues on the same model.
        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            try:
                value = execute(block.name, dict(block.input))
                payload, ok = json.dumps(value, default=str), True
            except Exception as exc:                   # a broken tool is data
                payload, ok = f"Error: {exc}", False
            calls.append(Call(name=block.name, args=dict(block.input), ok=ok,
                              summary=payload[:160]))
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": payload, **({"is_error": True} if not ok else {})})

        # Every result goes back in ONE user message. Splitting them teaches the
        # model to stop asking for several things at once.
        messages.append({"role": "user", "content": results})

    return Conversation(False, calls=calls, source="error", turns=max_turns,
                        error=f"Claude was still working after {max_turns} steps.",
                        needs_action="Try asking for one thing at a time.")
