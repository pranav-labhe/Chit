from fastapi import FastAPI
from pydantic import BaseModel
from pranav.chit.runtime import ChitRuntime
from pranav.chit.bridge import Bridge, Context

app = FastAPI()
rt = ChitRuntime.from_checkpoint("checkpoints/latest.pt")
bridge = Bridge(rt)

class Req(BaseModel):
    prompt: str
    tokens: int = 100
    temperature: float = 0.7

@app.post("/generate")
def generate(r: Req):
    return {"text": rt.generate(r.prompt, r.tokens, r.temperature)}

@app.post("/chat")
def chat(r: Req):
    return {"text": bridge.process(Context(user_input=r.prompt)).text}
