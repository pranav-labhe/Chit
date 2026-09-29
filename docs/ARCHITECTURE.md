# Architecture

```
Atmini ──► Bridge ──► ChitRuntime ──┬──► ChitModel (Transformer weights)
                                    └──► MemoryStore (recalled at inference)

POST /knowledge ──► KnowledgeStore ──(POST /knowledge/train)──► training job
                                                                    │
                        promoted checkpoint ◄───────────────────────┘
```

Chit is the model/runtime component, not the whole Atmini system.

Three kinds of "what Chit knows" are kept separate on purpose:

| | Where | Changes the weights? | Used when |
| --- | --- | --- | --- |
| Weights | `checkpoints/latest.pt` | – | every generation |
| Memory | `data/memory.json` | no | recalled into the prompt at `/chat` |
| Knowledge | `data/knowledge.db` | only when a training run is started | the next `/knowledge/train` |

Memory stays external so experiences do not require immediate retraining.
Knowledge is the queue of material the next training run will learn from.
Text formats shared by training data and prompts live in `formats.py`, so a
Q&A pair is taught in exactly the shape `/chat` asks questions.
