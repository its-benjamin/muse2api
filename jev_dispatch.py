"""Jev-powered tool-call dispatcher for muse2api.

The muse.ai assistant explicitly refuses to emit pseudo-tool-call JSON, so prompt
injection does not work. This module intercepts requests *before* they reach muse.ai:
Jev reads the conversation and the tool definitions, selects the right tool (or none),
fills its arguments, and returns a ready-to-ship ``tool_calls`` list — muse.ai is
never asked to do any of it.

Flow:
1. ``jev_tool_dispatch(messages, tools)`` is called when a request carries tools.
2. Jev gets one Choice question ("which tool, if any?") plus one Noul per string/enum
   parameter of every tool ("does the message supply a value for this parameter?") and
   one Choice per enum parameter ("which value?").  All questions are sent in a single
   request (speculative fan-out).
3. If Jev picks ``__none__`` or confidence < ``CONFIDENCE_THRESHOLD``, return ``None``
   so the caller falls through to the normal muse path.
4. Otherwise assemble the ``tool_calls`` list and return it.

The caller may supply ``MUSE2API_JEV_KEY`` as an environment variable.  The hard-coded
key is used as a fallback so it works out of the box.
"""
from __future__ import annotations

import json
import logging
import os
import uuid

log = logging.getLogger("muse2api")

# Confidence below this threshold → treat as "no tool call needed".
CONFIDENCE_THRESHOLD = 0.50

# Fallback key (set via env to override).
_DEFAULT_KEY = "apikey_21376f58ba8d69451e8c86722cc1be667c_64c8e08ff3b7d7fb998afe67c6e3662e8410a0c87fc23aee7459669999d33a04"


def _jev_api_key() -> str:
    return os.environ.get("MUSE2API_JEV_KEY", _DEFAULT_KEY)


def _sdk_available() -> bool:
    try:
        import typesafe_sdk  # noqa: F401
        return True
    except ImportError:
        return False


def _conversation_state(messages: list) -> str:
    """Render the last few turns as a plain-text state string for Jev."""
    parts = []
    # Keep last 6 messages to stay within reasonable token budget.
    for m in messages[-6:]:
        if not isinstance(m, dict):
            try:
                m = m.model_dump()
            except Exception:
                continue
        role = (m.get("role") or "user").strip()
        content = m.get("content") or ""
        if isinstance(content, list):
            # Handle multi-part content (text blocks).
            content = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        parts.append(f"{role.upper()}: {str(content).strip()}")
    return "\n".join(parts)


def _extract_fn(tool: dict) -> dict | None:
    """Return the function spec regardless of OpenAI tool shape."""
    if not isinstance(tool, dict):
        return None
    fn = tool.get("function")
    if isinstance(fn, dict) and fn.get("name"):
        return fn
    # Responses API shape: {type, name, parameters, ...}
    if tool.get("name"):
        return tool
    return None


def _enum_values(param_schema: dict) -> list[str] | None:
    """Return enum values if schema has them, else None."""
    enum = param_schema.get("enum")
    if isinstance(enum, list) and all(isinstance(v, str) for v in enum):
        return enum
    return None


def jev_tool_dispatch(messages: list, tools: list) -> list[dict] | None:
    """Try to resolve a tool call using Jev.  Returns OpenAI-format tool_calls or None.

    Returns None when:
    - typesafe_sdk is not installed
    - Jev picks __none__ (no tool needed)
    - Jev confidence is below CONFIDENCE_THRESHOLD
    - Any exception occurs (fail-safe: fall through to muse)
    """
    if not tools or not messages:
        return None
    if not _sdk_available():
        log.debug("typesafe_sdk not installed; skipping Jev tool dispatch")
        return None

    try:
        return _dispatch(messages, tools)
    except Exception as exc:
        log.warning("Jev dispatch error (falling through to muse): %s", exc)
        return None


def _dispatch(messages: list, tools: list) -> list[dict] | None:
    from typesafe_sdk import Choice, Noul, TypeSafeClient

    # Build tool name → fn spec map.
    fns: dict[str, dict] = {}
    for t in tools:
        fn = _extract_fn(t)
        if fn and fn.get("name"):
            fns[fn["name"]] = fn

    if not fns:
        return None

    state = _conversation_state(messages)

    # ── Question 1: which tool? ──────────────────────────────────────────────
    tool_options: dict[str, str] = {"__none__": "No tool is needed; answer in plain text"}
    for name, fn in fns.items():
        desc = (fn.get("description") or name).strip()
        tool_options[name] = desc

    questions: dict = {
        "__tool__": Choice(
            instructions=(
                "Based on the conversation, which tool should be called next, if any? "
                "Pick __none__ if the assistant can answer directly without calling a tool."
            ),
            criteria=tool_options,
        )
    }

    # ── Questions 2+: parameter values (speculative fan-out) ─────────────────
    # For each tool, for each string/enum parameter: ask a Noul (is it present?)
    # and a Choice (which value?) for enum params.
    param_questions: dict[str, tuple[str, str, list[str] | None]] = {}
    # key → (tool_name, param_name, enum_values_or_None)

    for t_name, fn in fns.items():
        params = fn.get("parameters") or {}
        props = params.get("properties") or {}
        required = set(params.get("required") or [])
        for p_name, p_schema in props.items():
            if not isinstance(p_schema, dict):
                continue
            p_type = p_schema.get("type", "string")
            if p_type not in ("string", "number", "integer", "boolean"):
                continue
            p_desc = p_schema.get("description") or p_name
            enum_vals = _enum_values(p_schema) if p_type == "string" else None
            noul_key = f"{t_name}.{p_name}.present"
            questions[noul_key] = Noul(
                instructions=(
                    f"Does the conversation clearly supply a value for the "
                    f"'{p_name}' parameter of {t_name}? "
                    f"Parameter description: {p_desc}."
                    + (" (required)" if p_name in required else " (optional)")
                )
            )
            param_questions[noul_key] = (t_name, p_name, enum_vals)
            if enum_vals:
                choice_key = f"{t_name}.{p_name}.value"
                questions[choice_key] = Choice(
                    instructions=(
                        f"What value does the conversation give for the '{p_name}' "
                        f"parameter of {t_name}? ({p_desc})"
                    ),
                    criteria={v: v for v in enum_vals},
                )
                param_questions[choice_key] = (t_name, p_name, enum_vals)

    # ── Single Jev call ──────────────────────────────────────────────────────
    with TypeSafeClient(api_key=_jev_api_key()) as client:
        result = client.system_one(state, questions)

    tool_answer = result.choices["__tool__"]
    chosen_tool = tool_answer.choice
    confidence = tool_answer.confidence

    log.debug("Jev tool choice: %s (confidence=%.2f)", chosen_tool, confidence)

    if chosen_tool == "__none__" or confidence < CONFIDENCE_THRESHOLD:
        return None

    fn = fns.get(chosen_tool)
    if not fn:
        return None

    # ── Assemble arguments ────────────────────────────────────────────────────
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    arguments: dict = {}

    for p_name, p_schema in props.items():
        if not isinstance(p_schema, dict):
            continue
        p_type = p_schema.get("type", "string")
        enum_vals = _enum_values(p_schema) if p_type == "string" else None

        noul_key = f"{chosen_tool}.{p_name}.present"
        if noul_key not in result.nouls:
            continue
        present_prob = result.nouls[noul_key].noul
        if present_prob < 0.5:
            continue  # Jev says value not present in conversation

        if enum_vals:
            choice_key = f"{chosen_tool}.{p_name}.value"
            if choice_key in result.choices:
                arguments[p_name] = result.choices[choice_key].choice
        else:
            # Free-form: Jev confirmed the value is present but can't extract it directly.
            # Leave as None so caller knows the arg slot is intended (agent will fill it).
            arguments[p_name] = None

    # Filter out None values unless they were required (keep required as empty string).
    required = set(params.get("required") or [])
    clean_args: dict = {}
    for k, v in arguments.items():
        if v is not None:
            clean_args[k] = v
        elif k in required:
            clean_args[k] = ""

    call_id = "call_jev_" + uuid.uuid4().hex[:16]
    return [{
        "id": call_id,
        "type": "function",
        "function": {
            "name": chosen_tool,
            "arguments": json.dumps(clean_args, ensure_ascii=False),
        },
    }]
