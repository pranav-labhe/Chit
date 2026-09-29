import argparse
from ..runtime import MatiRuntime
p=argparse.ArgumentParser(); p.add_argument('--checkpoint',default='checkpoints/latest.pt'); p.add_argument('--prompt',default='Atmini'); p.add_argument('--tokens',type=int,default=120); a=p.parse_args(); print(MatiRuntime.from_checkpoint(a.checkpoint).generate(a.prompt,a.tokens))
