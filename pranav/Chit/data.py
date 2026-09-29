from pathlib import Path
import torch
from torch.utils.data import Dataset
class TextDataset(Dataset):
    def __init__(self,path,tokenizer,block_size):
        ids=tokenizer.encode(Path(path).read_text(encoding='utf-8')); self.data=torch.tensor(ids,dtype=torch.long); self.block_size=block_size
        if len(ids)<=block_size: raise ValueError('Dataset is smaller than block_size.')
    def __len__(self): return len(self.data)-self.block_size
    def __getitem__(self,i):
        c=self.data[i:i+self.block_size+1]; return c[:-1],c[1:]
def random_batch(ds,batch_size,device):
    ix=torch.randint(0,len(ds),(batch_size,)); return torch.stack([ds[int(i)][0] for i in ix]).to(device),torch.stack([ds[int(i)][1] for i in ix]).to(device)
