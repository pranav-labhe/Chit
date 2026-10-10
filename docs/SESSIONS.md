# Chat sessions

A session is the ordered history of one conversation, stored under a session id.
It is separate from memory: memory holds durable facts shared by every
conversation; a session holds the messages of just one. Neither changes the
model's weights.

## Using it

`POST /chat` without a `session_id` starts a new conversation and returns its id.
Send that id back to continue it:

```json
POST /chat   {"message": "My name is Asha."}
-> {"text": "...", "session_id": "3f2b...c1", "metadata": {...}}

POST /chat   {"message": "Who am I?", "session_id": "3f2b...c1"}
```

| Endpoint | Purpose |
|---|---|
| `POST /sessions` | start an empty conversation |
| `GET /sessions` | list sessions, most recently used first (`limit`, `offset`) |
| `GET /sessions/{id}` | the session and its messages (`?limit=N` for the last N) |
| `GET /sessions/{id}/facts` | inspect explicit user-stated facts retained for the session |
| `PATCH /sessions/{id}/facts` | enable or disable extraction/context use (`{"enabled": false}`) |
| `POST /sessions/{id}/facts/refresh` | rebuild facts from retained user turns |
| `DELETE /sessions/{id}/facts` | clear derived facts while preserving the transcript |
| `GET /sessions/{id}/summary` | inspect summary, status, and coverage boundary |
| `PATCH /sessions/{id}/summary` | enable or disable background summarization (`{"enabled": false}`) |
| `POST /sessions/{id}/summary/refresh` | queue a summary of old turns when the session exceeds its retention window |
| `DELETE /sessions/{id}/summary` | clear the derived summary |
| `DELETE /sessions/{id}` | delete the session and its messages |

An unknown or deleted id returns 404. Sessions need the same `X-API-Key` as `/chat`.
`task: "continue"` does not use sessions (a plain-text continuation has no conversation).

## How history reaches the model

Before each reply the Bridge builds the prompt from the task header, recalled memory,
explicit session facts, derived summary (when available),
the last `CHIT_HISTORY_TURNS` messages, and the new message. Session facts have a separate
label from global memory and narrative summaries. Prompt trimming removes oldest turns,
then summary, lower-ranked memories, oldest facts, and only then truncates the end of the
current message. Messages remain stored in full.

When the session exceeds `CHIT_MAX_SESSION_TURNS`, a bounded background worker creates an
extractive narrative digest from complete older user/assistant exchanges. It reuses selected
source text and does not ask the compact model to invent a summary. The digest is explicitly
marked as derived context, records its covered-through turn sequence, and remains separate
from user-stated facts. Turns are pruned only after the digest commits. Status is `pending`,
`ready`, `disabled`, or `error`; failures leave turns available and can be retried. Facts remain
the authoritative source for explicit preferences and constraints.

Facts are extracted conservatively from direct user statements such as “my name is,”
“I live in,” “I prefer,” “my goal is,” explicit budget/deadline statements, and appointment
details. The extractor is deterministic and English-only; quoted text, block quotes, and
code spans are ignored. Unsupported phrasing produces no fact. Each fact includes its
source turn sequence, and a newer statement for the same key replaces the active value.
The full transcript remains authoritative. Extraction can be disabled per session, facts
can be cleared independently, and refresh rebuilds only from retained transcript turns.
Fact controls require the same API key as session operations.

**Limit:** history only helps a model trained on multi-turn text in this format. The
`chit_assistant_cpu` preset uses a 512-byte context, but the byte tokenizer means
multibyte scripts use that space more quickly. The session store is the foundation;
how much the model can use it depends on the model.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CHIT_SESSIONS_DB` | `data/sessions.db` | SQLite file |
| `CHIT_SESSION_TTL_DAYS` | `30` | delete sessions idle this long at start-up; `0` keeps them forever |
| `CHIT_MAX_SESSION_TURNS` | `200` | messages kept per session; the oldest are dropped |
| `CHIT_HISTORY_TURNS` | `8` | most recent messages offered to the model as context |

`data/sessions.db*` holds conversation text and derived session facts; keep it out of git.
