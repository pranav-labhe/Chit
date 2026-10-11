"""Boundary between Atmini and Chit: context in, decision out."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .formats import render_chat_prompt
from .search import search_web


def _is_casual_or_conversational(text: str, facts: list[dict] | None = None) -> bool:
    """Latency protection: identify greetings, conversational turns, identity, or math."""
    clean = text.strip().lower()
    if not clean or len(clean) < 2:
        return True

    # 1. Math / arithmetic deductions
    if re.search(r'^\s*(what\s+is\s+)?\d+\s*[\+\-\*\/\^\%]\s*\d+', clean):
        return True
    if re.search(r'\b(calculate|compute|solve)\b\s+\d+', clean):
        return True

    # 2. Greetings, pleasantries, and short conversational replies
    greetings = {
        "hi", "hello", "hey", "howdy", "greetings", "yo", "sup",
        "how are you", "how are you doing", "how do you do", "how is it going", "how's it going",
        "what's up", "whats up",
        "good morning", "good afternoon", "good evening", "good night",
        "thank you", "thanks", "thanks a lot", "thank you very much",
        "bye", "goodbye", "see you", "see ya", "cya",
        "ok", "okay", "sure", "cool", "great", "nice", "awesome",
        "yes", "no", "yep", "nope",
    }
    stripped_punct = re.sub(r'[\.\!\?\,\'\"]+', '', clean).strip()
    if stripped_punct in greetings:
        return True

    # 3. Personal statements / introducing facts
    personal_statements = (
        "my name is", "i am ", "i'm ", "call me ", "i live in", "i work at",
        "my favorite", "my preferred", "i like ", "i love "
    )
    if any(clean.startswith(prefix) for prefix in personal_statements):
        return True

    # 4. Identity & session-specific questions
    identity_queries = {
        "who am i", "what is my name", "what's my name", "whats my name",
        "where do i live", "tell me about myself", "do you know me",
        "who are you", "what is your name", "what's your name", "whats your name",
        "what do you do", "what are you",
    }
    if stripped_punct in identity_queries:
        return True

    # If user has active facts in session and asks about themselves:
    if facts and any(w in clean.split() for w in ("i", "me", "my", "myself")):
        return True

    return False


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
    search: bool = False


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
        max_snippet_chars = min(120, max(60, int(context / 3))) if context else 100

        web_grounded = False
        sources = []
        web_search_query = None

        # Explicit web search request (e.g. user toggled "Web" in UI or passed search=True)
        if c.search and c.task != "continue":
            snippets = search_web(c.user_input, max_results=2, max_chars=max_snippet_chars)
            if snippets:
                memories.extend([{"content": f"[Web] {s}", "id": "web-search"} for s in snippets])
                web_grounded = True
                sources = snippets
                web_search_query = c.user_input
                t = 0.0
                effective_top_k = 1

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
                    "web_grounded": web_grounded,
                    "sources": sources,
                }
                if web_search_query:
                    metadata["web_search_query"] = web_search_query
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

        # Autonomous Two-Pass Self-RAG:
        # If Pass 1 is uncertain and local memories/facts are empty, trigger web search and regenerate grounded reply
        # Latency protection: casual turns, greetings, self-introductions, and math deductions are skipped
        if (needs_retrieval and not memories and not c.facts and c.task == "chat"
                and not is_thinking and not _is_casual_or_conversational(c.user_input, c.facts)):
            snippets = search_web(c.user_input, max_results=2, max_chars=max_snippet_chars)
            if snippets:
                grounded_mems = [f"[Web] {s}" for s in snippets]
                grounded_prompt = render_chat_prompt(
                    c.user_input, grounded_mems, task=c.task, history=c.history,
                    max_tokens=max_prompt_tokens, tokenizer=self.runtime.tokenizer,
                    facts=c.facts, summary=c.summary)
                g_text, g_conf, g_finish = self._generate_with_details(
                    grounded_prompt, n_tokens, 0.0, 1, stop=stop if stop is not None else self.STOP)
                g_final = g_text.strip()
                g_trimmed = g_final.rstrip(" \t")
                g_incomplete = (g_finish == "length") and bool(g_trimmed) and not g_trimmed.endswith(self.TERMINAL_PUNCTUATION)
                g_is_uncertain = g_conf < self.UNCERTAINTY_THRESHOLD
                g_needs_retrieval = g_is_uncertain or (c.task == "chat" and g_conf < 0.35)
                g_metadata = {
                    "task": c.task,
                    "memory_ids": [],
                    "confidence": round(g_conf, 3),
                    "is_incomplete": g_incomplete,
                    "is_uncertain": g_is_uncertain,
                    "needs_retrieval": g_needs_retrieval,
                    "web_grounded": True,
                    "web_search_query": c.user_input,
                    "sources": snippets,
                }
                return ChitDecision(g_final, confidence=round(g_conf, 3), metadata=g_metadata)

        metadata = {
            "task": c.task,
            "memory_ids": [m.get("id") for m in memories],
            "confidence": round(conf, 3),
            "is_incomplete": is_incomplete,
            "is_uncertain": is_uncertain,
            "needs_retrieval": needs_retrieval,
            "web_grounded": web_grounded,
            "sources": sources,
        }
        if web_search_query:
            metadata["web_search_query"] = web_search_query
        return ChitDecision(final_text, confidence=round(conf, 3), metadata=metadata)
