from pranav.chit.runtime import ChitRuntime

rt = ChitRuntime.from_checkpoint("checkpoints/latest.pt")
while True:
    p = input("prompt> ")
    if not p: break
    print(rt.generate(p, max_new_tokens=120, temperature=0.7))
