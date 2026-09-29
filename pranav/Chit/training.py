from pathlib import Path
import random,numpy as np,torch
from tqdm import tqdm
from .data import TextDataset,random_batch
from .model import MatiModel
from .tokenizer import ByteTokenizer
def device_for(x):
    if x=='cpu': return torch.device('cpu')
    if x=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA requested but unavailable')
    return torch.device('cuda' if x=='cuda' or (x=='auto' and torch.cuda.is_available()) else 'cpu')
def seed(s): random.seed(s); np.random.seed(s); torch.manual_seed(s); torch.cuda.is_available() and torch.cuda.manual_seed_all(s)
@torch.no_grad()
def loss(model,ds,batch,steps,dev):
    model.eval(); a=[]
    for _ in range(steps): _,l=model(*random_batch(ds,batch,dev)); a.append(l.item())
    model.train(); return sum(a)/len(a)
def train(c):
    seed(c.seed); dev=device_for(c.device); tok=ByteTokenizer(); tr=TextDataset(c.data.train_file,tok,c.model.block_size); ev=TextDataset(c.data.eval_file,tok,c.model.block_size)
    m=MatiModel(**vars(c.model)).to(dev); opt=torch.optim.AdamW(m.parameters(),lr=c.training.learning_rate,weight_decay=c.training.weight_decay); Path('checkpoints').mkdir(exist_ok=True)
    print('Device:',dev,'Parameters:',sum(p.numel() for p in m.parameters()))
    for step in tqdm(range(1,c.training.max_steps+1),desc='Training Mati'):
        x,y=random_batch(tr,c.training.batch_size,dev); _,l=m(x,y); opt.zero_grad(set_to_none=True); l.backward(); torch.nn.utils.clip_grad_norm_(m.parameters(),c.training.grad_clip); opt.step()
        if step%c.training.eval_interval==0 or step==1: print(f'\nstep={step} train={loss(m,tr,c.training.batch_size,c.training.eval_steps,dev):.4f} eval={loss(m,ev,c.training.batch_size,c.training.eval_steps,dev):.4f}')
        if step%c.training.checkpoint_interval==0 or step==c.training.max_steps: torch.save({'model':m.state_dict(),'model_config':vars(c.model),'step':step},'checkpoints/latest.pt')
