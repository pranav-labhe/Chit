"""Inference runtime: a loaded model plus the memory it can draw on."""
from __future__ import annotations

from pathlib import Path

import torch

from .model import ChitModel, load_model_state
from .memory import MemoryStore
from .tokenizer import BpeTokenizer, ByteTokenizer, create_tokenizer
from .training import load_checkpoint


class ChitRuntime:
    def __init__(self, model: ChitModel, device: str | torch.device = "cpu", memory=None,
                 model_config: dict | None = None, checkpoint_meta: dict | None = None):
        self.device = torch.device(device)
        self.model = model.to(self.device).eval()
        self.tokenizer = ByteTokenizer()
        self.memory = memory if memory is not None else MemoryStore()
        self.model_config = model_config
        self.checkpoint_meta = checkpoint_meta or {}

    @classmethod
    def from_checkpoint(cls, path: str | Path, device: str | None = None,
                        memory=None) -> "ChitRuntime":
        ck = load_checkpoint(path)
        tok = ck.get("tokenizer", ByteTokenizer.name)
        tok_cfg = (ck.get("config") or {}).get("tokenizer") or {}
        tokenizer = create_tokenizer(tok, model_file=tok_cfg.get("model_file"),
                                     asset=ck.get("tokenizer_asset"))
        if isinstance(tokenizer, BpeTokenizer) and tokenizer.asset_sha256 != ck.get("tokenizer_sha256"):
            raise ValueError("checkpoint BPE tokenizer asset hash does not match its metadata")
        if tokenizer.vocab_size != ck["model_config"].get("vocab_size", tokenizer.vocab_size):
            raise ValueError("checkpoint tokenizer vocabulary does not match model_config.vocab_size")
        model = load_model_state(ChitModel(**ck["model_config"]), ck["model"])
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        meta = {k: ck.get(k) for k in ("format", "chit_version", "step", "total_steps",
                                        "init_from", "best_eval_loss", "last_eval", "metadata")}
        meta["path"] = str(path)
        runtime = cls(model, device, memory=memory, model_config=dict(ck["model_config"]), checkpoint_meta=meta)
        runtime.tokenizer = tokenizer
        return runtime

    def generate(self, prompt: str, max_new_tokens: int = 100, temperature: float = 0.8, top_k: int | None = 50,
                 stop: list[str] | None = None, repetition_penalty: float = 1.0,
                 return_details: bool = False) -> str | tuple[str, float, str]:
        """Return only the newly generated text, cut at the first ``stop`` string if given."""
        ids = self.tokenizer.encode(prompt) or self.tokenizer.encode("\n")  # model needs >= 1 token
        x = torch.tensor([ids], dtype=torch.long, device=self.device)
        prompt_len = x.size(1)
        clean_stops = [s for s in (stop or ()) if s]

        stop_fn = None
        if clean_stops:
            generated_ids: list[int] = []
            if isinstance(self.tokenizer, ByteTokenizer):
                stop_bytes = [s.encode("utf-8") for s in clean_stops]
                def _stop(idx: torch.Tensor) -> bool:
                    generated_ids.append(int(idx[0, -1].item()))
                    gen_data = bytes(generated_ids)
                    return any(sb in gen_data for sb in stop_bytes)
                stop_fn = _stop
            else:
                def _stop(idx: torch.Tensor) -> bool:
                    generated_ids.append(int(idx[0, -1].item()))
                    text = self.tokenizer.decode(generated_ids)
                    return any(s in text for s in clean_stops)
                stop_fn = _stop

        try:
            gen_res = self.model.generate(x, max_new_tokens, temperature, top_k,
                                          stop_fn=stop_fn, repetition_penalty=repetition_penalty,
                                          prompt_len=prompt_len, return_details=return_details)
        except TypeError:
            gen_res = self.model.generate(x, max_new_tokens, temperature, top_k,
                                          stop_fn=stop_fn, repetition_penalty=repetition_penalty,
                                          prompt_len=prompt_len)

        if isinstance(gen_res, tuple):
            y, confidence, finish_reason = gen_res
        else:
            y = gen_res
            confidence = 1.0
            finish_reason = "length"

        text = self.tokenizer.decode(y[0, prompt_len:].tolist())
        stopped_by_cut = False
        for s in clean_stops:
            if s in text:
                text = text[:text.index(s)]
                stopped_by_cut = True

        if stopped_by_cut:
            finish_reason = "stop"

        if return_details:
            return text, confidence, finish_reason
        return text

    def remember(self, *a, **k):
        return self.memory.add(*a, **k)

    def recall(self, *a, **k):
        return self.memory.search(*a, **k)
