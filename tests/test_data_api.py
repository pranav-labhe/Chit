import os

import pytest

from conftest import H, train_body
from pranav.chit import datasets
from pranav.chit.tools.split import main as split_cli

CORPUS = "\n".join(f"Atmini fact number {i} is remembered in memory {i * 7}." for i in range(60)) + "\n"


# ------------------------------------------------------------------ datasets.py


def test_split_corpus_no_overlap_dedupes_and_is_deterministic():
    text = CORPUS + "chit is small.\nChit  is small.\n\n\n"
    a = datasets.split_corpus(text)
    assert not set(a.train) & set(a.eval)
    assert len(a.train) + len(a.eval) == 61 and a.duplicates_removed == 1
    assert a.eval == datasets.split_corpus(text).eval
    assert a.eval != datasets.split_corpus(text, seed=7).eval


def test_paragraph_mode_keeps_pairs_together():
    pairs = "\n\n".join(f"User: Q{i}?\nChit: A{i}." for i in range(20))
    res = datasets.split_corpus(pairs, by="paragraph")
    for block in res.train + res.eval:
        q, a = block.split("\n")
        assert q[len("User: Q"):-1] == a[len("Chit: A"):-1]


def test_split_needs_two_items():
    with pytest.raises(ValueError):
        datasets.split_corpus("only one line")


def test_analyze_flags_leakage_and_size(tmp_path):
    (tmp_path / "t.txt").write_text("alpha line\nbeta line\ngamma line\n" * 40, encoding="utf-8")
    (tmp_path / "e.txt").write_text("alpha line\nnew line\n", encoding="utf-8")
    rep = datasets.analyze(tmp_path / "t.txt", tmp_path / "e.txt", block_size=16, max_bytes=10**6)
    assert rep["ready_to_train"] and rep["checks"]["eval_lines_also_in_train"] == 1
    assert any("also appear in train" in w for w in rep["warnings"])
    assert any("noisy" in w for w in rep["warnings"])
    small = datasets.analyze(tmp_path / "t.txt", tmp_path / "e.txt", block_size=500, max_bytes=10**6)
    assert not small["ready_to_train"]
    missing = datasets.analyze(tmp_path / "t.txt", tmp_path / "nope.txt", block_size=16, max_bytes=10**6)
    assert not missing["ready_to_train"] and missing["eval"] is None


def test_file_info_and_atomic_write(tmp_path):
    f = tmp_path / "x.txt"
    datasets.write_text(f, "one\ntwo")
    info = datasets.file_info(f)
    assert info["bytes"] == 7 and info["lines"] == 2 and len(info["sha256"]) == 64
    assert datasets.backup(f).endswith("x.txt.bak") and (tmp_path / "x.txt.bak").read_text() == "one\ntwo"
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]   # no temp files left behind


# ------------------------------------------------------------------ CLI


def test_cli_writes_refuses_overwrite_and_keeps_backup(tmp_path):
    src = tmp_path / "corpus.txt"
    src.write_text(CORPUS, encoding="utf-8")
    tr, ev = tmp_path / "train.txt", tmp_path / "eval.txt"
    args = [str(src), "--train-out", str(tr), "--eval-out", str(ev)]
    assert split_cli(args) == 0
    first = tr.read_text(encoding="utf-8")
    assert split_cli(args) == 2 and tr.read_text(encoding="utf-8") == first
    assert split_cli(args + ["--force", "--seed", "9"]) == 0
    assert (tmp_path / "train.txt.bak").read_text(encoding="utf-8") == first
    assert split_cli(args + ["--force", "--block-size", "100000"]) == 2


# ------------------------------------------------------------------ API


@pytest.fixture
def corpus(client, tmp_path):
    (tmp_path / "data" / "corpus.txt").write_text(CORPUS, encoding="utf-8")
    return "corpus.txt"


def test_data_status(client, corpus, tmp_path):
    r = client.get("/data", params={"config": "test"}, headers=H)
    assert r.status_code == 200
    d = r.json()
    assert d["ready_to_train"] and d["train"]["bytes"] > 0 and len(d["train"]["sha256"]) == 64
    assert d["checks"]["eval_lines_also_in_train"] == 0
    corpus_bytes = (tmp_path / "data" / "corpus.txt").stat().st_size
    assert {"name": "corpus.txt", "bytes": corpus_bytes} in d["sources"]
    assert client.get("/data", params={"config": "missing"}, headers=H).status_code == 404


def test_data_status_sees_files_changed_from_outside(client, tmp_path):
    before = client.get("/data", params={"config": "test"}, headers=H).json()["train"]["sha256"]
    (tmp_path / "data" / "train.txt").write_text("changed by a mount\n" * 30, encoding="utf-8")
    assert client.get("/data", params={"config": "test"}, headers=H).json()["train"]["sha256"] != before


def test_split_dry_run_writes_nothing(client, corpus, tmp_path):
    before = (tmp_path / "data" / "train.txt").read_text(encoding="utf-8")
    r = client.post("/data/split", json={"source": corpus, "config": "test", "dry_run": True}, headers=H)
    assert r.status_code == 200 and r.json()["written"] is False
    assert r.json()["would_overwrite"] and r.json()["train"]["items"] + r.json()["eval"]["items"] == 60
    assert (tmp_path / "data" / "train.txt").read_text(encoding="utf-8") == before


def test_split_refuses_to_overwrite_without_flag(client, corpus, tmp_path):
    before = (tmp_path / "data" / "train.txt").read_text(encoding="utf-8")
    r = client.post("/data/split", json={"source": corpus, "config": "test"}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["existing"]
    assert (tmp_path / "data" / "train.txt").read_text(encoding="utf-8") == before


def test_split_overwrite_writes_backs_up_and_leaves_no_overlap(client, corpus, tmp_path):
    old = (tmp_path / "data" / "train.txt").read_text(encoding="utf-8")
    r = client.post("/data/split", json={"source": corpus, "config": "test", "overwrite": True}, headers=H)
    assert r.status_code == 200 and r.json()["written"] and len(r.json()["backups"]) == 2
    assert (tmp_path / "data" / "train.txt.bak").read_text(encoding="utf-8") == old
    t = set((tmp_path / "data" / "train.txt").read_text(encoding="utf-8").splitlines())
    e = set((tmp_path / "data" / "eval.txt").read_text(encoding="utf-8").splitlines())
    assert t and e and not t & e and len(t) + len(e) == 60
    assert client.get("/data", params={"config": "test"}, headers=H).json()["ready_to_train"]


def test_split_rejects_files_not_larger_than_block_size(client, tmp_path):
    (tmp_path / "data" / "tiny.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
    r = client.post("/data/split", json={"source": "tiny.txt", "config": "test", "overwrite": True}, headers=H)
    assert r.status_code == 422 and "block_size" in str(r.json()["detail"])
    assert "Chit learns" in (tmp_path / "data" / "train.txt").read_text(encoding="utf-8")   # untouched


def test_split_source_must_stay_inside_the_data_folder(client, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text(CORPUS, encoding="utf-8")
    symlink_created = True
    try:
        os.symlink(outside, tmp_path / "data" / "link.txt")
    except OSError as e:
        # Creating symlinks on Windows may require Developer Mode or a privilege.
        if os.name != "nt" or getattr(e, "winerror", None) != 1314:
            raise
        symlink_created = False
    body = {"config": "test", "overwrite": True}
    for name in ("../secret.txt", "/etc/passwd", "a/b.txt", "..", ".hidden"):
        assert client.post("/data/split", json={**body, "source": name}, headers=H).status_code == 422
    if symlink_created:
        assert client.post("/data/split", json={**body, "source": "link.txt"}, headers=H).status_code == 404
    assert client.post("/data/split", json={**body, "source": "missing.txt"}, headers=H).status_code == 404


def test_split_requires_the_key(client, corpus):
    assert client.get("/data").status_code == 401
    assert client.post("/data/split", json={"source": corpus}).status_code == 401


def test_split_is_blocked_while_training_runs(client, corpus):
    job = client.post("/train", json=train_body(max_steps=100000), headers=H)
    assert job.status_code == 202
    try:
        r = client.post("/data/split", json={"source": corpus, "config": "test", "overwrite": True}, headers=H)
        assert r.status_code == 409 and r.json()["detail"]["active_job"] == job.json()["id"]
    finally:
        client.post(f"/train/{job.json()['id']}/cancel", headers=H)
