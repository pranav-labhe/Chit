import math

import pytest
import torch
import torch.nn.functional as F

from pranav.chit.model import ChitModel, load_model_state

CFG = dict(vocab_size=256, block_size=16, n_layer=2, n_head=2, n_embd=32)


def test_forward():
    m = ChitModel(**CFG)
    x = torch.randint(0, 256, (2, 16))
    y, l = m(x, x)
    assert y.shape == (2, 16, 256) and l is not None


def test_rejects_sequences_longer_than_block_size():
    with pytest.raises(ValueError):
        ChitModel(**CFG)(torch.zeros(1, 17, dtype=torch.long))


def _reference_attention(attn, x):
    """The original hand-written masked attention, to prove the fused kernel is equivalent."""
    b, t, c = x.shape
    q, k, v = attn.qkv(x).split(c, dim=2)
    q, k, v = (z.view(b, t, attn.n_head, c // attn.n_head).transpose(1, 2) for z in (q, k, v))
    a = (q @ k.transpose(-2, -1)) / math.sqrt(c // attn.n_head)
    a = a.masked_fill(torch.tril(torch.ones(t, t)) == 0, float("-inf"))
    y = (F.softmax(a, dim=-1) @ v).transpose(1, 2).contiguous().view(b, t, c)
    return attn.proj(y)


def test_fused_attention_matches_reference():
    torch.manual_seed(0)
    attn = ChitModel(**CFG).eval().blocks[0].attn
    x = torch.randn(2, 10, 32)
    assert torch.allclose(attn(x), _reference_attention(attn, x), atol=1e-5)


def test_loads_legacy_checkpoint_with_mask_buffers():
    state = ChitModel(**CFG).state_dict()
    for i in range(CFG["n_layer"]):  # what checkpoints from v0.1 contained
        state[f"blocks.{i}.attn.mask"] = torch.tril(torch.ones(16, 16)).view(1, 1, 16, 16)
    load_model_state(ChitModel(**CFG), state)  # strict load must succeed


def test_generate_restores_mode_and_greedy_is_deterministic():
    m = ChitModel(**CFG).train()
    x = torch.tensor([[1, 2, 3]])
    a = m.generate(x, 20, temperature=0)
    b = m.generate(x, 20, temperature=0)
    assert m.training and torch.equal(a, b) and a.shape == (1, 23)


def test_generate_rejects_empty_prompt():
    with pytest.raises(ValueError):
        ChitModel(**CFG).generate(torch.zeros(1, 0, dtype=torch.long), 5)
