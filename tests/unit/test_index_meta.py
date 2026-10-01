from pathlib import Path

from obslab.app import check_index_meta
from obslab.config import Settings

SRC = Path(__file__).resolve().parents[2] / "src" / "obslab"


def test_meta_check_rejects_an_index_built_with_another_model():
    fake = Settings(provider="fake")
    ollama = Settings(provider="ollama", embed_model="nomic-embed-text")
    assert check_index_meta(fake, {"embed_model": "fake-embed"}) is None
    assert check_index_meta(ollama, {"embed_model": "nomic-embed-text"}) is None
    assert "ingest" in check_index_meta(ollama, {"embed_model": "fake-embed"})


def test_the_index_only_lives_in_postgresql():
    # One index, in the database. The app has no code path that keeps a copy in a local file.
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for marker in ("OBSLAB_INDEX_PATH", "index.json", ".dump(", "InMemoryVectorStore.load"):
            assert marker not in text, f"{f.name}: {marker}"
