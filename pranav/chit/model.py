import math
import torch
import torch.nn as nn
import torch.nn.functional as F

class CausalSelfAttention(nn.Module):
    def __init__(self, n_embd, n_head, block_size, dropout):
        super().__init__(); assert n_embd % n_head == 0
        self.n_head=n_head; self.head_dim=n_embd//n_head
        self.qkv=nn.Linear(n_embd,3*n_embd); self.proj=nn.Linear(n_embd,n_embd)
        self.drop=nn.Dropout(dropout)
        self.register_buffer("mask", torch.tril(torch.ones(block_size,block_size)).view(1,1,block_size,block_size))
    def forward(self,x):
        b,t,c=x.shape; q,k,v=self.qkv(x).split(c,dim=2)
        q=q.view(b,t,self.n_head,self.head_dim).transpose(1,2); k=k.view(b,t,self.n_head,self.head_dim).transpose(1,2); v=v.view(b,t,self.n_head,self.head_dim).transpose(1,2)
        a=(q@k.transpose(-2,-1))/math.sqrt(self.head_dim); a=a.masked_fill(self.mask[:,:,:t,:t]==0,float('-inf')); a=F.softmax(a,dim=-1); a=self.drop(a)
        y=(a@v).transpose(1,2).contiguous().view(b,t,c); return self.drop(self.proj(y))

class Block(nn.Module):
    def __init__(self,n_embd,n_head,block_size,dropout):
        super().__init__(); self.ln1=nn.LayerNorm(n_embd); self.attn=CausalSelfAttention(n_embd,n_head,block_size,dropout); self.ln2=nn.LayerNorm(n_embd)
        self.mlp=nn.Sequential(nn.Linear(n_embd,4*n_embd),nn.GELU(),nn.Linear(4*n_embd,n_embd),nn.Dropout(dropout))
    def forward(self,x):
        x=x+self.attn(self.ln1(x)); return x+self.mlp(self.ln2(x))

class ChitModel(nn.Module):
    """Small decoder-only Transformer trained from scratch for Chit."""
    def __init__(self,vocab_size=256,block_size=128,n_layer=4,n_head=4,n_embd=128,dropout=0.0):
        super().__init__(); self.block_size=block_size
        self.token_embedding=nn.Embedding(vocab_size,n_embd); self.position_embedding=nn.Embedding(block_size,n_embd)
        self.blocks=nn.ModuleList([Block(n_embd,n_head,block_size,dropout) for _ in range(n_layer)])
        self.ln_f=nn.LayerNorm(n_embd); self.lm_head=nn.Linear(n_embd,vocab_size,bias=False); self.lm_head.weight=self.token_embedding.weight
        self.apply(self._init)
    def _init(self,m):
        if isinstance(m,nn.Linear): nn.init.normal_(m.weight,0.0,0.02); m.bias is not None and nn.init.zeros_(m.bias)
        elif isinstance(m,nn.Embedding): nn.init.normal_(m.weight,0.0,0.02)
    def forward(self,idx,targets=None):
        b,t=idx.shape
        if t>self.block_size: raise ValueError("sequence exceeds block size")
        p=torch.arange(t,device=idx.device); x=self.token_embedding(idx)+self.position_embedding(p)[None,:,:]
        for block in self.blocks: x=block(x)
        logits=self.lm_head(self.ln_f(x)); loss=None
        if targets is not None: loss=F.cross_entropy(logits.reshape(-1,logits.size(-1)),targets.reshape(-1))
        return logits,loss
    @torch.no_grad()
    def generate(self,idx,max_new_tokens,temperature=0.8,top_k=50):
        self.eval()
        for _ in range(max_new_tokens):
            logits,_=self(idx[:,-self.block_size:]); logits=logits[:,-1,:]/max(temperature,1e-5)
            if top_k: values,_=torch.topk(logits,min(top_k,logits.size(-1))); logits[logits<values[:,-1:]]=float('-inf')
            idx=torch.cat((idx,torch.multinomial(F.softmax(logits,dim=-1),1)),dim=1)
        return idx
