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
    history: list[dict] = field(default_factory=list)  # earlier turns of this session, oldest first
    facts: list[dict] = field(default_factory=list)  # explicit user statements; latest correction active
    summary: str = ""  # derived context, never a replacement for the retained transcript
    think: bool = False


@dataclass
class ChitDecision:
    text: str
    action: str | None = None
    confidence: float | None = None
    memory_to_store: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class Bridge:
    # Stop at actual conversation boundaries. A blank line is valid Markdown
    # (paragraphs, lists and fenced examples often use it), so it must not end
    # assistant output by itself.
    STOP = ["\nUser:", "\nChit:", "\nTask:"]
    REASONING_STOP = ["\nUser:", "\nTask:"]
    TERMINAL_PUNCTUATION = (".", "!", "?", '"', "'", "\n")
    UNCERTAINTY_THRESHOLD = 0.40

    def __init__(self, runtime, max_memories: int = 5, max_new_tokens: int = 256, temperature: float = 0.7):
        self.runtime = runtime
        self.max_memories = max_memories
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature

    def _generate_with_details(self, prompt: str, n_tokens: int, t: float, effective_top_k: int,
                              stop: list[str] | None) -> tuple[str, float, str]:
        try:
            res = self.runtime.generate(prompt, n_tokens, t, effective_top_k, stop=stop, return_details=True)
        except TypeError:
            res = self.runtime.generate(prompt, n_tokens, t, effective_top_k, stop=stop)

        if isinstance(res, tuple):
            return res[0], float(res[1]), str(res[2])
        return str(res), 1.0, "stop"

    def process(self, c: Context, temperature: float | None = None, *,
                max_new_tokens: int | None = None, top_k: int | None = None,
                stop: list[str] | None = None, think: bool | None = None) -> ChitDecision:
        t = self.temperature if temperature is None else temperature
        n_tokens = self.max_new_tokens if max_new_tokens is None else max_new_tokens
        is_byte_tokenizer = getattr(self.runtime.tokenizer, "vocab_size", 256) <= 256
        effective_top_k = top_k if top_k is not None else (1 if is_byte_tokenizer else 50)
        is_thinking = (c.think if think is None else think) or c.task == "reasoning"

        if c.task == "continue":  # plain-text model: the message is the start of a sentence, no chat wrapper
            text, conf, finish_reason = self._generate_with_details(
                c.user_input, n_tokens, t, effective_top_k,
                stop=stop if stop is not None else ["\n"])
            trimmed = text.rstrip(" \t")
            is_incomplete = (finish_reason == "length") and bool(trimmed) and not trimmed.endswith(self.TERMINAL_PUNCTUATION)
            is_uncertain = conf < self.UNCERTAINTY_THRESHOLD
            metadata = {
                "task": c.task,
                "memory_ids": [],
                "confidence": round(conf, 3),
                "is_incomplete": is_incomplete,
                "is_uncertain": is_uncertain,
                "needs_retrieval": is_uncertain,
            }
            return ChitDecision(text, confidence=round(conf, 3), metadata=metadata)

        memories = (c.memories or self.runtime.recall(c.user_input, self.max_memories, min_relevance=0.35))[: self.max_memories]
        if memories or c.facts:
            t = 0.0
            effective_top_k = 1
        context = (getattr(self.runtime, "model_config", None) or {}).get("block_size")
        max_prompt_tokens = (context - 16) if (context and is_thinking and context > 32) else context
        prompt = render_chat_prompt(c.user_input, [m.get("content", "") for m in memories], task=c.task,
                                    history=c.history, max_tokens=max_prompt_tokens, tokenizer=self.runtime.tokenizer,
                                    facts=c.facts, summary=c.summary)

        if is_thinking:
            # Native reasoning scaffold that activates the Answer: boundary
            reasoning_prompt = f"Input: {c.user_input.strip()}\nReasoning:"
            stop_seqs = stop if stop is not None else ["\nInput:", "\nUser:", "\nTask:"]
            raw, conf, finish_reason = self._generate_with_details(
                reasoning_prompt, n_tokens, t, effective_top_k, stop=stop_seqs)
            raw = raw.strip()
            if "Answer:" in raw:
                parts = raw.split("Answer:", 1)
                thoughts = parts[0].strip()
                answer = parts[1].strip()

                trimmed_ans = answer.rstrip(" \t")
                is_incomplete = (finish_reason == "length") and bool(trimmed_ans) and not trimmed_ans.endswith(self.TERMINAL_PUNCTUATION)
                is_uncertain = conf < self.UNCERTAINTY_THRESHOLD
                needs_retrieval = is_uncertain or (c.task == "chat" and conf < 0.35)

                metadata = {
                    "task": c.task,
                    "memory_ids": [m.get("id") for m in memories],
                    "thoughts": thoughts,
                    "confidence": round(conf, 3),
                    "is_incomplete": is_incomplete,
                    "is_uncertain": is_uncertain,
                    "needs_retrieval": needs_retrieval,
                }
                if thoughts and hasattr(self.runtime, "tokenizer"):
                    try:
                        metadata["thought_tokens"] = len(self.runtime.tokenizer.encode(thoughts))
                    except Exception:
                        metadata["thought_tokens"] = len(thoughts)
                return ChitDecision(text=answer, confidence=round(conf, 3), metadata=metadata)

            # If no Answer: boundary was produced (e.g. greetings or non-logic chat),
            # fall through to standard chat generation so no duplicate/irrelevant thought box is shown.

        text, conf, finish_reason = self._generate_with_details(
            prompt, n_tokens, t, effective_top_k,
            stop=stop if stop is not None else self.STOP)
        final_text = text.strip()
        trimmed_text = final_text.rstrip(" \t")
        is_incomplete = (finish_reason == "length") and bool(trimmed_text) and not trimmed_text.endswith(self.TERMINAL_PUNCTUATION)
        is_uncertain = conf < self.UNCERTAINTY_THRESHOLD
        needs_retrieval = is_uncertain or (c.task == "chat" and conf < 0.35)
        metadata = {
            "task": c.task,
            "memory_ids": [m.get("id") for m in memories],
            "confidence": round(conf, 3),
            "is_incomplete": is_incomplete,
            "is_uncertain": is_uncertain,
            "needs_retrieval": needs_retrieval,
        }
        return ChitDecision(final_text, confidence=round(conf, 3), metadata=metadata)
