from obslab.rag import corpus


def test_load_and_split(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\n" + "word " * 400, encoding="utf-8")
    (tmp_path / "ignore.bin").write_bytes(b"\x00")
    docs = corpus.load_folder(tmp_path)
    assert [d.metadata["source"] for d in docs] == ["a.md"]
    chunks = corpus.split(docs, chunk_size=300, overlap=50)
    assert len(chunks) > 1 and all(c.metadata["source"] == "a.md" for c in chunks)
