from dataclasses import dataclass,field
@dataclass
class AtminiContext:
    user_input:str; memories:list[dict]=field(default_factory=list); current_state:dict=field(default_factory=dict); task:str='chat'
@dataclass
class MatiDecision:
    text:str; action:str|None=None; confidence:float|None=None; memory_to_store:list[str]=field(default_factory=list); metadata:dict=field(default_factory=dict)
class AtminiBridge:
    def __init__(self,runtime): self.runtime=runtime
    def process(self,c):
        mem='\n'.join('- '+m.get('content','') for m in c.memories); prompt=f'Task: {c.task}\nKnown memory:\n{mem}\nUser: {c.user_input}\nChit:'
        return MatiDecision(self.runtime.generate(prompt),metadata={'task':c.task})
