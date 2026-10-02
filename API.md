# Chit API Reference

Version **0.2.0**. Base URL: `https://api.chitt.online` (deployed) or `http://127.0.0.1:8000` (local).
Interactive docs (Swagger UI): `/docs`. Machine-readable spec: `/openapi.json`.

This reference was written from the code on `main` (commit `5f2491b`). The sample responses are real:
each endpoint was called against a trained model and the output is shown here (long lists are
shortened with `...`). If the deployed server runs an older image, a field may differ; `/docs` is the
authority for what is deployed.

---

## Contents

1. [Conventions](#1-conventions)
2. [Endpoint index](#2-endpoint-index)
3. [Health and model](#3-health-and-model) — `GET /health`, `GET /ready`, `GET /model`
4. [Text generation](#4-text-generation) — `POST /generate`, `POST /chat`
5. [Sessions](#5-sessions) — `/sessions`
6. [Memory](#6-memory) — `/memory`
7. [Training](#7-training) — `/train`
8. [Knowledge](#8-knowledge) — `/knowledge`
9. [Training data](#9-training-data) — `/data`
10. [Shared objects](#10-shared-objects)
11. [Errors](#11-errors)
12. [Recommended workflows](#12-recommended-workflows)
13. [Server settings](#13-server-settings)

---

## 1. Conventions

**Format.** Requests and responses are JSON (`Content-Type: application/json`, UTF-8). Timestamps are
ISO-8601 in UTC. Ids are 32-character lowercase hex strings, except memory ids, which are UUIDs with dashes.

**Strict requests.** Every request body rejects unknown fields with `422`, so a misspelled field name is
an error and never silently ignored.

**Authentication.** Send the key in the `X-API-Key` header.

| Access level | Endpoints | Rule |
| --- | --- | --- |
| Public | `GET /health` | No key needed. |
| Key | `/ready`, `/model`, `/generate`, `/chat`, `/sessions*`, `/memory*` | If the server has `CHIT_API_KEY` set, the header is required (`401` otherwise). If the server has no key, these are open. |
| Training | `/train*`, `/knowledge*`, `/data*` | Same key rule, plus: if the server has **no** key configured these return `403`, unless it was started with `CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1` (local development only). |

**Concurrency.** A bounded FIFO inference queue runs one generation at a time per process/device.
Requests are rejected with `429` when the queue is full or queue wait expires. The server runs one
training job at a time; training and inference may compete for CPU/GPU resources.

**Model type matters.** Chit defaults to a byte-level neural brain trained from scratch, with optional
versioned BPE checkpoints and RoPE position encoding. It does not require an external AI service. Its learned knowledge, available memory, and context
determine what it can answer or create. `/generate` and `/chat` use assistant request formatting by
default; `/generate` retains raw continuation through `mode: "continue"`.

**Used in the examples below**

```bash
BASE=https://api.chitt.online
KEY=YOUR_API_KEY
```

PowerShell users: use `Invoke-RestMethod -Method Post -Uri ... -Headers @{ "X-API-Key" = $KEY } -ContentType "application/json" -Body '...'`
instead of `curl`.

---

## 2. Endpoint index

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | Public | Is the server up, is a model loaded, is a job running |
| GET | `/ready` | Key | Is the model, stores, and inference scheduler ready |
| GET | `/model` | Key | Size, settings and training history of the loaded model |
| POST | `/generate` | Key | Generate a response to a request; `mode: "continue"` opts into raw text continuation |
| POST | `/chat` | Key | Assistant request with memory and session history (or raw continuation via `task: "continue"`) |
| POST | `/sessions` | Key | Start an empty conversation |
| GET | `/sessions` | Key | List conversations |
| GET | `/sessions/{session_id}` | Key | One conversation with its messages |
| DELETE | `/sessions/{session_id}` | Key | Delete a conversation |
| POST | `/memory` | Key | Store a fact |
| GET | `/memory/search` | Key | Find stored facts by keyword |
| DELETE | `/memory/{memory_id}` | Key | Delete a stored fact |
| GET | `/train/configs` | Training | Names of the training presets |
| POST | `/train` | Training | Start a training job on the config's text files |
| GET | `/train` | Training | List recent jobs |
| GET | `/train/{job_id}` | Training | Status, progress and loss history of a job |
| POST | `/train/{job_id}/cancel` | Training | Stop a running job |
| POST | `/knowledge` | Training | Queue facts, Q&A or reasoning examples for training |
| GET | `/knowledge` | Training | List queued knowledge |
| GET | `/knowledge/stats` | Training | Counts by status and kind |
| GET | `/knowledge/{entry_id}` | Training | One knowledge entry |
| DELETE | `/knowledge/{entry_id}` | Training | Remove an entry from future training |
| POST | `/knowledge/train` | Training | Train on the stored knowledge |
| GET | `/data` | Training | Check the train/eval files on the server |
| POST | `/data/split` | Training | Split a corpus file into train and eval files |

---

## 3. Health and model

### GET /health

**Purpose.** Liveness check. It always answers, even when no model has been trained yet, so use it for
load-balancer and deployment health checks. **Access:** public.

**Request.** No parameters.

**Sample**

```bash
curl $BASE/health
```
```json
{
  "status": "ok",
  "version": "0.2.0",
  "model_loaded": true,
  "error": null,
  "training_job": null
}
```

**Response fields**

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | string | `ok` when a model is loaded, `no_model` when not. |
| `version` | string | API version. |
| `model_loaded` | boolean | Whether `/generate` and `/chat` can answer. |
| `error` | string or null | Why no model is loaded (for example `checkpoint not found: checkpoints/latest.pt (train first)`). |
| `training_job` | string or null | Id of the job that is queued or running now, otherwise `null`. |

**Recommended.** Poll this after a deployment until `status` is `ok`. A new server with no checkpoint
reports `no_model`: that is normal until the first training job finishes.

### GET /ready

**Purpose.** Readiness check for traffic routing. Returns `200` only when a model, memory, knowledge,
session store, and inference scheduler are initialized; otherwise returns `503` with per-component checks.
**Access:** key.

### GET /model

**Purpose.** Describes the model that is being served. **Access:** key. **Request.** No parameters.

**Sample**

```bash
curl -H "X-API-Key: $KEY" $BASE/model
```
```json
{
  "model_config": {"vocab_size": 256, "block_size": 128, "n_layer": 2, "n_head": 2, "n_embd": 64, "dropout": 0.0},
  "parameters": 124672,
  "device": "cpu",
  "checkpoint": {
    "format": 2,
    "chit_version": "0.2.0",
    "step": 3000,
    "total_steps": 3000,
    "init_from": null,
    "best_eval_loss": 1.6965870976448059,
    "last_eval": {"step": 3000, "train_loss": 0.09342920519411564, "eval_loss": 2.9523245334625243},
    "metadata": {},
    "path": "checkpoints/latest.pt"
  }
}
```

**Response fields**

| Field | Type | Meaning |
| --- | --- | --- |
| `model_config.vocab_size` | integer | Number of possible tokens. 256 for the byte tokenizer; configured vocabulary size for BPE. |
| `model_config.block_size` | integer | Context window in model tokens (for byte models, one token is one UTF-8 byte). |
| `model_config.position_encoding` | string | `absolute` (legacy default) or `rope`. |
| `tokenizer.name`, `tokenizer.vocab_size` | string, integer | Active tokenizer and vocabulary size. BPE responses include the tokenizer asset fingerprint. |
| `memory_search` | object | Keyword or hybrid retrieval mode and embedding coverage. |
| `inference` | object | Queue capacity and timeout; `batching` indicates whether dynamic batching is active. |
| `model_config.n_layer`, `n_head`, `n_embd` | integer | Number of transformer layers, attention heads, and the model width. |
| `model_config.dropout` | number | Dropout used in training. |
| `parameters` | integer | Number of weights. |
| `device` | string | `cpu` or `cuda`. |
| `checkpoint.step`, `total_steps` | integer | Steps this model was trained for. |
| `checkpoint.init_from` | string or null | Path of the model it was fine-tuned from, or `null` if trained from scratch. |
| `checkpoint.best_eval_loss` | number | Lowest eval loss seen during training. |
| `checkpoint.last_eval` | object | `step`, `train_loss`, `eval_loss` at the last check. |
| `checkpoint.metadata` | object | Extra information from the job that produced it. |
| `checkpoint.path` | string | File being served. |

**Errors.** `503` if no model is loaded.

**Recommended.** Compare `best_eval_loss` with `last_eval.eval_loss`. When the last value is much higher,
the model memorized its training text.

---

## 4. Text generation

### POST /generate

**Purpose.** Generate a response to a request using the same learned `Task: chat` format as
`/chat`. Set `mode: "continue"` to pass text directly to the model for raw continuation.
**Access:** key.

**Request body**

| Field | Type | Required | Default | Limits | Purpose |
| --- | --- | --- | --- | --- | --- |
| `prompt` | string | yes | — | 1–2000 characters | The user's request in assistant mode, or a raw text prefix in continue mode. |
| `mode` | string | no | `"assistant"` | `assistant` or `continue` | `assistant` formats the prompt as a request and includes relevant memory; `continue` sends it directly as a text prefix. |
| `tokens` | integer | no | 100 | 1–500 | Maximum new model tokens. For the byte tokenizer, each token is one UTF-8 byte. |
| `temperature` | number | no | 0.7 | 0–2 | Randomness. `0` always picks the most likely byte (same answer each time). Higher is more random. |
| `top_k` | integer | no | 50 | 1–256 | At each step, choose only among the `top_k` most likely bytes. Has no effect when `temperature` is 0. |
| `stop` | array of strings | no | none | up to 8 strings | Custom stop strings. In assistant mode, omitted or empty uses chat-turn markers; in continue mode, omitted or empty means no explicit stop. |

**Behavior**

- The returned `text` contains **only the generated response**, not your prompt.
- In the default `assistant` mode, the prompt is formatted as a `User:` request and relevant
  memories are included. Chat-turn markers are used as stops unless custom `stop` strings are given.
- In `continue` mode, the supplied prompt is passed directly to the model and the `stop` list is
  applied as given.
- Markdown written in `prompt` is preserved as request text, including headings, lists, tables,
  quotes, and fenced code. The model context limit still applies. To train from a `.md` corpus file,
  use `/data/split`; source files are read as text, not converted from Markdown into another format.

**Recommended.** For repeatable, least noisy output use `"temperature": 0`. Keep `tokens` at 40–120
unless you need more. Use `mode: "continue"` when raw continuation is needed.

**Sample**

```bash
curl -X POST $BASE/generate -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain how memory helps Chit.", "tokens": 100, "temperature": 0}'
```
```json
{"text": "Relevant memories can be included in the request context. Saving a memory does not change model weights."}
```

**Response fields**

| Field | Type | Meaning |
| --- | --- | --- |
| `text` | string | The generated response (your prompt is not repeated). |

**Errors.** `401` missing or wrong key. `422` a field is out of range, for example an empty `prompt` or `tokens` over 500.
`503` no model is loaded.

### POST /chat

**Purpose.** Respond to a request in chat format. It builds a prompt from the task, recalled memories,
and recent session messages, then stores the exchange. **Access:** key.

**Request body**

| Field | Type | Required | Default | Limits | Purpose |
| --- | --- | --- | --- | --- | --- |
| `message` | string | yes | — | 1–2000 characters | The user's message. |
| `task` | string | no | `"chat"` | up to 50 characters | `chat` uses the template. `continue` sends `message` straight to the model as the start of a sentence (like `/generate`, stopping at the end of the line). Any other value is written into the template as the task name. |
| `temperature` | number or null | no | `null` | 0–2 | Randomness. `null` uses the server default, 0.7. |
| `tokens` | integer or null | no | `null` | 1–500 | Maximum new model tokens; for the byte tokenizer, each token is one UTF-8 byte. |
| `session_id` | string or null | no | `null` | 32 lowercase hex characters | Continue this conversation. Omit it to start a new one; the new id is returned. Not allowed with `task: "continue"`. |

**Behavior.** With `task: "chat"` the prompt is built as:

```
Task: chat
Known memory:
- <up to 5 memories found by searching your message>
<last 8 messages of the session, as "User: ..." and "Chit: ...">
User: <message>
Chit:
```

Markdown in `message` (headings, lists, tables, quotes and code fences) stays as text in the request.
The prompt is shortened to fit the model's `block_size`: the oldest messages go first, then the
lowest-ranked memories, then the end of an overlong new request is truncated; session messages are
still stored in full. The reply stops at a chat-turn marker or the configured token limit (256 bytes
by default). The message and reply are saved to the session in full.

**Which endpoint to use.** Use `/chat` for a conversation that should use session history and recalled
memory. Use `/generate` for a single request or raw continuation. The model still needs suitable
training examples for the requested task and language.

**Sample: start a conversation, then continue it**

```bash
curl -X POST $BASE/chat -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"message": "Hello, I am", "temperature": 0}'
```
```json
{
  "text": "...",
  "session_id": "eefa8d7646ca4a99bf1ef6b514cf75c5",
  "metadata": {"task": "chat", "memory_ids": []}
}
```
```bash
curl -X POST $BASE/chat -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"message": "I learn", "session_id": "eefa8d7646ca4a99bf1ef6b514cf75c5", "temperature": 0}'
```

**Sample: plain continuation (no session)**

```bash
curl -X POST $BASE/chat -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"message": "Chit is the", "task": "continue", "temperature": 0}'
```
```json
{"text": " model inside Atmini.", "session_id": null, "metadata": {"task": "continue", "memory_ids": []}}
```

**Response fields**

| Field | Type | Meaning |
| --- | --- | --- |
| `text` | string | The model's reply. For `continue`, the part that follows `message`. |
| `session_id` | string or null | The conversation this exchange was saved to. `null` for `task: "continue"`. Send it back to continue the conversation. |
| `metadata.task` | string | The task that was used. |
| `metadata.memory_ids` | array of strings | Ids of the memories that were put into the prompt. |

**Errors.** `404` `session not found` (unknown or deleted `session_id`). `422` `session_id` is not 32 hex characters, or it was
combined with `task: "continue"`. `503` no model is loaded.

**Recommended.** Always keep the `session_id` from the first reply and send it with every later message.
Do not rely on long memory: the byte-level model has a limited `block_size`, so only part of the
history and memory may fit into a request.

---

## 5. Sessions

A session is the ordered history of one conversation. It is separate from memory: memory holds facts
shared by every conversation, a session holds the messages of one. Sessions are created automatically by
`POST /chat`, so you only need these endpoints to create one in advance, review history or delete it.

Limits (server settings): at most 200 messages are kept per session (oldest dropped); sessions idle for
30 days are deleted when the server starts.

### POST /sessions

**Purpose.** Start an empty conversation. **Access:** key. **Request.** No body. Returns `201`.

```bash
curl -X POST -H "X-API-Key: $KEY" $BASE/sessions
```
```json
{
  "id": "b212e85c807546d7a08531db226594f2",
  "created_at": "2026-10-01T08:21:49.769330+00:00",
  "updated_at": "2026-10-01T08:21:49.769330+00:00",
  "turns": 0
}
```

### GET /sessions

**Purpose.** List conversations, most recently used first. **Access:** key.

| Query parameter | Type | Default | Limits | Purpose |
| --- | --- | --- | --- | --- |
| `limit` | integer | 50 | 1–500 | Page size. |
| `offset` | integer | 0 | 0 or more | How many sessions to skip. |

```bash
curl -H "X-API-Key: $KEY" "$BASE/sessions?limit=5"
```
```json
{
  "total": 2, "limit": 5, "offset": 0,
  "sessions": [
    {"id": "b212e85c807546d7a08531db226594f2", "created_at": "...", "updated_at": "...", "turns": 0},
    {"id": "eefa8d7646ca4a99bf1ef6b514cf75c5", "created_at": "...", "updated_at": "...", "turns": 4}
  ]
}
```

`turns` counts messages (a question and its reply are 2).

### GET /sessions/{session_id}

**Purpose.** One conversation with its messages. **Access:** key.

| Parameter | In | Type | Purpose |
| --- | --- | --- | --- |
| `session_id` | path | string | The session id. |
| `limit` | query | integer 1–1000, optional | Return only the most recent N messages (still oldest first). Default: all. |

```bash
curl -H "X-API-Key: $KEY" $BASE/sessions/eefa8d7646ca4a99bf1ef6b514cf75c5
```
```json
{
  "id": "eefa8d7646ca4a99bf1ef6b514cf75c5",
  "created_at": "2026-10-01T08:21:49.590569+00:00",
  "updated_at": "2026-10-01T08:21:49.683996+00:00",
  "turns": 4,
  "summary": "User asked about memory and the assistant explained its function.",
  "facts": [{"key": "user_location", "value": "India"}],
  "messages": [
    {"role": "user", "content": "Hello, I am", "created_at": "2026-10-01T08:21:49.592302+00:00"},
    {"role": "assistant", "content": "...", "created_at": "2026-10-01T08:21:49.592302+00:00"},
    "..."
  ]
}
```

**Message fields.** `role` is `user` or `assistant`; `content` is the full text; `created_at` is the time it was saved.

### DELETE /sessions/{session_id}

**Purpose.** Delete a session and all of its messages. **Access:** key. Returns `204` with no body.

**Errors (all session endpoints).** `404` `session not found`, including for an id that is not 32 hex characters.

**Recommended.** Delete sessions that hold personal text once you no longer need them. Session text is
stored in `data/sessions.db`.

---

## 6. Memory

Memory records are stored in SQLite, separate from the model's weights; legacy JSON is imported and retained for recovery. Storing a memory
**never changes the model**; assistant-mode `/generate` and `/chat` find relevant memories and put them in the prompt.

### POST /memory

**Purpose.** Store a fact. **Access:** key. Returns `201`.

| Field | Type | Required | Default | Limits | Purpose |
| --- | --- | --- | --- | --- | --- |
| `content` | string | yes | — | 1–2000 characters | The fact. |
| `memory_type` | string | no | `"experience"` | up to 50 characters | A label for the kind of memory (for example `fact`, `concept`, `experience`). |
| `importance` | number | no | 0.5 | 0–1 | How much it matters. Used to rank memories that match equally well. |
| `tags` | array of strings | no | `[]` | up to 20 | Labels you can use to group memories. |

```bash
curl -X POST $BASE/memory -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"content": "Pranav lives in India.", "memory_type": "fact", "importance": 0.8, "tags": ["pranav", "profile"]}'
```
```json
{
  "id": "64b8a199-5eb2-4d77-934b-ad462a4712d4",
  "type": "fact",
  "content": "Pranav lives in India.",
  "importance": 0.8,
  "tags": ["pranav", "profile"],
  "created_at": "2026-10-01T08:21:49.778092+00:00"
}
```

**Response fields.** `id` (UUID, use it to delete), `type` (the `memory_type` you sent), `content`,
`importance`, `tags`, `created_at`. Memories created from knowledge with `remember: true` also carry a `source`
such as `knowledge:<entry id>`.

### GET /memory/search

**Purpose.** Find memories by keyword. **Access:** key.

| Query parameter | Type | Required | Default | Limits | Purpose |
| --- | --- | --- | --- | --- | --- |
| `q` | string | yes | — | 1–200 characters | Words to look for. |
| `limit` | integer | no | 5 | 1–50 | Maximum number of results. |

**Behavior.** Matching is by whole words, ignoring case, punctuation and common words such as "is" and
"the". Results are ranked by the number of shared words, then importance, then recency. Meaning is not
understood: "city" will not find "Nagpur".

```bash
curl -H "X-API-Key: $KEY" "$BASE/memory/search?q=Pranav&limit=3"
```
```json
{"results": [{"id": "64b8a199-5eb2-4d77-934b-ad462a4712d4", "type": "fact", "content": "Pranav lives in India.", "importance": 0.8, "tags": ["pranav", "profile"], "created_at": "2026-10-01T08:21:49.778092+00:00"}]}
```

### DELETE /memory/{memory_id}

**Purpose.** Delete one memory. **Access:** key. Returns `204`. `404` `memory not found` if it does not exist.

**Recommended.** Write memories as short, self-contained statements that contain the words someone
would search for. Use `importance` close to 1 for facts that must win ties.

---

## 7. Training

Training teaches the model. A job trains in the background, reports progress, and (by default) replaces
the model that is being served as soon as it succeeds, with no restart.

**What a job trains on.** The config chosen by `config` names a file in the server's `configs/` folder
(without `.json`) that sets the model size, training settings and the two text files
(`data.train_file`, `data.eval_file`). Fields you send in the request override the file for that job only.

### GET /train/configs

**Purpose.** Names you can use for `config`. **Access:** training. No parameters.

```bash
curl -H "X-API-Key: $KEY" $BASE/train/configs
```
```json
{"configs": ["chit_assistant_cpu", "chit_cpu_learning", "chit_strong", "chit_tiny", "chit_train_txt"]}
```

### POST /train

**Purpose.** Start a training job on the config's train and eval text. **Access:** training. Returns `202`
with the job and a `Location: /train/{id}` header.

**Request body** (all fields optional)

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `config` | string | `chit_cpu_learning` | Name of the preset in `configs/` (letters, digits, `_` and `-`, up to 64). Use `chit_assistant_cpu` for the new assistant-style corpus. |
| `seed` | integer | the config's | Random seed, for repeatable runs. |
| `device` | `auto`, `cpu` or `cuda` | the config's | Where to train. `cuda` fails with `422` if the server has no GPU. |
| `init` | `scratch`, `current` or `auto` | `scratch` | Starting weights. See below. |
| `model` | object | none | Override model size, see the table below. |
| `training` | object | none | Override training settings, see the table below. |
| `promote` | boolean | `true` | If true, a successful job becomes the served model. If false, it is trained and kept but not served. |

**`init` values**

| Value | Meaning |
| --- | --- |
| `scratch` | Random weights, using the config's model size. Gives a clean, repeatable result. |
| `current` | Continue from the model being served. The architecture (`block_size`, `n_layer`, `n_head`, `n_embd`) must not change, or the request fails with `422`. Fails if no model is served. |
| `auto` | Same as `current` when a model is served and the architecture is unchanged, otherwise `scratch`. |

**`model` overrides**

| Field | Type | Limits | Purpose |
| --- | --- | --- | --- |
| `block_size` | integer | 8–2048 | Context window in bytes. The train and eval files must both be larger than this. |
| `n_layer` | integer | 1–48 | Number of transformer layers. |
| `n_head` | integer | 1–64 | Attention heads. `n_embd` must be divisible by it. |
| `n_embd` | integer | 8–4096 | Model width. |
| `dropout` | number | 0 up to (not including) 1 | Randomly hides parts of the network while training, to reduce memorizing. |

**`training` overrides**

| Field | Type | Limits | Purpose |
| --- | --- | --- | --- |
| `batch_size` | integer | 1–1024 | Pieces of text used in each step. |
| `learning_rate` | number | above 0, up to 1 | Size of each step. Too high is unstable, too low is slow. |
| `weight_decay` | number | 0–1 | Regularization strength. |
| `max_steps` | integer | 1 or more (server cap: 100000) | Number of steps to train. |
| `eval_interval` | integer | 1 or more | Measure the loss every N steps. |
| `eval_steps` | integer | 1–1000 | Batches used for each measurement. |
| `checkpoint_interval` | integer | 1 or more | Save progress every N steps. |
| `grad_clip` | number | above 0, up to 100 | Caps the size of an update, for stability. |
| `warmup_steps` | integer | 0 or more | Steps to ramp the learning rate up from zero at the start. |
| `lr_schedule` | `constant` or `cosine` | — | `cosine` lowers the learning rate smoothly towards the end. |
| `min_lr_ratio` | number | 0–1 | With `cosine`, the final learning rate as a share of the starting one. |

**Checks before the job starts (`422` with a list of messages if any fail):** `vocab_size` must be 256;
`max_steps` within the server cap; `cuda` available if requested; both text files must exist and be
**larger than `block_size` bytes**; `n_embd` divisible by `n_head`.

**Sample**

```bash
curl -X POST $BASE/train -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"config": "chit_strong", "init": "scratch"}'
```

Response (`202`): the job object, here freshly queued and shortened.

```json
{
  "id": "1adc741f15164a2e9f0d8c7c883c1103",
  "state": "queued",
  "step": 0,
  "max_steps": 3000,
  "progress": 0.0,
  "latest": null,
  "history": [],
  "config": {"seed": 42, "device": "cpu", "model": {"...": "..."}, "training": {"...": "..."},
             "data": {"train_file": "data/train.txt", "eval_file": "data/eval.txt"}},
  "promote": true,
  "promoted": false,
  "metadata": {"init": "scratch"},
  "created_at": "2026-10-01T08:21:49.800302+00:00",
  "started_at": null,
  "finished_at": null
}
```
All job fields are described under [The job object](#the-job-object).

**Errors.** `404` `config not found: <name>`. `409` another job is already active (the body names it, see [Errors](#11-errors)).
`422` an override is out of range, a data file is missing or too small, or `init` is not possible.
`500` the config file itself is invalid.

**Recommended.** Start with `{"config": "chit_assistant_cpu", "init": "scratch"}`. Run `GET /data?config=...` first to
confirm the files are ready. Poll `GET /train/{id}` every few seconds. For a quick test add
`"training": {"max_steps": 60}`.

### GET /train

**Purpose.** List recent jobs, newest first. The server keeps the 50 most recent. **Access:** training.

```json
{"jobs": [ {"id": "1adc741f15164a2e9f0d8c7c883c1103", "state": "succeeded", "...": "..."} ]}
```
Each entry is a [job object](#the-job-object).

### GET /train/{job_id}

**Purpose.** Status of one job: use it to watch progress. **Access:** training. `404` `training job not found`.

```bash
curl -H "X-API-Key: $KEY" $BASE/train/1adc741f15164a2e9f0d8c7c883c1103
```
```json
{
  "id": "1adc741f15164a2e9f0d8c7c883c1103",
  "state": "succeeded",
  "step": 60,
  "max_steps": 60,
  "progress": 1.0,
  "latest": {"step": 60, "train_loss": 2.902951, "eval_loss": 2.907317, "at": "2026-10-01T08:21:54.165970+00:00"},
  "history": [
    {"step": 1, "train_loss": 5.516232, "eval_loss": 5.513243, "at": "2026-10-01T08:21:51.778800+00:00"},
    {"step": 30, "train_loss": 3.936099, "eval_loss": 3.940216, "at": "2026-10-01T08:21:52.911398+00:00"},
    "..."
  ],
  "config": {"seed": 42, "device": "cpu", "model": {"...": "..."}, "training": {"...": "..."},
             "data": {"train_file": "data/train.txt", "eval_file": "data/eval.txt"}},
  "promote": true,
  "promoted": true,
  "promotion_error": null,
  "checkpoint": "checkpoints/jobs/1adc741f15164a2e9f0d8c7c883c1103/latest.pt",
  "init_checkpoint": null,
  "metadata": {"init": "scratch"},
  "post_success_error": null,
  "error": null,
  "cancel_requested": false,
  "created_at": "2026-10-01T08:21:49.800302+00:00",
  "started_at": "2026-10-01T08:21:49.800661+00:00",
  "finished_at": "2026-10-01T08:21:54.187083+00:00"
}
```

**Recommended.** Wait until `state` is `succeeded` **and** `promoted` is `true`. A job can succeed
without being served if `promote` was `false` or loading failed (`promotion_error` says why).

### POST /train/{job_id}/cancel

**Purpose.** Ask a job to stop. **Access:** training. Returns `202` with the job.

Cancelling is cooperative: the job stops at its next step, so the first response usually shows
`state: "running"` with `cancel_requested: true`, and a moment later `state: "cancelled"`. The served model
is left as it was. `409` `job <id> already succeeded` (or failed/cancelled) if it has already finished; `404` if unknown.

### The job object

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Job id. |
| `state` | string | `queued`, `running`, `succeeded`, `failed` or `cancelled`. The last three are final. |
| `step`, `max_steps` | integer | Steps done and total. |
| `progress` | number | `step / max_steps`, from 0 to 1. |
| `latest` | object or null | Most recent loss reading: `step`, `train_loss`, `eval_loss`, `at`. |
| `history` | array | All loss readings so far (step 1 and every `eval_interval` steps). |
| `config` | object | The settings actually used after your overrides: `seed`, `device`, `model`, `training`, `data`. |
| `promote` | boolean | Whether the job was asked to become the served model. |
| `promoted` | boolean | Whether it did become the served model. |
| `promotion_error` | string or null | Why promotion failed, if it did. |
| `checkpoint` | string or null | Path of the finished model file. |
| `init_checkpoint` | string or null | Copy of the starting weights when `init` was `current`/`auto`; otherwise `null`. |
| `metadata` | object | Extra details: `init`, and for knowledge jobs a `knowledge` object (entries used, `repeat`, `select`, dataset size and hash). |
| `post_success_error` | string or null | An error from the step after training, such as marking knowledge as trained. |
| `error` | string or null | Why the job failed. |
| `cancel_requested` | boolean | Cancel was requested. |
| `created_at`, `started_at`, `finished_at` | string or null | Timestamps. `null` until reached. |

**Reading the losses.** `train_loss` falling means the model is learning. If `eval_loss` rises while
`train_loss` keeps falling, it is memorizing the training text.

---

## 8. Knowledge

The knowledge store is a queue of things you want Chit to learn. Adding knowledge does **not** change the
model; it is stored with status `pending` and is learned by `POST /knowledge/train`, after which the entries
become `trained`.

### POST /knowledge

**Purpose.** Add 1–500 items in one call. All items are validated first: if one is invalid, none are stored
(`422`). **Access:** training. Returns `201`.

**Request body**

| Field | Type | Required | Purpose |
| --- | --- | --- | --- |
| `items` | array (1–500) | yes | The items to add. Each has a `kind`. |

**Fields on every item**

| Field | Type | Default | Limits | Purpose |
| --- | --- | --- | --- | --- |
| `kind` | `text`, `qa` or `reasoning` | required | — | Selects the shape of the item. |
| `tags` | array of strings | `[]` | up to 20; each 1–50 characters of letters, digits and `._:/-` | Labels for filtering and selecting what to train on. |
| `source` | string or null | `null` | up to 200 characters | Where it came from, for your own records. |
| `remember` | boolean | `false` | — | Also store it as a memory, so assistant-mode `/generate` and `/chat` can use it before training. |

**Fields by `kind`**

| `kind` | Field | Limits | Purpose |
| --- | --- | --- | --- |
| `text` | `text` | 1–20000 characters | A passage or fact written as plain text. Best for a model trained on plain sentences. |
| `qa` | `question` | 1–2000 | The question. |
| `qa` | `answer` | 1–5000 | The answer. Rendered in training as `User: <question>` / `Chit: <answer>`. |
| `reasoning` | `input` | 1–5000 | The problem. |
| `reasoning` | `reasoning` | 1–10000 | The steps. |
| `reasoning` | `answer` | 1–5000 | The conclusion. |

**Behavior.** An item identical to one already stored (same kind and content) is not added again: it comes back
with `created: false`. Tags are cleaned and sorted.

**Sample**

```bash
curl -X POST $BASE/knowledge -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{
  "items": [
    {"kind": "qa", "question": "Where is Pranav from?", "answer": "Pranav is from India.",
     "tags": ["profile"], "source": "readme", "remember": true},
    {"kind": "text", "text": "Chit runs on a small CPU server.", "tags": ["infra"]},
    {"kind": "reasoning", "input": "Is 6 even?", "reasoning": "6 divided by 2 is 3 with no remainder.", "answer": "Yes."}
  ]}'
```
```json
{
  "created": 3,
  "duplicates": 0,
  "items": [
    {
      "id": "c5f696d2dd414f72bcfd2f441bfa20b9",
      "kind": "qa",
      "payload": {"question": "Where is Pranav from?", "answer": "Pranav is from India."},
      "tags": ["profile"],
      "source": "readme",
      "status": "pending",
      "created_at": "2026-10-01T08:21:49.790078+00:00",
      "trained_at": null,
      "trained_job_id": null,
      "created": true,
      "memory_id": "c8a3f59d-0d55-4ec6-85a5-4970ce9427b3"
    },
    "..."
  ]
}
```

**Response fields**

| Field | Type | Meaning |
| --- | --- | --- |
| `created` | integer | Number of new entries. |
| `duplicates` | integer | Items that already existed. |
| `items[]` | array | One [knowledge entry](#the-knowledge-entry) per item you sent, in order, plus `created` (new or not) and `memory_id` (the memory made when `remember` was true, otherwise `null`). |

**Recommended.** Use `qa` only if the model is trained on and prompted with `User:` / `Chit:`; use `text` for plain
sentences. Write the same fact in several wordings (several items), because varied examples help Chit use facts in new requests.

### GET /knowledge

**Purpose.** List stored entries, newest first. **Access:** training.

| Query parameter | Type | Default | Purpose |
| --- | --- | --- | --- |
| `status` | `pending` or `trained` | all | Only entries with this status. |
| `kind` | `text`, `qa` or `reasoning` | all | Only this kind. |
| `tag` | string, repeatable (up to 10) | none | Only entries that have **all** the given tags. |
| `limit` | integer 1–500 | 50 | Page size. |
| `offset` | integer 0+ | 0 | Entries to skip. |

```bash
curl -H "X-API-Key: $KEY" "$BASE/knowledge?status=pending&limit=2"
```
```json
{"total": 3, "limit": 2, "offset": 0, "items": [ {"id": "0323d7db14744225ba9f7d8d563462da", "kind": "reasoning", "...": "..."} ]}
```

### GET /knowledge/stats

**Purpose.** Counts. **Access:** training.

```json
{"total": 3, "by_status": {"pending": 3, "trained": 0}, "by_kind": {"text": 1, "qa": 1, "reasoning": 1}}
```

### GET /knowledge/{entry_id}

**Purpose.** One entry. **Access:** training. `404` `knowledge entry not found`.

```json
{
  "id": "c5f696d2dd414f72bcfd2f441bfa20b9",
  "kind": "qa",
  "payload": {"question": "Where is Pranav from?", "answer": "Pranav is from India."},
  "tags": ["profile"],
  "source": "readme",
  "status": "pending",
  "created_at": "2026-10-01T08:21:49.790078+00:00",
  "trained_at": null,
  "trained_job_id": null
}
```

### DELETE /knowledge/{entry_id}

**Purpose.** Remove an entry from future training. **Access:** training. Returns `204`; `404` if unknown.
A model that already trained on the entry keeps what it learned until you retrain with `init: "scratch"`.

### The knowledge entry

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Entry id. |
| `kind` | string | `text`, `qa` or `reasoning`. |
| `payload` | object | The content: `{text}`, `{question, answer}` or `{input, reasoning, answer}`. |
| `tags` | array | Labels. |
| `source` | string or null | Where it came from. |
| `status` | string | `pending` (not yet trained) or `trained`. |
| `created_at` | string | When it was added. |
| `trained_at`, `trained_job_id` | string or null | When and by which job it was trained. |

### POST /knowledge/train

**Purpose.** Train on the stored knowledge now. It builds a dataset from the knowledge (and, by default, the
config's `train.txt`), then runs a normal training job. **Access:** training. Returns `202` with a [job object](#the-job-object)
whose `metadata.knowledge` describes the dataset.

**Request body.** All the fields of [`POST /train`](#post-train) (`config`, `seed`, `device`, `model`, `training`,
`promote`) and `init` (which here defaults to **`auto`**), plus:

| Field | Type | Default | Limits | Purpose |
| --- | --- | --- | --- | --- |
| `select` | `all` or `pending` | `all` | — | `all` trains on every entry, which limits forgetting. `pending` trains only on entries not yet trained. |
| `tags` | array of strings | `[]` | up to 10 | Only entries that have all these tags. |
| `include_base` | boolean | `true` | — | Mix in the config's `data.train_file` text, so the model keeps its general text. |
| `repeat` | integer | 3 | 1–100 | How many times the knowledge appears in the dataset. More repeats make a small dataset count for more. |

**Behavior.** Entries become `trained` only when the job succeeds **and** is promoted. A failed or cancelled job
leaves them `pending`. The eval file is the config's `data.eval_file`, unchanged.

**Sample**

```bash
curl -X POST $BASE/knowledge/train -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"config": "chit_strong", "repeat": 30}'
```
Response: `202`, a job whose metadata contains:
```json
"metadata": {
  "init": "auto",
  "knowledge": {"entries": 3, "select": "all", "tags": [], "repeat": 5, "include_base": true,
                "dataset_bytes": 12737, "dataset_sha256": "5bc98b17...", "manifest": "checkpoints/jobs/<id>/dataset/manifest.json"}
}
```

**Errors.** `422` `no knowledge matches this request; add some with POST /knowledge`, or the dataset exceeds the size limit,
or the base file is missing. `409` a job is already active. Other errors as in `POST /train`.

**Recommended.** Use `select: "all"` and `repeat` 10–30 for small amounts of knowledge. For a clean, repeatable model use `init: "scratch"`;
`auto` or `current` fine-tunes the served model faster but can make it forget older text.

---

## 9. Training data

These endpoints check and prepare `train.txt` and `eval.txt`, which usually arrive from outside the API (for example a
folder mounted into a container).

### GET /data

**Purpose.** Report on the config's train and eval files as they are on the server right now. Run it after mounting or
editing files and before training. **Access:** training.

| Query parameter | Type | Default | Purpose |
| --- | --- | --- | --- |
| `config` | string | `chit_cpu_learning` | Which config's files and `block_size` to check. `404` if the config does not exist. |

```bash
curl -H "X-API-Key: $KEY" "$BASE/data?config=chit_strong"
```
```json
{
  "config": "chit_strong",
  "block_size": 128,
  "train": {"path": "data/train.txt", "bytes": 11887, "lines": 242, "sha256": "5c977168...", "modified_at": "2026-10-01T08:21:47.369941+00:00"},
  "eval":  {"path": "data/eval.txt",  "bytes": 2198,  "lines": 43,  "sha256": "67e28cc8...", "modified_at": "2026-10-01T08:21:47.369423+00:00"},
  "checks": {
    "train_larger_than_block_size": true,
    "eval_larger_than_block_size": true,
    "eval_distinct_lines": 43,
    "eval_lines_also_in_train": 0,
    "train_repeated_lines": 0
  },
  "warnings": [],
  "ready_to_train": true,
  "sources": [{"name": "eval.txt", "bytes": 2198}, {"name": "prompts.txt", "bytes": 1351}, "..."]
}
```

**Response fields**

| Field | Meaning |
| --- | --- |
| `block_size` | The context size the files are checked against. |
| `train`, `eval` | `path`, `bytes`, `lines`, `sha256` (changes when the file changes) and `modified_at`; `null` if the file is missing. |
| `checks.*_larger_than_block_size` | Each file must be larger than `block_size` bytes, or training is rejected. |
| `checks.eval_distinct_lines` | Different lines in the eval file. |
| `checks.eval_lines_also_in_train` | Eval lines that also occur in train. A high share makes the eval loss look better than the model really is (repeated answers like `I do not know.` are fine). |
| `checks.train_repeated_lines` | Lines repeated inside train (informational; repeating is sometimes intentional). |
| `warnings` | Plain-language problems: a missing file, eval under 1 KB (noisy loss), eval under 2% of train, or high overlap. |
| `ready_to_train` | `true` when both files exist and are larger than `block_size`. |
| `sources` | Up to 100 `.txt` and `.md` files in the data folder that `POST /data/split` can read. |

### POST /data/split

**Purpose.** Split one corpus file from the server's data folder into the config's train and eval files, with no
line in both. **Access:** training.

**Request body**

| Field | Type | Required | Default | Limits | Purpose |
| --- | --- | --- | --- | --- | --- |
| `source` | string | yes | — | a plain file name in the data folder; no folders; up to 100 characters | The corpus to split (see `sources` in `GET /data`). |
| `config` | string | no | `chit_cpu_learning` | existing preset | Decides where the files are written (its `train_file` and `eval_file`) and which `block_size` they must exceed. |
| `by` | `line` or `paragraph` | no | `line` | — | What counts as one item. `paragraph` keeps blocks separated by blank lines together, for example `User:` / `Chit:` pairs. |
| `eval_fraction` | number | no | 0.1 | above 0, below 0.5 | Share of items held out for eval. |
| `seed` | integer | no | 42 | 0–4294967295 | Fixes the shuffle, so the same input gives the same split. |
| `overwrite` | boolean | no | `false` | — | Required if the output files already exist. The old files are kept as `<name>.bak`. |
| `dry_run` | boolean | no | `false` | — | Report what would be written and write nothing. |

**Behavior.** Blank lines and exact duplicates (ignoring case and extra spaces) are removed, the rest is shuffled, and the
eval share is held out. Paraphrases are not detected as duplicates. The write is atomic, so training never reads half a file.
It is refused while a training job is active.

```bash
curl -X POST $BASE/data/split -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"source": "corpus.txt", "config": "chit_strong", "eval_fraction": 0.1, "dry_run": true}'
```
```json
{
  "source": "corpus.txt",
  "config": "chit_strong",
  "by": "line",
  "seed": 42,
  "duplicates_removed": 0,
  "train": {"path": "data/train.txt", "items": 218, "bytes": 10740},
  "eval": {"path": "data/eval.txt", "items": 24, "bytes": 1147},
  "would_overwrite": ["data/train.txt", "data/eval.txt"],
  "warnings": [],
  "written": false,
  "backups": []
}
```

**Response fields.** `train` and `eval` give the output `path`, number of `items` and `bytes`; `duplicates_removed` counts items
dropped; `would_overwrite` lists existing output files; `warnings` notes a small eval file; `written` is `true` only when files
were written; `backups` lists the `.bak` files that were made.

**Errors**

| Status | Meaning |
| --- | --- |
| `404` | The source file or config does not exist, or the source is outside the data folder. |
| `409` | Output files already exist and `overwrite` is `false` (`detail.existing` lists them), or a training job is active (`detail.active_job`). |
| `422` | The name is not a plain file name, the source is not UTF-8 text or is too large, there are fewer than 2 distinct items, or a resulting file would not be larger than `block_size` (nothing is written). |
| `500` | The files could not be written, for example the folder is read-only. |

**Recommended.** Always run with `"dry_run": true` first. Then send `overwrite: true` to apply. Use `by: "paragraph"` for Q&A data.

---

## 10. Shared objects

| Object | Where it appears | Description |
| --- | --- | --- |
| Job object | `/train*`, `/knowledge/train` | [The job object](#the-job-object) |
| Knowledge entry | `/knowledge*` | [The knowledge entry](#the-knowledge-entry) |
| Memory | `/memory*` | [POST /memory](#post-memory) response fields |
| Session | `/sessions*` | [Sessions](#5-sessions): `id`, `created_at`, `updated_at`, `turns`, and `messages` on the single-session call |

---

## 11. Errors

Errors are JSON with a `detail` field. The shape of `detail` depends on the cause.

| Status | When | `detail` |
| --- | --- | --- |
| `401` | Missing or wrong `X-API-Key` | `"invalid or missing API key"` |
| `403` | A training endpoint is called but the server has no API key configured | `"training API disabled: set CHIT_API_KEY ..."` |
| `404` | Unknown job, session, memory, knowledge entry, config or source | a short string such as `"session not found"` |
| `409` | A job is already running, or a file would be overwritten | an object, see below |
| `422` | The request is invalid | a list; see below |
| `429` | Inference queue is full or queue wait expires | object with `code: "inference_overloaded"`; includes `Retry-After: 1` |
| `500` | A server-side problem such as an invalid config file or an unwritable folder | a string |
| `503` | No model is loaded yet | a string such as `"checkpoint not found: checkpoints/latest.pt (train first)"` |

**`422` has two shapes.**

1. Field validation (the common case): a list of objects with `type`, `loc` (where the problem is), `msg` and `input`.
```json
{"detail": [
  {"type": "string_too_short", "loc": ["body", "prompt"], "msg": "String should have at least 1 character", "input": "", "ctx": {"min_length": 1}},
  {"type": "less_than_equal", "loc": ["body", "tokens"], "msg": "Input should be less than or equal to 500", "input": 9999, "ctx": {"le": 500}}
]}
```
2. Rules checked by the server (data files, model size, knowledge): a list of plain strings.
```json
{"detail": ["data.train_file must be larger than model.block_size (128 bytes)"]}
```

**`409` is an object.**
```json
{"detail": {"message": "training job 1adc741f15164a2e9f0d8c7c883c1103 is already active",
            "active_job": "1adc741f15164a2e9f0d8c7c883c1103"}}
```
```json
{"detail": {"message": "train/eval files already exist; send overwrite=true to replace them (the old files are kept as .bak)",
            "existing": ["data/train.txt", "data/eval.txt"]}}
```
(a job-state conflict from `cancel` is a plain string: `"job <id> already succeeded"`).

**Recommended client behavior.** On `409` from `POST /train`, read `detail.active_job` and watch that job instead of retrying.
On `503`, wait and call `GET /health`. On `422`, show `detail` to the user: it names the field or rule.

---

## 12. Recommended workflows

**A. Train the assistant preset and generate a response**

1. Put `train.txt` and `eval.txt` in the data folder (or `POST /data/split` from one `corpus.txt`).
2. `GET /data?config=chit_assistant_cpu` → `ready_to_train` is `true`.
3. `POST /train` with `{"config": "chit_assistant_cpu", "init": "scratch"}` → save `id`.
4. Poll `GET /train/{id}` until `state` is `succeeded` and `promoted` is `true`.
5. `POST /generate` with `{"prompt": "Explain a topic or make something", "temperature": 0}`.

**B. Teach new facts without editing files**

1. `POST /knowledge` with `text` items (several wordings per fact). Add `"remember": true` to make them available to assistant-mode `/generate` and `/chat` immediately.
2. `POST /knowledge/train` with `{"config": "chit_assistant_cpu", "repeat": 20}` and poll the job.
3. `GET /knowledge/stats` shows them move from `pending` to `trained`.

**C. A multi-turn chat client**

1. `POST /chat` with `{"message": "..."}` → keep `session_id`.
2. `POST /chat` with the same `session_id` for every later message.
3. `GET /sessions/{id}` to display the history, `DELETE /sessions/{id}` when done.

**D. Remember something now, without training**

`POST /memory` stores it at once; `GET /memory/search` finds it; `/chat` includes matching memories in the prompt.

**Python example (flow A)**

```python
import os, time, requests

BASE = "https://api.chitt.online"
H = {"X-API-Key": os.environ["CHIT_API_KEY"]}

job = requests.post(f"{BASE}/train", headers=H, json={"config": "chit_assistant_cpu", "init": "scratch"}).json()
while True:
    j = requests.get(f"{BASE}/train/{job['id']}", headers=H).json()
    print(j["state"], j["step"], "/", j["max_steps"])
    if j["state"] in ("succeeded", "failed", "cancelled"):
        break
    time.sleep(3)

r = requests.post(f"{BASE}/generate", headers=H,
                  json={"prompt": "Explain how memory helps Chit.", "tokens": 60, "temperature": 0})
print(r.json()["text"])
```

---

## 13. Server settings

Set as environment variables on the server (not request parameters).

| Variable | Default | Effect |
| --- | --- | --- |
| `CHIT_API_KEY` | unset | The API key. When set, every endpoint except `/health` needs it. Training endpoints are disabled without it. |
| `CHIT_ALLOW_UNAUTHENTICATED_TRAINING` | unset | `1` opens training endpoints without a key. Local development only. |
| `CHIT_CHECKPOINT` | `checkpoints/latest.pt` | The model file that is served. |
| `CHIT_CONFIG_DIR` | `configs` | Where training presets are read from. |
| `CHIT_JOBS_DIR` | `checkpoints/jobs` | Where each job's files are written. |
| `CHIT_MAX_TRAIN_STEPS` | `100000` | Upper limit for `training.max_steps`. |
| `CHIT_MAX_DATASET_MB` | `200` | Upper limit for a generated dataset or a split source. |
| `CHIT_MEMORY_PATH` | `data/memory.json` | Legacy memory JSON import and recovery source. |
| `CHIT_MEMORY_DB` | `data/memory.db` | Canonical SQLite memory database. |
| `CHIT_INFERENCE_QUEUE_SIZE` | `32` | Maximum waiting inference requests. |
| `CHIT_INFERENCE_QUEUE_TIMEOUT` | `30` seconds | Maximum time waiting before inference starts. |
| `CHIT_EMBEDDING_MODEL_PATH` | unset | Local Sentence-Transformers model directory; optional hybrid retrieval. |
| `CHIT_EMBEDDING_MODEL_VERSION` | asset fingerprint | Stable ID for vectors from this embedding model. |
| `CHIT_EMBEDDING_SEMANTIC_THRESHOLD` | unset | Optional threshold calibrated using retrieval evaluation. |
| `CHIT_KNOWLEDGE_DB` | `data/knowledge.db` | Knowledge database. |
| `CHIT_SESSIONS_DB` | `data/sessions.db` | Session database. |
| `CHIT_SESSION_TTL_DAYS` | `30` | Idle sessions older than this are deleted at start-up. `0` keeps them forever. |
| `CHIT_MAX_SESSION_TURNS` | `200` | Messages kept per session. |
| `CHIT_HISTORY_TURNS` | `8` | Most recent session messages offered to the model as context. |
| `CHIT_DATA_DIR` | `data` | Folder that `POST /data/split` reads corpus files from. |
