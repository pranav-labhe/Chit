from dataclasses import dataclass, field
import json
@dataclass
class ModelConfig: vocab_size:int=256; block_size:int=128; n_layer:int=4; n_head:int=4; n_embd:int=128; dropout:float=0.0
@dataclass
class TrainingConfig: batch_size:int=16; learning_rate:float=3e-4; weight_decay:float=0.1; max_steps:int=1000; eval_interval:int=100; eval_steps:int=20; checkpoint_interval:int=100; grad_clip:float=1.0
@dataclass
class DataConfig: train_file:str='data/train.txt'; eval_file:str='data/eval.txt'
@dataclass
class ChitConfig:
    seed:int=42; device:str='auto'; model:ModelConfig=field(default_factory=ModelConfig); training:TrainingConfig=field(default_factory=TrainingConfig); data:DataConfig=field(default_factory=DataConfig)
def load_config(path):
    with open(path, encoding='utf-8') as f:
        r = json.load(f)
    return ChitConfig(
        r.get('seed', 42), r.get('device', 'auto'),
        ModelConfig(**r.get('model', {})),
        TrainingConfig(**r.get('training', {})),
        DataConfig(**r.get('data', {})),
    )
