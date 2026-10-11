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
                       history: list[dict] | None = None, max_bytes: int | None = None,
                       max_tokens: int | None = None, tokenizer=None,
                       facts: list[dict] | None = None, summary: str = "") -> str:
    """Build the chat prompt: task header, recalled memory, earlier turns, then the new message.

    ``history`` is a list of ``{"role": "user"|"assistant", "content": ...}``, oldest first.
    With ``max_bytes`` or ``max_tokens`` (the model's context size) the prompt is shortened until it fits:
    first the oldest turns are dropped, then the lowest-ranked memories, then the
    end of an overlong current message is truncated. Without history or a size
    limit the result is identical to the original single-turn prompt.
    """
    mems = [m for m in memories if m]
    turns = [(t["role"], t["content"]) for t in (history or [])]
    session_facts = [f for f in (facts or []) if f.get("key") and f.get("value")]
    summary = summary.strip()

    is_tiny = (max_tokens is not None and max_tokens < 64) or (max_bytes is not None and max_bytes < 64)
    use_grounded_contract = (bool(mems) or bool(session_facts)) and not is_tiny

    def build() -> str:
        mem_block = ("Known memory:\n" + "\n".join(f"- {m}" for m in mems) + "\n") if mems else ""
        fact_block = ("User-stated facts (latest correction wins):\n" +
                      "\n".join(f"- {f['key']}: {f['value']}" for f in session_facts) + "\n") \
            if session_facts else ""
        summary_block = f"Earlier conversation summary (derived context):\n{summary}\n" if summary else ""
        past = "".join(f"{USER if r == 'user' else ASSISTANT} {c.strip()}\n" for r, c in turns)
        return f"Task: {task}\n{mem_block}{fact_block}{summary_block}{past}{USER} {user_input.strip()}\n{ASSISTANT}"

    user_input = user_input.strip()
    prompt = build()
    if max_tokens is not None:
        if tokenizer is None:
            raise ValueError("tokenizer is required when max_tokens is set")
        count = lambda value: len(tokenizer.encode(value))
        while count(prompt) > max_tokens and turns:
            turns.pop(0)
            while turns and turns[0][0] != "user":
                turns.pop(0)
            prompt = build()
        if count(prompt) > max_tokens and summary:
            summary = ""
            prompt = build()
        if count(prompt) > max_tokens and use_grounded_contract:
            use_grounded_contract = False
            prompt = build()
        while count(prompt) > max_tokens and mems:
            mems.pop()
            prompt = build()
        while count(prompt) > max_tokens and session_facts:
            session_facts.pop(0)
            prompt = build()
        if count(prompt) > max_tokens:
            original = tokenizer.encode(user_input)
            user_input = ""
            budget = max_tokens - count(build())
            if budget >= 0:
                sliced_ids = original[:budget]
                if getattr(tokenizer, "name", "") == "byte-utf8":
                    user_input = bytes(sliced_ids).decode("utf-8", errors="ignore")
                else:
                    user_input = tokenizer.decode(sliced_ids)
                if user_input.count("```") % 2 == 1:
                    closed = user_input + "\n```"
                    temp = user_input
                    user_input = closed
                    if count(build()) <= max_tokens:
                        user_input = closed
                    else:
                        user_input = temp
                prompt = build()
        return prompt
    if max_bytes is None:
        return prompt
    while len(prompt.encode("utf-8")) > max_bytes and turns:
        turns.pop(0)
        while turns and turns[0][0] != "user":  # never start on a reply with no question before it
            turns.pop(0)
        prompt = build()
    if len(prompt.encode("utf-8")) > max_bytes and summary:
        summary = ""
        prompt = build()
    if len(prompt.encode("utf-8")) > max_bytes and use_grounded_contract:
        use_grounded_contract = False
        prompt = build()
    while len(prompt.encode("utf-8")) > max_bytes and mems:
        mems.pop()  # search returns the best match first, so drop from the end
        prompt = build()
    while len(prompt.encode("utf-8")) > max_bytes and session_facts:
        session_facts.pop(0)  # facts are oldest-first, so preserve the latest corrections
        prompt = build()
    # A long new request can itself exceed the context window. Preserve its
    # beginning (where instructions usually appear) and truncate only after
    # dropping older turns and memories. Keep the old behavior for tiny test or
    # legacy models whose entire prompt scaffold cannot fit.
    if len(prompt.encode("utf-8")) > max_bytes:
        original = user_input
        user_input = ""
        scaffold = build()
        budget = max_bytes - len(scaffold.encode("utf-8"))
        if budget >= 0:
            user_input = original.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
            if user_input.count("```") % 2 == 1:
                closed = user_input + "\n```"
                if len(scaffold.encode("utf-8")) + len(closed.encode("utf-8")) <= max_bytes:
                    user_input = closed
            prompt = build()
    return prompt
