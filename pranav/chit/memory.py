import json,uuid
from datetime import datetime,timezone
from pathlib import Path
class MemoryStore:
    def __init__(self,path='data/memory.json'):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists(): self.path.write_text('[]',encoding='utf-8')
    def _load(self): return json.loads(self.path.read_text(encoding='utf-8'))
    def _save(self,x): self.path.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
    def add(self,content,memory_type='experience',importance=.5,tags=None):
        x=self._load(); item={'id':str(uuid.uuid4()),'type':memory_type,'content':content,'importance':float(importance),'tags':tags or [],'created_at':datetime.now(timezone.utc).isoformat()}; x.append(item); self._save(x); return item
    def all(self): return self._load()
    def search(self,q,limit=5):
        terms=set(q.lower().split()); scored=[]
        for x in self._load():
            score=sum(t in x['content'].lower() for t in terms)
            if score: scored.append((score,x))
        scored.sort(key=lambda z:(z[0],z[1].get('importance',0)),reverse=True); return [x for _,x in scored[:limit]]
