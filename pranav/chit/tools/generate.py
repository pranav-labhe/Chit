import argparse
from ..runtime import ChitRuntime
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--checkpoint', default='checkpoints/latest.pt')
    p.add_argument('--prompt', default='Chit')
    p.add_argument('--tokens', type=int, default=120)
    a = p.parse_args()
    print(ChitRuntime.from_checkpoint(a.checkpoint).generate(a.prompt, a.tokens))

if __name__ == '__main__':
    main()
