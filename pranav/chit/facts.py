"""Conservative extraction of explicit, user-stated session facts.

This module deliberately uses narrow patterns rather than asking a small model to
invent a summary. Only direct user messages are passed here; quoted/code text is
removed, and every extracted value retains its source turn sequence.
"""
from __future__ import annotations

import re

_PATTERNS = (
    ("name", re.compile(r"\bmy name is\s+([^.!?,;\n]{1,100})", re.I)),
    ("name", re.compile(r"\bcall me\s+([^.!?,;\n]{1,100})", re.I)),
    ("name", re.compile(r"\b[iI] am\s+([A-Z][a-z]{1,30})\b")),
    ("location", re.compile(r"\bi live in\s+([^.!?,;\n]{1,100})", re.I)),
    ("location", re.compile(r"\bi am (?:based|located) in\s+([^.!?,;\n]{1,100})", re.I)),
    ("email", re.compile(r"\b(?:my email is|reach me at)\s+([^\s,;]+@[^\s,;]+)", re.I)),
    ("project", re.compile(r"\b(?:i am working on|my project is)\s+([^.!?;\n]{1,100})", re.I)),
    ("preference", re.compile(r"\bi (?:prefer|like|dislike|don't like|do not like)\s+([^.!?;\n]{1,140})", re.I)),
    ("goal", re.compile(r"\bmy goal is\s+([^.!?;\n]{1,140})", re.I)),
    ("budget", re.compile(r"\b(?:my budget is|i can spend up to)\s+([^.!?;\n]{1,100})", re.I)),
    ("deadline", re.compile(r"\b(?:the )?deadline is\s+([^.!?;\n]{1,100})", re.I)),
    ("deadline", re.compile(r"\bi need (?:it|this|that) by\s+([^.!?;\n]{1,100})", re.I)),
    ("appointment", re.compile(r"\bmy appointment is\s+([^.!?;\n]{1,100})", re.I)),
)

_REJECTED_NAMES = frozenset({
    "sorry", "ready", "fine", "here", "done", "sure", "busy", "tired", "back",
    "happy", "sad", "good", "bad", "okay", "ok", "not", "just", "also"
})


def _remove_untrusted_spans(text: str) -> str:
    text = re.sub(r"```.*?```|`[^`]*`", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*>.*$", " ", text)
    text = re.sub(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'", " ", text)
    return text


def extract_explicit_facts(user_text: str) -> list[dict[str, str]]:
    """Return only narrow, explicit fact forms; unsupported text yields no facts."""
    safe_text = _remove_untrusted_spans(user_text)
    facts: dict[str, str] = {}
    for key, pattern in _PATTERNS:
        match = pattern.search(safe_text)
        if not match:
            continue
        value = " ".join(match.group(1).strip().split()).strip(" .,:;!?-—")
        if not value or len(value) > 140:
            continue
        if key == "name" and value.lower() in _REJECTED_NAMES:
            continue
        if key not in facts:
            facts[key] = value
    return [{"key": key, "value": value} for key, value in facts.items()]
