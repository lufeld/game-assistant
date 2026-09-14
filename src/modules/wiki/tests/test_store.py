"""Tests for store.py - writing a ParsedPage into the pages ledger + Chroma.

No network involved (unlike resolve.py/fetch.py), just local SQLite and
Chroma - so real I/O against a throwaway directory is cheap and reliable
here. Each test gets its own tmp_path, so there's no shared state between
runs and nothing to clean up.
"""

import sqlite3

from parse import ParsedPage, ProseSection
from store import _prose_collection, store_page


def _store(tmp_path, page, *, title="Test Page", revid=100):
    db_path = tmp_path / "game_db.sqlite3"
    chroma_dir = tmp_path / "chroma_db"
    store_page(
        title=title, pageid=1, revid=revid, url="https://example.com/Test_Page",
        page=page, db_path=db_path, chroma_dir=chroma_dir,
    )
    return db_path, chroma_dir


def test_store_page_writes_the_pages_ledger(tmp_path):
    page = ParsedPage(summary="A test summary.", sections=[])
    db_path, _ = _store(tmp_path, page)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT title, revid FROM pages WHERE title = ?", ("Test Page",)).fetchone()
    assert row == ("Test Page", 100)


def test_store_page_upserts_rather_than_duplicating(tmp_path):
    db_path, chroma_dir = _store(tmp_path, ParsedPage(summary="v1", sections=[]), revid=100)
    store_page(
        title="Test Page", pageid=1, revid=200, url="https://example.com/Test_Page",
        page=ParsedPage(summary="v2", sections=[]), db_path=db_path, chroma_dir=chroma_dir,
    )

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT revid FROM pages WHERE title = ?", ("Test Page",)).fetchall()
    assert rows == [(200,)]


def test_store_page_writes_summary_and_section_chunks(tmp_path):
    page = ParsedPage(summary="A test summary.", sections=[ProseSection("Usage", 2, "Some usage text.")])
    _, chroma_dir = _store(tmp_path, page)

    collection = _prose_collection(chroma_dir)
    got = collection.get(where={"page_title": "Test Page"})
    assert sorted(m["section_title"] for m in got["metadatas"]) == ["Summary", "Usage"]


def test_store_page_replaces_stale_chunks_on_reingest(tmp_path):
    """A page that shrinks on re-fetch shouldn't leave orphaned chunks behind."""
    first = ParsedPage(summary="S", sections=[ProseSection("A", 2, "text a"), ProseSection("B", 2, "text b")])
    db_path, chroma_dir = _store(tmp_path, first)

    second = ParsedPage(summary="S", sections=[ProseSection("A", 2, "text a")])
    store_page(
        title="Test Page", pageid=1, revid=200, url="https://example.com/Test_Page",
        page=second, db_path=db_path, chroma_dir=chroma_dir,
    )

    collection = _prose_collection(chroma_dir)
    got = collection.get(where={"page_title": "Test Page"})
    assert sorted(m["section_title"] for m in got["metadatas"]) == ["A", "Summary"]


def test_store_page_splits_long_sections_before_embedding(tmp_path):
    """all-MiniLM-L6-v2 truncates at 256 tokens - a long section must become
    multiple chunks or its tail is never actually searchable."""
    long_text = "\n\n".join(f"Paragraph {i} with some real words in it." for i in range(200))
    page = ParsedPage(summary="", sections=[ProseSection("Usage", 2, long_text)])
    _, chroma_dir = _store(tmp_path, page)

    collection = _prose_collection(chroma_dir)
    got = collection.get(where={"page_title": "Test Page"})
    usage_chunks = [m for m in got["metadatas"] if m["section_title"] == "Usage"]
    assert len(usage_chunks) > 1
