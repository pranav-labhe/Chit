# Mati — Pranav's Atmini Brain

Mati is an experimental from-scratch neural-model layer for Atmini.

Milestones covered by this scaffold:
1. neural fundamentals
2. tiny language model
3. tiny Transformer
4. own tokenizer + weights
5. Mati training data
6. external memory
7. reasoning examples
8. Atmini integration boundary
9. CPU/GPU-ready training
10. checkpoint/export foundation for Mati v1

This is intentionally small and beginner-friendly. The initial model is not a ChatGPT replacement; the goal is to give Pranav a real model that he can understand, train, modify and eventually grow.

## Quick start

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
python -m pranav_mati.tools.train --config configs/mati_cpu_learning.json
python -m pranav_mati.tools.generate --checkpoint checkpoints/latest.pt --prompt "Atmini"
```

The package name is `pranav_mati` and the project is `Mati`.
