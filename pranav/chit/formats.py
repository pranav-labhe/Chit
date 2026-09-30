"""Text formats shared by training data and inference prompts.

Keeping them in one place guarantees that knowledge taught as Q&A is rendered
exactly the way the Bridge later prompts the model (``User: ...\\nChit:``),
so what the model learns in training is what it is asked at inference.
"""
from __future__ import annotations

USER, ASSISTANT = "User:", "Chit:"


def render_qa(question: str, answer: str) -> str:
    return f"{USER} {question.strip()}\n{ASSISTANT} {answer.strip()}\n"


def render_reasoning(input: str, reasoning: str, answer: str) -> str:
    return f"Input: {input.strip()}\nReasoning: {reasoning.strip()}\nAnswer: {answer.strip()}\n"


def render_text(text: str) -> str:
    text = text.strip()
    return text + "\n"


def render_chat_prompt(user_input: str, memories: list[str], task: str = "chat",
                       history: list[dict] | None = None, max_bytes: int | None = None) -> str:
    """Build the chat prompt: task header, recalled memory, earlier turns, then the new message.

    ``history`` is a list of ``{"role": "user"|"assistant", "content": ...}``, oldest first.
    With ``max_bytes`` (the model's context size) the prompt is shortened until it fits:
    first the oldest turns are dropped, then the lowest-ranked memories. The new
    message is never dropped. Without history the result is identical to the
    original single-turn prompt.
    """
    mems = [m for m in memories if m]
    turns = [(t["role"], t["content"]) for t in (history or [])]

    def build() -> str:
        mem = "\n".join(f"- {m}" for m in mems) or "- (none)"
        past = "".join(f"{USER if r == 'user' else ASSISTANT} {c.strip()}\n" for r, c in turns)
        return f"Task: {task}\nKnown memory:\n{mem}\n{past}{USER} {user_input.strip()}\n{ASSISTANT}"

    prompt = build()
    if max_bytes is None:
        return prompt
    while len(prompt.encode("utf-8")) > max_bytes and turns:
        turns.pop(0)
        while turns and turns[0][0] != "user":  # never start on a reply with no question before it
            turns.pop(0)
        prompt = build()
    while len(prompt.encode("utf-8")) > max_bytes and mems:
        mems.pop()  # search returns the best match first, so drop from the end
        prompt = build()
    return prompt
