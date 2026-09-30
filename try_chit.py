"""Interactive prompt loop for a trained checkpoint.

    python try_chit.py [checkpoint]      (empty line, Ctrl-D or Ctrl-C to quit)
"""
import sys

from pranav.chit.runtime import ChitRuntime


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "checkpoints/latest.pt"
    try:
        rt = ChitRuntime.from_checkpoint(path)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"could not load {path}: {e}\nTrain first: python -m pranav.chit.tools.train", file=sys.stderr)
        return 2
    while True:
        try:
            prompt = input("prompt> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            return 0
        print(rt.generate(prompt, max_new_tokens=120, temperature=0.7))


if __name__ == "__main__":
    sys.exit(main())
