from pranav.chit.runtime import ChitRuntime

rt = ChitRuntime.from_checkpoint("checkpoints/latest.pt")
print(rt.generate("Atmini is", max_new_tokens=100, temperature=0.7, top_k=20))
