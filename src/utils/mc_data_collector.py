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


BASE_API_URL = "https://minecraft.wiki/api.php"
BASE_PAGE_URL = "https://minecraft.wiki/"
DEFAULT_USER_AGENT = "game-assistant-wiki-fetcher/1.0"

def make_client() -> httpx.Client:
	return httpx.Client(
		timeout=httpx.Timeout(30.0, connect=10.0),
		headers={"User-Agent": DEFAULT_USER_AGENT},
		follow_redirects=True,
	)

def request_json(client: httpx.Client, params: dict[str, Any]) -> dict[str, Any]:
	response = client.get(BASE_API_URL, params=params)
	response.raise_for_status()
	payload = response.json()

	if "error" in payload:
		raise RuntimeError(f"minecraft.wiki API error: {payload['error']}")

	return payload

def request_page_info(client: httpx.Client, page_title: str) -> dict[str, Any]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "info",
        "titles": page_title,
    }
    return request_json(client, params)

def request_page_layout(client: httpx.Client, page_title: str) -> dict[str, Any]:
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
        "page": page_title,
        "prop": "sections|categories",
    }
    return request_json(client, params)

def request_page_section_content(client: httpx.Client, page_title: str, section_index: int) -> dict[str, Any]:
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
        "page": page_title,
        "prop": "wikitext",
        "section": section_index,
    }
    return request_json(client, params)

if __name__ == "__main__":
    """Sample usage of the get_raw_minecraft_data function."""

    client = make_client()

    # save html content of a specific Minecraft wiki page to a file
    # with open("diamond_sword.html", "w", encoding="utf-8") as f:
    #     f.write(request_json(client, {"action": "parse", "page": "Diamond Sword", "format": "json"})["parse"]["text"]["*"])

    #pprint(request_page_layout(client, "Diamond Sword"))
    #reply = client.get("https://minecraft.wiki/api.php?action=parse&page=Diamond_Sword&redirects=1&prop=wikitext&section=0&format=json&formatversion=2")
    reply = request_page_section_content(client, "Diamond Sword", 0)
    pprint(reply)
    # save reply to a file
    with open("diamond_sword_section_1.json", "w", encoding="utf-8") as f:
        json.dump(reply, f, indent=4)