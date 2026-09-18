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
# letting plain_text() delete them, but that don't have their own
# recipe-shaped renderer below (yet, for Furnace - see _render_template) -
# generic name:value fields, same treatment as an infobox. DropLine (mob
# drop tables) is confirmed vanishing silently otherwise. Spawn table is
# handled separately (_spawn_table_to_markdown) since its fields nest their
# own Spawn row templates rather than being flat values.
STRUCTURED_TEMPLATES = {"furnace", "dropline"}

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


# Crafting's own ingredient fields are the 3x3 grid cells (A1-C3) or, for a
# shapeless recipe (per Template:Crafting's own docs - the wiki template
# itself distinguishes shaped from shapeless this way: grid letters means
# arrangement matters, plain numbers means it doesn't), plain numbered
# positional args ("1", "2", ...) - confirmed on real pages: Lantern/Bread/
# Redstone Lamp use A1-C3 (shaped), Diamond Sword's repair recipe (combine
# two damaged swords) uses "1"/"2" (shapeless). The letter is the COLUMN
# and the digit is the ROW, not the other way around - confirmed against
# real recipe shapes, since a naive letter=row reading gets it backwards:
# Diamond Sword's B1/B2/B3 is a vertical column in-game (diamond, diamond,
# stick stacked), and Bread's A2/B2/C2 is a horizontal row (three wheat
# side by side) - both only make sense with letter=column, digit=row.
# Dumping these raw (as _fields_to_markdown does) reads as "A1: Iron
# Nugget, A2: Iron Nugget, ..." - grid-position jargon the model had
# trouble turning into a spoken answer.
_GRID_CELL_RE = re.compile(r"^[ABC][123]$", re.IGNORECASE)
_GRID_COLUMNS = "ABC"  # A=left, B=middle, C=right
_GRID_ROWS = "123"  # 1=top, 2=middle, 3=bottom

# Template bookkeeping, not recipe content - confirmed on real pages
# (type/foot/showname/name on Lantern, Bread, Diamond Sword's normal
# recipe; ignoreusage/showdescription on Diamond Sword's repair recipe).
_CRAFTING_NOISE_FIELDS = {"type", "foot", "foot2", "showname", "name", "ignoreusage", "showdescription", "showusage"}


def _with_count(item: str, count: int) -> str:
    return item if count == 1 else f"{count}x {item}"


def _aggregate_ingredients(items: list[str]) -> str:
    """["Iron Nugget"]*8 + ["Torch"] -> "8x Iron Nugget + Torch" - counts each
    distinct ingredient by how many grid slots/positional args it occupies,
    since the grid has no separate count field (a cell holding "Iron Nugget"
    three times means 3 iron nuggets, not 1 with a multiplier elsewhere)."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for item in items:
        if item not in counts:
            order.append(item)
        counts[item] = counts.get(item, 0) + 1
    return " + ".join(_with_count(item, counts[item]) for item in order)


def _parse_count_suffix(text: str) -> str:
    """"Lantern" -> "Lantern"; "Iron Nugget,9" -> "9x Iron Nugget" - a
    trailing ",N" is a result count, not part of the name, on both
    Crafting's Output (confirmed: Iron Nugget's own recipe is
    Output=Iron Nugget,9) and each item in Stonecutting's output list
    (confirmed: Stone's page lists "Stone Slab, 2; Stone Stairs; ...")."""
    name, sep, tail = text.rpartition(",")
    if sep and tail.strip().isdigit():
        return _with_count(name.strip(), int(tail.strip()))
    return text


def _grid_cells(fields: dict[str, str]) -> dict[tuple[int, int], str]:
    """(row, col) -> item name for each filled grid cell, 0-indexed."""
    cells: dict[tuple[int, int], str] = {}
    for name, value in fields.items():
        if not _GRID_CELL_RE.match(name):
            continue
        text = _cell_text(value)
        if not text:
            continue
        col = _GRID_COLUMNS.index(name[0].upper())
        row = _GRID_ROWS.index(name[1])
        cells[(row, col)] = text
    return cells


def _describe_shape(cells: dict[tuple[int, int], str]) -> str:
    """A natural-language description of a shaped recipe's arrangement, e.g.
    "Iron Nugget fills the crafting grid, with Torch in the center", or
    "in a vertical column, top to bottom: Diamond, Diamond, Stick".

    Generated in code rather than left for the answering model to read off
    a coordinate grid itself - tried that first, and the model
    misinterpreted a vertical column (Diamond Sword's actual recipe) as two
    items side by side. Handing it an already-correct sentence to relay
    removes the chance to get it wrong.

    Only the shapes seen on real recipes so far (row, column, border+center
    like Lantern, plus-shape like Redstone Lamp) get a tailored phrasing;
    anything else falls back to a plain row-by-row description - always
    correct, just less naturally phrased for shapes not seen yet.

    Trimmed to the bounding box of filled cells, not always all 9 - the
    game matches shaped recipes by relative arrangement anywhere in the
    grid, not by absolute position, so cells outside it carry no
    information worth spending words on.
    """
    if not cells:
        return ""

    min_row, max_row = min(r for r, _ in cells), max(r for r, _ in cells)
    min_col, max_col = min(c for _, c in cells), max(c for _, c in cells)
    height, width = max_row - min_row + 1, max_col - min_col + 1

    def at(r: int, c: int) -> str:
        return cells.get((r, c), "")

    if height == 1 and width == 1:
        return ""  # a single cell has nothing to arrange - the ingredient summary already says it all

    if height == 1:
        row = [at(min_row, c) for c in range(min_col, max_col + 1)]
        if len(set(row)) == 1:
            return f"{_with_count(row[0], len(row))} in a horizontal row"
        return "in a horizontal row, left to right: " + ", ".join(row)

    if width == 1:
        col = [at(r, min_col) for r in range(min_row, max_row + 1)]
        if len(set(col)) == 1:
            return f"{_with_count(col[0], len(col))} stacked in a vertical column"
        return "in a vertical column, top to bottom: " + ", ".join(col)

    if height == 3 and width == 3:
        mid_r, mid_c = min_row + 1, min_col + 1
        center = at(mid_r, mid_c)
        border = [at(r, c) for r in range(min_row, max_row + 1) for c in range(min_col, max_col + 1) if (r, c) != (mid_r, mid_c)]
        if center and border[0] and border[0] != center and all(item == border[0] for item in border):
            return f"{border[0]} fills the crafting grid, with {center} in the center"

        edges = {at(mid_r - 1, mid_c), at(mid_r + 1, mid_c), at(mid_r, mid_c - 1), at(mid_r, mid_c + 1)}
        corners_empty = all(at(r, c) == "" for r in (min_row, max_row) for c in (min_col, max_col))
        if center and corners_empty and len(edges) == 1 and "" not in edges:
            return f"{next(iter(edges))} surrounds {center} in the center, forming a plus shape"

    # Fallback: always correct, just literal - one clause per used row.
    row_labels = ("first row", "second row", "third row")
    parts = [
        f"{row_labels[i]}: " + ", ".join(at(r, c) or "empty" for c in range(min_col, max_col + 1))
        for i, r in enumerate(range(min_row, max_row + 1))
    ]
    return "; ".join(parts)


def _crafting_to_markdown(raw_name: str, fields: dict[str, str]) -> str:
    ingredients = [
        _cell_text(value)
        for name, value in fields.items()
        if (_GRID_CELL_RE.match(name) or name.isdigit()) and _cell_text(value)
    ]
    output = next((v for k, v in fields.items() if k.lower() == "output"), None)
    shaped = any(_GRID_CELL_RE.match(name) for name in fields)

    # A ";"-separated cell value isn't one ingredient - it's several
    # per-tier alternatives packed into one template display (confirmed on
    # the general "Sword" page: B1/B2/Output each list 6 materials/results,
    # one per tier, for a recipe whose shape is identical across all of
    # them). Zipping N parallel lists across multiple fields correctly
    # would need to trust they're all the same length and in matching tier
    # order - risky to get silently wrong - and produced exactly that kind
    # of nonsense in testing (a "6-slot vertical stack" that doesn't exist)
    # when treated as one item per cell instead. The surrounding wiki prose
    # already states the general rule in plain language, so this template
    # contributes nothing rather than something wrong.
    if any(";" in item for item in ingredients) or (output and ";" in output):
        return ""

    lines = []
    summary = _aggregate_ingredients(ingredients) if ingredients else ""
    if summary and output:
        lines.append(f"**{raw_name}:** {summary} = {_parse_count_suffix(_cell_text(output))}")
    elif summary:
        lines.append(f"**{raw_name}:** {summary}")
    elif output:
        lines.append(f"**{raw_name}:** {_parse_count_suffix(_cell_text(output))}")

    # Shapeless recipes (plain numbered ingredients) have no arrangement to
    # lose - the summary line above is already the complete picture. Shaped
    # recipes (grid-cell fields) do lose real information without this:
    # e.g. 3x Wheat alone doesn't say it has to be a horizontal row, and
    # some items only differ from each other by shape given the same
    # ingredients (stairs vs. other results from the same planks).
    if shaped:
        shape = _describe_shape(_grid_cells(fields))
        if shape:
            lines.append(f"- **Shape** (arrangement matters): {shape}")

    # Anything left over (e.g. Diamond Sword's repair recipe has a
    # freeform "description" field) is real content, not noise - keep it
    # rather than silently drop fields this function doesn't recognize.
    for name, value in fields.items():
        lower = name.lower()
        if _GRID_CELL_RE.match(name) or name.isdigit() or lower == "output" or lower in _CRAFTING_NOISE_FIELDS:
            continue
        text = _cell_text(value)
        if text:
            lines.append(f"- **{name}**: {text}")

    return "\n".join(lines)


def _leftover_fields(raw_name: str, fields: dict[str, str], used: set[str], noise: set[str]) -> list[str]:
    """Bullet lines for fields a renderer didn't already use - same "unknown
    isn't noise" reasoning as _crafting_to_markdown: keep whatever a
    template's own noise-field list doesn't specifically name, rather than
    silently drop fields this codebase hasn't seen an example of yet."""
    lines = []
    for name, value in fields.items():
        if name in used or name.lower() in noise:
            continue
        text = _cell_text(value)
        if text:
            lines.append(f"- **{name}**: {text}")
    return lines


# Smelting's positional args are fixed by order, not name: 1=ingredient,
# 2=output, 3=XP reward - confirmed on two real recipes (Stone's Cobblestone
# ->Stone and Cobblestone->Smooth Stone). name/showname are a display-label
# override, head/tail/foot are table-layout flags for when several Smelting
# calls in a row form one combined table - none of that is recipe content.
_SMELTING_NOISE_FIELDS = {"name", "showname", "head", "tail", "foot"}


def _smelting_to_markdown(raw_name: str, fields: dict[str, str]) -> str:
    ingredient = _cell_text(fields.get("1", ""))
    output = _cell_text(fields.get("2", ""))
    xp = _cell_text(fields.get("3", ""))

    lines = []
    if ingredient and output:
        line = f"**{raw_name}:** {ingredient} = {output}"
        if xp:
            line += f" ({xp} XP)"
        lines.append(line)

    lines.extend(_leftover_fields(raw_name, fields, {"1", "2", "3"}, _SMELTING_NOISE_FIELDS))
    return "\n".join(lines)


# Smithing's 4 positional args are fixed by order - confirmed on two real
# Netherite Upgrade recipes (Diamond Sword and Sword pages, identical
# shape): 1=a label for the recipe itself (not an ingredient - there's only
# one smithing recipe in vanilla today, but the label exists in case a page
# ever lists more than one), 2=base item, 3=material added, 4=result.
# head/tail are the same table-layout flags as Smelting's.
_SMITHING_NOISE_FIELDS = {"head", "tail", "showname", "foot"}


def _smithing_to_markdown(raw_name: str, fields: dict[str, str]) -> str:
    label = _cell_text(fields.get("1", ""))
    base = _cell_text(fields.get("2", ""))
    addition = _cell_text(fields.get("3", ""))
    output = _cell_text(fields.get("4", ""))

    lines = []
    if base and addition and output:
        header = f"**{raw_name} ({label}):**" if label else f"**{raw_name}:**"
        lines.append(f"{header} {base} + {addition} = {output}")

    lines.extend(_leftover_fields(raw_name, fields, {"1", "2", "3", "4"}, _SMITHING_NOISE_FIELDS))
    return "\n".join(lines)


# Stonecutting's 2 positional args - confirmed on Stone's real page:
# 1=ingredient, 2=every possible output, semicolon-separated, each
# optionally with a Crafting-Output-style ",N" count suffix (reuses
# _parse_count_suffix). One input can cut into many different results,
# unlike every other recipe template here which has exactly one output.
_STONECUTTING_NOISE_FIELDS = {"head", "showname", "foot"}


def _stonecutting_to_markdown(raw_name: str, fields: dict[str, str]) -> str:
    ingredient = _cell_text(fields.get("1", ""))
    outputs_raw = _cell_text(fields.get("2", ""))

    lines = []
    if ingredient and outputs_raw:
        outputs = [_parse_count_suffix(piece.strip()) for piece in outputs_raw.split(";") if piece.strip()]
        lines.append(f"**{raw_name}:** {ingredient} = " + ", ".join(outputs))

    lines.extend(_leftover_fields(raw_name, fields, {"1", "2"}, _STONECUTTING_NOISE_FIELDS))
    return "\n".join(lines)


# Brewing's positional args - confirmed on two real recipes on Stone's page
# (Water Bottle+Stone->Mundane Potion, and Stone->Potion of Infestation with
# no base at all): 1=ingredient added, 2=result potion. "base" (the potion
# being brewed from, e.g. Water Bottle) is a named field and genuinely
# optional - the second real example omits it entirely, not just leaves it
# blank, so the starting potion isn't always known.
_BREWING_NOISE_FIELDS = {"head", "foot", "showname", "showvariants"}


def _brewing_to_markdown(raw_name: str, fields: dict[str, str]) -> str:
    ingredient = _cell_text(fields.get("1", ""))
    result = _cell_text(fields.get("2", ""))
    base = _cell_text(fields.get("base", ""))

    lines = []
    if ingredient and result:
        left = f"{base} + {ingredient}" if base else ingredient
        lines.append(f"**{raw_name}:** {left} = {result}")

    lines.extend(_leftover_fields(raw_name, fields, {"1", "2", "base"}, _BREWING_NOISE_FIELDS))
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

    if name == "crafting":
        markdown = _crafting_to_markdown(raw_name, fields)
        return _as_block(markdown) if markdown else ""
    if name == "smelting":
        markdown = _smelting_to_markdown(raw_name, fields)
        return _as_block(markdown) if markdown else ""
    if name == "smithing":
        markdown = _smithing_to_markdown(raw_name, fields)
        return _as_block(markdown) if markdown else ""
    if name == "stonecutting":
        markdown = _stonecutting_to_markdown(raw_name, fields)
        return _as_block(markdown) if markdown else ""
    if name == "brewing":
        markdown = _brewing_to_markdown(raw_name, fields)
        return _as_block(markdown) if markdown else ""
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
