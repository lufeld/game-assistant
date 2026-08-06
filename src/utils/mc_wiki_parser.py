"""Fetch player-focused data from minecraft.wiki.

This module intentionally keeps the first data shape simple:
- collect pages from selected categories
- fetch the rendered page content through the MediaWiki API
- normalize the HTML into plain text
- export one JSON file per page plus a manifest

That gives us a clean intermediate format for later chunking, embeddings,
and graph construction.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from html import unescape
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup


BASE_API_URL = "https://minecraft.wiki/api.php"
BASE_PAGE_URL = "https://minecraft.wiki/wiki/"
DEFAULT_USER_AGENT = "game-assistant-wiki-fetcher/1.0"
DEFAULT_CATEGORIES = (
	"Tutorials",
	"Items",
	"Biomes",
	"Blocks",
	"Mobs",
	"Farming",
	"Food",
	"Enchanting",
	"Potions",
	"Structures",
	"Transport",
	"Combat",
	"Exploration",
	"Redstone",
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "game_info" / "minecraft_wiki"


@dataclass(slots=True)
class WikiSection:
	index: str
	level: int
	title: str
	anchor: str


@dataclass(slots=True)
class WikiPage:
	pageid: int
	title: str
	display_title: str
	url: str
	source_categories: list[str]
	categories: list[str]
	sections: list[WikiSection]
	summary: str
	plain_text: str
	fetched_at: str


def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def _make_client() -> httpx.Client:
	return httpx.Client(
		timeout=httpx.Timeout(30.0, connect=10.0),
		headers={"User-Agent": DEFAULT_USER_AGENT},
		follow_redirects=True,
	)


def _request_json(client: httpx.Client, params: dict[str, Any]) -> dict[str, Any]:
	response = client.get(BASE_API_URL, params=params)
	response.raise_for_status()
	payload = response.json()

	if "error" in payload:
		raise RuntimeError(f"minecraft.wiki API error: {payload['error']}")

	return payload


def _normalize_category_title(category: str) -> str:
	category = category.strip()
	if category.lower().startswith("category:"):
		return category
	return f"Category:{category}"


def _slugify(title: str) -> str:
	slug = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
	return slug or "page"


def _clean_html_to_text(html: str) -> str:
	soup = BeautifulSoup(html, "lxml")

	for selector in ("script", "style", "sup.reference", "table.infobox", "div.navbox", "ol.references"):
		for element in soup.select(selector):
			element.decompose()

	text = soup.get_text("\n")
	text = text.replace("\r", "\n")
	text = re.sub(r"[ \t]+", " ", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


def _extract_summary(plain_text: str) -> str:
	for paragraph in (block.strip() for block in plain_text.split("\n\n")):
		if paragraph:
			return paragraph
	return ""


def fetch_category_members(
	client: httpx.Client,
	category: str,
	*,
	recursive: bool = True,
	max_pages: int | None = None,
) -> list[dict[str, Any]]:
	"""Fetch main-namespace pages from a wiki category.

	When recursive is enabled, subcategories are traversed too.
	The return value is deduplicated by pageid/title.
	"""

	root_category = _normalize_category_title(category)
	pending_categories = [root_category]
	seen_pages: set[str] = set()
	collected: list[dict[str, Any]] = []

	while pending_categories:
		current_category = pending_categories.pop(0)
		continue_token: str | None = None

		while True:
			params: dict[str, Any] = {
				"action": "query",
				"list": "categorymembers",
				"cmtitle": current_category,
				"cmlimit": "50",
				"format": "json",
			}
			params["cmnamespace"] = "0|14" if recursive else 0
			if recursive:
				params["cmtype"] = "page|subcat"
			if continue_token:
				params["cmcontinue"] = continue_token

			payload = _request_json(client, params)
			members = payload.get("query", {}).get("categorymembers", [])

			for member in members:
				title = member.get("title", "")
				pageid = member.get("pageid")
				ns = member.get("ns")

				if ns == 14 and recursive:
					pending_categories.append(title)
					continue

				if ns != 0:
					continue

				page_key = str(pageid or title)
				if page_key in seen_pages:
					continue

				seen_pages.add(page_key)
				collected.append(
					{
						"pageid": pageid,
						"title": title,
						"source_category": root_category.removeprefix("Category:"),
					}
				)

				if max_pages is not None and len(collected) >= max_pages:
					return collected

			continue_token = payload.get("continue", {}).get("cmcontinue")
			if not continue_token:
				break

	return collected


def fetch_page(client: httpx.Client, title: str, source_categories: Sequence[str] | None = None) -> WikiPage:
	"""Fetch one wiki page and normalize it into a player-friendly record."""

	params = {
		"action": "parse",
		"page": title,
		"prop": "sections|text|categories|displaytitle",
		"format": "json",
	}
	payload = _request_json(client, params)
	parse = payload.get("parse")
	if not parse:
		raise RuntimeError(f"minecraft.wiki did not return parse data for {title!r}")

	html_text = parse.get("text", {}).get("*") or ""
	plain_text = _clean_html_to_text(html_text)
	sections = [
		WikiSection(
			index=str(section.get("index", "")),
			level=int(section.get("level", 0) or 0),
			title=unescape(str(section.get("line", ""))),
			anchor=unescape(str(section.get("anchor", ""))),
		)
		for section in parse.get("sections", [])
	]
	categories = [unescape(str(category.get("*") or category.get("title") or "")) for category in parse.get("categories", [])]
	page_title = str(parse.get("title") or title)
	display_title = BeautifulSoup(str(parse.get("displaytitle") or page_title), "lxml").get_text(" ", strip=True)

	return WikiPage(
		pageid=int(parse.get("pageid") or 0),
		title=page_title,
		display_title=display_title,
		url=f"{BASE_PAGE_URL}{quote(page_title.replace(' ', '_'))}",
		source_categories=list(source_categories or []),
		categories=categories,
		sections=sections,
		summary=_extract_summary(plain_text),
		plain_text=plain_text,
		fetched_at=_utc_now_iso(),
	)


def fetch_player_focused_wiki_data(
	categories: Sequence[str] = DEFAULT_CATEGORIES,
	*,
	recursive: bool = True,
	max_pages_per_category: int | None = None,
	max_total_pages: int | None = None,
	pause_seconds: float = 0.0,
) -> list[WikiPage]:
	"""Fetch player-relevant pages from minecraft.wiki.

	The returned records are already normalized for later chunking and RAG.
	"""

	collected_pages: list[WikiPage] = []
	seen_titles: set[str] = set()

	with _make_client() as client:
		for category in categories:
			members = fetch_category_members(
				client,
				category,
				recursive=recursive,
				max_pages=max_pages_per_category,
			)

			for member in members:
				title = member["title"]
				if title in seen_titles:
					continue

				page = fetch_page(client, title, source_categories=[member["source_category"]])
				collected_pages.append(page)
				seen_titles.add(title)

				if pause_seconds > 0:
					time.sleep(pause_seconds)

				if max_total_pages is not None and len(collected_pages) >= max_total_pages:
					return collected_pages

	return collected_pages


def export_wiki_pages(pages: Sequence[WikiPage], output_dir: Path, *, overwrite: bool = False) -> Path:
	"""Write one JSON file per page plus a manifest file."""

	pages_dir = output_dir / "pages"
	pages_dir.mkdir(parents=True, exist_ok=True)

	manifest = {
		"source": "minecraft.wiki",
		"fetched_at": _utc_now_iso(),
		"page_count": len(pages),
		"pages": [],
	}

	for page in pages:
		record = asdict(page)
		filename = f"{_slugify(page.title)}.json"
		output_path = pages_dir / filename

		if output_path.exists() and not overwrite:
			logging.info("Skipping existing file: %s", output_path)
		else:
			with output_path.open("w", encoding="utf-8") as handle:
				json.dump(record, handle, ensure_ascii=False, indent=2)

		manifest["pages"].append(
			{
				"title": page.title,
				"display_title": page.display_title,
				"pageid": page.pageid,
				"url": page.url,
				"file": f"pages/{filename}",
				"source_categories": page.source_categories,
				"categories": page.categories,
			}
		)

	manifest_path = output_dir / "manifest.json"
	with manifest_path.open("w", encoding="utf-8") as handle:
		json.dump(manifest, handle, ensure_ascii=False, indent=2)

	return manifest_path


def build_argument_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Fetch player-focused data from minecraft.wiki")
	parser.add_argument(
		"--categories",
		nargs="*",
		default=list(DEFAULT_CATEGORIES),
		help="Category names to fetch, without the Category: prefix.",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=DEFAULT_OUTPUT_DIR,
		help="Directory for exported wiki data.",
	)
	parser.add_argument(
		"--max-pages-per-category",
		type=int,
		default=None,
		help="Stop after this many pages from each category.",
	)
	parser.add_argument(
		"--max-total-pages",
		type=int,
		default=None,
		help="Stop after this many pages overall.",
	)
	parser.add_argument(
		"--no-recursive",
		action="store_true",
		help="Do not traverse subcategories.",
	)
	parser.add_argument(
		"--pause-seconds",
		type=float,
		default=0.0,
		help="Pause between page fetches to be polite to the wiki.",
	)
	parser.add_argument(
		"--overwrite",
		action="store_true",
		help="Overwrite existing page files.",
	)
	return parser


def main() -> None:
	logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

	parser = build_argument_parser()
	args = parser.parse_args()

	pages = fetch_player_focused_wiki_data(
		categories=args.categories,
		recursive=not args.no_recursive,
		max_pages_per_category=args.max_pages_per_category,
		max_total_pages=args.max_total_pages,
		pause_seconds=args.pause_seconds,
	)

	manifest_path = export_wiki_pages(pages, args.output_dir, overwrite=args.overwrite)

	print(f"Fetched {len(pages)} pages from minecraft.wiki")
	print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
	main()
