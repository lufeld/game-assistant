"""Parse a minecraft.wiki page's raw wikitext into page-ready prose.

fetch.py hands over one big wikitext string; this module turns it into a
page summary and a list of section chunks, with every table and every
infobox/recipe/drop/spawn-table template already rendered as markdown and
substituted directly at its original position - not stripped, and not
collected separately and appended elsewhere. A rendered markdown block is
just plain text with no wiki syntax, so wikitextparser leaves it alone on
re-parse (verified: a literal "| a | b |" table line doesn't get
reinterpreted as wikitext table syntax, which requires an opening "{|").
Substituting in place means structured content ends up between the same
two sentences it always sat between - e.g. a mob's drop table lands right
after "On death", not after an unrelated "Milking" subsection that happens
to come later in the section.

A few wikitext constructs get resolved before section-splitting even
happens, because wikitextparser's plain_text() doesn't render them, it
deletes them - silently corrupting real content rather than leaving raw
markup behind:
- <br> and <ref>...</ref>: vanish instead of leaving a separator or being
  dropped as a footnote, running adjacent values together
  ("1<br>SE I: 3.5" -> "1SE I: 3.5", "Sharpness<ref>note</ref>" ->
  "Sharpnessnote").
- small inline templates (hp, xp, jebe, in, only, control, code, JE, BE,
  ItemLink/BlockLink/EntityLink/EnvLink, collapse, load advancements):
  {{hp|7}} was getting deleted entirely instead of rendering "7".
- block-level templates (Infobox*, the crafting-family, DropLine, Spawn
  table) and wikitables get rendered as markdown rather than substituted
  inline - flattening a table to tab-mashed plain text loses which row is
  which edition, and simply deleting a drop/spawn table (as plain_text()
  does for anything it doesn't recognize) loses the data entirely.

Infobox fields that are purely image/display metadata (image filenames,
per-variant image group labels, caption/size overrides) are dropped rather
than rendered - a field like "*-2caption: Baby" is meaningless without the
image it labels, and the image itself isn't useful to a text assistant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import wikitextparser as wtp

INFOBOX_PREFIX = "infobox"

# Templates whose fields are worth keeping as a markdown block rather than
# letting plain_text() delete them - the crafting-family (recipes) and
# DropLine (mob drop tables), both confirmed vanishing silently otherwise.
# Spawn table is handled separately (_spawn_table_to_markdown) since its
# fields nest their own Spawn row templates rather than being flat values.
STRUCTURED_TEMPLATES = {
    "crafting", "smelting", "furnace", "smithing", "stonecutting", "brewing",
    "dropline",
}

# Templates whose only job is to display another page's name inline - a
# rendering concern, independent of whether that reference is ever used as
# a graph edge (currently not - see module docstring in store.py).
_NAME_LINK_TEMPLATES = {"itemlink", "blocklink", "entitylink", "envlink"}

_SPAWN_CATEGORY_LABELS = {
    "monster": "Hostile mobs",
    "creature": "Passive mobs",
    "ambient": "Ambient mobs",
    "underground": "Underground mobs",
    "watercreature": "Water creatures",
    "waterambient": "Water ambient mobs",
    "undergroundwatercreature": "Underground water creatures",
}

# Sections that are noise for prose retrieval - the wiki-wide list already
# decided in wiki_data_collector.py's SECTION_BLACKLIST, plus "Data values"
# (ID tables, no narrative text).
SECTION_BLACKLIST = {
    "Sounds", "Achievements", "Videos", "History", "Issues", "Trivia",
    "Gallery", "References", "See also", "Tutorial videos",
    "External links", "Designs", "Navigation", "Data values",
}

_HEADING_RE = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.MULTILINE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_REF_RE = re.compile(r"<ref[^>]*?/>|<ref[^>]*?>.*?</ref>", re.IGNORECASE | re.DOTALL)
_EDITION_NAMES = {"je": "Java Edition", "java": "Java Edition", "be": "Bedrock Edition", "bedrock": "Bedrock Edition"}
_BLOCK_JOIN = "\n\n"

# Infobox fields that are image/display metadata, not game data: image
# filenames (by extension), and the naming conventions confirmed on real
# pages for multi-variant image groups - Cow's Temperate/Cold/Warm textures
# use "*-1size"/"*-2caption"; Cold Ocean's regular/Vibrant-Visuals variants
# use "1-1size"/"2-1size" (no asterisk) - plus group/group2/group3 labels.
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg")
_IMAGE_FIELD_NAME_RE = re.compile(r"image|^[\d*]+-\d+(?:size|caption)?$|^group\d*$", re.IGNORECASE)

# Rendering/display metadata, not game data: exact hex tint values (biome
# grass/foliage/water colors, etc.) inform nothing a player would ask about,
# and the pattern is systematic across every biome infobox on the wiki, not
# a one-off. Name-based rather than value-based, since by the time a field
# like watercolor reaches here its value is already resolved to something
# like "#3D57D6 (Java Edition); #2080C9 (Bedrock Edition)" - no longer a
# bare hex code a value-shape check could catch.
_COLOR_FIELD_NAME_RE = re.compile(r"colou?r", re.IGNORECASE)


def _is_image_field(name: str, value: str) -> bool:
    if _IMAGE_FIELD_NAME_RE.search(name):
        return True
    return value.strip().lower().endswith(_IMAGE_EXTENSIONS)


def _is_color_field(name: str) -> bool:
    return bool(_COLOR_FIELD_NAME_RE.search(name))


def _as_block(text: str) -> str:
    """Wrap block-level content in blank lines so it doesn't run into surrounding prose."""
    return f"\n\n{text}\n\n" if text else ""


def _cell_text(raw: str | None) -> str:
    """Light cleanup for a table cell or infobox value: strip remaining wiki
    markup (links, bold/italics) and keep it on one line.

    raw can be None - Table.data() documents str | None as its cell type,
    for cells left empty by a rowspan/colspan gap (confirmed on a real
    table on "The Nether" page, which crashed here before this check).
    """
    if not raw:
        return ""
    text = wtp.parse(raw).plain_text().strip()
    return re.sub(r"\s+", " ", text)


def _template_fields(template: wtp.Template) -> dict[str, str]:
    return {str(arg.name).strip(): str(arg.value).strip() for arg in template.arguments}


def _fields_to_markdown(fields: dict[str, str]) -> str:
    lines = []
    for name, value in fields.items():
        if _is_image_field(name, value) or _is_color_field(name):
            continue
        text = _cell_text(value)
        if text:
            lines.append(f"- **{name}**: {text}")
    return "\n".join(lines)


def _table_to_markdown(table: wtp.Table) -> str:
    rows = table.data()
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    lines = []
    for i, row in enumerate(rows):
        cells = [_cell_text(cell) for cell in row] + [""] * (width - len(row))
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * width) + "|")
    return "\n".join(lines)


def _spawn_row_line(row: wtp.Template) -> str:
    fields = _template_fields(row)
    name = fields.get("1", "?")
    detail = ", ".join(
        f"{label} {fields[key]}" for key, label in (("weight", "weight"), ("size", "group size")) if fields.get(key)
    )
    line = f"- {name} ({detail})" if detail else f"- {name}"
    note = fields.get("note")
    if note:
        line += f" — {_cell_text(note)}"
    return line


def _spawn_table_to_markdown(fields: dict[str, str]) -> str:
    edition = fields.get("edition", "").strip().lower()
    edition_label = _EDITION_NAMES.get(edition, fields.get("edition", ""))
    lines = [f"**Spawn table ({edition_label}):**" if edition_label else "**Spawn table:**"]

    for key, value in fields.items():
        if key == "edition" or not value.strip():
            continue
        rows = [t for t in wtp.parse(value).templates if str(t.name).strip().lower() == "spawn row"]
        if not rows:
            continue
        label = _SPAWN_CATEGORY_LABELS.get(key.strip().lower(), key.strip().title())
        lines.append(f"{label}:")
        lines.extend(_spawn_row_line(row) for row in rows)

    return "\n".join(lines) if len(lines) > 1 else ""


def _render_template(raw_name: str, fields: dict[str, str]) -> str | None:
    """Best-effort text/markdown for known templates - see module docstring.

    Returns None for anything unrecognized, which leaves it for plain_text()
    to delete - the same fallback behavior as before, just narrower in scope
    now that spawn tables, advancement lists, and collapse boxes are handled.
    """
    name = raw_name.lower()

    if name == "je":
        return "Java Edition"
    if name == "be":
        return "Bedrock Edition"
    if name in ("hp", "xp"):
        values = [v for k, v in fields.items() if k.isdigit()]
        return " / ".join(values) if len(values) > 1 else (values[0] if values else "")
    if name == "jebe":
        values = [v for k, v in fields.items() if k.isdigit()]
        return f"{values[0]} (Java) / {values[1]} (Bedrock)" if len(values) >= 2 else (values[0] if values else "")
    if name in ("in", "only"):
        value = fields.get("1")
        return f"({_EDITION_NAMES.get(value.strip().lower(), value)})" if value else None
    if name in ("control", "code", "color"):
        return fields.get("1")
    if name in _NAME_LINK_TEMPLATES:
        return fields.get("1")
    if name == "collapse":
        return fields.get("content")
    if name == "load advancements":
        return fields.get("1")
    if name == "droptable":
        # A wrapper around DropLine children - by the time this node is
        # visited (spans starting later are mutated first), its args are
        # already-rendered DropLine markdown, not raw templates. Just
        # unwrap them; DropTable itself carries no fields of its own.
        return _as_block(_BLOCK_JOIN.join(v for v in fields.values() if v.strip()))

    if name.startswith(INFOBOX_PREFIX) or name in STRUCTURED_TEMPLATES:
        markdown = _fields_to_markdown(fields)
        return _as_block(f"**{raw_name}:**\n{markdown}") if markdown else ""
    if name == "spawn table":
        return _as_block(_spawn_table_to_markdown(fields))

    return None


def _resolve_structured_content(wikitext: str) -> str:
    """Substitute known templates and all wikitables with rendered text, in place.

    Mutated right-to-left by span start (latest-starting/innermost nodes
    first) so an earlier node's character span is never invalidated by a
    mutation that comes after it - confirmed necessary for nested cases like
    {{jebe|{{hp|7}}|{{hp|8}}}}, where jebe's own .arguments read the already
    -resolved "7"/"8" once the inner hp templates are done, and for Spawn
    table, whose own field values contain nested Spawn row templates that
    must stay untouched (they have no renderer of their own) until Spawn
    table itself parses them out. The caller must re-parse the returned
    string - plain_text() on the same mutated tree keeps using stale spans
    and renders as if nothing changed.
    """
    parsed = wtp.parse(wikitext)
    nodes: list[wtp.WikiText] = list(parsed.templates) + list(parsed.tables)

    for node in sorted(nodes, key=lambda n: n.span[0], reverse=True):
        if isinstance(node, wtp.Table):
            node.string = _as_block(_table_to_markdown(node))
        else:
            rendered = _render_template(str(node.name).strip(), _template_fields(node))
            if rendered is not None:
                node.string = rendered

    return parsed.string


def _clean_prose(text: str) -> str:
    """Lighten wiki headings to a markdown-ish form and collapse blank runs."""
    text = _HEADING_RE.sub(lambda m: f"{'#' * (len(m.group(1)) - 1)} {m.group(2)}", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass(slots=True)
class ProseSection:
    title: str
    level: int
    text: str


@dataclass(slots=True)
class ParsedPage:
    summary: str
    sections: list[ProseSection]


def parse_page(wikitext: str) -> ParsedPage:
    wikitext = _BR_RE.sub("; ", wikitext)
    wikitext = _REF_RE.sub("", wikitext)
    wikitext = _resolve_structured_content(wikitext)
    parsed = wtp.parse(wikitext)

    summary = _clean_prose(parsed.sections[0].plain_text())

    sections = []
    for section in parsed.sections:
        title = (section.title or "").strip()
        if not title or section.level != 2 or title in SECTION_BLACKLIST:
            continue
        text = _clean_prose(section.plain_text())
        if text:
            sections.append(ProseSection(title, section.level, text))

    return ParsedPage(summary, sections)


if __name__ == "__main__":
    import argparse
    import dataclasses
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Parse a cached minecraft.wiki page")
    parser.add_argument("cache_file", type=Path)
    parser.add_argument(
        "--out", type=Path,
        help="Write the parsed page as JSON to this path instead of printing to the terminal",
    )
    args = parser.parse_args()

    raw = json.loads(args.cache_file.read_text(encoding="utf-8"))
    page = parse_page(raw["wikitext"])

    if args.out:
        args.out.write_text(json.dumps(dataclasses.asdict(page), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(f"=== summary ({len(page.summary)} chars) ===\n{page.summary}\n")
        for section in page.sections:
            print(f"=== {section.title} ({len(section.text)} chars) ===\n{section.text}\n")
