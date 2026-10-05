# Training API

The Chit API trains candidates in the background. By default, candidates are
not served until they pass the reviewed promotion workflow. `force_promote: true`
is an explicit override that installs a successful candidate immediately.

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

Every field is optional. The default config remains `chit_cpu_learning`; pass `chit_assistant_cpu` for the new assistant corpus. Other
values come from the selected config file in `configs/`.

```bash
curl -X POST localhost:8000/train \
  -H "X-API-Key: $CHIT_API_KEY" -H "Content-Type: application/json" \
  -d '{
        "config": "chit_assistant_cpu",
        "seed": 7,
        "device": "cpu",
        "init": "scratch",
        "model":    {"block_size": 512, "n_layer": 4, "n_head": 4, "n_embd": 128, "dropout": 0.05},
        "training": {"max_steps": 500, "learning_rate": 0.0005, "batch_size": 8},
        "promote": false,
        "force_promote": false
      }'
```

`init` chooses the starting weights: `scratch` (default, random init),
`current` (fine-tune the served model; its architecture is used and
architecture overrides are rejected) or `auto` (`current` when possible,
otherwise `scratch`). When fine-tuning, the served checkpoint is copied to
`checkpoints/jobs/<id>/init.pt` first, so the run is reproducible.

`training` also accepts `warmup_steps`, `lr_schedule` (`constant` or `cosine`)
and `min_lr_ratio` (the cosine floor as a fraction of `learning_rate`).

Set `force_promote: true` in the `POST /train` body to install the candidate as
the served checkpoint when training succeeds. This explicitly bypasses the
Golden Set reviewer and evaluation gates. The previous checkpoint is archived
and a forced-promotion decision is recorded in `checkpoints/champion.json`.
This does not bypass checkpoint loading or tokenizer-family compatibility
checks. If you also send `promote: true`, it is accepted only when
`force_promote: true`; otherwise the API returns `422` with that explanation.

```json
{"config":"chit_assistant_cpu","init":"auto","promote":true,"force_promote":true}
```

To train on knowledge you have taught Chit, use `POST /knowledge/train`
instead; see [KNOWLEDGE_API.md](KNOWLEDGE_API.md).

Training presets may optionally use source-aware streams in `data.sources`:

```json
"data": {
  "train_file": "data/train.txt",
  "eval_file": "data/eval.txt",
  "sources": [
    {"path": "data/english_foundation/structural.txt", "weight": 0.3},
    {"path": "data/english_foundation/conversation.txt", "weight": 0.3},
    {"path": "data/english_foundation/project_facts.txt", "weight": 0.1}
  ]
}
```

Weights are relative and normalized. Each batch row chooses a source, then a random token window
within that source; this prevents source proportions from being determined only by concatenated file
length and prevents a window from crossing file boundaries. The legacy `data.train_file` path remains
active when `sources` is omitted. Candidate checkpoint metadata records configured weights and sampled
window counts. The local `chit_english_foundation` preset demonstrates the feature and uses the
existing held-out `data/eval.txt` without overwriting corpus files.

For candidate response generation and review of the English capability suite, see [EVALUATION.md](EVALUATION.md).

Poll `GET /train/{id}` (the `Location` header) until `state` is `succeeded`,
`failed` or `cancelled`. The response includes `step`, `progress` (0–1), `latest`
and `history` (train/eval loss at each evaluation), `error`, `promoted` and
`promotion_error`, plus `init_checkpoint` and `metadata`.

Requests are validated before a job starts. Unknown fields, out-of-range
values, `n_embd` not divisible by `n_head`, `max_steps` above
`CHIT_MAX_TRAIN_STEPS`, unavailable CUDA, and data files smaller than
`block_size` all return `422` with a list of problems.

Training data comes from the config file on the server. Clients cannot
point training at arbitrary files.

During API training, every saved checkpoint is automatically evaluated on the
held-out text file. Job status exposes an `evaluations` list with report paths,
perplexity, and bits/byte, plus `final_evaluation`. Golden response generation
is intentionally a separate bounded step because it runs the model on all 50
cases and still requires human review.

## Candidate evaluation and promotion

Training jobs always write candidates under `checkpoints/jobs/<id>/`. By
default, they do not replace the served model. `promote: true` without
`force_promote: true` is rejected. The force option bypasses the review gates;
use it only when intentionally accepting an unreviewed candidate. Otherwise,
evaluate the candidate and current
champion with the same `data/eval.txt` and `data/golden_set.json`; have two
reviewers independently rate every golden response using the rubric in
`docs/GOLDEN_SET.md`. The ratings file must bind to the exact checkpoint and
golden-set SHA-256 values reported by `eval_runner.py`.

Create one reviewed ratings file per checkpoint, using the hashes from that
checkpoint's evaluation output:

```json
{
  "golden_set_sha256": "<hash from report>",
  "checkpoint_sha256": "<hash from report>",
  "ratings": [
    {"id": "G001", "passed": true, "critical_failure": false,
     "reviewers": ["reviewer-a", "reviewer-b"]}
  ]
}
```

Include each case ID exactly once. `passed` is the adjudicated decision after
independent review; set `critical_failure` if the response triggers any critical
rubric failure.

```bash
python -m pranav.chit.tools.eval_runner --checkpoint checkpoints/jobs/<job-id>/latest.pt \
  --eval-file data/eval.txt --golden-set data/golden_set.json \
  --max-new-tokens 64 --output checkpoints/jobs/<job-id>/responses.json
python -m pranav.chit.tools.eval_runner --checkpoint checkpoints/latest.pt \
  --eval-file data/eval.txt --golden-set data/golden_set.json \
  --output checkpoints/evaluations/champion.json
python -m pranav.chit.tools.promote_candidate \
  --candidate checkpoints/jobs/<job-id>/latest.pt \
  --candidate-eval checkpoints/jobs/<job-id>/evaluation.json \
  --champion-eval checkpoints/evaluations/champion.json
```

Reviewers score every candidate response and record the checkpoint and Golden
Set hashes from its response report. Then repeat the candidate evaluation with
`--max-new-tokens 64 --ratings checkpoints/jobs/<job-id>/ratings.json` and save
the result as `evaluation.json`; this binds ratings to the generated report.
Promotion requires fully scorable passing Golden Set gates for the candidate,
no more than 5% held-out bits/byte regression, matching tokenizer family, and
matching evaluation data hashes. When a valid passing champion report exists,
the candidate must also exceed it by a paired bootstrap 95% lower bound above
a 2 percentage-point behavior lift. For the first eligible champion only, a
context-ineligible incumbent with zero scorable cases may be replaced by a
candidate that passes the absolute two-reviewer Golden Set gate; this bootstrap
path is recorded in the manifest. The promoted
and previous checkpoints are archived under `checkpoints/champions/` and
tracked in `checkpoints/champion.json`. Restart the service after CLI promotion
so it loads the newly installed champion. Keep the manifest and archive
together for rollback. Restore a retained checkpoint with
`python -m pranav.chit.tools.rollback_champion --to-sha256 <checkpoint-sha256>`;
restart the service after rollback as well.

## How it behaves

- **One job at a time.** Training runs in a background thread in the API process.
- **Served model is protected.** Each job writes to `checkpoints/jobs/<id>/`.
  Failed, cancelled, and successful jobs leave `CHIT_CHECKPOINT` unchanged;
  evaluation-backed promotion is an explicit operator action described above.
- **Cancellation is cooperative.** The job stops before its next training step.
- **Audit trail.** `checkpoints/jobs/<id>/job.json` records each job's final state.
  The in-memory list keeps the last 50 jobs. Job directories are never deleted
  automatically, so set up retention for your storage.
- **Restarts.** A job running when the server stops is cancelled on graceful
  shutdown and is not resumed. Job history is reloaded from `job.json` files on
  start-up; a job that was still active when the process died is shown as
  `failed` with an `interrupted` error.

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `CHIT_API_KEY` | – | Required for training (sent as `X-API-Key`) |
| `CHIT_CHECKPOINT` | `checkpoints/latest.pt` | Served model; target of promotion |
| `CHIT_CONFIG_DIR` | `configs` | Trainable configs |
| `CHIT_JOBS_DIR` | `checkpoints/jobs` | Per-job output |
| `CHIT_MAX_TRAIN_STEPS` | `100000` | Upper bound for `training.max_steps` |
| `CHIT_ALLOW_UNAUTHENTICATED_TRAINING` | – | `1` = allow training and knowledge without a key (dev only) |

## Production notes

- Run **one worker**. Model state and the job registry live in the process.
- Training shares CPU/GPU with inference, so `/generate` slows down while a job
  runs. For heavy training, run the API on a GPU host or train via the CLI on a
  separate machine and deploy the checkpoint.
- Put the API behind TLS and a reverse proxy. Use a long random `CHIT_API_KEY`.
