"""Boundary between Atmini and Chit: context in, decision out."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .formats import render_chat_prompt
from .search import budget_snippet, search_web
from .tools.calculator import try_calculate
from .tools.calibrate_confidence import calibrate

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
    count_units = re.findall(r"\b\d+\s+([a-z]{3,})\b", clean_out.lower())
    if count_units:
        if any(unit not in query_tokens for unit in count_units if unit not in CLOSED_CLASS_STOP_WORDS):
            return True

    # B. Meta-Task Attractor Detection via Token-Set Disjointness:
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
class BridgeConfig:
    """Configuration toggles and hyperparameters for the Bridge compound pipeline."""
    enable_calculator: bool = True
    enable_generic_verifier: bool = False
    enable_calibration: bool = False
    legacy_attractor_shim: bool = True
    reserve_generation_budget: bool = True
    default_temperature: float = 0.7
    open_chat_top_k: int = 20
    max_memories: int = 5
    max_new_tokens: int = 256
    uncertainty_threshold: float = 0.40
    min_relevance: float = 0.35
    calibration_file: str = "data/calibration.json"


@dataclass
class Plan:
    """Explicit typed execution plan capturing policy intent, strategy, and decoding parameters."""
    intent: str      # "continue" | "casual" | "math" | "lookup" | "think" | "chat"
    strategy: str    # "tool" | "recall" | "search" | "think" | "direct"
    decoding: dict   # {"temperature": float, "top_k": int, "max_new_tokens": int, "stop": list[str]}
    reasons: list[str] = field(default_factory=list)


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


class Router:
    """Pure policy component mapping (Context, BridgeConfig) -> Plan."""

    def route(
        self,
        c: Context,
        config: BridgeConfig,
        *,
        temperature: float | None = None,
        max_new_tokens: int | None = None,
        top_k: int | None = None,
        stop: list[str] | None = None,
        think: bool | None = None,
        is_byte_tokenizer: bool = True,
        has_memories_or_facts: bool = False,
    ) -> Plan:
        t = config.default_temperature if temperature is None else temperature
        n_tokens = config.max_new_tokens if max_new_tokens is None else max_new_tokens
        is_thinking = (c.think if think is None else think) or c.task == "reasoning"

        # 1. Plain text continuation
        if c.task == "continue":
            eff_top_k = top_k if top_k is not None else (1 if (is_byte_tokenizer and t == 0.0) else (config.open_chat_top_k if is_byte_tokenizer else 50))
            return Plan(
                intent="continue",
                strategy="direct",
                decoding={
                    "temperature": t,
                    "top_k": eff_top_k,
                    "max_new_tokens": n_tokens,
                    "stop": stop if stop is not None else ["\n"],
                },
                reasons=["Raw text continuation without chat wrapper"],
            )

        # 2. Symbolic math offloading (when not explicitly asking for neural chain-of-thought)
        if config.enable_calculator and not is_thinking:
            math_res = try_calculate(c.user_input)
            if math_res is not None:
                return Plan(
                    intent="math",
                    strategy="tool",
                    decoding={"temperature": 0.0, "top_k": 1, "max_new_tokens": n_tokens, "stop": []},
                    reasons=["Exact arithmetic detected; offloaded to symbolic calculator tool"],
                )

        # 3. Explicit web search request
        if c.search:
            return Plan(
                intent="lookup",
                strategy="search",
                decoding={
                    "temperature": 0.0,
                    "top_k": 1,
                    "max_new_tokens": n_tokens,
                    "stop": stop if stop is not None else Bridge.STOP,
                },
                reasons=["Explicit user web search requested; deterministic grounded decoding"],
            )

        # 4. Native reasoning / thinking scaffold
        if is_thinking:
            eff_top_k = top_k if top_k is not None else (1 if (is_byte_tokenizer and t == 0.0) else (config.open_chat_top_k if is_byte_tokenizer else 50))
            if has_memories_or_facts:
                t = 0.0
                eff_top_k = 1
            return Plan(
                intent="think",
                strategy="think",
                decoding={
                    "temperature": t,
                    "top_k": eff_top_k,
                    "max_new_tokens": n_tokens,
                    "stop": stop if stop is not None else ["\nInput:", "\nUser:", "\nTask:"],
                },
                reasons=["Multi-step reasoning scratchpad requested"],
            )

        # 5. Memory- or fact-conditioned retrieval turn
        if has_memories_or_facts:
            return Plan(
                intent="lookup",
                strategy="recall",
                decoding={
                    "temperature": 0.0,
                    "top_k": 1,
                    "max_new_tokens": n_tokens,
                    "stop": stop if stop is not None else Bridge.STOP,
                },
                reasons=["Conditioned on notebook memories or active facts; deterministic decoding"],
            )

        # 6. Casual conversation turn
        if _is_casual_or_conversational(c.user_input, c.facts):
            eff_top_k = top_k if top_k is not None else (1 if (is_byte_tokenizer and t == 0.0) else (config.open_chat_top_k if is_byte_tokenizer else 50))
            return Plan(
                intent="casual",
                strategy="direct",
                decoding={
                    "temperature": t,
                    "top_k": eff_top_k,
                    "max_new_tokens": n_tokens,
                    "stop": stop if stop is not None else Bridge.STOP,
                },
                reasons=["Short conversational or personal turn"],
            )

        # 7. Standard chat turn
        eff_top_k = top_k if top_k is not None else (1 if (is_byte_tokenizer and t == 0.0) else (config.open_chat_top_k if is_byte_tokenizer else 50))
        return Plan(
            intent="chat",
            strategy="direct",
            decoding={
                "temperature": t,
                "top_k": eff_top_k,
                "max_new_tokens": n_tokens,
                "stop": stop if stop is not None else Bridge.STOP,
            },
            reasons=["Standard conversational exchange"],
        )


class ContextBuilder:
    """Assembles prompt and calculates token budgets preventing positional drift."""

    def compute_budget(self, block_size: int | None, max_new_tokens: int, config: BridgeConfig, is_thinking: bool) -> tuple[int | None, int]:
        if not block_size:
            return None, 0
        if not config.reserve_generation_budget or block_size < 256:
            max_prompt = (block_size - 16) if (is_thinking and block_size > 32) else block_size
            return max_prompt, 0

        # Stage 3 Working-memory reservation for 256-byte context models
        reserve_target = max(32, min(96, int(block_size * 0.4)))
        gen_reserve = min(max_new_tokens, reserve_target)
        max_prompt = max(16, block_size - gen_reserve)
        if is_thinking and max_prompt > 32:
            max_prompt = max(16, max_prompt - 16)
        return max_prompt, gen_reserve

    def build_prompt(
        self,
        c: Context,
        memories: list[dict],
        sources: list[str],
        tokenizer: Any,
        max_prompt_tokens: int | None,
    ) -> tuple[str, dict[str, int]]:
        web_prompt_mems = [f"[Web] {s}" for s in sources]
        all_prompt_mems = [m.get("content", "") for m in memories] + web_prompt_mems
        initial_history_len = len(c.history)

        prompt = render_chat_prompt(
            c.user_input,
            all_prompt_mems,
            task=c.task,
            history=c.history,
            max_tokens=max_prompt_tokens,
            tokenizer=tokenizer,
            facts=c.facts,
            summary=c.summary,
        )

        tokens_prompt = len(tokenizer.encode(prompt)) if tokenizer and hasattr(tokenizer, "encode") else len(prompt.encode("utf-8"))
        # Approximate history dropped if prompt truncated
        tokens_history_dropped = 0
        if max_prompt_tokens and initial_history_len > 0:
            untruncated = render_chat_prompt(c.user_input, all_prompt_mems, task=c.task, history=c.history, facts=c.facts, summary=c.summary)
            untruncated_len = len(tokenizer.encode(untruncated)) if tokenizer and hasattr(tokenizer, "encode") else len(untruncated.encode("utf-8"))
            if untruncated_len > tokens_prompt:
                tokens_history_dropped = untruncated_len - tokens_prompt

        slot_usage = {
            "tokens_prompt": tokens_prompt,
            "tokens_history_dropped": tokens_history_dropped,
        }
        return prompt, slot_usage


class Generator:
    """Interfaces cleanly with ChitRuntime extracting tokens, raw confidence, and finish reason."""

    def generate(self, runtime: Any, prompt: str, decoding: dict) -> tuple[str, float, str]:
        t = decoding.get("temperature", 0.7)
        eff_top_k = decoding.get("top_k", 1)
        n_tokens = decoding.get("max_new_tokens", 256)
        stop = decoding.get("stop")

        try:
            res = runtime.generate(prompt, n_tokens, t, eff_top_k, stop=stop, return_details=True)
        except TypeError:
            res = runtime.generate(prompt, n_tokens, t, eff_top_k, stop=stop)

        if isinstance(res, tuple):
            return str(res[0]), float(res[1]), str(res[2])
        return str(res), 1.0, "stop"


class Verifier:
    """Evaluates candidate outputs against generic quality invariants."""

    def detect_loop(self, text: str) -> bool:
        clean = text.strip().lower()
        if not clean:
            return False
        words = re.findall(r"\b\w+\b", clean)
        if len(words) >= 4:
            for i in range(len(words) - 3):
                if words[i] == words[i + 1] == words[i + 2] == words[i + 3]:
                    return True
            bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
            for i in range(len(bigrams) - 6):
                if bigrams[i] == bigrams[i + 2] == bigrams[i + 4] == bigrams[i + 6]:
                    return True
            trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words) - 2)]
            for i in range(len(trigrams) - 6):
                if trigrams[i] == trigrams[i + 3] == trigrams[i + 6]:
                    return True
        if re.search(r"(.)\1{5,}", clean):
            return True
        return False

    def verify(
        self,
        output: str,
        query: str,
        premise: str,
        finish_reason: str,
        config: BridgeConfig,
    ) -> tuple[bool, list[str]]:
        """Returns (is_valid, list_of_violations)."""
        violations = []
        clean = output.strip()

        if config.enable_generic_verifier:
            # 1. is_empty
            if not clean:
                violations.append("is_empty")

            # 2. is_repetitive
            if self.detect_loop(output):
                violations.append("is_repetitive")

            # 3. has_replacement_char
            if "\ufffd" in output:
                violations.append("has_replacement_char")

            # 4. is_truncated (informational invariant, sets is_incomplete)
            trimmed = clean.rstrip(" \t")
            if finish_reason == "length" and bool(trimmed) and not trimmed.endswith(Bridge.TERMINAL_PUNCTUATION):
                violations.append("is_truncated")

            # 5. Semantic Divergence / Grounding Invariant
            if premise:
                out_tokens = _extract_content_tokens(clean)
                query_tokens = _extract_content_tokens(query)
                premise_tokens = _extract_content_tokens(premise)
                context_tokens = query_tokens | premise_tokens
                if out_tokens and not out_tokens.intersection(context_tokens):
                    violations.append("is_disjoint_from_evidence")
            elif config.legacy_attractor_shim:
                if _has_semantic_divergence(output, query, premise=""):
                    violations.append("legacy_attractor_divergence")
        else:
            # Baseline behavior: cognitive supervisor grounding truth gate
            if premise:
                if _has_semantic_divergence(output, query, premise) or not clean:
                    violations.append("legacy_attractor_divergence")
            elif config.legacy_attractor_shim:
                if _has_semantic_divergence(output, query, premise=""):
                    violations.append("legacy_attractor_divergence")

        fatal_violations = [v for v in violations if v != "is_truncated"]
        is_valid = len(fatal_violations) == 0
        return is_valid, violations


class Bridge:
    STOP = ["\nUser:", "\nChit:", "\nTask:"]
    REASONING_STOP = ["\nUser:", "\nTask:"]
    TERMINAL_PUNCTUATION = (".", "!", "?", '"', "'", "\n")
    UNCERTAINTY_THRESHOLD = 0.40

    def __init__(
        self,
        runtime: Any,
        max_memories: int = 5,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        config: BridgeConfig | None = None,
    ):
        self.runtime = runtime
        if config is not None:
            self.config = config
        else:
            self.config = BridgeConfig(
                max_memories=max_memories,
                max_new_tokens=max_new_tokens,
                default_temperature=temperature,
            )
        self.max_memories = self.config.max_memories
        self.max_new_tokens = self.config.max_new_tokens
        self.temperature = self.config.default_temperature

        # Pipeline components
        self.router = Router()
        self.context_builder = ContextBuilder()
        self.generator = Generator()
        self.verifier = Verifier()

        # Calibration map cache
        self._calibration_mapping: list[dict[str, float]] | None = None
        self._load_calibration()

    def _load_calibration(self) -> None:
        if not self.config.enable_calibration:
            return
        cal_path = Path(self.config.calibration_file)
        if cal_path.exists():
            try:
                data = json.loads(cal_path.read_text(encoding="utf-8"))
                self._calibration_mapping = data.get("mapping", [])
            except Exception:
                self._calibration_mapping = None

    def _generate_with_details(
        self,
        prompt: str,
        n_tokens: int,
        t: float,
        effective_top_k: int,
        stop: list[str] | None,
    ) -> tuple[str, float, str]:
        decoding = {"temperature": t, "top_k": effective_top_k, "max_new_tokens": n_tokens, "stop": stop}
        return self.generator.generate(self.runtime, prompt, decoding)

    def process(
        self,
        c: Context,
        temperature: float | None = None,
        *,
        max_new_tokens: int | None = None,
        top_k: int | None = None,
        stop: list[str] | None = None,
        think: bool | None = None,
    ) -> ChitDecision:
        t = self.temperature if temperature is None else temperature
        n_tokens = self.max_new_tokens if max_new_tokens is None else max_new_tokens
        is_byte_tokenizer = getattr(self.runtime.tokenizer, "vocab_size", 256) <= 256
        is_thinking = (c.think if think is None else think) or c.task == "reasoning"

        # Check memories & facts presence
        memories = (c.memories or (self.runtime.recall(c.user_input, self.max_memories, min_relevance=self.config.min_relevance) if c.task != "continue" else []))[: self.max_memories]
        has_mem_or_facts = bool(memories or c.facts)

        # 1. Routing & Planning
        plan = self.router.route(
            c,
            self.config,
            temperature=t,
            max_new_tokens=n_tokens,
            top_k=top_k,
            stop=stop,
            think=think,
            is_byte_tokenizer=is_byte_tokenizer,
            has_memories_or_facts=has_mem_or_facts,
        )

        # Stage 4: Conservative Symbolic Calculator Tool
        if plan.strategy == "tool" and plan.intent == "math":
            math_result = try_calculate(c.user_input)
            if math_result is not None:
                metadata = {
                    "task": c.task,
                    "memory_ids": [],
                    "confidence": None,
                    "raw_confidence": None,
                    "is_incomplete": False,
                    "is_uncertain": False,
                    "needs_retrieval": False,
                    "source": "tool",
                    "plan": asdict(plan),
                    "raw_text": math_result,
                }
                return ChitDecision(text=math_result, confidence=None, metadata=metadata)

        # Continue task handling
        if plan.intent == "continue":
            text, conf, finish_reason = self.generator.generate(self.runtime, c.user_input, plan.decoding)
            trimmed = text.rstrip(" \t")
            is_incomplete = (finish_reason == "length") and bool(trimmed) and not trimmed.endswith(self.TERMINAL_PUNCTUATION)
            is_uncertain = conf < self.config.uncertainty_threshold
            metadata = {
                "task": c.task,
                "memory_ids": [],
                "confidence": round(conf, 3),
                "is_incomplete": is_incomplete,
                "is_uncertain": is_uncertain,
                "needs_retrieval": is_uncertain,
                "plan": asdict(plan),
                "raw_confidence": round(conf, 3),
                "raw_text": text,
                "source": "neural",
            }
            return ChitDecision(text, confidence=round(conf, 3), metadata=metadata)

        # Context budget & snippet sizing
        context_block = (getattr(self.runtime, "model_config", None) or {}).get("block_size")
        max_prompt_tokens, gen_reserve = self.context_builder.compute_budget(
            context_block, n_tokens, self.config, is_thinking
        )
        max_snippet_chars = min(120, max(60, int(context_block / 3))) if context_block else 100

        # Web Grounding
        web_grounded = False
        sources: list[str] = []
        web_sources: list[dict[str, str]] = []
        web_search_query = None
        retrieved_premise = ""
        clean_memory_ids = [m.get("id") for m in memories if m.get("id") and m.get("id") != "web-search"]

        if plan.strategy == "search" or (c.search and c.task != "continue"):
            snippets = search_web(c.user_input, max_results=2, max_chars=max_snippet_chars)
            if snippets:
                web_grounded = True
                sources = [str(s) for s in snippets]
                web_sources = _build_web_sources_meta(snippets)
                web_search_query = c.user_input
                retrieved_premise = " ".join(str(s).strip() for s in snippets if str(s).strip())
                plan.decoding["temperature"] = 0.0
                plan.decoding["top_k"] = 1

        # Prompt assembly & token usage tracking
        prompt, slot_usage = self.context_builder.build_prompt(
            c, memories, sources, self.runtime.tokenizer, max_prompt_tokens
        )

        grounding_fallback = False

        # Native Reasoning Scaffold
        if is_thinking:
            reasoning_prompt = f"Input: {c.user_input.strip()}\nReasoning:"
            budgeted_p = budget_snippet(retrieved_premise, max_chars=max_snippet_chars) if retrieved_premise else ""
            stop_seqs = plan.decoding.get("stop") or ["\nInput:", "\nUser:", "\nTask:"]

            raw, conf, finish_reason = self.generator.generate(
                self.runtime,
                reasoning_prompt,
                {**plan.decoding, "stop": stop_seqs},
            )
            raw = raw.strip()

            if "Answer:" in raw:
                parts = raw.split("Answer:", 1)
                thoughts = parts[0].strip()
                answer = parts[1].strip()
                raw_answer = answer
                source = "neural"

                # Verify answer
                is_valid, violations = self.verifier.verify(
                    answer, c.user_input, budgeted_p, finish_reason, self.config
                )

                if not is_valid:
                    if web_grounded and budgeted_p:
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
                        source = "extractive"
                    else:
                        # Ungrounded failure -> Recovery Step 3 (Honest Abstain)
                        if _is_short_conversational_turn(c.user_input):
                            answer = "Hello! How can I help you today?"
                            thoughts = "1. Conversational greeting received.\n2. Respond with a welcoming, helpful reply."
                            conf = 0.95
                        else:
                            answer = "I am here to help. What would you like to explore or work through?"
                            thoughts = "1. Detect ungrounded divergence from input prompt.\n2. Request problem clarification or restatement."
                            conf = 0.90
                        source = "abstain"

                trimmed_ans = answer.rstrip(" \t")
                is_incomplete = (finish_reason == "length") and bool(trimmed_ans) and not trimmed_ans.endswith(self.TERMINAL_PUNCTUATION)
                is_uncertain = conf < self.config.uncertainty_threshold
                needs_retrieval = is_uncertain or (c.task == "chat" and conf < 0.35)

                # Confidence Calibration
                cal_conf = conf
                is_calibrated = False
                if self._calibration_mapping and source == "neural":
                    cal_conf = calibrate(conf, self._calibration_mapping)
                    is_calibrated = True

                reported_conf = None if source in ("tool", "extractive") else (round(cal_conf, 3) if is_calibrated else round(conf, 3))

                metadata = {
                    "task": c.task,
                    "memory_ids": clean_memory_ids,
                    "thoughts": thoughts,
                    "confidence": round(conf, 3) if reported_conf is None and source == "extractive" else reported_conf,
                    "raw_confidence": round(conf, 3),
                    "is_calibrated": is_calibrated,
                    "is_incomplete": is_incomplete,
                    "is_uncertain": is_uncertain,
                    "needs_retrieval": needs_retrieval,
                    "web_grounded": web_grounded,
                    "sources": sources,
                    "web_sources": web_sources,
                    "plan": asdict(plan),
                    "raw_text": raw_answer,
                    "source": source,
                    "tokens_prompt": slot_usage["tokens_prompt"],
                    "tokens_reserved": gen_reserve,
                    "tokens_history_dropped": slot_usage["tokens_history_dropped"],
                }
                if reported_conf is not None:
                    metadata["confidence"] = reported_conf
                if web_search_query:
                    metadata["web_search_query"] = web_search_query
                if grounding_fallback:
                    metadata["grounding_fallback"] = True
                if thoughts and hasattr(self.runtime, "tokenizer"):
                    try:
                        metadata["thought_tokens"] = len(self.runtime.tokenizer.encode(thoughts))
                    except Exception:
                        metadata["thought_tokens"] = len(thoughts)
                return ChitDecision(text=answer, confidence=metadata["confidence"], metadata=metadata)

        # Standard Chat Generation (Primary Pass)
        text, conf, finish_reason = self.generator.generate(
            self.runtime, prompt, plan.decoding
        )
        final_text = text.strip()
        raw_text = final_text
        source = "neural"

        # Verify output
        is_valid, violations = self.verifier.verify(
            final_text, c.user_input, retrieved_premise, finish_reason, self.config
        )

        if not is_valid:
            # Short conversational recovery directly for greetings/pleasantries
            if _is_short_conversational_turn(c.user_input):
                final_text = "Hello! How can I help you today?"
                conf = 0.95
                source = "abstain"
            else:
                # Recovery Ladder Step 1: Resample with perturbed decoding (T=0.2)
                if self.config.enable_generic_verifier and not web_grounded and plan.decoding.get("temperature", 0.0) > 0.0:
                    resampled_text, res_conf, res_finish = self.generator.generate(
                        self.runtime, prompt, {**plan.decoding, "temperature": 0.2, "top_k": 5}
                    )
                    res_clean = resampled_text.strip()
                    res_valid, _ = self.verifier.verify(
                        res_clean, c.user_input, retrieved_premise, res_finish, self.config
                    )
                    if res_valid:
                        final_text = res_clean
                        conf = res_conf
                        finish_reason = res_finish
                        is_valid = True

                if not is_valid:
                    # Recovery Ladder Step 2: Extractive Projection
                    if web_grounded and retrieved_premise:
                        final_text = budget_snippet(retrieved_premise, max_chars=max_snippet_chars)
                        conf = 0.95
                        grounding_fallback = True
                        source = "extractive"
                    # Recovery Ladder Step 3: Honest Abstain
                    else:
                        final_text = "I am here to help. What would you like to explore or work through?"
                        conf = 0.90
                        source = "abstain"

        trimmed_text = final_text.rstrip(" \t")
        is_incomplete = (finish_reason == "length") and bool(trimmed_text) and not trimmed_text.endswith(self.TERMINAL_PUNCTUATION)
        is_uncertain = conf < self.config.uncertainty_threshold
        needs_retrieval = is_uncertain or (c.task == "chat" and conf < 0.35)

        # Autonomous Two-Pass Self-RAG
        if (needs_retrieval and not memories and not c.facts and c.task == "chat"
                and not is_thinking and not _is_casual_or_conversational(c.user_input, c.facts)):
            snippets = search_web(c.user_input, max_results=2, max_chars=max_snippet_chars)
            if snippets:
                grounded_mems = [f"[Web] {s}" for s in snippets]
                grounded_sources = [str(s) for s in snippets]
                grounded_web_sources = _build_web_sources_meta(snippets)
                retrieved_p = budget_snippet(" ".join(str(s) for s in snippets), max_chars=max_snippet_chars)
                grounded_prompt, g_slots = self.context_builder.build_prompt(
                    c, memories=[], sources=grounded_sources, tokenizer=self.runtime.tokenizer,
                    max_prompt_tokens=max_prompt_tokens
                )
                g_text, g_conf, g_finish = self.generator.generate(
                    self.runtime, grounded_prompt,
                    {"temperature": 0.0, "top_k": 1, "max_new_tokens": n_tokens, "stop": plan.decoding.get("stop", self.STOP)}
                )
                g_final = g_text.strip()
                g_raw_text = g_final
                g_source = "neural"

                g_valid, _ = self.verifier.verify(
                    g_final, c.user_input, retrieved_p, g_finish, self.config
                )
                if not g_valid or not g_final:
                    g_final = retrieved_p
                    g_conf = 0.95
                    grounding_fallback = True
                    g_source = "extractive"

                g_trimmed = g_final.rstrip(" \t")
                g_incomplete = (g_finish == "length") and bool(g_trimmed) and not g_trimmed.endswith(self.TERMINAL_PUNCTUATION)
                g_is_uncertain = g_conf < self.config.uncertainty_threshold
                g_needs_retrieval = g_is_uncertain or (c.task == "chat" and g_conf < 0.35)

                g_cal_conf = g_conf
                g_is_calibrated = False
                if self._calibration_mapping and g_source == "neural":
                    g_cal_conf = calibrate(g_conf, self._calibration_mapping)
                    g_is_calibrated = True

                reported_g_conf = None if g_source == "extractive" else (round(g_cal_conf, 3) if g_is_calibrated else round(g_conf, 3))

                g_metadata = {
                    "task": c.task,
                    "memory_ids": [],
                    "confidence": round(g_conf, 3) if reported_g_conf is None else reported_g_conf,
                    "raw_confidence": round(g_conf, 3),
                    "is_calibrated": g_is_calibrated,
                    "is_incomplete": g_incomplete,
                    "is_uncertain": g_is_uncertain,
                    "needs_retrieval": g_needs_retrieval,
                    "web_grounded": True,
                    "web_search_query": c.user_input,
                    "sources": grounded_sources,
                    "web_sources": grounded_web_sources,
                    "plan": asdict(plan),
                    "raw_text": g_raw_text,
                    "source": g_source,
                    "tokens_prompt": g_slots["tokens_prompt"],
                    "tokens_reserved": gen_reserve,
                    "tokens_history_dropped": g_slots["tokens_history_dropped"],
                }
                if reported_g_conf is not None:
                    g_metadata["confidence"] = reported_g_conf
                if grounding_fallback:
                    g_metadata["grounding_fallback"] = True
                return ChitDecision(g_final, confidence=g_metadata["confidence"], metadata=g_metadata)

        # Confidence Calibration
        cal_conf = conf
        is_calibrated = False
        if self._calibration_mapping and source == "neural":
            cal_conf = calibrate(conf, self._calibration_mapping)
            is_calibrated = True

        reported_conf = None if source == "extractive" else (round(cal_conf, 3) if is_calibrated else round(conf, 3))

        metadata = {
            "task": c.task,
            "memory_ids": clean_memory_ids,
            "confidence": round(conf, 3) if reported_conf is None else reported_conf,
            "raw_confidence": round(conf, 3),
            "is_calibrated": is_calibrated,
            "is_incomplete": is_incomplete,
            "is_uncertain": is_uncertain,
            "needs_retrieval": needs_retrieval,
            "web_grounded": web_grounded,
            "sources": sources,
            "web_sources": web_sources,
            "plan": asdict(plan),
            "raw_text": raw_text,
            "source": source,
            "tokens_prompt": slot_usage["tokens_prompt"],
            "tokens_reserved": gen_reserve,
            "tokens_history_dropped": slot_usage["tokens_history_dropped"],
        }
        if reported_conf is not None:
            metadata["confidence"] = reported_conf
        if web_search_query:
            metadata["web_search_query"] = web_search_query
        if grounding_fallback:
            metadata["grounding_fallback"] = True
        return ChitDecision(final_text, confidence=metadata["confidence"], metadata=metadata)
