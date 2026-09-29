import argparse
from ..config import load_config
from ..training import train
p=argparse.ArgumentParser(); p.add_argument('--config',default='configs/mati_cpu_learning.json'); a=p.parse_args(); train(load_config(a.config))
