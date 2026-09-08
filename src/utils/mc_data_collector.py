from minebase import load_version, load_common_data, Edition
from pprint import pprint  # pretty print (for easier readability)

def get_raw_minecraft_data(version: str = "1.21.6", edition: Edition = Edition.PC) -> dict:
    common_data = load_common_data(edition)
    version_info = load_version(version, edition)

    status_server_bound_packets = version_info["protocol"]["status"]["toServer"]["types"]["packet"]

    return version_info

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

from wiki_data_collector import WikiDataCollector


BASE_API_URL = "https://minecraft.wiki/api.php"
BASE_PAGE_URL = "https://minecraft.wiki/"
DEFAULT_USER_AGENT = "game-assistant-wiki-fetcher/1.0"

def make_client() -> httpx.Client:
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

def request_wikipage_info(client: httpx.Client, page_title: str) -> dict[str, Any]:
    return request_wikipage_info_many(client, [page_title])

def request_wikipage_info_many(client: httpx.Client, page_titles: list[str]) -> dict[str, Any]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "info",
        "redirects": 1,
        "titles": "|".join(page_titles),
    }
    return _request_json(client, params)

def request_wikipage_layout(client: httpx.Client, page_title: str) -> dict[str, Any]:
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
        "page": page_title,
        "prop": "sections|categories",
    }
    return _request_json(client, params)

def request_wikipage_section_content(client: httpx.Client, page_title: str, section_index: int) -> dict[str, Any]:
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
        "page": page_title,
        "prop": "wikitext",
        "section": section_index,
    }
    return _request_json(client, params)

def parse_wiki_page_info(cls, info: dict[str, Any]) -> dict[str, int]:
        if not info:
            return {}

        # query is the response wrapping the normalized/redirected page and 
        query = info.get("query", {})
        pages = query.get("pages", {})

        parsed_pages = {}

        for pageid, page in pages.items():
            if pageid == "-1":
                # Page not found
                continue
            title = page.get("title")
            parsed_pages[title] = int(pageid)

        return parsed_pages

def parse_wiki_page_categories(layout: dict[str, Any]) -> list[str]:
    if not layout:
        return []

    categories = layout.get("parse", {}).get("categories", [])
    category_titles = [cat.get("category") for cat in categories if "hidden" not in cat]

    return category_titles

def parse_wiki_page_sections(layout: dict) -> list[dict]:
    if not layout:
        return []

    sections = layout.get("parse", {}).get("sections", [])
    result = []

    for section in sections:
        title = section.get("line", "")
        if not title:
            continue

        clean_title = unescape(title)
        clean_title = re.sub(r"<.*?>", "", clean_title).strip()

        raw_level = section.get("level")
        try:
            normalized_level = max(1, int(raw_level) - 1)
        except (TypeError, ValueError):
            normalized_level = 1

        result.append({
            "title": clean_title,
            "index": section.get("index"),
            "level": normalized_level,
            "number": section.get("number"),
        })

    return result


def group_wiki_page_sections(layout: dict) -> list[dict]:
    """Group sections into a top-level tree with child subsections.

    Example output:
    [
      {"title": "Obtaining", "index": "1", "level": 1, "number": "1", "children": [
        {"title": "Generated loot", "index": "2", "level": 2, "number": "1.1"},
        {"title": "Crafting", "index": "3", "level": 2, "number": "1.2"}
      ]},
      ...
    ]
    """
    sections = parse_wiki_page_sections(layout)
    if not sections:
        return []

    grouped: list[dict] = []
    current_top: dict | None = None

    for section in sections:
        level = int(section.get("level", 1) or 1)
        node = {
            "title": section["title"],
            "index": section.get("index"),
            "level": level,
            "number": section.get("number"),
        }

        if level == 1:
            current_top = {**node, "children": []}
            grouped.append(current_top)
        elif current_top is not None:
            current_top["children"].append(node)

    return grouped

if __name__ == "__main__":
    """Sample usage of the get_raw_minecraft_data function."""

    client = make_client()

    # save html content of a specific Minecraft wiki page to a file
    # with open("diamond_sword.html", "w", encoding="utf-8") as f:
    #     f.write(request_json(client, {"action": "parse", "page": "Diamond Sword", "format": "json"})["parse"]["text"]["*"])

    #pprint(request_page_layout(client, "Diamond Sword"))
    #reply = client.get("https://minecraft.wiki/api.php?action=parse&page=Diamond_Sword&redirects=1&prop=wikitext&section=0&format=json&formatversion=2")
    
    item = "diamond sword"

    collector = WikiDataCollector()

    info = WikiDataCollector.try_for_wikipages(collector, [item, "strong sword", "slime farm"])
    pprint (info)

    sections = collector.get_wikipage_sections(list(info.keys())[0])
    pprint(sections)

    all_sections_content = collector.get_all_wikipage_sections_content(list(info.keys())[0])
    with open("diamond_sword_all_sections_content.json", "w", encoding="utf-8") as f:
        json.dump(all_sections_content, f, indent=4)

    # info = request_wikipage_info_many(client, [item, "strong sword"])
    # with open("diamond_sword_info.json", "w", encoding="utf-8") as f:
    #     json.dump(info, f, indent=4)

    # layout = request_wikipage_layout(client, item)
    # categories = parse_wiki_page_categories(layout)
    # sections = parse_wiki_page_sections(layout)
    # sections = group_wiki_page_sections(layout)
    # pprint(sections)
    # with open("diamond_sword_layout.json", "w", encoding="utf-8") as f:
    #     json.dump(layout, f, indent=4)

    # content = request_wikipage_section_content(client, item, 1)
    # with open("diamond_sword_section_1.json", "w", encoding="utf-8") as f:
    #     json.dump(content, f, indent=4)

    # pprint(content)

    # save reply to a file
    # with open("diamond_sword_info.json", "w", encoding="utf-8") as f:
    #     json.dump(info, f, indent=4)
    # with open("diamond_sword_layout.json", "w", encoding="utf-8") as f:
    #     json.dump(layout, f, indent=4)
    # with open("diamond_sword_section_1.json", "w", encoding="utf-8") as f:
    #     json.dump(content, f, indent=4)