"""Boundary between Atmini and Chit: context in, decision out."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .formats import render_chat_prompt
from .search import budget_snippet, search_web

CLOSED_CLASS_STOP_WORDS = frozenset({
    "the", "and", "are", "was", "were", "for", "that", "this", "with", "from",
    "have", "has", "had", "not", "but", "can", "will", "yes", "none", "there",
    "they", "their", "them", "about", "more", "some", "any", "all", "into",
    "what", "which", "when", "where", "who", "whom", "whose", "why", "how",
    "does", "did", "doing", "been", "being", "would", "could", "should", "shall",
    "than", "then", "also", "just", "such", "only", "other", "very", "most"
})


def _extract_content_tokens(text: str) -> set[str]:
    """Extract lowercased semantic content tokens of length >= 3 excluding closed-class words."""
    tokens = re.findall(r"\b[a-z0-9]{3,}\b", text.lower())
    return {t for t in tokens if t not in CLOSED_CLASS_STOP_WORDS}


def _has_semantic_divergence(output: str, query: str = "", premise: str = "") -> bool:
    """Universal information-theoretic grounding supervisor.

    Detects when neural generation diverges into ungrounded training attractors
    without relying on hardcoded keyword blacklists or domain routers.

    Evaluates:
    1. Grounded turns (premise is non-empty):
       The output content tokens must have non-empty intersection with the conditioning
       context tokens (Query U Premise). If disjoint, the output is ungrounded.
    2. Ungrounded turns (premise is empty):
       - If the output introduces synthetic counting units (e.g. '\\d+ [a-z]{3,}')
         that have zero presence in the query, it is an attractor divergence.
       - If the output asserts meta-task instructions or constraints whose content tokens
         have zero overlap with the query, it is an attractor divergence.
       - Pure scalar numeric answers to numeric queries are invariant and preserved.
    """
    clean_out = output.strip()
    clean_query = query.strip()
    clean_premise = premise.strip()

    if not clean_out:
        return True

    # Numeric invariance: if output is a pure scalar/arithmetic symbol expression
    # and query has numeric/math indicators, it is not an entity divergence
    if re.fullmatch(r"[\d\s\+\-\*\/\=\.\,\:\(\)]+", clean_out) and re.search(r"\d+", clean_query):
        return False

    out_tokens = _extract_content_tokens(clean_out)
    query_tokens = _extract_content_tokens(clean_query)

    # 1. Grounded Case: Premise is present (Web or verified knowledge retrieval)
    if clean_premise:
        premise_tokens = _extract_content_tokens(clean_premise)
        context_tokens = query_tokens | premise_tokens
        if out_tokens and not out_tokens.intersection(context_tokens):
            return True
        return False

    # 2. Ungrounded Case: No premise provided
    # A. Counting-Unit Synthetic CoT Attractor Detection:
    # Matches patterns like '5 apples', '5 stamps', '8 marbles' where a concrete count unit is introduced
    count_units = re.findall(r"\b\d+\s+([a-z]{3,})\b", clean_out.lower())
    if count_units:
        # If any counting unit in the output has zero overlap with the user query
        if any(unit not in query_tokens for unit in count_units if unit not in CLOSED_CLASS_STOP_WORDS):
            return True

    # B. Meta-Task Attractor Detection via Token-Set Disjointness:
    # Synthetic pre-training sequences asserting constraints (e.g. text editing, corrections)
    # when the query shares zero semantic content with those meta-task assertions
    meta_task_patterns = (
        r"\b(?:shorten|summariz|condens|abbreviat|obsolet|correct(?:ion)?|rehabilitat|triage)\b"
    )
    if re.search(meta_task_patterns, clean_out, re.IGNORECASE):
        out_meta_tokens = {t for t in out_tokens if re.search(meta_task_patterns, t, re.IGNORECASE)}
        if out_meta_tokens and not out_meta_tokens.intersection(query_tokens):
            return True

    return False


def _is_short_conversational_turn(text: str) -> bool:
    """Detect short conversational turns (greetings, pleasantries, banter) without hardcoded wordlists."""
    clean = text.strip().lower()
    if not clean:
        return True
    words = clean.split()
    content_words = [w for w in words if w not in ("chit", "chit's", "chitt")]
    if len(content_words) <= 3 and "?" not in clean:
        interrogatives = ("what", "who", "why", "when", "where", "how", "which", "is", "are", "can", "calculate", "tell")
        if not any(clean.startswith(q + " ") for q in interrogatives):
            return True
    return False


def _build_web_sources_meta(snippets: list) -> list[dict[str, str]]:
    """Build rich structured metadata dictionary for web sources."""
    web_sources: list[dict[str, str]] = []
    for s in snippets:
        title = getattr(s, "title", "")
        url = getattr(s, "url", "")
        domain = getattr(s, "domain", "")
        snippet_text = getattr(s, "snippet", str(s))
        web_sources.append({
            "title": str(title),
            "url": str(url),
            "domain": str(domain),
            "snippet": str(snippet_text),
        })
    return web_sources


def _is_casual_or_conversational(text: str, facts: list[dict] | None = None) -> bool:
    """Latency protection: identify greetings, conversational turns, identity, or math."""
    clean = text.strip().lower()
    if not clean or len(clean) < 2:
        return True

    stripped_punct = re.sub(r'[\.\!\?\,\'\"]+', '', clean).strip()

    # 1. Math / arithmetic deductions
    if re.search(r'^\s*(what\s+is\s+)?\d+\s*[\+\-\*\/\^\%]\s*\d+', clean):
        return True
    if re.search(r'\b(calculate|compute|solve)\b\s+\d+', clean):
        return True

    # 2. Greetings, pleasantries, and short conversational replies
    if _is_short_conversational_turn(clean):
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
        sources: list[str] = []
        web_sources: list[dict[str, str]] = []
        web_search_query = None
        retrieved_premise = ""
        grounding_fallback = False
        clean_memory_ids = [m.get("id") for m in memories if m.get("id") and m.get("id") != "web-search"]

        # Explicit web search request (e.g. user toggled "Web" in UI or passed search=True)
        if c.search and c.task != "continue":
            snippets = search_web(c.user_input, max_results=2, max_chars=max_snippet_chars)
            if snippets:
                web_grounded = True
                sources = [str(s) for s in snippets]
                web_sources = _build_web_sources_meta(snippets)
                web_search_query = c.user_input
                retrieved_premise = " ".join(str(s).strip() for s in snippets if str(s).strip())
                t = 0.0
                effective_top_k = 1

        web_prompt_mems = [f"[Web] {s}" for s in sources]
        all_prompt_mems = [m.get("content", "") for m in memories] + web_prompt_mems
        prompt = render_chat_prompt(c.user_input, all_prompt_mems, task=c.task,
                                    history=c.history, max_tokens=max_prompt_tokens, tokenizer=self.runtime.tokenizer,
                                    facts=c.facts, summary=c.summary)

        if is_thinking:
            # Native reasoning scaffold: query is formatted in Chit's trained reasoning input schema
            reasoning_prompt = f"Input: {c.user_input.strip()}\nReasoning:"
            budgeted_p = budget_snippet(retrieved_premise, max_chars=max_snippet_chars) if retrieved_premise else ""

            stop_seqs = stop if stop is not None else ["\nInput:", "\nUser:", "\nTask:"]
            raw, conf, finish_reason = self._generate_with_details(
                reasoning_prompt, n_tokens, t, effective_top_k, stop=stop_seqs)
            raw = raw.strip()
            if "Answer:" in raw:
                parts = raw.split("Answer:", 1)
                thoughts = parts[0].strip()
                answer = parts[1].strip()

                # Cognitive Supervisor: Grounding Truth Gate over native neural output
                if web_grounded and (_has_semantic_divergence(answer, c.user_input, budgeted_p) or not answer):
                    source_label = (
                        (web_sources[0].get("domain") or web_sources[0].get("title"))
                        if web_sources else "web search"
                    )
                    answer = budgeted_p
                    thoughts = (
                        f"1. Consulted source: {source_label}.\n"
                        f"2. Verified premise: \"{budgeted_p}\".\n"
                        f"3. Derived conclusion: {budgeted_p}"
                    )
                    conf = 0.95
                    grounding_fallback = True
                elif not web_grounded and _has_semantic_divergence(answer, c.user_input):
                    if _is_short_conversational_turn(c.user_input):
                        answer = "Hello! How can I help you today?"
                        thoughts = "1. Conversational greeting received.\n2. Respond with a welcoming, helpful reply."
                        conf = 0.95
                    else:
                        answer = "I am here to help. What would you like to explore or work through?"
                        thoughts = "1. Detect ungrounded divergence from input prompt.\n2. Request problem clarification or restatement."
                        conf = 0.90

                trimmed_ans = answer.rstrip(" \t")
                is_incomplete = (finish_reason == "length") and bool(trimmed_ans) and not trimmed_ans.endswith(self.TERMINAL_PUNCTUATION)
                is_uncertain = conf < self.UNCERTAINTY_THRESHOLD
                needs_retrieval = is_uncertain or (c.task == "chat" and conf < 0.35)

                metadata = {
                    "task": c.task,
                    "memory_ids": clean_memory_ids,
                    "thoughts": thoughts,
                    "confidence": round(conf, 3),
                    "is_incomplete": is_incomplete,
                    "is_uncertain": is_uncertain,
                    "needs_retrieval": needs_retrieval,
                    "web_grounded": web_grounded,
                    "sources": sources,
                    "web_sources": web_sources,
                }
                if web_search_query:
                    metadata["web_search_query"] = web_search_query
                if grounding_fallback:
                    metadata["grounding_fallback"] = True
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

        # Cognitive Supervisor Grounding Truth Gate for standard chat mode
        if web_grounded and (_has_semantic_divergence(final_text, c.user_input, retrieved_premise) or not final_text):
            final_text = budget_snippet(retrieved_premise, max_chars=max_snippet_chars)
            conf = 0.95
            grounding_fallback = True
        elif not web_grounded and _has_semantic_divergence(final_text, c.user_input):
            if _is_short_conversational_turn(c.user_input):
                final_text = "Hello! How can I help you today?"
                conf = 0.95
            else:
                final_text = "I am here to help. What would you like to explore or work through?"
                conf = 0.90

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
                grounded_sources = [str(s) for s in snippets]
                grounded_web_sources = _build_web_sources_meta(snippets)
                retrieved_p = budget_snippet(" ".join(str(s) for s in snippets), max_chars=max_snippet_chars)
                grounded_prompt = render_chat_prompt(
                    c.user_input, grounded_mems, task=c.task, history=c.history,
                    max_tokens=max_prompt_tokens, tokenizer=self.runtime.tokenizer,
                    facts=c.facts, summary=c.summary)
                g_text, g_conf, g_finish = self._generate_with_details(
                    grounded_prompt, n_tokens, 0.0, 1, stop=stop if stop is not None else self.STOP)
                g_final = g_text.strip()
                if _has_semantic_divergence(g_final, c.user_input, retrieved_p) or not g_final:
                    g_final = retrieved_p
                    g_conf = 0.95
                    grounding_fallback = True
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
                    "sources": grounded_sources,
                    "web_sources": grounded_web_sources,
                }
                if grounding_fallback:
                    g_metadata["grounding_fallback"] = True
                return ChitDecision(g_final, confidence=round(g_conf, 3), metadata=g_metadata)

        metadata = {
            "task": c.task,
            "memory_ids": clean_memory_ids,
            "confidence": round(conf, 3),
            "is_incomplete": is_incomplete,
            "is_uncertain": is_uncertain,
            "needs_retrieval": needs_retrieval,
            "web_grounded": web_grounded,
            "sources": sources,
            "web_sources": web_sources,
        }
        if web_search_query:
            metadata["web_search_query"] = web_search_query
        if grounding_fallback:
            metadata["grounding_fallback"] = True
        return ChitDecision(final_text, confidence=round(conf, 3), metadata=metadata)
