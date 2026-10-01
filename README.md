# Chit — चित् — Pranav's Atmini Brain

**चित् (Chit) is the neural brain of Atmini.** It is a byte-level Transformer trained from scratch,
with its own weights, memory, learning path, and conversation context. Its API supports communication,
problem solving, storing experience, teaching knowledge, and training.

> **Read this first — what Chit is and is not.** Chit is Atmini's from-scratch cognitive core.
> `/generate` and `/chat` format messages for a context-aware Chit response, while `/generate` can still
> do raw continuation with `mode: "continue"`. It learns from reviewed data, memory, and dialogue;
> its context window and available training compute shape how much it can learn and use at once.

---

## Contents
1. [Quick start](#1-quick-start)
2. [What should I use for what?](#2-what-should-i-use-for-what)
3. [Recommended workflow: train on your own text](#3-recommended-workflow-train-on-your-own-text)
4. [Run the API server](#4-run-the-api-server)
5. [API reference and examples](#5-api-reference-and-examples)
6. [Settings (environment variables)](#6-settings-environment-variables)
7. [Files and folders](#7-files-and-folders)
8. [Troubleshooting](#8-troubleshooting)
9. [Tests](#9-tests)

---

## 1. Quick start

You need **Python 3.10 or newer**. Run everything from the repository root (the `Chit` folder).

```bash
# 1. Create an isolated environment (recommended)
python -m venv .venv
source .venv/bin/activate            # Linux / macOS / Git Bash
# .venv\Scripts\Activate.ps1         # Windows PowerShell
# .venv\Scripts\activate.bat         # Windows cmd

# 2. Install (PyTorch is a large download; this can take a few minutes)
pip install -r requirements.txt

# 3. Train Chit's CPU preset on the curated data
python -m pranav.chit.tools.train --config configs/chit_assistant_cpu.json

# 4. Start both the API and browser console from the repository root
python -m pranav.chit.ui
```

Training prints `step=... train=... eval=...` lines and writes `checkpoints/latest.pt`.
The CPU preset trains Chit's current architecture within the available resources; lower loss does not by itself prove
that it understands new requests or can solve unfamiliar problems well. With the server running, try `POST /generate` using the examples
below or visit `http://127.0.0.1:8000/docs`. The console is at `http://127.0.0.1:8001/`; enter the configured
`CHIT_API_KEY` once to unlock it.

> **Why `chit_train_txt.json` and not `chit_cpu_learning.json`?**
> `chit_cpu_learning.json` runs only 300 steps at a low learning rate, which is too little to learn
> even a small text: in testing it produced nonsense. `chit_train_txt.json` (2500 steps, learning
> rate 0.003) reproduced the sample sentences correctly.

`try_chit.py` and `pranav.chit.tools.generate` are raw continuation tools. For request-oriented
assistant behavior, use the API endpoints (`/generate` or `/chat`). Both tools sample with randomness
by default, so small mistakes are normal. For greedy raw continuation:

```bash
python -m pranav.chit.tools.generate --prompt "I am" --tokens 40 --temperature 0
```

---

## 2. What should I use for what?

| I want to… | Use | Notes |
| --- | --- | --- |
| Ask Chit to understand, answer, or help solve something | `POST /generate` or `POST /chat` | Both format requests for Chit's response; `/chat` adds session history and memory. |
| Continue text literally | `POST /generate` with `mode: "continue"` | Sends the prompt directly to the model without the assistant wrapper. |
| Give Chit a fact **right now**, without retraining | `POST /memory` | Stored outside the model; recalled by assistant-mode `/generate` and `/chat`. Never changes the weights. |
| Teach Chit new material and train on it | `POST /knowledge`, then `POST /knowledge/train` | Knowledge is queued, then baked into the weights when you train. |
| Retrain from my own text file | Edit `data/train.txt`, then `POST /train` or the CLI | See [section 3](#3-recommended-workflow-train-on-your-own-text). |
| Prepare train/eval from one big text file (for example a mounted folder) | `POST /data/split`, then check with `GET /data` | Holds out an eval set with no overlap. Docs: `docs/DATA_API.md`. |
| Explore the API in a browser | `http://localhost:8000/docs` | Interactive; works the same on every operating system. |
| Open the Chit browser console | `http://localhost:8001/` | Chat, generation, and controls for every documented API route. |
| Connect Atmini | `POST /generate` or `POST /chat` with the `X-API-Key` header | Keep the server on `127.0.0.1`. |

**Memory vs knowledge vs weights**

| | Stored in | Changes the model? | Available |
| --- | --- | --- | --- |
| **Memory** (`/memory`) | `data/memory.json` | No | immediately in assistant-mode `/generate` and `/chat` |
| **Knowledge** (`/knowledge`) | `data/knowledge.db` | Only after `/knowledge/train` | after training |
| **Weights** | `checkpoints/latest.pt` | — | what the model was trained on |

**`/generate` or `/chat`?**
Use `/generate` for a single request or raw text continuation. Use `/chat` when the exchange needs
conversation history and memory. Both assistant modes use the same `Task: chat` / `User:` / `Chit:`
format and benefit from training examples written in that format.

---

## 3. Recommended workflow: train on your own text

0. **Big corpus?** Put it in the data folder as `corpus.txt` and run `POST /data/split` (or
   `python -m pranav.chit.tools.split corpus.txt`) to create both files with no overlap. Then `GET /data` shows `ready_to_train`.
1. **Write your text in `data/train.txt`** — one fact or sentence per line. Vary the wording, and
   repeat the important lines. Put a few *different* lines in `data/eval.txt`.
   The eval file must be **larger than `model.block_size` bytes** (512 for the assistant preset), or the API
   rejects the job with `422`.
2. **Train** — either way (the API accepts a named preset; pass `chit_assistant_cpu` to use the assistant corpus):
   ```bash
   python -m pranav.chit.tools.train --config configs/chit_assistant_cpu.json
   ```
   or, with the server running, `POST /train` (see [section 5](#5-api-reference-and-examples)).
   The API promotes the finished model automatically, with no restart.
3. **Generate** from a request:
   ```json
   {"prompt": "Explain how memory helps Chit.", "tokens": 60, "temperature": 0}
   ```
4. **Check the loss.** A training loss far below the eval loss (for example 0.07 vs 0.9) means the
   model is memorising your text. That is expected at this size. More varied text is the biggest
   improvement.

**Teaching requests:** add varied `Task: chat` / `User:` / `Chit:` examples to `data/train.txt` (or
teach Q&A with `POST /knowledge` and train through `/knowledge/train`). Cover multiple tasks and
wordings; repeated examples alone encourage memorization.

```
User: What is Chit?
Chit: Chit is the model inside Atmini.
```

In `/generate`, send the request as `prompt`. In `/chat`, send it as `message` and keep the returned
`session_id` to continue the conversation.

**Settings worth changing** (in a file in `configs/`, or per request under `"training"` / `"model"`):

| Setting | Effect |
| --- | --- |
| `configs/chit_assistant_cpu.json` | 512-byte context and Chit's current CPU training preset with conversation and problem-solving examples. |
| `training.max_steps` | Longer training. 300 is too few; 2500–3000 worked on the sample text. |
| `training.learning_rate` | `0.003` worked for the earlier byte-model preset; `0.0005` learned too slowly there. |
| `model.block_size` | Context length in bytes. Larger needs a larger `data/eval.txt`. |
| `model.n_layer`, `model.n_embd` | Bigger model, slower training. `configs/chit_tiny.json` is a larger preset. |
| `device` | `cpu`, `cuda` or `auto`. |

---

## 4. Run the API server

```bash
# Linux / macOS / Git Bash
export CHIT_API_KEY="$(python -c 'import secrets; print(secrets.token_hex(24))')"
python -m pranav.chit.ui
```

```powershell
# Windows PowerShell
$env:CHIT_API_KEY = python -c "import secrets; print(secrets.token_hex(24))"
python -m pranav.chit.ui
```

- Open **http://localhost:8000/docs** for an interactive page where you can try every endpoint.
- Open **http://localhost:8001/** for the Chit console. It asks for the same API key once per browser session.
- Use **one worker** (the default). The loaded model and the training-job list live in the process.
- Keep `--host 127.0.0.1` unless you have set `CHIT_API_KEY` and put HTTPS in front of the server.
- If no model is trained yet, the server still starts: `GET /health` reports `no_model` and
  `/generate` returns `503` until a model is trained.
- Local development without a key: set `CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1` to allow the
  training and knowledge endpoints without `CHIT_API_KEY`. Never do this on a shared machine.

**Authentication.** When `CHIT_API_KEY` is set, every endpoint except `/health` needs the header
`X-API-Key: <your key>`.

---

## 5. API reference and examples

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Server status, whether a model is loaded, active training job (no key needed) |
| GET | `/model` | Loaded model details |
| GET | `/data` | Check the train/eval files on the server: size, hash, overlap, `ready_to_train` |
| POST | `/data/split` | Split a corpus file from the data folder into train and eval (`overwrite`, `dry_run`) |
| POST | `/generate` | Respond to a request; `mode: "continue"` opts into raw continuation. Supports `prompt`, `tokens`, `temperature`, `top_k`, `stop` |
| POST | `/chat` | Chat template + recalled memory: `message`, `task` |
| POST | `/memory` | Store a fact (`content`, optional `tags`, `importance`) |
| GET | `/memory/search?q=…` | Search memory |
| DELETE | `/memory/{id}` | Delete a memory (the `id` is the UUID returned when you added it) |
| POST | `/knowledge` | Teach items: `text`, `qa` or `reasoning` |
| GET | `/knowledge`, `/knowledge/stats`, `/knowledge/{id}` | List, count, view |
| DELETE | `/knowledge/{id}` | Remove from future training |
| POST | `/knowledge/train` | Train on the stored knowledge (`repeat`, `init`, `training`, …) |
| GET | `/train/configs` | Config names available for training |
| POST | `/train` | Start a background training job (`202`; `409` if one is already running) |
| GET | `/train`, `/train/{id}` | List jobs; status, progress, loss history |
| POST | `/train/{id}/cancel` | Stop a running job |

The `/train*` and `/knowledge*` endpoints also need the key, and return `403` if `CHIT_API_KEY` is
not set (unless the dev flag above is on). Full details: `docs/TRAINING_API.md`, `docs/KNOWLEDGE_API.md`.

### Examples

The examples read your key from `CHIT_API_KEY`.

**Generate** — send a request for a response (or use `mode: "continue"` for raw continuation):

```bash
# Linux / macOS / Git Bash
curl -X POST http://localhost:8000/generate \
  -H "X-API-Key: $CHIT_API_KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "Explain how memory helps Chit.", "tokens": 60, "temperature": 0}'
```
```powershell
# Windows PowerShell
$h = @{ "X-API-Key" = $env:CHIT_API_KEY }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/generate -Headers $h `
  -ContentType "application/json" `
  -Body '{"prompt": "Explain how memory helps Chit.", "tokens": 60, "temperature": 0}'
```

**Train, wait, then generate** (Python; `pip install requests` first):

```python
import os, time, requests

BASE = "http://localhost:8000"
H = {"X-API-Key": os.environ["CHIT_API_KEY"]}

job = requests.post(f"{BASE}/train", headers=H,
                    json={"config": "chit_assistant_cpu", "init": "scratch"}).json()
while True:
    j = requests.get(f"{BASE}/train/{job['id']}", headers=H).json()
    print(j["state"], j["step"], "/", j["max_steps"])
    if j["state"] in ("succeeded", "failed", "cancelled"):
        break
    time.sleep(2)

print(requests.post(f"{BASE}/generate", headers=H, json={
    "prompt": "Explain how memory helps Chit.", "tokens": 60, "temperature": 0}).json()["text"])
```

**Store and search a memory:**

```bash
curl -X POST http://localhost:8000/memory -H "X-API-Key: $CHIT_API_KEY" \
  -H "Content-Type: application/json" -d '{"content": "Pranav lives in India."}'
curl -H "X-API-Key: $CHIT_API_KEY" "http://localhost:8000/memory/search?q=Pranav"
```

**Teach Q&A, then train on it:**

```bash
curl -X POST http://localhost:8000/knowledge -H "X-API-Key: $CHIT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"kind": "qa", "question": "Who created Chit?", "answer": "Pranav created Chit."}]}'

curl -X POST http://localhost:8000/knowledge/train -H "X-API-Key: $CHIT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"config": "chit_assistant_cpu", "repeat": 30}'
```

Then ask with `POST /generate`, prompt `"Who created Chit?"`, `temperature` 0.

> On Windows, PowerShell's `curl` is not real curl. Use `Invoke-RestMethod` as above, `curl.exe`
> with the JSON saved in a file (`-d "@body.json"`), or the `/docs` page.

---

## 6. Settings (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `CHIT_API_KEY` | *(unset)* | Key for the `X-API-Key` header. When set, every endpoint except `/health` requires it. Training and knowledge endpoints are disabled without it. |
| `CHIT_ALLOW_UNAUTHENTICATED_TRAINING` | *(unset)* | `1` allows training and knowledge without a key. **Local development only.** |
| `CHIT_CHECKPOINT` | `checkpoints/latest.pt` | Model file that is served |
| `CHIT_CONFIG_DIR` | `configs` | Where training configs are read from |
| `CHIT_JOBS_DIR` | `checkpoints/jobs` | Output folder for background training jobs |
| `CHIT_MAX_TRAIN_STEPS` | `100000` | Upper limit on `training.max_steps` |
| `CHIT_MAX_DATASET_MB` | `200` | Upper limit on a generated training set |
| `CHIT_MEMORY_PATH` | `data/memory.json` | Memory file |
| `CHIT_DATA_DIR` | `data` | Folder `POST /data/split` reads corpus files from |
| `CHIT_KNOWLEDGE_DB` | `data/knowledge.db` | Knowledge database |

Setting a variable: `export NAME=value` (Linux/macOS/Git Bash), `$env:NAME = "value"` (PowerShell),
`set NAME=value` (cmd). It lasts for that terminal window.

---

## 7. Files and folders

| Path | What it is |
| --- | --- |
| `data/train.txt`, `data/eval.txt` | Training and held-out evaluation examples |
| `data/prompts.txt`, `data/CORPUS.md` | Open-ended review prompts and corpus provenance/use notes |
| `data/memory.json`, `data/memory_seed.json` | External memory and the facts it starts with |
| `data/knowledge.db` | Taught knowledge (SQLite) |
| `configs/*.json` | Training presets |
| `checkpoints/latest.pt` | The trained model that is served |
| `checkpoints/jobs/<id>/` | One folder per API training job (weights, dataset, `job.json`) |
| `pranav/chit/` | Source: `model.py`, `training.py`, `api.py`, `jobs.py`, `knowledge.py`, `memory.py`, … |
| `docs/` | Architecture, roadmap, training and knowledge API guides |

Trained weights and your own data are local files. Add them to `.gitignore` so they are not
committed by accident:

```
checkpoints/
data/memory.json
data/knowledge.db*
```

---

## 8. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Output is gibberish | The current from-scratch weights may not have learned that request pattern yet. Use `temperature: 0`, add reviewed request examples to `train.txt`, preserve held-out examples in `eval.txt`, and train with `chit_assistant_cpu.json`. |
| `ModuleNotFoundError: pranav` | Run commands from the repository root. |
| `401` | Missing or wrong `X-API-Key` header. |
| `403` on `/train` or `/knowledge` | `CHIT_API_KEY` is not set on the server (or set the dev flag). |
| `503` on `/generate` | No model yet: train first. `GET /health` shows the reason. |
| `409` on `/train` | A job is already running; wait for it or `POST /train/{id}/cancel`. |
| `422 … must be larger than model.block_size` | Add text to `data/eval.txt` (and `train.txt`), or lower `model.block_size`. |
| `CUDA requested but unavailable` | Set `"device": "cpu"` (or `"auto"`). |
| Training is slow while the server runs | Training and serving share the same CPU. |

---

## 9. Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```
