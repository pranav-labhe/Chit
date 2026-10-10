# Knowledge API: teaching Chit

Teaching is two steps, on purpose:

1. **Teach** – `POST /knowledge` stores what you want Chit to learn. Nothing about
   the model changes yet. Entries start as `pending`.
2. **Train when you say so** – `POST /knowledge/train` builds a dataset from the
   stored knowledge and starts a background training job. When the job succeeds
   and is evaluated. Training creates a candidate; entries remain pending until
   the candidate passes reviewed evaluation and is promoted through the
   operator workflow documented in `TRAINING_API.md`.

This follows Chit's own design rule: an experience is stored first, and the
weights change only when a deliberate training run is started.

All knowledge endpoints use the same auth as the training API (`X-API-Key`,
see [TRAINING_API.md](TRAINING_API.md)).

## Kinds

| `kind` | Fields | Rendered into training text as |
| --- | --- | --- |
| `text` | `text` | the text itself |
| `qa` | `question`, `answer` | `User: <question>\nChit: <answer>` (the same format `/chat` prompts with) |
| `reasoning` | `input`, `reasoning`, `answer` | `Input: …\nReasoning: …\nAnswer: …` |

Every item may also carry `tags` (letters, digits, `_ . : / -`), `source` (for
audit) and `remember`. With `"remember": true` the item is also written to
memory, so `/chat` can recall it immediately, before any training has happened.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/knowledge` | Add 1–500 items atomically (all or none). `201` |
| `GET` | `/knowledge` | List, newest first. Filters: `status`, `kind`, `tag` (repeatable), `limit`, `offset` |
| `GET` | `/knowledge/stats` | Counts by status and kind |
| `GET` | `/knowledge/{id}` | One entry |
| `DELETE` | `/knowledge/{id}` | Remove from future training. `204` |
| `POST` | `/knowledge/train` | Train on stored knowledge now. `202` with the job |

Identical content (ignoring surrounding and repeated whitespace) is stored once;
re-teaching it returns the existing entry with `"created": false`.

## Teach

```bash
curl -X POST localhost:8000/knowledge -H "X-API-Key: $CHIT_API_KEY" -H "Content-Type: application/json" -d '{
  "items": [
    {"kind": "qa", "question": "Who is building Chit?", "answer": "Pranav is building Chit.", "tags": ["identity"]},
    {"kind": "text", "text": "Chit stores new experiences as memory first.", "remember": true},
    {"kind": "reasoning", "input": "Is it raining? No data.", "reasoning": "No information is available.", "answer": "I do not know."}
  ]}'
```

Bulk-load a JSONL file offline (same item shape, one per line):

```bash
python -m pranav.chit.tools.teach data/reasoning.jsonl --kind reasoning --tag seed
```

## Train on it

```bash
curl -X POST localhost:8000/knowledge/train -H "X-API-Key: $CHIT_API_KEY" \
  -H "Content-Type: application/json" -d '{"training": {"max_steps": 500}}'
```

Then poll `GET /train/{id}` exactly as for any training job. All `/train`
fields are accepted (`config`, `seed`, `device`, `model`, `training`,
`promote`), plus:

| Field | Default | |
| --- | --- | --- |
| `init` | `auto` | `current` fine-tunes the served model; `scratch` starts from random weights; `auto` uses `current` when a compatible model is served, else `scratch` |
| `select` | `all` | `all` trains on every entry; `pending` only on entries not yet trained |
| `tags` | `[]` | only entries that have all of these tags |
| `include_base` | `true` | mix in the config's `train_file` corpus |
| `repeat` | `3` | times the knowledge appears in the dataset (1–100) |

**Why `select: all` is the default.** Fine-tuning only on new
facts tends to forget older ones. Retraining on everything (plus the base
corpus) avoids that; use `pending` for quick top-ups.

**Fine-tuning keeps the architecture.** With `init: current`/`auto`, the served
model's architecture is used and the config's `model` section is ignored.
`current` with architecture overrides returns `422`; `auto` falls back to scratch.

**`repeat`.** Training samples random windows, so a few facts in a large base
corpus are rarely seen. Raising `repeat` weights knowledge more heavily.

## Traceability

Each knowledge job writes, under `checkpoints/jobs/<id>/`:

- `dataset/train.txt` – the exact training text
- `dataset/manifest.json` – entry ids, sizes and the dataset's SHA-256
- `init.pt` – a copy of the starting weights, when fine-tuning

The job's `metadata.knowledge` and every checkpoint's `metadata` record the
dataset hash, so any served model can be traced back to what it was taught.

## Status rules

- An entry becomes `trained` only when a job that included it **succeeded and
  was promoted**. With `promote: false` it stays `pending`.
- Deleting a `trained` entry stops it being used in future runs, but the served
  model keeps what it learned until it is retrained with `init: scratch`.

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `CHIT_KNOWLEDGE_DB` | `data/knowledge.db` | SQLite knowledge database |
| `CHIT_MAX_DATASET_MB` | `200` | Upper bound for a generated training set |
| `CHIT_MEMORY_PATH` | `data/memory.json` | Memory file (used by `remember`) |

Back up `data/knowledge.db` like any database: it is the source of truth for
everything Chit has been taught.
