# Chit (चित्): Atmini's brain

Chit is the cognitive core of Atmini. Its work is to understand the user's message and context,
communicate clearly, ask when important information is missing, reason through a problem, and help
the user choose a next step. Atmini can add tools and actions around Chit; Chit does not take
real-world actions without an explicit capability and permission path.

## Capability stages

1. **Language foundation** — UTF-8 byte model trained from scratch; CPU and CUDA training paths.
2. **Communication** — English, Hindi, and Sanskrit examples for dialogue, questions, instructions,
   explanations, and creative work.
3. **Structured input** — Markdown headings, lists, tables, quotes, checklists, and code fences are
   retained in requests and represented in training and held-out prompts.
4. **Problem solving** — identify the goal and constraints, find the next useful step, explain a
   simple chain of reasoning, ask clarifying questions, and state what is unknown.
5. **Continuity and learning** — sessions retain conversational context; memory holds experiences;
   API-taught knowledge remains separate and can be trained deliberately.
6. **Measured growth** — review held-out behavior by language and capability, then expand the corpus,
   context, model capacity, and training throughput in stages that fit the available CPU and RAM.
7. **Atmini integration** — later connect Chit's reasoning to approved tools and actions with a
   clear user-confirmation path.

## Current repository state

- The inference path formats requests, recalls matching memory, and (for `/chat`) adds recent session
  history. It does not call an external model or AI service.
- The assistant curriculum contains request/response examples, including Markdown and practical
  problem-solving. `data/prompts.txt` supplies open-ended review prompts; `data/eval.txt` is held out.
- Memory search currently ranks keyword overlap; paraphrase-aware and multilingual recall remain to be built.
- There is no separate intent router or tool/action execution path yet. Problem-solving behavior is learned
  through examples, with external actions kept for a later explicitly authorized Atmini integration.
- The byte-level training corpus is now stored compactly in host memory, so dataset size is less likely
  to be the first RAM limit on the documented two-core, 2-GiB CPU instance.
- Behavioral review of a freshly trained checkpoint remains required. Training loss alone is not
  evidence that Chit communicates or solves problems reliably.

Keep model weights, reviewed corpus, API-taught knowledge, runtime memory, session history, and the
Atmini action layer distinct so each can be inspected and improved deliberately.
