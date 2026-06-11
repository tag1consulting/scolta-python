"""PythonIndexer facade behaviour.

Regression: process_chunk hardcoded {"language": "en"} into the fresh
BuildIntent instead of the language the indexer was constructed with.
"""

from scolta.content import ContentItem
from scolta.index.indexer import PythonIndexer


def _item():
    return ContentItem(
        "1", "Bonjour", "<h1>Bonjour</h1><p>Le monde entier.</p>",
        "/bonjour", "2024-01-01", "Site", "fr",
    )


def test_process_chunk_uses_configured_language(tmp_path):
    idx = PythonIndexer(str(tmp_path / "s"), str(tmp_path / "o"), language="fr")
    captured = {}
    original_prepare = idx.coordinator.prepare

    def spy(intent):
        captured["source_meta"] = intent.source_meta
        return original_prepare(intent)

    idx.coordinator.prepare = spy
    idx.process_chunk([_item()], 0, total_pages=1)

    assert captured["source_meta"] == {"language": "fr"}
