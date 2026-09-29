import json
from pathlib import Path
import torch
def export_chit(checkpoint_path,output_dir='exports/chit_v1'):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); c=torch.load(checkpoint_path,map_location='cpu',weights_only=True)
    torch.save(c['model'],out/'chit_weights.pt'); (out/'model_config.json').write_text(json.dumps(c['model_config'], indent=2)); (out/'meta.json').write_text(json.dumps({'version':'0.1.0','step':c.get('step'),'tokenizer':'byte-utf8'},indent=2)); return out
