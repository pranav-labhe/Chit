import pytest

from pranav.chit.ingest import chunk_text, knowledge_items


def test_chunking_is_bounded_and_overlapping(tmp_path):
    source = tmp_path / "book.md"
    source.write_text("alpha " * 1200, encoding="utf-8")
    items = knowledge_items(source, chunk_chars=500, overlap=100, tags=["book"])
    assert len(items) > 2
    assert all(i["kind"] == "text" and len(i["text"]) <= 500 for i in items)
    assert all(i["tags"] == ["book"] for i in items)
    assert all("book.md#chunk=" in i["source"] for i in items)


def test_chunk_validation():
    with pytest.raises(ValueError):
        chunk_text("x", chunk_chars=100)
    with pytest.raises(ValueError):
        chunk_text("x", chunk_chars=256, overlap=256)


def test_plain_text_and_unknown_text_extensions_are_supported(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("A small note.", encoding="utf-8")
    items = knowledge_items(source)
    assert items[0]["text"] == "A small note."

    source2 = tmp_path / "notes.custom"
    source2.write_text("Custom text.", encoding="utf-8")
    assert knowledge_items(source2)[0]["text"] == "Custom text."
