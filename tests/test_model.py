import torch
from pranav_mati.model import MatiModel
def test_forward():
    m=MatiModel(vocab_size=256,block_size=16,n_layer=2,n_head=2,n_embd=32); x=torch.randint(0,256,(2,16)); y,l=m(x,x); assert y.shape==(2,16,256) and l is not None
