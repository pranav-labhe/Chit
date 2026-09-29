# Azure later

Develop on CPU first. When training becomes slow, move the same repository to a temporary Azure Linux GPU VM, run a larger config, save the checkpoint, then stop/delete the compute resource. The code supports `device=auto` and `device=cuda`.
