import torch
from .model import ChitModel
from .tokenizer import ByteTokenizer
from .memory import MemoryStore
class MatiRuntime:
    def __init__(self,model,device='cpu',memory=None): self.model=model.to(device); self.device=device; self.tokenizer=ByteTokenizer(); self.memory=memory or MemoryStore(); self.model.eval()
    @classmethod
    def from_checkpoint(cls,path,device=None):
        c=torch.load(path,map_location='cpu',weights_only=False); m=MatiModel(**c['model_config']); m.load_state_dict(c['model']); device=device or ('cuda' if torch.cuda.is_available() else 'cpu'); return cls(m,device)
    def generate(self,prompt,max_new_tokens=100,temperature=.8,top_k=50):
        x=torch.tensor([self.tokenizer.encode(prompt)],dtype=torch.long,device=self.device); y=self.model.generate(x,max_new_tokens,temperature,top_k); return self.tokenizer.decode(y[0].tolist())
    def remember(self,*a,**k): return self.memory.add(*a,**k)
    def recall(self,*a,**k): return self.memory.search(*a,**k)
