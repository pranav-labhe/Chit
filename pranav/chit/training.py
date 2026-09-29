"""Training loop for Chit.

Used by both the CLI (``python -m pranav.chit.tools.train``) and the training
API (``pranav.chit.jobs``). The optional callbacks let a caller observe
progress and stop a run cooperatively without touching the loop itself.
"""
from __future__ import annotations

import os
import random
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from tqdm import tqdm

from .data import TextDataset, random_batch
from .model import ChitModel
from .tokenizer import ByteTokenizer


class TrainingCancelled(Exception):
    """Raised when ``should_stop`` asks the loop to stop early."""


def device_for(x):
    if x == 'cpu':
        return torch.device('cpu')
    if x == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    return torch.device('cuda' if x == 'cuda' or (x == 'auto' and torch.cuda.is_available()) else 'cpu')


def seed(s):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


@torch.no_grad()
def loss(model, ds, batch, steps, dev):
    model.eval()
    a = []
    for _ in range(steps):
        _, l = model(*random_batch(ds, batch, dev))
        a.append(l.item())
    model.train()
    return sum(a) / len(a)


def save_checkpoint(obj, path):
    """Write a checkpoint atomically, so a reader never sees a half-written file."""
    path = Path(path)
    tmp = path.with_name(f'{path.name}.tmp-{os.getpid()}')
    try:
        torch.save(obj, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def train(
    c,
    output_dir='checkpoints',
    *,
    on_step: Callable[[int], None] | None = None,
    on_eval: Callable[[int, float, float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    keep_step_checkpoints: bool = True,
    progress: bool = True,
) -> Path:
    """Train a Chit model from config ``c``; return the path of the final checkpoint.

    on_step(step)                       called after every optimizer step
    on_eval(step, train_loss, eval_loss) called at every evaluation point
    should_stop()                       checked every step; True raises TrainingCancelled
    keep_step_checkpoints               also keep step_NNNNNN.pt files, not only latest.pt
    progress                            show a tqdm bar and print losses (CLI use)
    """
    seed(c.seed)
    dev = device_for(c.device)
    tok = ByteTokenizer()
    if c.model.vocab_size != tok.vocab_size:
        raise ValueError(f'model.vocab_size must equal tokenizer vocab ({tok.vocab_size})')
    tr = TextDataset(c.data.train_file, tok, c.model.block_size)
    ev = TextDataset(c.data.eval_file, tok, c.model.block_size)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    latest = out / 'latest.pt'
    t = c.training

    m = ChitModel(**asdict(c.model)).to(dev)
    opt = torch.optim.AdamW(m.parameters(), lr=t.learning_rate, weight_decay=t.weight_decay)
    if progress:
        print('Device:', dev, 'Parameters:', sum(p.numel() for p in m.parameters()))

    steps = range(1, t.max_steps + 1)
    for step in (tqdm(steps, desc='Training Chit') if progress else steps):
        if should_stop and should_stop():
            raise TrainingCancelled(f'cancelled at step {step - 1}')
        x, y = random_batch(tr, t.batch_size, dev)
        _, l = m(x, y)
        opt.zero_grad(set_to_none=True)
        l.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), t.grad_clip)
        opt.step()
        if on_step:
            on_step(step)

        if step % t.eval_interval == 0 or step == 1 or step == t.max_steps:
            tl = loss(m, tr, t.batch_size, t.eval_steps, dev)
            el = loss(m, ev, t.batch_size, t.eval_steps, dev)
            if progress:
                tqdm.write(f'step={step} train={tl:.4f} eval={el:.4f}')
            if on_eval:
                on_eval(step, tl, el)

        if step % t.checkpoint_interval == 0 or step == t.max_steps:
            ck = {'model': m.state_dict(), 'optimizer': opt.state_dict(),
                  'model_config': asdict(c.model), 'step': step}
            if keep_step_checkpoints:
                save_checkpoint(ck, out / f'step_{step:06d}.pt')
            save_checkpoint(ck, latest)
    return latest
