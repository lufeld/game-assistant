"""LLM-facing tools for the agent's reactive tool-calling loop.

Thin wrappers around existing wiki/ and player/ primitives - the underlying
resolve/fetch/parse/store and player_db functions are reused as-is, not
duplicated or modified (see src/modules/wiki/resolve.py's search_candidates,
the one new addition those modules needed). Each wrapper's docstring is what
Ollama's tool-schema generator reads to decide when the model should call
it, so these are written for the model, not for a developer.

No wrapper exposes a path parameter (db_path/cache_dir/chroma_dir) - always
the default - so nothing in the model-visible schema lets a hallucinated
argument redirect a read at an arbitrary path.
"""

from __future__ import annotations

from pathlib import Path

try:
    from modules import orchestrator
    from modules.agent import skills
    from modules.player import player_db
    from modules.wiki import fetch, parse, resolve, store
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from modules import orchestrator
    from modules.agent import skills
    from modules.player import player_db
    from modules.wiki import fetch, parse, resolve, store


# --- wiki tools -------------------------------------------------------

_DEFAULT_SEARCH_LIMIT = 5


def wiki_search_candidates(term: str, limit: int | None = None) -> list[str]:
    """Search the Minecraft Wiki for pages related to `term`. Returns
    ranked candidate titles - the top result is NOT guaranteed to be the
    right one (ranked by keyword overlap, not concept match). Use your own
    judgment to pick the best match, checking one with wiki_page_overview
    first if it's not obvious from the title alone. Use this when you don't
    already know the exact page title.
    IMPORTANT: follow up with wiki_page_search on the chosen title to find
    the specific information you need!

    Args:
        term: Plain-language search term or best guess at the topic, e.g.
            "pickaxe", "slime block" or "repair sword".
        limit: Maximum number of candidate titles to return. Omit this
            argument entirely to use a sensible default.
    """
    return resolve.search_candidates(term, limit=limit if limit is not None else _DEFAULT_SEARCH_LIMIT)


def wiki_page_overview(title: str) -> str:
    """Get a short summary and section headings for a Minecraft Wiki page.
    Use this to check a page looks right, or see what topics/items it
    mentions, before searching it for specific facts. `title` should be an
    exact or near-exact page title - use wiki_search_candidates first if
    you're not sure.

    Args:
        title: The exact or near-exact wiki page title, e.g. "Bread" or
            "Wither Skeleton".
    """
    resolved = orchestrator.ensure_page(title)
    if resolved is None:
        return f"No page found for {title!r}."
    raw = fetch.get_page(resolved.title)
    parsed = parse.parse_page(raw.wikitext)
    return parsed.summary + "\n\nSections: " + ", ".join(s.title for s in parsed.sections)


_MAX_WIKI_RESULTS = 3  # see wiki_page_search - capped regardless of what's requested


def wiki_page_search(title: str, query: str, n_results: int = _MAX_WIKI_RESULTS) -> list[str]:
    """Search within ONE already-identified Minecraft Wiki page for passages
    relevant to `query` - e.g. crafting ingredients, stats, spawn conditions,
    or what items/things a list-like page mentions. Keep queries specific
    and call again with a different query if you need more, rather than
    requesting many results at once - most pages don't have many distinct
    chunks anyway, and a large result tends to derail into summarizing
    everything just read instead of continuing the actual task. Can be
    called multiple times with different pages or queries in the same turn.

    Args:
        title: The already-identified wiki page to search within.
        query: What you want to know about that page, in plain language -
            keep it narrow and specific, e.g. "crafting recipe" rather than
            "everything about this item".
        n_results: How many passages to return. There's an internal cap you
            cannot exceed - a larger value will not return more passages, so
            leave this at the default and issue a second, differently-worded
            call instead if you need more.
    """
    resolved = orchestrator.ensure_page(title)
    if resolved is None:
        return [f"No page found for {title!r}."]
    # Capped, not just defaulted low - observed live: qwen3:14b explicitly
    # requested n_results=10 for a broad query and got a large result full
    # of tables, then never got back to the player-state check it still
    # needed to do, answering with a generic info-dump instead. A smaller
    # default alone wouldn't have helped since the model overrode it anyway.
    return store.query_prose(resolved.title, query, n_results=min(n_results, _MAX_WIKI_RESULTS))


# --- player tools -------------------------------------------------------

def player_inventory() -> list[dict]:
    """Everything currently in the player's inventory/hotbar, with counts.
    The result does NOT include items in chests/barrels or other containers - use
    player_find_items() to check those too. Use this when you need to know
what the player has on them, but not when you need to check for a specific
item in the player's OVERALL possession - player_find_items() is more efficient for that,
    """
    return player_db.get_inventory()


_ALL_CONTAINERS_LIMIT = 50


def _normalize_item_name(name: str) -> str:
    """Make a wiki-style title ("Iron Sword", "Cooked Beef") and a
    Minecraft registry id ("minecraft:iron_sword") comparable: strip any
    "namespace:" prefix, replace underscores with spaces, lowercase.
    Without this, wiki-derived names (what wiki_page_search actually
    returns) never matched stored items at all - confirmed live:
    player_find_items(["Iron Sword"]) and (["iron sword"]) both returned
    empty against data stored as "minecraft:iron_sword"; only the exact
    underscore-joined registry string ever matched."""
    if ":" in name:
        name = name.split(":", 1)[1]
    return name.replace("_", " ").lower()


def player_find_items(names: list[str]) -> dict[str, list[dict]]:
    """Check BOTH the player's inventory AND every known chest/barrel for
    EACH of these item names, all in one call - use this instead of
    checking one item or one location at a time, especially when you have
    several candidate item names to check (e.g. multiple food item names
    found from a wiki page). Matches regardless of whether the name is
    phrased as a wiki title or a Minecraft registry id. Returns a dict
    keyed by each name you passed in, each with a list of matches (empty
    list if that name wasn't found anywhere).

    Args:
        names: Item name substrings to search for, e.g. ["Bread", "rabbit",
            "cooked beef"] - NOT category words like "food" or "tools",
            real item names rarely contain those.
    """
    inventory = player_db.get_inventory()
    containers = player_db.find_container("", limit=_ALL_CONTAINERS_LIMIT)

    results: dict[str, list[dict]] = {}
    for name in names:
        needle = _normalize_item_name(name)
        matches: list[dict] = []
        for slot in inventory:
            if needle in _normalize_item_name(slot["item"]):
                matches.append({"location": "inventory", "slot": slot["slot"], "item": slot["item"], "count": slot["count"]})
        for container in containers:
            for item in container["items"]:
                if needle in _normalize_item_name(item["item"]):
                    matches.append({
                        "location": "container", "kind": container["kind"],
                        "dim": container["dim"], "x": container["x"], "y": container["y"], "z": container["z"],
                        "item": item["item"], "count": item["count"],
                    })
        results[name] = matches
    return results


def player_equipment() -> dict[str, str]:
    """What the player is currently wearing/holding, by slot (mainhand,
    offhand, head, chest, legs, feet)."""
    return player_db.get_equipment()


def player_effects() -> list[dict]:
    """The player's currently active potion/status effects."""
    return player_db.get_effects()


def player_vitals() -> dict | None:
    """The player's health, hunger, saturation, XP, and game mode."""
    return player_db.get_vitals()


def player_position() -> dict | None:
    """The player's current coordinates, dimension, and biome."""
    return player_db.get_position()


def player_spawn_point() -> dict | None:
    """Where the player's bed or respawn anchor was last set."""
    return player_db.get_spawn_point()


_DEFAULT_DEATHS_LIMIT = 5


def player_deaths(limit: int | None = None) -> list[dict]:
    """The player's most recent deaths, with location and cause.

    Args:
        limit: Maximum number of recent deaths to return, most recent first.
            Omit this argument entirely to use a sensible default.
    """
    return player_db.get_deaths(limit=limit if limit is not None else _DEFAULT_DEATHS_LIMIT)


def player_find_placements(name_substring: str) -> list[dict]:
    """Where a functional block (torch, furnace, bed, ...) matching this
    name was placed in the world - not the same as player_find_items
    (stored/carried items, not world placements). Matches regardless of
    whether the name is phrased as a wiki title or a Minecraft registry id.

    Args:
        name_substring: Partial or full block name to search for, e.g.
            "torch" or "bed".
    """
    return player_db.find_placements(name_substring.replace(" ", "_"))


def player_visited_structures(kind_substring: str | None = None) -> list[dict]:
    """Structures (village, fortress, ...) the player has discovered. Pass
    no argument to list all of them, or a partial name to filter.

    Args:
        kind_substring: Partial structure type name to filter by, e.g.
            "village" - omit this argument entirely to list all of them.
    """
    return player_db.get_visited_structures(kind_substring)


# --- skills -----------------------------------------------------------

# General starting points for broad "what X exist" questions - the model
# can call wiki_page_search on one of these to get a list of specific information
SEED_PAGES = ["Food", "Items", "Mob", "Biomes", "Brewing", "Blocks", "Structures"]


TOOLS = [
    wiki_search_candidates, wiki_page_overview, wiki_page_search,
    player_inventory, player_find_items,
    player_equipment, player_effects, player_vitals, player_position,
    player_spawn_point, player_deaths, player_find_placements,
    player_visited_structures,
    *skills.SKILLS,
]
TOOL_MAP = {fn.__name__: fn for fn in TOOLS}
