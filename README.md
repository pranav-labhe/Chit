# Chit — चित् — Pranav's Atmini Brain

Chit is from-scratch neural-model layer for Atmini.

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
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
python -m pranav.chit.tools.train --config configs/chit_cpu_learning.json
python -m pranav.chit.tools.generate --checkpoint checkpoints/latest.pt --prompt "Atmini"
```

The package name is `pranav.chit` and the project is `Chit`.
