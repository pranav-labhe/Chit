# Training data API

`data/train.txt` and `data/eval.txt` are what `POST /train` learns from. They often arrive
from outside the API, for example a folder mounted into a container, so two endpoints let you
check and prepare them without shell access. Both need the same key as the training API
(`X-API-Key`, or `CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1` for local development).

## `GET /data?config=<name>`

Reports the train and eval files that config uses, as they are on the server right now:

```json
{
  "config": "chit_train_txt", "block_size": 64,
  "train": {"path": "data/train.txt", "bytes": 1265, "lines": 27, "sha256": "…", "modified_at": "…"},
  "eval":  {"path": "data/eval.txt",  "bytes": 134,  "lines": 3,  "sha256": "…", "modified_at": "…"},
  "checks": {"train_larger_than_block_size": true, "eval_larger_than_block_size": true,
             "eval_distinct_lines": 3, "eval_lines_also_in_train": 0, "train_repeated_lines": 2},
  "warnings": ["eval file is under 1024 bytes, so the eval loss will be noisy"],
  "ready_to_train": true,
  "sources": [{"name": "corpus.txt", "bytes": 48213}]
}
```

- Run it after mounting or editing files, before training. `sha256` and `modified_at` show
  whether a file changed.
- `ready_to_train` is false when a file is missing or not larger than `model.block_size`
  (the same rule `POST /train` enforces).
- `eval_lines_also_in_train` counts distinct eval lines that also occur in train. A high share means
  the eval loss looks better than the model really is. Repeated answers such as
  `Chit: I do not know.` are normal and expected to overlap.
- `sources` lists `.txt` and `.md` files in the data folder that `POST /data/split` can read.

## `POST /data/split`

Splits one corpus file from the data folder into the config's `data.train_file` and
`data.eval_file`.

```json
{"source": "corpus.txt", "config": "chit_train_txt", "by": "line",
 "eval_fraction": 0.1, "seed": 42, "overwrite": false, "dry_run": false}
```

| Field | Meaning |
| --- | --- |
| `source` | File name inside `CHIT_DATA_DIR` (default `data`). No folders or paths; symlinks that leave the folder are refused. |
| `config` | Which config's train/eval paths to write and whose `block_size` to check. |
| `by` | `line`, or `paragraph` to keep blocks separated by blank lines together (for `User:` / `Chit:` pairs). |
| `eval_fraction` | Share of items held out, between 0 and 0.5. |
| `seed` | Fixed by default, so the same input gives the same split. |
| `overwrite` | Needed when the train or eval file already exists. The old files are kept as `<name>.bak`. |
| `dry_run` | Report what would be written and write nothing. |

Blank lines and exact duplicates (ignoring case and extra spaces) are removed, the rest is shuffled,
and no item appears in both files. Paraphrases are not detected as duplicates.

Responses: `200` with the report (`written`, item and byte counts, `backups`, `warnings`);
`409` if the files exist and `overwrite` is false, or a training job is active; `404` if the source
or config is missing; `422` if the result would not be larger than `block_size` (nothing is written).
The same split is available offline: `python -m pranav.chit.tools.split corpus.txt`.

## Containers

- Mount the data folder read-write (`./data:/app/data`) so the API can write the two files and the `.bak` copies.
- Files are written by renaming a temporary file into place, so training never reads half a file. If
  `train.txt` is itself mounted as a single file, the API writes it in place instead.
- Do not start training while a split is running.
- `CHIT_DATA_DIR` changes the folder that `source` names are read from.
