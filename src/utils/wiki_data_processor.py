"""Small source-level wikitext parsing experiment.

Unlike the API fetcher, this module works on raw MediaWiki markup. It keeps
template values in their original form because Minecraft Wiki templates need
wiki-specific rendering rules that a generic parser cannot infer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest import result

from dotenv import parser
import wikitextparser as wtp


DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "diamond_sword.wikitext"


def _template_record(template: Any) -> dict[str, Any]:
	return {
		"name": str(template.name).strip(),
		"arguments": {
			str(parameter.name).strip(): str(parameter.value).strip()
			for parameter in template.arguments
		},
	}


def _table_record(table: Any) -> list[list[str]]:
	return [
		[str(cell).strip() for cell in row]
		for row in table.data()
	]


def parse_wikitext(source: str, source_path: Path | None = None) -> dict[str, Any]:
	"""Extract useful source structures without trying to render wiki templates."""

	if "\n" not in source and "\\n" in source:
		source = source.replace("\\n", "\n")

	parsed = wtp.parse(source)
	infoboxes = [
		_template_record(template)
		for template in parsed.templates
		if str(template.name).strip().lower().startswith("infobox")
	]

	sections = []
	for section in parsed.sections:
		title = str(section.title or "").strip()
		if title:
			sections.append({"level": section.level, "title": title})

	return {
		"source": str(source_path) if source_path else None,
		"characters": len(source),
		"infoboxes": infoboxes,
		"sections": sections,
		"templates": [_template_record(template) for template in parsed.templates],
		"links": [str(link.title).strip() for link in parsed.wikilinks],
		"tables": [_table_record(table) for table in parsed.tables],
	}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structures from Minecraft Wiki wikitext")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--pretty", action="store_true", help="Print indented JSON")
    args = parser.parse_args()

    result = parse_wikitext(args.source.read_text(encoding="utf-8"), args.source)
    indent = 2 if args.pretty else None
    with open("diamond_sword_parsed.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=indent)


if __name__ == "__main__":
	main()

