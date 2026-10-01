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
| `DELETE /sessions/{id}` | delete the session and its messages |

An unknown or deleted id returns 404. Sessions need the same `X-API-Key` as `/chat`.
`task: "continue"` does not use sessions (a plain-text continuation has no conversation).

## How history reaches the model

Before each reply the Bridge builds the prompt from the task header, recalled memory,
the last `CHIT_HISTORY_TURNS` messages of the session, and the new message, all in the
`User:` / `Chit:` format. The prompt is then shortened to fit the model's context
(`block_size`): the oldest turns are dropped first, then the lowest-ranked memories.
The current message is kept at the end of the prompt; if it alone exceeds the remaining model context, its end is
truncated for generation. Messages are always stored in full, even when their full text does not fit in the context.

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

`data/sessions.db*` holds conversation text; keep it out of git.
