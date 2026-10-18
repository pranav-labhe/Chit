import math

import pytest
import torch
import torch.nn.functional as F

from pranav.chit.model import CausalSelfAttention, ChitModel, load_model_state

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


def test_rope_matches_manual_two_dimensional_rotation():
    attn = CausalSelfAttention(n_embd=2, n_head=1, dropout=0.0, position_encoding="rope").eval()
    x = torch.tensor([[[[1.0, 0.0], [1.0, 0.0]]]])
    actual = attn._apply_rope(x)
    expected = torch.tensor([[[[1.0, 0.0], [math.cos(1.0), math.sin(1.0)]]]])
    assert torch.allclose(actual, expected, atol=1e-6)


def test_rope_model_is_causal_and_has_finite_gradients():
    torch.manual_seed(3)
    model = ChitModel(**CFG, position_encoding="rope").train()
    ids = torch.randint(0, CFG["vocab_size"], (2, 10))
    logits, loss = model(ids, ids)
    assert logits.shape == (2, 10, CFG["vocab_size"])
    assert torch.isfinite(loss)
    loss.backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
    model.eval()
    with torch.no_grad():
        prefix, _ = model(ids[:, :5])
        full, _ = model(ids[:, :10])
    assert torch.allclose(prefix, full[:, :5], atol=1e-5)


def test_rope_checkpoint_round_trip():
    model = ChitModel(**CFG, position_encoding="rope")
    clone = load_model_state(ChitModel(**CFG, position_encoding="rope"), model.state_dict())
    assert clone.position_encoding == "rope"
    with pytest.raises(ValueError, match="even attention head"):
        ChitModel(vocab_size=256, block_size=8, n_layer=1, n_head=1, n_embd=3,
                  position_encoding="rope")


def test_generate_stop_fn_halts_early():
    m = ChitModel(**CFG).eval()
    x = torch.tensor([[1, 2, 3]])
    # Prompt is 3 tokens. If max_new_tokens=20, but stop_fn triggers at total length 6:
    out = m.generate(x, 20, stop_fn=lambda idx: idx.size(1) >= 6)
    assert out.shape == (1, 6)  # exactly 3 prompt + 3 generated


def test_generate_repetition_penalty_reduces_repeated_token_logits():
    torch.manual_seed(42)
    m = ChitModel(**CFG).eval()
    # If repetition penalty is applied, greedy generation avoids immediate cycles
    x = torch.tensor([[5, 5, 5]])
    standard = m.generate(x, 10, temperature=0, repetition_penalty=1.0)
    penalized = m.generate(x, 10, temperature=0, repetition_penalty=2.5)
    assert standard.shape == penalized.shape == (1, 13)
    # The penalized generation should differ from unpenalized
    assert not torch.equal(standard, penalized)


def test_generate_repetition_penalty_does_not_penalize_prompt_tokens():
    torch.manual_seed(42)
    m = ChitModel(**CFG).eval()
    x = torch.tensor([[5, 5, 5]])
    # When prompt_len=3, the first generated token is not penalized against the prompt tokens
    # so generating 1 token with or without repetition penalty produces identical first token
    t1_std = m.generate(x, 1, temperature=0, repetition_penalty=1.0)
    t1_pen = m.generate(x, 1, temperature=0, repetition_penalty=5.0, prompt_len=3)
    assert torch.equal(t1_std, t1_pen)


@pytest.mark.parametrize("pos_enc", ["absolute", "rope"])
def test_kv_cache_matches_uncached_greedy_generation(pos_enc):
    torch.manual_seed(7)
    m = ChitModel(**CFG, position_encoding=pos_enc).eval()
    x = torch.tensor([[10, 20, 30, 40]])
    cached_ids, cached_conf, cached_fin = m.generate(
        x, 20, temperature=0, use_cache=True, return_details=True
    )
    uncached_ids, uncached_conf, uncached_fin = m.generate(
        x, 20, temperature=0, use_cache=False, return_details=True
    )
    assert torch.equal(cached_ids, uncached_ids)
    assert abs(cached_conf - uncached_conf) < 1e-5
    assert cached_fin == uncached_fin


def test_forward_ignores_masked_targets():
    torch.manual_seed(11)
    m = ChitModel(**CFG).eval()
    x = torch.randint(0, 256, (1, 8))
    targets = x.clone()
    targets[:, :5] = -100
    logits, loss = m(x, targets)
    expected = F.cross_entropy(logits[:, 5:, :].reshape(-1, 256), x[:, 5:].reshape(-1))
    assert torch.allclose(loss, expected, atol=1e-6)



