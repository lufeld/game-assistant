"""Persist a parsed wiki page into the Game DB: a SQLite ingestion ledger + Chroma prose.

fetch.py caches raw wikitext; parse.py turns one page into a ParsedPage
(summary + section prose, with tables/infobox/recipes/drops already folded
in as markdown). This module writes that prose into Chroma and records the
page in a small SQLite ledger.

There is deliberately no separate facts/edges schema here. That existed to
feed graph edges (crafted_from, dropped_by, related), and the graph is
shelved for now - its only real signal would have come from interpreting
recipe/drop templates, which is a bigger job than extraction, and the raw
wikilink-based "related" edges tried in an earlier version were mostly
noise (confirmed on real pages - 90+ edges per page, nearly all incidental
mentions, not meaningful game relationships). Nothing is lost by not
persisting facts/recipes/drops as separate rows: fetch.py's raw wikitext
cache means parse_page() can be re-run later if a typed store is ever
worth building.

Storing a page replaces whatever prose was stored for it before, so a page
that shrinks on re-fetch (fewer sections) doesn't leave stale chunks behind
- important once lazy re-fetching on a changed revid is wired up.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

try:
    from .fetch import _slugify
    from .parse import ParsedPage
except ImportError:
    from fetch import _slugify
    from parse import ParsedPage

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "game_db.sqlite3"
DEFAULT_CHROMA_DIR = Path(__file__).resolve().parents[3] / "data" / "chroma_db"
PROSE_COLLECTION = "wiki_prose"
MAX_CHUNK_WORDS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    title TEXT PRIMARY KEY,
    pageid INTEGER NOT NULL,
    revid INTEGER NOT NULL,
    url TEXT NOT NULL,
    stored_at TEXT NOT NULL
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def _prose_collection(chroma_dir: Path):
    client = chromadb.PersistentClient(path=str(chroma_dir))
    ef = embedding_functions.ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])
    return client.get_or_create_collection(PROSE_COLLECTION, embedding_function=ef)


def _split_large_section(text: str, max_words: int = MAX_CHUNK_WORDS) -> list[str]:
    """Split by paragraph when a section is too big for one embedding to see in full.

    all-MiniLM-L6-v2 truncates at 256 tokens - an unsplit section would still be
    stored whole, but only its first ~200 words would ever be embedded.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    word_count = 0

    for paragraph in paragraphs:
        words = len(paragraph.split())
        if current and word_count + words > max_words:
            chunks.append("\n\n".join(current))
            current, word_count = [], 0
        current.append(paragraph)
        word_count += words

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _prose_chunks(page: ParsedPage) -> list[tuple[str, str, int, str]]:
    """Flatten the summary + sections into (section_title, section_level, chunk_index, text)."""
    sources = [("Summary", 0, page.summary)] if page.summary else []
    sources += [(s.title, s.level, s.text) for s in page.sections]

    chunks = []
    for title, level, text in sources:
        pieces = _split_large_section(text)
        for index, piece in enumerate(pieces):
            chunks.append((title, level, index, piece))
    return chunks


def store_page(
    *,
    title: str,
    pageid: int,
    revid: int,
    url: str,
    page: ParsedPage,
    db_path: Path = DEFAULT_DB_PATH,
    chroma_dir: Path = DEFAULT_CHROMA_DIR,
) -> None:
    """Write one page's prose to Chroma and record it in the pages ledger."""
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO pages (title, pageid, revid, url, stored_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(title) DO UPDATE SET "
            "pageid=excluded.pageid, revid=excluded.revid, url=excluded.url, stored_at=excluded.stored_at",
            (title, pageid, revid, url, datetime.now(timezone.utc).isoformat()),
        )

    collection = _prose_collection(chroma_dir)
    existing = collection.get(where={"page_title": title})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    slug = _slugify(title)
    ids, documents, metadatas = [], [], []
    for section_title, level, chunk_index, text in _prose_chunks(page):
        ids.append(f"{slug}__{_slugify(section_title)}__{chunk_index}")
        # TODO: consider reworking the embedding - some prose chunks are just a few words
        documents.append(text)
        metadatas.append({"page_title": title, "section_title": section_title, "level": level})

    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)


def peek_stored_revid(title: str, db_path: Path = DEFAULT_DB_PATH) -> int | None:
    """Return the revid this page was last *stored* at, or None if it's never been stored.

    Distinct from fetch.py's peek_cached_revid: that answers "do I have the
    raw wikitext on disk", this answers "is wiki_prose actually current for
    this page" - a page can be cached without ever having been stored (a
    previous run fetched but didn't finish ingesting), so the orchestrator's
    staleness check needs this, not the raw-cache revid.
    """
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT revid FROM pages WHERE title = ?", (title,)).fetchone()
    return row[0] if row else None


def query_prose(
    page_title: str,
    query_text: str,
    *,
    n_results: int = 5,
    chroma_dir: Path = DEFAULT_CHROMA_DIR,
) -> list[str]:
    """Semantic search within one already-stored page's chunks."""
    collection = _prose_collection(chroma_dir)
    results = collection.query(query_texts=[query_text], where={"page_title": page_title}, n_results=n_results)
    return results["documents"][0] if results["documents"] else []


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fetch import get_page
    from parse import parse_page
    from resolve import PageNotFound, resolve_title

    parser = argparse.ArgumentParser(description="Resolve, fetch, parse, and store one wiki page")
    parser.add_argument("term")
    args = parser.parse_args()

    try:
        resolved = resolve_title(args.term)
    except PageNotFound as exc:
        print(exc)
        raise SystemExit(1)

    raw = get_page(resolved.title)
    parsed = parse_page(raw.wikitext)
    store_page(title=resolved.title, pageid=resolved.pageid, revid=resolved.lastrevid, url=raw.url, page=parsed)

    chunk_count = len(_prose_chunks(parsed))
    print(f"stored {resolved.title!r}: {chunk_count} prose chunks")
