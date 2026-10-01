# Architecture

```
POST /generate ──┐
                 ├──► Bridge ──► ChitRuntime ──► ChitModel (Transformer weights)
POST /chat ──────┘       │
                         ├──► MemoryStore (recalled at inference)
                         └──► SessionStore (recent conversation context)

POST /knowledge ──► KnowledgeStore ──(POST /knowledge/train)──► training job
                                                                    │
                        promoted checkpoint ◄───────────────────────┘
```

Chit (चित्) is Atmini's neural brain: it reads the user's message, uses the supplied context, and
generates a response. The larger Atmini system may add tools and actions around this cognitive core.

Three kinds of "what Chit knows" are kept separate on purpose:

| | Where | Changes the weights? | Used when |
| --- | --- | --- | --- |
| Weights | `checkpoints/latest.pt` | – | every generation |
| Memory | `data/memory.json` | no | recalled into assistant-mode `/generate` and `/chat` prompts |
| Knowledge | `data/knowledge.db` | only when a training run is started | the next `/knowledge/train` |

Both `/generate` (assistant mode) and `/chat` use the shared request format and can
include relevant memory. `/chat` also includes and saves session history. Raw
continuation remains available through `/generate` with `mode: "continue"` or
`/chat` with `task: "continue"`.

Memory stays external so experiences do not require immediate retraining.
Knowledge is the queue of material the next training run will learn from.
Text formats shared by training data and prompts live in `formats.py`, so a
Q&A pair is taught in exactly the shape `/chat` asks questions. Markdown is retained as user text;
the model learns to interpret headings, lists, tables, quotes, and code fences through examples.
