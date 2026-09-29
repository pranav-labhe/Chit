"""Generate text from a checkpoint.

    python -m pranav.chit.tools.generate --prompt "Atmini" --tokens 120
"""
import argparse
import sys

from ..runtime import ChitRuntime


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkpoint", default="checkpoints/latest.pt")
    p.add_argument("--prompt", default="Chit")
    p.add_argument("--tokens", type=int, default=120)
    p.add_argument("--temperature", type=float, default=0.8, help="0 = greedy")
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--device", choices=("cpu", "cuda"))
    a = p.parse_args(argv)
    try:
        rt = ChitRuntime.from_checkpoint(a.checkpoint, device=a.device)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"error: could not load {a.checkpoint}: {e}", file=sys.stderr)
        return 2
    print(rt.generate(a.prompt, a.tokens, a.temperature, a.top_k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
