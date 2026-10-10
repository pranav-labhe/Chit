"""Decoder-only Transformer trained from scratch for Chit."""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

# Checkpoints written before attention switched to scaled_dot_product_attention
# stored the causal mask as a buffer. It is recomputed now, so drop it on load.
_LEGACY_BUFFER_SUFFIXES = (".attn.mask",)


class CausalSelfAttention(nn.Module):
    def __init__(self, n_embd: int, n_head: int, dropout: float,
                 position_encoding: str = "absolute", rope_theta: float = 10000.0):
        super().__init__()
        if n_embd % n_head:
            raise ValueError(f"n_embd ({n_embd}) must be divisible by n_head ({n_head})")
        self.n_head = n_head
        self.dropout = dropout
        self.position_encoding = position_encoding
        self.rope_theta = rope_theta
        if position_encoding == "rope" and (n_embd // n_head) % 2:
            raise ValueError("RoPE requires an even attention head dimension")
        self.qkv = nn.Linear(n_embd, 3 * n_embd)
        self.proj = nn.Linear(n_embd, n_embd)
        self.resid_drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, t, c = x.shape
        q, k, v = self.qkv(x).split(c, dim=2)
        # (b, t, c) -> (b, heads, t, head_dim)
        q, k, v = (z.view(b, t, self.n_head, c // self.n_head).transpose(1, 2) for z in (q, k, v))
        if self.position_encoding == "rope":
            q, k = self._apply_rope(q), self._apply_rope(k)
        # Fused kernel (Flash / memory-efficient attention where available), causal mask built in.
        y = F.scaled_dot_product_attention(
            q, k, v, dropout_p=self.dropout if self.training else 0.0, is_causal=True)
        y = y.transpose(1, 2).contiguous().view(b, t, c)
        return self.resid_drop(self.proj(y))

    def _apply_rope(self, x: torch.Tensor) -> torch.Tensor:
        _, _, length, head_dim = x.shape
        inv_freq = 1.0 / (self.rope_theta ** (
            torch.arange(0, head_dim, 2, device=x.device, dtype=torch.float32) / head_dim))
        angles = torch.outer(torch.arange(length, device=x.device, dtype=torch.float32), inv_freq)
        cos = angles.cos().to(dtype=x.dtype)[None, None, :, :]
        sin = angles.sin().to(dtype=x.dtype)[None, None, :, :]
        paired = x.reshape(*x.shape[:-1], head_dim // 2, 2)
        even, odd = paired[..., 0], paired[..., 1]
        rotated = torch.stack((even * cos - odd * sin, even * sin + odd * cos), dim=-1)
        return rotated.flatten(-2)


class Block(nn.Module):
    def __init__(self, n_embd: int, n_head: int, dropout: float,
                 position_encoding: str = "absolute", rope_theta: float = 10000.0):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)
        self.attn = CausalSelfAttention(n_embd, n_head, dropout, position_encoding, rope_theta)
        self.ln2 = nn.LayerNorm(n_embd)
        self.mlp = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.GELU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln1(x))
        return x + self.mlp(self.ln2(x))


class ChitModel(nn.Module):
    """Decoder-only Transformer with configurable token vocabulary and positions."""

    def __init__(self, vocab_size: int = 256, block_size: int = 128, n_layer: int = 4,
                 n_head: int = 4, n_embd: int = 128, dropout: float = 0.0,
                 position_encoding: str = "absolute", rope_theta: float = 10000.0):
        super().__init__()
        if position_encoding not in ("absolute", "rope"):
            raise ValueError("position_encoding must be 'absolute' or 'rope'")
        if rope_theta <= 0:
            raise ValueError("rope_theta must be positive")
        self.block_size = block_size
        self.vocab_size = vocab_size
        self.position_encoding = position_encoding
        self.rope_theta = rope_theta
        self.token_embedding = nn.Embedding(vocab_size, n_embd)
        if position_encoding == "absolute":
            self.position_embedding = nn.Embedding(block_size, n_embd)
        self.drop = nn.Dropout(dropout)
        self.blocks = nn.ModuleList([Block(n_embd, n_head, dropout, position_encoding, rope_theta)
                                     for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)
        self.lm_head.weight = self.token_embedding.weight  # weight tying
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, 0.0, 0.02)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, 0.0, 0.02)

    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, idx: torch.Tensor, targets: torch.Tensor | None = None):
        b, t = idx.shape
        if t > self.block_size:
            raise ValueError(f"sequence length {t} exceeds block_size {self.block_size}")
        pos = torch.arange(t, device=idx.device)
        x = self.token_embedding(idx)
        if self.position_encoding == "absolute":
            x = x + self.position_embedding(pos)[None, :, :]
        x = self.drop(x)
        for block in self.blocks:
            x = block(x)
        logits = self.lm_head(self.ln_f(x))
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
        return logits, loss

    @torch.no_grad()
    def generate(self, idx: torch.Tensor, max_new_tokens: int, temperature: float = 0.8,
                 top_k: int | None = 50, generator: torch.Generator | None = None) -> torch.Tensor:
        """Sample ``max_new_tokens`` tokens after ``idx`` (shape ``(b, t)``, t >= 1).

        ``temperature <= 0`` means greedy decoding. The module's train/eval mode is
        restored afterwards, so calling this mid-training has no side effects.
        """
        if idx.dim() != 2 or idx.size(1) == 0:
            raise ValueError("idx must have shape (batch, t) with t >= 1")
        was_training = self.training
        self.eval()
        try:
            for _ in range(max_new_tokens):
                logits, _ = self(idx[:, -self.block_size:])
                logits = logits[:, -1, :]
                if temperature <= 0:
                    nxt = logits.argmax(dim=-1, keepdim=True)
                else:
                    logits = logits / temperature
                    if top_k:
                        kth = torch.topk(logits, min(top_k, logits.size(-1))).values[:, -1:]
                        logits = logits.masked_fill(logits < kth, float("-inf"))
                    nxt = torch.multinomial(F.softmax(logits, dim=-1), 1, generator=generator)
                idx = torch.cat((idx, nxt), dim=1)
        finally:
            self.train(was_training)
        return idx


def clean_state_dict(state: dict) -> dict:
    """Drop buffers that older checkpoints stored but the current model recomputes."""
    return {k: v for k, v in state.items() if not k.endswith(_LEGACY_BUFFER_SUFFIXES)}


def load_model_state(model: ChitModel, state: dict) -> ChitModel:
    """Load weights strictly, accepting checkpoints from older versions of this file."""
    model.load_state_dict(clean_state_dict(state), strict=True)
    return model
