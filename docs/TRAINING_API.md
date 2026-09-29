# Training API

The Chit API can train a new model in the background and, when training
succeeds, start serving it without a restart.

```bash
export CHIT_API_KEY=change-me
uvicorn pranav.chit.api:app --host 127.0.0.1 --port 8000   # single worker
```

Training endpoints always need authentication. If `CHIT_API_KEY` is not set they
return `403`, unless `CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1` is set (local development only).

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/train/configs` | Config names that can be trained |
| `POST` | `/train` | Start a job. `202` with the job; `409` if a job is already active |
| `GET` | `/train` | Recent jobs, newest first |
| `GET` | `/train/{id}` | Job status, progress and loss history |
| `POST` | `/train/{id}/cancel` | Stop a queued or running job (`409` if it already finished) |

`GET /health` also reports `training_job`, the id of the active job, or `null`.

## Starting a job

Every field is optional. Values not given come from the named config file
in `configs/`.

```bash
curl -X POST localhost:8000/train \
  -H "X-API-Key: $CHIT_API_KEY" -H "Content-Type: application/json" \
  -d '{
        "config": "chit_cpu_learning",
        "seed": 7,
        "device": "cpu",
        "model":    {"block_size": 64, "n_layer": 2, "n_head": 2, "n_embd": 64, "dropout": 0.0},
        "training": {"max_steps": 500, "learning_rate": 0.0005, "batch_size": 8},
        "promote": true
      }'
```

Poll `GET /train/{id}` (the `Location` header) until `state` is `succeeded`,
`failed` or `cancelled`. The response includes `step`, `progress` (0–1), `latest`
and `history` (train/eval loss at each evaluation), `error`, `promoted` and
`promotion_error`.

Requests are validated before a job starts. Unknown fields, out-of-range
values, `n_embd` not divisible by `n_head`, `max_steps` above
`CHIT_MAX_TRAIN_STEPS`, unavailable CUDA, and data files smaller than
`block_size` all return `422` with a list of problems.

Training data comes from the config file on the server. Clients cannot
point training at arbitrary files.

## How it behaves

- **One job at a time.** Training runs in a background thread in the API process.
- **Served model is protected.** Each job writes to `checkpoints/jobs/<id>/`. Only
  a successful job with `promote: true` replaces `CHIT_CHECKPOINT`. The new
  checkpoint is loaded and validated first, then copied into place atomically and
  swapped in between requests. Failed or cancelled jobs never touch the served model.
- **Cancellation is cooperative.** The job stops before its next training step.
- **Audit trail.** `checkpoints/jobs/<id>/job.json` records each job's final state.
  The in-memory list keeps the last 50 jobs. Job directories are never deleted
  automatically, so set up retention for your storage.
- **Restarts.** A job running when the server stops is cancelled on graceful
  shutdown and is not resumed.

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `CHIT_API_KEY` | – | Required for training (sent as `X-API-Key`) |
| `CHIT_CHECKPOINT` | `checkpoints/latest.pt` | Served model; target of promotion |
| `CHIT_CONFIG_DIR` | `configs` | Trainable configs |
| `CHIT_JOBS_DIR` | `checkpoints/jobs` | Per-job output |
| `CHIT_MAX_TRAIN_STEPS` | `100000` | Upper bound for `training.max_steps` |
| `CHIT_ALLOW_UNAUTHENTICATED_TRAINING` | – | `1` = allow training without a key (dev only) |

## Production notes

- Run **one worker**. Model state and the job registry live in the process.
- Training shares CPU/GPU with inference, so `/generate` slows down while a job
  runs. For heavy training, run the API on a GPU host or train via the CLI on a
  separate machine and deploy the checkpoint.
- Put the API behind TLS and a reverse proxy. Use a long random `CHIT_API_KEY`.
