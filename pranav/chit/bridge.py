"""Boundary between Atmini and Chit: context in, decision out."""
from __future__ import annotations

from dataclasses import dataclass, field

from .formats import render_chat_prompt


@dataclass
class Context:
    user_input: str
    memories: list[dict] = field(default_factory=list)
    current_state: dict = field(default_factory=dict)
    task: str = "chat"
    session_turns: list[dict] = field(default_factory=list)


@dataclass
class ChitDecision:
    text: str
    action: str | None = None
    confidence: float | None = None
    memory_to_store: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class Bridge:
    STOP = ["\nUser:", "\nChit:", "\nTask:", "\n\n"]

    def __init__(
        self,
        runtime,
        max_memories: int = 5,
        max_new_tokens: int = 120,
        temperature: float = 0.7,
        max_turns: int = 16,
    ):
        self.runtime = runtime
        self.max_memories = max_memories
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.max_turns = max_turns

    def process(self, c: Context) -> ChitDecision:
        memories = (c.memories or self.runtime.recall(c.user_input, self.max_memories))[: self.max_memories]
        turns = (c.session_turns or [])[-self.max_turns:]
        prompt = render_chat_prompt(
            c.user_input,
            [m.get("content", "") for m in memories],
            task=c.task,
            turns=turns,
        )
        text = self.runtime.generate(prompt, self.max_new_tokens, self.temperature, stop=self.STOP).strip()
        return ChitDecision(
            text,
            metadata={
                "task": c.task,
                "memory_ids": [m.get("id") for m in memories],
                "session_turn_count": len(turns),
            },
        )

