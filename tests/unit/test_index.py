from langchain_core.documents import Document

from obslab.app import check_index_meta
from obslab.config import Settings
from obslab.rag import index
from obslab.rag.providers import HashingEmbeddings


def test_build_writes_metadata_next_to_the_index(tmp_path):
    path = tmp_path / "index.json"
    docs = [Document(page_content="etcd snapshot save", metadata={"source": "etcd.md"})]
    index.build(docs, HashingEmbeddings(), path, meta={"provider": "fake", "embed_model": "fake-embed"})
    assert index.load_meta(path) == {"provider": "fake", "embed_model": "fake-embed", "chunks": 1}
    assert len(index.load(path, HashingEmbeddings()).store) == 1


def test_missing_index_says_how_to_build_it(tmp_path):
    try:
        index.load(tmp_path / "nope.json", HashingEmbeddings())
    except FileNotFoundError as e:
        assert "obslab ingest" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_meta_check_rejects_an_index_built_with_another_model():
    fake = Settings(provider="fake")
    ollama = Settings(provider="ollama", embed_model="nomic-embed-text")
    assert check_index_meta(fake, {"embed_model": "fake-embed"}) is None
    assert check_index_meta(ollama, {"embed_model": "nomic-embed-text"}) is None
    assert check_index_meta(fake, None) is None                      # older index without metadata
    assert "ingest" in check_index_meta(ollama, {"embed_model": "fake-embed"})
