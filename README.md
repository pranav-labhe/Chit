# Chit — चित् — Pranav's Atmini Brain

Chit is a from-scratch neural-model layer for Atmini.

Milestones covered by this scaffold:
1. neural fundamentals
2. tiny language model
3. tiny Transformer
4. own tokenizer + weights
5. Chit training data
6. external memory
7. reasoning examples
8. Atmini integration boundary
9. CPU/GPU-ready training
10. checkpoint/export foundation for Chit v1

## Quick start

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements-dev.txt     # requirements.txt for runtime only
python -m pranav.chit.tools.train --config configs/chit_cpu_learning.json
python -m pranav.chit.tools.generate --checkpoint checkpoints/latest.pt --prompt "Atmini"
python -m pytest
```

The package is `pranav.chit` (under the `pranav` namespace) and the project is Chit.

## Training over HTTP

The API can also train and hot-swap the model. See [docs/TRAINING_API.md](docs/TRAINING_API.md).

```bash
export CHIT_API_KEY=change-me
uvicorn pranav.chit.api:app --port 8000
curl -X POST localhost:8000/train -H "X-API-Key: $CHIT_API_KEY" \
  -H "Content-Type: application/json" -d '{"training": {"max_steps": 300}}'
```

## Teaching Chit

Store knowledge now; train on it when you decide. See [docs/KNOWLEDGE_API.md](docs/KNOWLEDGE_API.md).

```bash
curl -X POST localhost:8000/knowledge -H "X-API-Key: $CHIT_API_KEY" -H "Content-Type: application/json" \
  -d '{"items": [{"kind": "qa", "question": "Who is building Chit?", "answer": "Pranav is building Chit."}]}'
curl -X POST localhost:8000/knowledge/train -H "X-API-Key: $CHIT_API_KEY" \
  -H "Content-Type: application/json" -d '{"training": {"max_steps": 500}}'
```

## Other endpoints

`GET /health`, `GET /model` (loaded checkpoint details), `POST /generate`,
`POST /chat`, `POST /memory`, `GET /memory/search`, `DELETE /memory/{id}`.
Interactive docs are served at `/docs` while the API runs.
