import argparse
from ..config import load_config
from ..training import train
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='configs/chit_cpu_learning.json')
    a = p.parse_args()
    train(load_config(a.config))

if __name__ == '__main__':
    main()
