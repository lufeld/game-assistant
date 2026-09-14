"""Fetch whole-page wikitext from minecraft.wiki, cached to disk.

One page = one API call = one cache file. A page already on disk is never
re-fetched unless the caller asks for a refresh.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

BASE_API_URL = "https://minecraft.wiki/api.php"
BASE_PAGE_URL = "https://minecraft.wiki/wiki/"
DEFAULT_USER_AGENT = "game-assistant-wiki-fetcher/1.0"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "wiki_cache"


@dataclass(slots=True)
class WikiPageRaw:
    title: str
    pageid: int
    revid: int
    url: str
    wikitext: str
    fetched_at: str
    # Defaulted so cache files written before this field existed still load
    # via WikiPageRaw(**data) - they just report no categories until re-fetched.
    categories: list[str] = field(default_factory=list)


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    )


def _slugify(title: str) -> str:
    # Lowercased so "diamond sword" and "Diamond Sword" share one cache
    # file - fetch.py doesn't know these are the same page, only the slug does.
    slug = re.sub(r"[^a-z0-9._-]+", "_", title.lower()).strip("_")
    return slug or "page"


def _cache_path(title: str, cache_dir: Path) -> Path:
    return cache_dir / f"{_slugify(title)}.json"


def fetch_page_wikitext(client: httpx.Client, title: str) -> WikiPageRaw:
    """Call the API once and return the page's full wikitext."""
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
        "page": title,
        "prop": "wikitext|revid|categories",
    }
    response = client.get(BASE_API_URL, params=params)
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        raise RuntimeError(f"minecraft.wiki API error for {title!r}: {payload['error']}")

    parse = payload["parse"]
    canonical_title = parse["title"]
    # "hidden" is only present (and true) on wiki-housekeeping categories
    # (tracking pages needing cleanup, etc.) - not real classification.
    categories = [
        cat["category"].replace("_", " ")
        for cat in parse.get("categories", [])
        if not cat.get("hidden")
    ]

    return WikiPageRaw(
        title=canonical_title,
        pageid=parse["pageid"],
        revid=parse["revid"],
        url=f"{BASE_PAGE_URL}{quote(canonical_title.replace(' ', '_'))}",
        wikitext=parse["wikitext"],
        fetched_at=datetime.now(timezone.utc).isoformat(),
        categories=categories,
    )


def _read_cache(path: Path) -> WikiPageRaw:
    data = json.loads(path.read_text(encoding="utf-8"))
    return WikiPageRaw(**data)


def _write_cache(path: Path, page: WikiPageRaw) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(page), ensure_ascii=False, indent=2), encoding="utf-8")


def get_page(
    title: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    force_refresh: bool = False,
    client: httpx.Client | None = None,
) -> WikiPageRaw:
    """Return a page's wikitext - from disk if cached, from the API otherwise."""
    cache_path = _cache_path(title, cache_dir)

    if not force_refresh and cache_path.exists():
        return _read_cache(cache_path)

    owns_client = client is None
    client = client or make_client()
    try:
        page = fetch_page_wikitext(client, title)
    finally:
        if owns_client:
            client.close()

    _write_cache(_cache_path(page.title, cache_dir), page)
    return page


def peek_cached_revid(title: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> int | None:
    """Return the revid already on disk for this title, or None if uncached."""
    path = _cache_path(title, cache_dir)
    if not path.exists():
        return None
    return _read_cache(path).revid


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch one minecraft.wiki page's wikitext")
    parser.add_argument("title")
    parser.add_argument("--force", action="store_true", help="Ignore the cache and re-fetch")
    args = parser.parse_args()

    page = get_page(args.title, force_refresh=args.force)
    #page = get_page(title, force_refresh=force)
    print(f"{page.title}  (revid {page.revid}, {len(page.wikitext)} chars)")
    print(f"cached at {_cache_path(page.title, DEFAULT_CACHE_DIR)}")
