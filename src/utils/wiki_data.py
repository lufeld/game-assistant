from typing import Any, Optional

class WikiPageInfo:
    def __init__(self, pageid: int, title: str):
        self.pageid = pageid
        self.title = title

    @classmethod
    def from_wiki(cls, info: dict[str, Any]) -> dict[str, int]:
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