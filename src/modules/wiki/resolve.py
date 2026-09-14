"""Resolve a free-form query term to a canonical minecraft.wiki page title.

fetch.py trusts whatever title it's given and hard-errors if the page
doesn't exist, so this module is what makes sure it never gets a bad one.
A cheap query+info call handles casing and real redirects and, as a free
side effect, always returns the page's current revid - which is also how
callers know whether fetch.py's cached wikitext is stale. When that direct
lookup misses, a full-text search is the fallback for anything MediaWiki
can't redirect on its own (typos, plurals, loose phrasing). Every successful
resolution is cached so the same fallback search never runs twice for the
same term.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

try:
    from .fetch import BASE_API_URL, DEFAULT_CACHE_DIR, make_client
except ImportError:
    from fetch import BASE_API_URL, DEFAULT_CACHE_DIR, make_client

ALIASES_FILENAME = "aliases.json"


class PageNotFound(Exception):
    """No minecraft.wiki page could be resolved for a term."""


@dataclass(slots=True)
class ResolvedTitle:
    term: str
    title: str
    pageid: int
    lastrevid: int
    matched_via: str  # "alias" | "direct" | "search"
    alternates: tuple[str, ...] = ()  # other search candidates, when matched_via == "search"


def _aliases_path(cache_dir: Path) -> Path:
    return cache_dir / ALIASES_FILENAME


def _load_aliases(cache_dir: Path) -> dict[str, str]:
    path = _aliases_path(cache_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _remember_alias(cache_dir: Path, term: str, title: str) -> None:
    path = _aliases_path(cache_dir)
    aliases = _load_aliases(cache_dir)
    aliases[term.lower()] = title
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")


def _lookup_info(client: httpx.Client, title: str) -> dict | None:
    """Cheap existence + redirect + revid check. None if the title doesn't exist."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "info",
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    response = client.get(BASE_API_URL, params=params)
    response.raise_for_status()
    page = response.json()["query"]["pages"][0]
    return None if page.get("missing") else page


def _search_candidates(client: httpx.Client, term: str, limit: int = 3) -> list[str]:
    """Full-text search fallback for terms MediaWiki can't redirect on its own.

    Ranked by keyword co-occurrence across the whole article body, not by
    concept match - the top hit is a best guess, not a resolved title.
    """
    params = {
        "action": "query",
        "list": "search",
        "srsearch": term,
        "srlimit": limit,
        "format": "json",
        "formatversion": 2,
    }
    response = client.get(BASE_API_URL, params=params)
    response.raise_for_status()
    results = response.json()["query"]["search"]
    return [r["title"] for r in results]


def resolve_title(
    term: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    client: httpx.Client | None = None,
) -> ResolvedTitle:
    """Turn a query term into a canonical, currently-existing page title."""
    aliased_title = _load_aliases(cache_dir).get(term.lower())

    owns_client = client is None
    client = client or make_client()
    try:
        if aliased_title is not None:
            info = _lookup_info(client, aliased_title)
            if info is not None:
                return ResolvedTitle(term, info["title"], info["pageid"], info["lastrevid"], "alias")
            # The page behind the old alias is gone (renamed/deleted) - re-resolve below.

        info = _lookup_info(client, term)
        if info is not None:
            # Not aliased: a direct hit costs the same one lookup either way.
            return ResolvedTitle(term, info["title"], info["pageid"], info["lastrevid"], "direct")

        candidates = _search_candidates(client, term)
        if candidates:
            info = _lookup_info(client, candidates[0])
            if info is not None:
                _remember_alias(cache_dir, term, info["title"])
                return ResolvedTitle(
                    term, info["title"], info["pageid"], info["lastrevid"], "search",
                    alternates=tuple(candidates[1:]),
                )

        raise PageNotFound(f"No minecraft.wiki page found for {term!r}")
    finally:
        if owns_client:
            client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resolve a term to a minecraft.wiki page title")
    parser.add_argument("term")
    args = parser.parse_args()

    try:
        resolved = resolve_title(args.term)
    except PageNotFound as exc:
        print(exc)
    else:
        print(f"{resolved.term!r} -> {resolved.title!r}  (via {resolved.matched_via}, revid {resolved.lastrevid})")
        if resolved.alternates:
            print(f"  runner-ups: {', '.join(resolved.alternates)}")
