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


def render_chat_prompt(user_input: str, memories: list[str], task: str = "chat") -> str:
    mem = "\n".join(f"- {m}" for m in memories if m) or "- (none)"
    return f"Task: {task}\nKnown memory:\n{mem}\n{USER} {user_input.strip()}\n{ASSISTANT}"
