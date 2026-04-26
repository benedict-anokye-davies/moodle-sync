from __future__ import annotations

from moodle_sync.embeddings import HashingEmbedder, get_embedder


def test_missing_sentence_transformers_falls_back_to_hashing_embedder(monkeypatch):
    real_import = __import__

    def blocked_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)

    embedder = get_embedder()

    assert isinstance(embedder, HashingEmbedder)
    assert embedder.embed(["retrieval test"]).shape == (1, 384)
