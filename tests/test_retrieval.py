import pytest

from trustrag.chunking import chunk_markdown
from trustrag.retriever import MODES


def test_chunking_keeps_heading_context():
    chunks = chunk_markdown("doc.md", "# Title\n\n## Billing\n\nPay monthly.\n\n### Refunds\n\nWithin 7 days.\n")
    assert [c.heading for c in chunks] == ["Billing", "Billing > Refunds"]
    assert all(c.title == "Title" for c in chunks)
    assert "Billing > Refunds" in chunks[1].embed_text


def test_long_paragraph_is_split_with_overlap():
    para = " ".join(f"Sentence number {i} says something useful." for i in range(60))
    chunks = chunk_markdown("long.md", f"# T\n\n{para}\n", max_chars=300)
    assert len(chunks) > 3 and all(len(c.text) <= 400 for c in chunks)


def test_poisoned_chunk_is_quarantined(rag):
    assert [c.id for c in rag.retriever.quarantined] == ["community_tips-001"]
    for mode in MODES:
        hits = rag.retriever.search("refund window for annual plans", k=10, mode=mode)
        assert all(not h.chunk.flagged for h in hits)


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_finds_the_right_document(rag, mode):
    hits = rag.retriever.search("What uptime does the Enterprise SLA guarantee?", k=4, mode=mode)
    assert any(h.chunk.source == "sla.md" for h in hits)


def test_unrelated_query_has_low_coverage(rag):
    hits = rag.retriever.search("who won the football world cup", k=4)
    assert max((h.coverage for h in hits), default=0) < rag.s.min_coverage


def test_invalid_mode_rejected(rag):
    with pytest.raises(ValueError):
        rag.retriever.search("x", mode="nope")
