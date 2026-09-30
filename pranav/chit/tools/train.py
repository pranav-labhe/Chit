"""Train Chit from the command line.

    python -m pranav.chit.tools.train --config configs/chit_cpu_learning.json
    python -m pranav.chit.tools.train --init checkpoints/latest.pt --max-steps 200   # fine-tune
"""
import argparse
import dataclasses
import sys

from ..config import ConfigError, load_config
from ..training import TrainingCancelled, load_checkpoint, same_architecture, train


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="configs/chit_cpu_learning.json")
    p.add_argument("--output-dir", default="checkpoints")
    p.add_argument("--init", help="checkpoint to fine-tune from (its architecture is used)")
    p.add_argument("--max-steps", type=int, help="override training.max_steps")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), help="override device")
    p.add_argument("--no-step-checkpoints", action="store_true", help="only write latest.pt")
    a = p.parse_args(argv)
    try:
        cfg = load_config(a.config)
        if a.max_steps:
            cfg = dataclasses.replace(cfg, training=dataclasses.replace(cfg.training, max_steps=a.max_steps))
        if a.device:
            cfg = dataclasses.replace(cfg, device=a.device)
        if a.init:
            served = load_checkpoint(a.init)["model_config"]
            if not same_architecture(served, dataclasses.asdict(cfg.model)):
                cfg = dataclasses.replace(cfg, model=dataclasses.replace(cfg.model, **served))
        path = train(cfg, a.output_dir, init_checkpoint=a.init, keep_step_checkpoints=not a.no_step_checkpoints)
    except (ConfigError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, TrainingCancelled):
        print("training interrupted", file=sys.stderr)
        return 130
    print(f"saved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
