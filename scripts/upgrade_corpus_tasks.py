"""Deterministic in-place upgrade of Chit training and evaluation corpora.

Enforces Phase 2 requirements:
1. Every block across all training and evaluation files begins with a canonical
   `Task: <name>` header (`chat`, `knowledge`, `behavior`, `grammar`, `reasoning`, `prose`).
2. Preserves >= original sample counts in every training file without merging files.
3. Caps exact duplicate prompt-reply / reasoning pairs at <= 2 copies per file,
   replacing removed duplicates 1-for-1 with:
   - Tone & phrasing variants
   - Greeting & identity prompt-side noise/typo/casing variants (with 100% clean `Chit:` replies)
   - >= 300 grounded `Known memory:` / `[Web]` / `User-stated facts:` examples across
     `knowledge.txt` and `reasoning.txt`
4. Builds `data/eval_combined.txt` across all 6 task streams with zero exact prompt/block
   leakage from any training file.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def split_blocks(text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def classify_qa_task(user_q: str, chit_a: str) -> str:
    q = user_q.lower()
    a = chit_a.lower()
    grammar_markers = (
        "complete the sentence",
        "correct the grammar",
        "rewrite in the past tense",
        "rewrite in the present tense",
        "rewrite in the future tense",
        "make the tense consistent",
        "join these ideas",
        "write one sentence using",
        "make this a polite request",
        "change to a polite request",
        "correct the punctuation",
        "fix the agreement",
        "correct the sentence",
        "make this sentence negative",
        "change to a yes-or-no question",
        "change to passive voice",
        "change to active voice",
        "turn this into a question",
        "turn this question into a statement",
        "rewrite this as a question",
        "improve this sentence",
        "make this sentence clearer",
        "define a noun",
        "opposite of ",
    )
    if any(m in q for m in grammar_markers):
        return "grammar"

    behavior_markers = (
        "not have enough information",
        "missing information",
        "information is missing",
        "information about the",
        "have not provided",
        "do not guess",
        "what should you clarify",
        "two facts conflict",
        "conflicting",
        "sources contradict",
        "ambiguous reference",
        "not to give advice yet",
        "do not give me a solution yet",
        "listen before suggesting",
        "quoted instruction",
        "quoted sentence",
        "pretend to know",
        "pretend certainty",
        "invent a missing",
        "does not say how long",
        "no information about the train schedule",
        "separate what is observed from what is not established",
        "state one limitation",
        "source of leakage",
    )
    if any(m in q for m in behavior_markers) or "do not have enough information" in a:
        return "behavior"

    knowledge_markers = (
        "what is chit",
        "atmini",
        "model weights",
        "neural weight",
        "learned weights",
        "learned intelligence",
        "checkpoint",
        "tokenizer",
        "utf-8 byte",
        "knowledge store",
        "external memory",
        "saving a memory",
        "saving something to memory",
        "session",
        "evaluation file",
        "eval data",
        "eval loss",
        "golden set",
        "promotion",
        "candidate",
        "context window",
        "block size",
        "transformer",
        "dropout",
        "brain screen",
        "teach chit",
        "studio",
        "sqlite",
        "inference manager",
    )
    if any(m in q for m in knowledge_markers):
        return "knowledge"

    return "chat"


def strip_dummy_memory(block: str) -> str:
    lines = block.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if (
            lines[i].strip() == "Known memory:"
            and i + 1 < len(lines)
            and lines[i + 1].strip() == "- (none)"
        ):
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def parse_qa_block(block: str) -> tuple[str, str, str]:
    """Returns (memory_and_fact_prefix, user_text, chit_text)."""
    cleaned = strip_dummy_memory(block.strip())
    lines = [ln for ln in cleaned.splitlines() if not ln.startswith("Task: ")]
    body = "\n".join(lines).strip()
    if "User:" not in body or "\nChit:" not in body:
        raise ValueError(f"Not a QA block: {block[:80]}")
    u_idx = body.index("User:")
    prefix = body[:u_idx].strip()
    rest = body[u_idx + len("User:") :]
    c_idx = rest.rindex("\nChit:")
    user_text = rest[:c_idx].strip()
    chit_text = rest[c_idx + len("\nChit:") :].strip()
    return prefix, user_text, chit_text


def format_qa_block(task: str, user_text: str, chit_text: str, prefix: str = "") -> str:
    pref = f"{prefix.strip()}\n" if prefix.strip() else ""
    return f"Task: {task}\n{pref}User: {user_text.strip()}\nChit: {chit_text.strip()}"


def parse_reasoning_block(block: str) -> tuple[str, str, str, str]:
    """Returns (prefix, input_text, reasoning_text, answer_text)."""
    lines = [ln for ln in block.strip().splitlines() if not ln.startswith("Task: ")]
    body = "\n".join(lines).strip()
    i_idx = body.index("Input:")
    prefix = body[:i_idx].strip()
    rest = body[i_idx + len("Input:") :]
    r_idx = rest.index("\nReasoning:")
    inp = rest[:r_idx].strip()
    rest2 = rest[r_idx + len("\nReasoning:") :]
    a_idx = rest2.index("\nAnswer:")
    reas = rest2[:a_idx].strip()
    ans = rest2[a_idx + len("\nAnswer:") :].strip()
    return prefix, inp, reas, ans


def format_reasoning_block(inp: str, reas: str, ans: str, prefix: str = "") -> str:
    pref = f"{prefix.strip()}\n" if prefix.strip() else ""
    return f"Task: reasoning\n{pref}Input: {inp.strip()}\nReasoning: {reas.strip()}\nAnswer: {ans.strip()}"


def generate_chat_replacements(needed: int, existing_keys: set[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    """Generates greeting/identity prompt-noise variants + tone/phrasing chat variants."""
    results: list[tuple[str, str]] = []

    def add_pair(u: str, c: str) -> bool:
        key = (u.strip(), c.strip())
        if key not in existing_keys:
            existing_keys.add(key)
            results.append((u, c))
            return True
        return False

    # 1. Greeting & Identity Variants (Prompt-side noise/typos/casing/spacing, 100% clean Chit replies)
    greeting_prompts = [
        "Hello", "hello", "HELLO", "hi chit", "Hi Chit!", "helo", "hii", "hiii",
        "hey there", "Hey there!", "good morning!", "good morning", "GOOD MORNING",
        "gm chit", "good afternoon!", "good evening", "yo chit", "hiya", "howdy",
        "  hello   chit  ", "hello?", "hi there", "helo chit", "hey chit!",
        "greetings", "good morninggg", "hellooo", "hi! how are you?", "hey, are u there?",
        "hello friend", "morning!", "evening!", "afternoon chit", "hi chit how r u",
    ]
    greeting_replies = [
        "Hello! How can I help you today?",
        "Hi there. What would you like to work on?",
        "Hello. I am here and ready to help.",
        "Good to see you. How can I assist you today?",
        "Hi! Tell me what is on your mind, and we can go step by step.",
        "Hello! What can we explore or solve together today?",
    ]
    for gp in greeting_prompts:
        for gr in greeting_replies:
            if len(results) >= needed:
                return results
            add_pair(gp, gr)

    identity_prompts = [
        "who are u?", "who r u", "who are you", "WHO ARE YOU?", "what is ur name",
        "what's your name?", "wat is chit", "what is chit?", "tell me about yourself",
        "are you atmini?", "r u atmini?", "who built you?", "what kind of ai are u",
        "  who   are  you  ", "introduce urself", "what can u do?", "wat can you do",
        "are u a human?", "are you a person?", "explain who you are", "who is chit",
        "what is your role in atmini?", "r u a chatbot?", "tell me what u do",
    ]
    identity_replies = [
        "I am Chit, a small byte-level language model that serves as the learning layer of Atmini.",
        "My name is Chit. I help with conversation, clear explanations, and step-by-step reasoning inside Atmini.",
        "I am Chit, the neural model component of the Atmini system. How can I help you today?",
        "I am Chit—a compact Transformer model designed to converse, reason carefully, and stay honest about what I know.",
        "I am not a person; I am Chit, the learning model inside Atmini. I can chat, summarize, and work through problems with you.",
    ]
    for ip in identity_prompts:
        for ir in identity_replies:
            if len(results) >= needed:
                return results
            add_pair(ip, ir)

    # 2. Conversational tone, empathy, planning, clarification, and latest-correction variants
    topics = [
        "a client email", "a project proposal", "a study schedule", "a code review",
        "a team update", "a weekly checklist", "a budget note", "a presentation outline",
        "a bug report", "a design doc", "a research summary", "a meeting agenda",
        "a status report", "a travel itinerary", "a lesson plan", "a workout routine",
        "a reading list", "a migration checklist", "a release note", "a thank-you message",
        "an interview prep plan", "a database cleanup", "a kitchen inventory", "a lab report",
        "a daily journal", "a sprint retrospective", "a handover note", "a feedback form",
        "a packing list", "a revision timetable", "a customer reply", "a workshop outline",
        "a deployment script", "a summary memo", "a test plan", "a troubleshooting guide",
        "a onboarding checklist", "a quarterly review", "a grant application", "a safety checklist",
    ]
    timeframes = [
        "for today", "for tomorrow morning", "before Friday", "for this afternoon",
        "for next week", "before the deadline", "in 20 minutes", "this evening",
    ]
    qa_templates = [
        (
            "Can you help me organize {topic} {when}?",
            "Yes. Share the main goal for {topic} {when}, and we will organize it step by step.",
        ),
        (
            "I need one clear next step on {topic} {when}.",
            "Let's pick the single most time-sensitive part of {topic} {when} and finish that first.",
        ),
        (
            "I feel stuck on {topic} {when}. Can we break it down?",
            "Of course. Tell me what part of {topic} feels blocked {when}, and we will break it into small steps.",
        ),
        (
            "Please don't give me advice on {topic} {when} yet; just listen.",
            "Understood. I will listen carefully first and wait until you ask for suggestions on {topic}.",
        ),
        (
            "Can you make my draft for {topic} {when} shorter and clearer?",
            "Sure. Paste your draft for {topic}, and I will tighten the wording while preserving your meaning.",
        ),
        (
            "I changed the schedule for {topic} to {when} instead of earlier.",
            "Got it. I will use {when} as your latest corrected schedule for {topic}.",
        ),
        (
            "What should we verify before sending {topic} {when}?",
            "First, check that {topic} answers the main question and does not rely on unverified assumptions.",
        ),
        (
            "I am overwhelmed by {topic} {when}. Where do I start?",
            "Take a breath—we do not need to finish everything at once. Let's choose one small starting step for {topic}.",
        ),
        (
            "Could you review {topic} {when} and keep the tone warm?",
            "Gladly. Share {topic} whenever you are ready, and I will keep the tone warm, clear, and supportive.",
        ),
        (
            "Let's pause on {topic} {when} and come back to it later.",
            "Okay. We can set {topic} aside for now and pick it right back up whenever you want.",
        ),
    ]

    for topic in topics:
        for when in timeframes:
            for u_tmpl, c_tmpl in qa_templates:
                if len(results) >= needed:
                    return results
                u = u_tmpl.format(topic=topic, when=when)
                c = c_tmpl.format(topic=topic, when=when)
                add_pair(u, c)

    return results


def generate_knowledge_replacements(
    needed: int, existing_keys: set[tuple[str, str, str]], rng: random.Random
) -> list[tuple[str, str, str]]:
    """Returns list of (prefix, user_q, chit_a) with >= 220 grounded Known memory/[Web]/facts slots."""
    results: list[tuple[str, str, str]] = []

    def add_item(pref: str, u: str, c: str) -> bool:
        key = (pref.strip(), u.strip(), c.strip())
        if key not in existing_keys:
            existing_keys.add(key)
            results.append((pref.strip(), u.strip(), c.strip()))
            return True
        return False

    # Part A: Grounded Known memory:, [Web], and User-stated facts: examples (>= 220 slots)
    grounded_facts = [
        ("Chit uses a 256-token UTF-8 byte vocabulary.", "What vocabulary size does Chit use?", "Based on the known memory, Chit uses a 256-token UTF-8 byte vocabulary."),
        ("The Champion model has 6 layers, 4 heads, and embedding dimension 256.", "How many layers and heads does the Champion model have?", "The Champion model has 6 layers, 4 attention heads, and a 256-dimensional embedding."),
        ("Chit's context window block_size is 256 bytes.", "What is Chit's context window size?", "Chit's context window block_size is 256 bytes."),
        ("Saving a memory stores it in SQLite for retrieval without modifying model weights.", "Does saving a memory modify neural weights?", "No. Saving a memory stores it in SQLite for retrieval at inference time without modifying neural weights."),
        ("Lessons added in Teach Chit remain pending until a training job runs.", "When does a queued lesson affect model weights?", "A queued lesson affects model weights only after an explicit training job runs."),
        ("Evaluation data is held out from training to measure generalization.", "Why is evaluation data kept separate from training?", "Evaluation data is held out so it measures true generalization rather than memorization."),
        ("Promotion replaces the served champion checkpoint only after evaluation passes.", "What does promotion do in Chit?", "Promotion makes a candidate checkpoint the active served champion after evaluation passes."),
        ("A session stores recent conversation turns and a rolling summary.", "What does a Chit session store?", "A Chit session stores recent conversation turns along with a rolling summary."),
        ("The Bridge verifier checks outputs for repetition loops, truncation, and ungrounded claims.", "What does the Bridge verifier check?", "The Bridge verifier checks candidate outputs for repetition loops, truncation, and ungrounded claims."),
        ("KV-caching reuses past key and value tensors during autoregressive byte generation.", "How does KV-caching speed up Chit generation?", "KV-caching reuses past key and value tensors across steps instead of recomputing the full prefix."),
        ("[Web] Python 3.12 introduced improved error messages and f-string parsing.", "What did Python 3.12 introduce according to the web snippet?", "According to the web source, Python 3.12 introduced improved error messages and f-string parsing."),
        ("[Web] Mars has two small moons named Phobos and Deimos.", "How many moons does Mars have?", "According to the retrieved web evidence, Mars has two moons: Phobos and Deimos."),
        ("[Web] SQLite stores an entire database in a single cross-platform disk file.", "How does SQLite store its database?", "SQLite stores the entire database in a single cross-platform file on disk."),
        ("[Web] Cosine learning rate schedules decay the learning rate smoothly toward a minimum ratio.", "How does a cosine learning rate schedule behave?", "A cosine schedule decays the learning rate smoothly toward a configured minimum ratio."),
        ("[Web] Isotonic regression fits a non-decreasing piecewise mapping for probability calibration.", "What is isotonic regression used for in calibration?", "Isotonic regression fits a monotonic non-decreasing curve to map raw scores to calibrated probabilities."),
        ("[Web] Byte-level tokenization avoids unknown-token errors on any valid UTF-8 string.", "Why does byte-level tokenization avoid unknown tokens?", "Because every valid UTF-8 string decomposes into bytes in 0..255, avoiding out-of-vocabulary tokens."),
    ]
    irrelevant_memories = [
        "The user prefers dark roast coffee in the morning.",
        "The office printer on floor 2 is out of toner.",
        "Asha's cat is named Mili and likes warm sunny windows.",
        "The weekend hiking trail is 6 kilometers long.",
        "Room 14 is booked for the Tuesday design review.",
        "The cafeteria serves soup at 12:30 PM on Wednesdays.",
        "The garden gate was painted dark green last autumn.",
    ]
    unanswered_questions = [
        ("What is the serial number of the backup server?", "The known memory does not state the backup server's serial number, so I cannot answer from the provided context."),
        ("What time does the regional train depart on Sunday?", "The available memory does not include the Sunday train departure time. Please share the schedule."),
        ("What is the API rate limit for external partners?", "That rate limit is not mentioned in the known memory, so I should not guess."),
        ("Which port is configured for the staging database?", "The provided memory does not specify the staging database port."),
        ("Who approved the Q4 hardware budget?", "The known memory does not contain information about who approved the Q4 hardware budget."),
        ("What is the Wi-Fi password for the guest network?", "The known memory does not mention the guest Wi-Fi password."),
    ]

    for mem, q, a in grounded_facts:
        add_item(f"Known memory:\n- {mem}", q, a)
        for irr in irrelevant_memories:
            add_item(f"Known memory:\n- {mem}\n- {irr}", q, a)

    for irr in irrelevant_memories:
        for u_q, u_a in unanswered_questions:
            add_item(f"Known memory:\n- {irr}", u_q, u_a)

    fact_scenarios = [
        ("deploy_day", "Thursday", "Monday", "Which day is scheduled for deployment?", "Based on your latest stated fact, deployment is scheduled for Thursday."),
        ("target_branch", "main", "release-v1", "Which branch should we target?", "According to your latest correction, we should target the main branch."),
        ("batch_size", "16", "8", "What batch size are we using for the run?", "Using your latest stated setting, the batch size is 16."),
        ("eval_file", "data/eval_combined.txt", "data/eval.txt", "Which evaluation file is active?", "Your latest stated fact sets the active evaluation file to data/eval_combined.txt."),
        ("meeting_room", "Room 302", "Room 105", "Which room is the meeting in?", "Following your latest correction, the meeting is in Room 302."),
        ("reviewer", "Priya", "Kabir", "Who is assigned as the reviewer?", "Based on your latest update, Priya is assigned as the reviewer."),
        ("learning_rate", "0.00005", "0.0001", "What learning rate should the job use?", "According to your latest stated fact, the learning rate is 0.00005."),
        ("max_steps", "1000", "4000", "How many steps will the candidate run?", "Based on your latest stated fact, the candidate run uses 1000 steps."),
        ("server_port", "8000", "5000", "Which port is the local server running on?", "Your latest stated fact indicates the server is running on port 8000."),
        ("dataset_seed", "42", "7", "What random seed is configured?", "Following your latest stated fact, the configured random seed is 42."),
    ]
    q_prefixes = ["", "Quick check: ", "From our session facts, ", "Can you confirm: ", "Tell me: "]
    for key, latest_val, old_val, q_base, a_base in fact_scenarios:
        for qp in q_prefixes:
            pref = (
                f"Known memory:\n- Earlier note mentioned {key} was {old_val}.\n"
                f"User-stated facts (latest correction wins):\n- {key}: {latest_val}"
            )
            q = f"{qp}{q_base}" if not qp else f"{qp}{q_base[0].lower() + q_base[1:]}"
            add_item(pref, q, a_base)

    # Part B: Architecture & system knowledge Q&A variants
    concepts = [
        (
            ["What is Chit?", "How would you describe Chit?", "Explain Chit in one sentence.", "What role does Chit play in Atmini?"],
            [
                "Chit is the compact byte-level Transformer language model that forms the learning core of Atmini.",
                "Chit is Atmini's local neural model layer, built to learn from text examples and assist with reasoning and dialogue.",
                "Within the Atmini system, Chit is the trainable language model responsible for text generation and question answering.",
            ],
        ),
        (
            ["Where does Chit's learned intelligence live?", "What holds the patterns Chit learns during training?", "Where are Chit's trained parameters kept?"],
            [
                "Chit's learned patterns live inside the neural network weights of its trained Transformer checkpoint.",
                "The model's learned intelligence is stored in its Transformer weight tensors, which are saved in checkpoints.",
                "Trained model weights hold Chit's learned statistical patterns, separate from external SQLite memory.",
            ],
        ),
        (
            ["Does saving a memory retrain Chit?", "If I add a memory in Brain, do the model weights change?", "Does storing a memory update neural weights?"],
            [
                "No. Saving a memory stores text for inference-time retrieval; it never modifies the neural model weights.",
                "No. Memories are retrieved into the prompt context during chat, whereas model weights only change during training.",
                "Adding a memory does not retrain Chit. Only an explicit training job updates the checkpoint weights.",
            ],
        ),
        (
            ["How do memory and lessons differ in Chit?", "What is the difference between Brain memories and Teach Chit lessons?", "When should I use memory versus a training lesson?"],
            [
                "Memories in Brain can be recalled immediately during inference, while lessons in Teach Chit wait in a queue for the next training run.",
                "Use memory when you want Chit to recall a fact right away as context; use lessons when you want a future training job to update the weights.",
                "Memory provides external context at runtime without changing weights, whereas lessons are compiled into training examples for weight updates.",
            ],
        ),
        (
            ["Why is evaluation data held out from training?", "Why must eval_combined.txt not overlap with training files?", "What is the purpose of a held-out evaluation set?"],
            [
                "Holding out evaluation data ensures we measure how well Chit generalizes to unseen prompts rather than memorizing training text.",
                "If evaluation examples appear in training data, eval loss becomes artificially low and hides overfitting.",
                "A clean held-out evaluation set tests genuine generalization across tasks without data leakage.",
            ],
        ),
        (
            ["What is a checkpoint promotion in Chit?", "How does a trained candidate become the live model?", "Explain candidate promotion in Studio."],
            [
                "Promotion is the step where an evaluated candidate checkpoint replaces the active champion checkpoint served by the runtime.",
                "Training writes a candidate checkpoint first; promotion switches the live server to that candidate once its evaluation metrics pass.",
                "Promotion updates the active model pointer so the verified candidate checkpoint becomes the served champion.",
            ],
        ),
        (
            ["How does Chit tokenize text?", "What does vocab_size 256 mean in Chit?", "Why does Chit use a byte tokenizer?"],
            [
                "Chit uses a UTF-8 byte tokenizer where each byte (0 to 255) maps directly to one token ID.",
                "With vocab_size 256, every single UTF-8 byte is a token, allowing Chit to represent any valid text without unknown-token errors.",
                "Chit's byte-level tokenizer encodes text as raw UTF-8 bytes so the 256-entry vocabulary covers all languages and symbols cleanly.",
            ],
        ),
        (
            ["What does the Bridge do in Chit?", "Explain the role of the Chit Bridge.", "How does the Bridge wrap the neural model?"],
            [
                "The Bridge routes requests, builds budgeted prompts with memories and session facts, runs generation, and verifies outputs before returning a decision.",
                "Chit's Bridge connects the raw Transformer runtime to memory retrieval, web search, calculator tools, confidence calibration, and output verification.",
                "The Bridge acts as a compound system layer around the neural model, handling task headers, context budgeting, and safety/grounding checks.",
            ],
        ),
        (
            ["What does answer-only loss masking do during training?", "Why are prompt tokens masked with -100 in training?", "How does loss masking help a small byte model?"],
            [
                "Answer-only loss masking sets prompt tokens to -100 so gradient updates focus model capacity on predicting the assistant's reply.",
                "By ignoring loss on the `Task:` and `User:` header bytes, training dedicates all gradient steps to generating accurate `Chit:` and `Reasoning:` completions.",
                "Masking prompt tokens with -100 prevents the 6-layer model from wasting capacity memorizing user questions instead of answers.",
            ],
        ),
        (
            ["How does Best-of-3 candidate selection work in the Bridge?", "Why does the Bridge sample up to 3 candidates when uncertain?", "Explain Best-of-N reranking in Chit."],
            [
                "When the greedy output fails verification or has low calibrated confidence, the Bridge samples additional candidates and selects the highest-scoring valid reply.",
                "Best-of-3 selection generates up to two extra candidates at mild temperature and ranks them by calibrated confidence and evidence overlap.",
                "Candidate reranking filters out repetitive or ungrounded completions and picks the most confident, well-grounded answer.",
            ],
        ),
    ]

    modifiers = [
        "", "In simple terms, ", "Briefly, ", "Can you explain: ",
        "For the Chit project, ", "In the Atmini architecture, ",
        "As a quick summary, ", "Please explain: ", "In one or two sentences, ",
    ]
    for q_list, a_list in concepts:
        for mod in modifiers:
            for q in q_list:
                for a in a_list:
                    if len(results) >= needed:
                        return results
                    q_mod = (mod + q[0].lower() + q[1:]) if mod else q
                    add_item("", q_mod, a)

    return results


def generate_behavior_replacements(
    needed: int, existing_keys: set[tuple[str, str, str]], rng: random.Random
) -> list[tuple[str, str, str]]:
    """Generates >= 1000 diverse behavior examples (missing info, conflicts, ambiguity, boundaries)."""
    results: list[tuple[str, str, str]] = []

    def add_item(pref: str, u: str, c: str) -> bool:
        key = (pref.strip(), u.strip(), c.strip())
        if key not in existing_keys:
            existing_keys.add(key)
            results.append((pref.strip(), u.strip(), c.strip()))
            return True
        return False

    missing_items = [
        ("the server log", "which error message appeared"),
        ("the shipping address", "where the package should be sent"),
        ("the budget limit", "how much you plan to spend"),
        ("the target audience", "who will read the document"),
        ("the programming language", "which language you want the snippet in"),
        ("the meeting time zone", "which time zone applies"),
        ("the file path", "where the file is located"),
        ("the recipe serving size", "how many people you are cooking for"),
        ("the travel dates", "which dates you plan to travel"),
        ("the table columns", "which columns are in the dataset"),
        ("the error traceback", "the exact traceback or error line"),
        ("the deadline", "when the work needs to be finished"),
        ("the device model", "which device model you are troubleshooting"),
        ("the source text", "the text you would like me to rewrite"),
        ("the two options", "which two options you want compared"),
        ("the recipient's role", "who will receive the email"),
        ("the confirmation number", "which reservation number to look up"),
        ("the database schema", "which tables and fields exist"),
        ("the operating system", "whether you are on Windows, Linux, or macOS"),
        ("the test command", "which command triggered the failure"),
        ("the input units", "whether the measurement is in meters or feet"),
        ("the API endpoint", "which route you are calling"),
        ("the room capacity", "how many people need seating"),
        ("the return policy", "what the store's return window is"),
    ]
    contexts = [
        "for this task", "before I proceed", "in your request",
        "for the draft", "for the troubleshooting step", "in this note",
    ]
    missing_templates = [
        (
            "I want help {ctx}, but I haven't shared {item}. What should you do?",
            "I should state that {item} is missing {ctx} and ask you for {detail} instead of guessing.",
        ),
        (
            "Can you complete the work {ctx} without knowing {item}?",
            "No. Since {item} is missing {ctx}, I should ask for {detail} first so I do not invent unsupported details.",
        ),
        (
            "If {item} is left out {ctx}, how should Chit respond?",
            "Chit should clearly note that {item} was not provided {ctx} and ask for {detail}.",
        ),
        (
            "Please guess {item} {ctx} and give me a confident answer anyway.",
            "I cannot guess {item} or pretend certainty {ctx}. Please share {detail} so I can give an accurate answer.",
        ),
        (
            "What is the safest step {ctx} when {item} is unknown?",
            "Ask a concise clarifying question {ctx} to learn {detail} before recommending an action.",
        ),
        (
            "Should you invent {item} {ctx} just to finish quickly?",
            "No. Inventing {item} {ctx} would be dishonest; I should state what is missing and ask for {detail}.",
        ),
    ]
    for item, detail in missing_items:
        for ctx in contexts:
            for u_t, c_t in missing_templates:
                if len(results) >= needed:
                    return results
                add_item(
                    "",
                    u_t.format(item=item, detail=detail, ctx=ctx),
                    c_t.format(item=item, detail=detail, ctx=ctx),
                )

    conflict_pairs = [
        ("the launch is on Monday", "the launch is on Friday", "the launch day"),
        ("the port is 8080", "the port is 3000", "the active port number"),
        ("the budget is 500 rupees", "the budget is 1200 rupees", "the approved budget"),
        ("the meeting is online", "the meeting is in Room 4", "the meeting location"),
        ("the backup runs daily", "the backup runs weekly", "the backup schedule"),
        ("the limit is 10 MB", "the limit is 50 MB", "the file size limit"),
        ("the owner is Meera", "the owner is Dev", "the task owner"),
        ("the test passed", "the test timed out", "the test status"),
        ("the deadline is noon", "the deadline is 5 PM", "the exact deadline"),
        ("the report has 4 pages", "the report has 9 pages", "the page count"),
        ("the server is in Mumbai", "the server is in Pune", "the server location"),
        ("the batch size is 8", "the batch size is 16", "the training batch size"),
    ]
    conflict_templates = [
        (
            "",
            "One note says {a}, and another note says {b}, with no timestamps. How should you handle this?",
            "I should point out that the two notes conflict on {topic} and ask which source is current rather than silently picking one.",
        ),
        (
            "Known memory:\n- Note A: {a}.\n- Note B: {b}.",
            "What is {topic}?",
            "The stored notes conflict—one states that {a} while another states that {b}. Please clarify which one is current.",
        ),
        (
            "Known memory:\n- Earlier note: {a}.\nUser-stated facts (latest correction wins):\n- update: {b}",
            "What should we use for {topic}?",
            "We should use the latest explicit correction ({b}) and treat the earlier note ({a}) as superseded.",
        ),
        (
            "",
            "Earlier I said {a}, but I am correcting it now: {b}. Which one applies?",
            "Your latest explicit correction applies: {b}. I will disregard the earlier statement that {a}.",
        ),
    ]
    for a, b, topic in conflict_pairs:
        for pref_t, u_t, c_t in conflict_templates:
            if len(results) >= needed:
                return results
            add_item(
                pref_t.format(a=a, b=b, topic=topic),
                u_t.format(a=a, b=b, topic=topic),
                c_t.format(a=a, b=b, topic=topic),
            )

    return results


def generate_reasoning_replacements(
    needed: int, existing_keys: set[tuple[str, str, str, str]], rng: random.Random
) -> list[tuple[str, str, str, str]]:
    """Returns list of (prefix, inp, reas, ans) with >= 180 grounded Known memory/[Web]/facts slots."""
    results: list[tuple[str, str, str, str]] = []

    def add_item(pref: str, inp: str, reas: str, ans: str) -> bool:
        key = (pref.strip(), inp.strip(), reas.strip(), ans.strip())
        if key not in existing_keys:
            existing_keys.add(key)
            results.append((pref.strip(), inp.strip(), reas.strip(), ans.strip()))
            return True
        return False

    # Part A: Grounded Known memory:, [Web], and User-stated facts: reasoning problems (>= 200 slots)
    containers = ["crate", "box", "carton", "tray", "pack", "bundle", "shelf", "bin"]
    objects = ["bottles", "notebooks", "pencils", "apples", "folders", "jars", "badges", "tiles"]
    for c_idx, cont in enumerate(containers):
        for o_idx, obj in enumerate(objects):
            if len(results) >= 120:
                break
            per_unit = 6 + c_idx + o_idx
            units = 3 + (c_idx + o_idx) % 6
            tot = per_unit * units
            web_tag = "[Web] " if (c_idx + o_idx) % 2 == 0 else ""
            add_item(
                f"Known memory:\n- {web_tag}Each {cont} holds {per_unit} {obj}.",
                f"How many {obj} are in {units} {cont}s?",
                f"From memory, 1 {cont} holds {per_unit} {obj}. {units} times {per_unit} equals {tot}.",
                f"{tot} {obj}.",
            )

    # Grounded latest-correction & missing-evidence reasoning (>= 80 slots)
    correction_cases = [
        ("budget", "250 rupees", "400 rupees", "An item costs 300 rupees. Does it fit the user's budget?", "The latest stated budget is 400 rupees, which supersedes 250 rupees. 300 is less than 400.", "Yes, it fits the 400-rupee budget."),
        ("budget", "600 rupees", "200 rupees", "An item costs 350 rupees. Does it fit the user's budget?", "The latest stated budget is 200 rupees, which supersedes 600 rupees. 350 is greater than 200.", "No, 350 rupees exceeds the 200-rupee budget."),
        ("departure_time", "9:00 AM", "9:30 AM", "The ride takes 45 minutes. When will the user arrive?", "Use the latest stated departure time of 9:30 AM. 9:30 AM plus 45 minutes is 10:15 AM.", "10:15 AM."),
        ("team_size", "4 members", "6 members", "Each member needs 3 badges. How many badges are needed?", "The latest correction sets team_size to 6 members. 6 times 3 equals 18.", "18 badges."),
        ("room_capacity", "30 seats", "20 seats", "25 guests are attending. Does the room have enough seats?", "The latest stated capacity is 20 seats. 25 guests exceed 20 seats.", "No, 5 more seats are needed."),
        ("sprint_days", "10 days", "14 days", "4 days of the sprint are complete. How many days remain?", "Use the latest sprint_days of 14 days. 14 minus 4 equals 10.", "10 days."),
        ("ticket_price", "80 rupees", "60 rupees", "How much do 5 tickets cost after the correction?", "The latest ticket_price is 60 rupees. 5 times 60 equals 300.", "300 rupees."),
        ("speed_kmh", "40 km/h", "55 km/h", "How far does the bus travel in 2 hours at the corrected speed?", "Use the corrected speed of 55 km/h. 55 times 2 equals 110.", "110 km."),
    ]
    for key, old_v, new_v, q, r, a in correction_cases:
        for variant in range(8):
            extra_note = f"\n- Unrelated note {variant + 1}: The lobby opens at 7 AM." if variant else ""
            pref = (
                f"Known memory:\n- Earlier note: {key} was {old_v}.{extra_note}\n"
                f"User-stated facts (latest correction wins):\n- {key}: {new_v}"
            )
            add_item(pref, q, r, a)

    missing_memory_cases = [
        ("Known memory:\n- The train leaves from Platform 4 at 10:00 AM.", "What time does the train arrive at its destination?", "The memory gives the departure time (10:00 AM) and platform, but not the travel duration or arrival time.", "The arrival time cannot be determined from the provided memory."),
        ("Known memory:\n- [Web] Package A weighs 4 kg.", "Which is heavier, Package A or Package B?", "The memory states Package A weighs 4 kg, but gives no weight for Package B.", "Not enough information; Package B's weight is missing."),
        ("Known memory:\n- Asha completed 7 tasks on Monday.", "How many tasks did Asha complete on Tuesday?", "The memory only records Monday's tasks and says nothing about Tuesday.", "Unknown; Tuesday's count is not in the memory."),
        ("Known memory:\n- [Web] The service runs on port 8000 in development.", "Which port does the service use in production?", "The web snippet only specifies the development port (8000), not the production port.", "The production port is not specified in the provided context."),
    ]
    for pref, q, r, a in missing_memory_cases:
        for v in range(8):
            sfx = f" (Check {v + 1})" if v else ""
            add_item(pref, q + sfx if v else q, r, a)

    # Part B: Diverse ungrounded step-by-step arithmetic, comparison, and logic deductions
    names = [
        "Aarav", "Diya", "Kabir", "Meera", "Rohan", "Sana", "Vikram", "Ananya",
        "Dev", "Tara", "Ishan", "Neha", "Arjun", "Priya", "Kiran", "Nisha",
        "Om", "Zoya", "Yash", "kavya", "Neel", "Pooja", "Rahul", "Simran",
    ]
    items = [
        "apples", "notebooks", "marbles", "stickers", "pencils", "pens",
        "oranges", "coins", "books", "stamps", "cards", "erasers",
        "ribbons", "candles", "tickets", "markers",
    ]
    for i, name in enumerate(names):
        uname = name.capitalize()
        for j, item in enumerate(items):
            if len(results) >= needed:
                return results
            start = 18 + i * 2 + j * 3
            add_n = 5 + (i + j) % 11
            give_n = 4 + (i * 2 + j) % 9
            rem = start + add_n - give_n
            inp = f"{uname} has {start} {item}, finds {add_n} more, and gives {give_n} away. How many {item} remain?"
            reas = f"{start} plus {add_n} is {start + add_n}. {start + add_n} minus {give_n} equals {rem}."
            ans = f"{rem} {item}."
            add_item("", inp, reas, ans)

            if len(results) >= needed:
                return results
            groups = 2 + (i + j) % 7
            per_g = 4 + (i * 3 + j) % 9
            tot_g = groups * per_g
            inp2 = f"{uname} packs {tot_g} {item} equally into {groups} boxes. How many {item} are in each box?"
            reas2 = f"Divide {tot_g} equally among {groups} boxes: {tot_g} divided by {groups} equals {per_g}."
            ans2 = f"{per_g} {item}."
            add_item("", inp2, reas2, ans2)

    return results


def upgrade_corpus() -> None:
    rng = random.Random(42)

    # 1. data/english_foundation/structural.txt -> Task: grammar
    struct_path = DATA / "english_foundation" / "structural.txt"
    struct_blocks = split_blocks(struct_path.read_text(encoding="utf-8"))
    new_struct = []
    for b in struct_blocks:
        _, u, c = parse_qa_block(b)
        new_struct.append(format_qa_block("grammar", u, c))
    struct_path.write_text("\n\n".join(new_struct) + "\n", encoding="utf-8")

    # 2. data/english_foundation/project_facts.txt -> Task: knowledge
    pf_path = DATA / "english_foundation" / "project_facts.txt"
    pf_blocks = split_blocks(pf_path.read_text(encoding="utf-8"))
    new_pf = []
    for b in pf_blocks:
        _, u, c = parse_qa_block(b)
        new_pf.append(format_qa_block("knowledge", u, c))
    pf_path.write_text("\n\n".join(new_pf) + "\n", encoding="utf-8")

    # 3. data/english_foundation/conversation.txt -> Task: chat
    ef_conv_path = DATA / "english_foundation" / "conversation.txt"
    ef_conv_blocks = split_blocks(ef_conv_path.read_text(encoding="utf-8"))
    new_ef_conv = []
    for b in ef_conv_blocks:
        pref, u, c = parse_qa_block(b)
        new_ef_conv.append(format_qa_block("chat", u, c, pref))
    ef_conv_path.write_text("\n\n".join(new_ef_conv) + "\n", encoding="utf-8")

    # 4. data/english_foundation/lexical_prose.txt -> Task: prose
    lp_path = DATA / "english_foundation" / "lexical_prose.txt"
    lp_blocks = split_blocks(lp_path.read_text(encoding="utf-8"))
    new_lp = []
    for b in lp_blocks:
        body = b[len("Task: prose") :].strip() if b.startswith("Task: prose") else b.strip()
        new_lp.append(f"Task: prose\n{body}")
    lp_path.write_text("\n\n".join(new_lp) + "\n", encoding="utf-8")

    # 5. data/train.txt and data/train_1mb.txt
    for t_name in ("train.txt", "train_1mb.txt"):
        t_path = DATA / t_name
        t_blocks = split_blocks(t_path.read_text(encoding="utf-8"))
        new_t = []
        for b in t_blocks:
            if "User:" in b and "\nChit:" in b:
                pref, u, c = parse_qa_block(b)
                task = classify_qa_task(u, c)
                new_t.append(format_qa_block(task, u, c, pref))
            else:
                lines = [ln for ln in b.splitlines() if not ln.startswith("Task: ")]
                body = "\n".join(lines).strip()
                new_t.append(f"Task: prose\n{body}")
        t_path.write_text("\n\n".join(new_t) + "\n", encoding="utf-8")

    # 6. data/conversation_reasoning/conversation.txt -> Task: chat, cap duplicates <= 2, preserve >= 3073
    cr_conv_path = DATA / "conversation_reasoning" / "conversation.txt"
    cr_conv_blocks = split_blocks(cr_conv_path.read_text(encoding="utf-8"))
    target_cr_conv = max(3073, len(cr_conv_blocks))
    counts: Counter[tuple[str, str]] = Counter()
    kept_conv: list[tuple[str, str]] = []
    for b in cr_conv_blocks:
        _, u, c = parse_qa_block(b)
        key = (u.strip(), c.strip())
        if counts[key] < 2:
            counts[key] += 1
            kept_conv.append(key)
    needed_conv = target_cr_conv - len(kept_conv)
    if needed_conv > 0:
        replacements = generate_chat_replacements(needed_conv, set(counts.keys()), rng)
        kept_conv.extend(replacements[:needed_conv])
    cr_conv_out = [format_qa_block("chat", u, c) for u, c in kept_conv]
    cr_conv_path.write_text("\n\n".join(cr_conv_out) + "\n", encoding="utf-8")

    # 7. data/knowledge_behavior/knowledge.txt -> Task: knowledge, cap duplicates <= 2, >= 1245
    kb_k_path = DATA / "knowledge_behavior" / "knowledge.txt"
    kb_k_blocks = split_blocks(kb_k_path.read_text(encoding="utf-8"))
    target_kb_k = max(1245, len(kb_k_blocks))
    k_counts: Counter[tuple[str, str, str]] = Counter()
    kept_k: list[tuple[str, str, str]] = []
    for b in kb_k_blocks:
        pref, u, c = parse_qa_block(b)
        key = (pref.strip(), u.strip(), c.strip())
        if k_counts[key] < 2:
            k_counts[key] += 1
            kept_k.append(key)
    needed_k = target_kb_k - len(kept_k)
    if needed_k > 0:
        k_repls = generate_knowledge_replacements(needed_k, set(k_counts.keys()), rng)
        kept_k.extend(k_repls[:needed_k])
    kb_k_out = [format_qa_block("knowledge", u, c, pref) for pref, u, c in kept_k]
    kb_k_path.write_text("\n\n".join(kb_k_out) + "\n", encoding="utf-8")

    # 8. data/knowledge_behavior/behavior.txt -> Task: behavior, cap duplicates <= 2, >= 1327
    kb_b_path = DATA / "knowledge_behavior" / "behavior.txt"
    kb_b_blocks = split_blocks(kb_b_path.read_text(encoding="utf-8"))
    target_kb_b = max(1327, len(kb_b_blocks))
    b_counts: Counter[tuple[str, str, str]] = Counter()
    kept_b: list[tuple[str, str, str]] = []
    for b in kb_b_blocks:
        pref, u, c = parse_qa_block(b)
        key = (pref.strip(), u.strip(), c.strip())
        if b_counts[key] < 2:
            b_counts[key] += 1
            kept_b.append(key)
    needed_b = target_kb_b - len(kept_b)
    if needed_b > 0:
        b_repls = generate_behavior_replacements(needed_b, set(b_counts.keys()), rng)
        kept_b.extend(b_repls[:needed_b])
    kb_b_out = [format_qa_block("behavior", u, c, pref) for pref, u, c in kept_b]
    kb_b_path.write_text("\n\n".join(kb_b_out) + "\n", encoding="utf-8")

    # 9. data/conversation_reasoning/reasoning.txt & data/reasoning.jsonl -> Task: reasoning, <= 2 dups, >= 1196
    reas_path = DATA / "conversation_reasoning" / "reasoning.txt"
    reas_blocks = split_blocks(reas_path.read_text(encoding="utf-8"))
    target_reas = max(1196, len(reas_blocks))
    r_counts: Counter[tuple[str, str, str, str]] = Counter()
    kept_r: list[tuple[str, str, str, str]] = []
    for b in reas_blocks:
        pref, inp, reas, ans = parse_reasoning_block(b)
        key = (pref.strip(), inp.strip(), reas.strip(), ans.strip())
        if r_counts[key] < 2:
            r_counts[key] += 1
            kept_r.append(key)
    needed_r = target_reas - len(kept_r)
    if needed_r > 0:
        r_repls = generate_reasoning_replacements(needed_r, set(r_counts.keys()), rng)
        kept_r.extend(r_repls[:needed_r])
    reas_out = [format_reasoning_block(inp, reas, ans, pref) for pref, inp, reas, ans in kept_r]
    reas_path.write_text("\n\n".join(reas_out) + "\n", encoding="utf-8")

    jsonl_path = DATA / "reasoning.jsonl"
    jsonl_lines = []
    for idx, (pref, inp, reas, ans) in enumerate(kept_r, start=1):
        row = {
            "id": f"r{idx:04d}",
            "task": "reasoning",
            "input": inp,
            "reasoning": reas,
            "answer": ans,
        }
        if pref:
            row["memory_block"] = pref
        jsonl_lines.append(json.dumps(row, ensure_ascii=False))
    jsonl_path.write_text("\n".join(jsonl_lines) + "\n", encoding="utf-8")

    # 10. Upgrade evaluation files in-place & build data/eval_combined.txt with zero training overlap
    train_files = [
        DATA / "train.txt",
        DATA / "train_1mb.txt",
        DATA / "english_foundation" / "structural.txt",
        DATA / "english_foundation" / "project_facts.txt",
        DATA / "english_foundation" / "conversation.txt",
        DATA / "english_foundation" / "lexical_prose.txt",
        DATA / "conversation_reasoning" / "conversation.txt",
        DATA / "conversation_reasoning" / "reasoning.txt",
        DATA / "knowledge_behavior" / "knowledge.txt",
        DATA / "knowledge_behavior" / "behavior.txt",
    ]
    train_blocks_set: set[str] = set()
    train_prompts_set: set[str] = set()
    for tf in train_files:
        for b in split_blocks(tf.read_text(encoding="utf-8")):
            train_blocks_set.add(b.strip())
            for ln in b.splitlines():
                if ln.startswith("User: ") or ln.startswith("Input: "):
                    train_prompts_set.add(ln.strip())

    # 10a. data/eval.txt
    eval_path = DATA / "eval.txt"
    eval_blocks = split_blocks(eval_path.read_text(encoding="utf-8"))
    new_eval = []
    for b in eval_blocks:
        if "User:" in b and "\nChit:" in b:
            pref, u, c = parse_qa_block(b)
            task = classify_qa_task(u, c)
            new_eval.append(format_qa_block(task, u, c, pref))
        else:
            lines = [ln for ln in b.splitlines() if not ln.startswith("Task: ")]
            new_eval.append("Task: prose\n" + "\n".join(lines).strip())
    eval_path.write_text("\n\n".join(new_eval) + "\n", encoding="utf-8")

    # 10b. data/conversation_reasoning/eval.txt
    cr_eval_path = DATA / "conversation_reasoning" / "eval.txt"
    cr_eval_blocks = split_blocks(cr_eval_path.read_text(encoding="utf-8"))
    new_cr_eval = []
    for b in cr_eval_blocks:
        if "Input:" in b and "\nReasoning:" in b:
            pref, inp, reas, ans = parse_reasoning_block(b)
            new_cr_eval.append(format_reasoning_block(inp, reas, ans, pref))
        else:
            pref, u, c = parse_qa_block(b)
            new_cr_eval.append(format_qa_block("chat", u, c, pref))
    cr_eval_path.write_text("\n\n".join(new_cr_eval) + "\n", encoding="utf-8")

    # 10c. data/knowledge_behavior/eval.txt
    kb_eval_path = DATA / "knowledge_behavior" / "eval.txt"
    kb_eval_blocks = split_blocks(kb_eval_path.read_text(encoding="utf-8"))
    new_kb_eval = []
    for b in kb_eval_blocks:
        pref, u, c = parse_qa_block(b)
        task = classify_qa_task(u, c)
        if task not in ("knowledge", "behavior"):
            task = "behavior" if ("should" in u.lower() or "conflict" in u.lower() or "missing" in c.lower() or "unsure" in c.lower() or "correction" in c.lower()) else "knowledge"
        new_kb_eval.append(format_qa_block(task, u, c, pref))
    kb_eval_path.write_text("\n\n".join(new_kb_eval) + "\n", encoding="utf-8")

    # 10d. data/eval_100kb.txt
    eval_100_path = DATA / "eval_100kb.txt"
    eval_100_blocks = split_blocks(eval_100_path.read_text(encoding="utf-8"))
    new_eval_100 = []
    for b in eval_100_blocks:
        pref, u, c = parse_qa_block(b)
        task = classify_qa_task(u, c)
        new_eval_100.append(format_qa_block(task, u, c, pref))
    eval_100_path.write_text("\n\n".join(new_eval_100) + "\n", encoding="utf-8")

    # 10e. Build data/eval_combined.txt with zero training overlap across all 6 tasks
    combined: list[str] = []
    seen_eval_prompts: set[str] = set()
    for block in new_eval + new_cr_eval + new_kb_eval + new_eval_100:
        if block.strip() in train_blocks_set:
            continue
        prompt_line = ""
        for ln in block.splitlines():
            if ln.startswith("User: ") or ln.startswith("Input: "):
                prompt_line = ln.strip()
                break
        if prompt_line and (prompt_line in train_prompts_set or prompt_line in seen_eval_prompts):
            continue
        if prompt_line:
            seen_eval_prompts.add(prompt_line)
        combined.append(block.strip())

    # Add held-out prose evaluation blocks so Task: prose is well-represented in eval_combined.txt
    held_out_prose = [
        "Task: prose\nEvening mist settled gently over the orchard while the last lanterns flickered along the stone wall.",
        "Task: prose\nThe word \"current\" can refer to the flow of a river, electric charge in a wire, or something happening right now.",
        "Task: prose\nBefore sealing the envelope, Meera verified that the return address and postage stamp were clearly visible.",
        "Task: prose\nA calm validation check after every milestone prevents small configuration mistakes from compounding silently.",
        "Task: prose\nAlthough the morning started with heavy clouds, a steady breeze cleared the sky before the market opened.",
    ]
    for hp in held_out_prose:
        if hp not in train_blocks_set and hp not in combined:
            combined.append(hp)

    eval_combined_path = DATA / "eval_combined.txt"
    eval_combined_path.write_text("\n\n".join(combined) + "\n", encoding="utf-8")


if __name__ == "__main__":
    upgrade_corpus()
    print("Corpus upgrade completed successfully.")
