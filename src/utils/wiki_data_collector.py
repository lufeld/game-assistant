from typing import Any, Optional

import httpx

BASE_API_URL = "https://minecraft.wiki/api.php"
BASE_PAGE_URL = "https://minecraft.wiki/"
DEFAULT_USER_AGENT = "game-assistant-wiki-fetcher/1.0"

SECTION_BLACKLIST = {
    "Sounds",
    "Achievements",
    # "Advancements",
    "Videos",
    "History",
    "Issues",
    "Trivia",
    "Gallery",
    "References",
    "See also",
    "References",
    "Tutorial videos",
    "External links",
    "Designs",
    #"Navigation",
}
    

class WikiDataCollector:
    def __init__(self):
        self.client = self.__make_client()

    @staticmethod
    def __make_client() -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        )

    def __request_json(self, params: dict[str, Any]) -> dict[str, Any]:
        response = self.client.get(BASE_API_URL, params=params)
        response.raise_for_status()
        payload = response.json()

        if "error" in payload:
            raise RuntimeError(f"minecraft.wiki API error: {payload['error']}")

        return payload

    def __request_wikipage_infos(self, page_titles: list[str]) -> dict[str, Any]:
        params = {
            "action": "query",
            "format": "json",
            "prop": "info",
            "redirects": 1,
            "titles": "|".join(page_titles),
        }
        return self.__request_json(params)

    def __request_wikipage_layout(self, page_title: str) -> dict[str, Any]:
        params = {
            "action": "parse",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
            "page": page_title,
            "prop": "sections|categories",
        }
        return self.__request_json(params)

    def __request_wikipage_section_content(self, page_title: str, section_index: int) -> dict[str, Any]:
        params = {
            "action": "parse",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
            "page": page_title,
            "prop": "wikitext",
            "section": section_index,
        }
        return self.__request_json(params)

    def __request_wikipage_all_sections_content(self, page_title: str) -> dict[str, Any]:
        params = {
            "action": "parse",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
            "page": page_title,
            "prop": "wikitext",
            "section": "all",
        }
        return self.__request_json(params)

    def __parse_wiki_page_info(self, info: dict[str, Any]) -> dict[str, int]:
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

    def __parse_wiki_page_categories(self, layout: dict[str, Any]) -> list[str]:
        if not layout:
            return []

        categories = layout.get("parse", {}).get("categories", [])
        category_titles = [cat.get("category") for cat in categories if "hidden" not in cat]

        return category_titles

    def __parse_wiki_page_sections(self, layout: dict[str, Any], toclevel: int = 1) -> list[dict[str, Any]]:
        if not layout:
            return []

        relevant_fields = ["toclevel", "level", "line", "number", "index", "fromtitle"]

        sections = layout.get("parse", {}).get("sections", [])
        filtered_sections = [sec for sec in sections if sec.get("toclevel") <= toclevel and sec.get("line") not in SECTION_BLACKLIST]
        filtered_sections = [{k: v for k, v in sec.items() if k in relevant_fields} for sec in filtered_sections]

        return filtered_sections

    def try_for_wikipages(self, keywords: list[str]) -> dict[str, int] | None:
        info = self.__request_wikipage_infos(keywords)
        parsed_info = self.__parse_wiki_page_info(info)

        if not parsed_info or len(parsed_info) == 0:
            return None

        # Return the first page ID found
        return parsed_info

    def get_wikipage_sections(self, page_title: str, toclevel: int = 1) -> list[dict[str, Any]]:
        layout = self.__request_wikipage_layout(page_title)
        sections = self.__parse_wiki_page_sections(layout, toclevel)
        return sections

    def get_all_wikipage_sections_content(self, page_title: str) -> dict[str, Any]:
        content = self.__request_wikipage_all_sections_content(page_title)
        return content