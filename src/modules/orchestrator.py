"""Route a player's question to wiki knowledge and answer it - the synchronous v1.

Four steps, each a plain function so this is testable the same way as the
wiki/ modules (call it with text, read what comes back):

    ROUTE    - one constrained-JSON Ollama call: which entities is this
               about, does answering need the player's own state.
    ENSURE   - per entity, make sure wiki_prose is actually current for it
               (resolve -> compare against what's *stored*, not just
               cached -> fetch/parse/store only if missing or stale).
    RETRIEVE - semantic search within each resolved page's own chunks,
               not the whole corpus - narrows an easy problem (which
               chunk, on a page we already know is the right one) instead
               of a hard one (which page, from raw keyword/vector search
               across everything).
    ANSWER   - one Ollama call reads the retrieved chunks directly; no
               separate query-paraphrase step. Widening RETRIEVE's top-k
               and letting the answering model read multiple candidates is
               cheaper (one fewer LLM call per turn) than a paraphrase step,
               and this session's own testing showed raw natural-phrasing
               queries already land the right chunk within a small top-k.

player_info replaces an earlier bare need_player_state boolean - the router
now names *which* category of the player's own state a question needs
(inventory, position, deaths, ...), the same way entities already names
which wiki pages it needs, plus an optional player_target (an item or
structure-kind name) for the categories that search rather than just
snapshot. _player_state_context() dispatches that decision straight to the
matching player_db read function.

Deliberately synchronous, not the asyncio audio_in/dialog/game_ingest/
audio_out task design from the original blueprint - that's for wrapping
real concurrency (always-on STT, the Fabric mod) around this once it's
needed, not for solving routing and concurrency at the same time.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import ollama

try:
    from modules import player_db
    from modules.wiki.fetch import get_page, peek_cached_revid
    from modules.wiki.parse import parse_page
    from modules.wiki.resolve import PageNotFound, ResolvedTitle, resolve_title
    from modules.wiki.store import peek_stored_revid, query_prose, store_page
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from modules import player_db
    from modules.wiki.fetch import get_page, peek_cached_revid
    from modules.wiki.parse import parse_page
    from modules.wiki.resolve import PageNotFound, ResolvedTitle, resolve_title
    from modules.wiki.store import peek_stored_revid, query_prose, store_page

MODEL_NAME = "qwen3:4b-instruct"
N_RESULTS = 5

_PLAYER_INFO_CATEGORIES = [
    "none", "inventory", "equipment", "effects", "vitals", "position",
    "spawn_point", "deaths", "game_time", "containers", "placements", "structures",
]

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {"type": "string"}},
        "player_info": {"type": "string", "enum": _PLAYER_INFO_CATEGORIES},
        "player_target": {"type": ["string", "null"]},
    },
    "required": ["entities", "player_info", "player_target"],
}

# Few-shot, not zero-shot: a bare instruction misclassified "How do I make a
# beacon?" as needing player state with no entity extracted at all (verified
# against qwen3:4b-instruct before this was added, back when this was just a
# need_player_state boolean). One example per player_info category below,
# not verified in isolation yet - see the batch prompts file for the real check.
ROUTE_SYSTEM_PROMPT = """You are a routing step for a Minecraft voice assistant. Given the player's question, extract:
- entities: Minecraft item/block/mob/mechanic names being asked about, as they'd appear as a wiki page title (e.g. "Diamond Sword", "Beacon"). Empty list if none.
- player_info: which category of the PLAYER's own current state answering needs - not general game knowledge, even if phrased with "I"/"my". One of:
  "none" (most questions), "inventory", "equipment", "effects", "vitals" (health/hunger/XP/game mode), "position",
  "spawn_point", "deaths", "game_time", "containers" (where an item is stored), "placements" (where an item was placed, e.g. torches), "structures" (discovered villages/fortresses/etc.)
- player_target: the specific item or structure name being asked about, only for inventory/containers/placements/structures when one is named - otherwise null.

Examples:
Q: How do I make a beacon?
A: {"entities": ["Beacon"], "player_info": "none", "player_target": null}

Q: How many diamonds do I have?
A: {"entities": [], "player_info": "inventory", "player_target": "diamond"}

Q: What's in my inventory?
A: {"entities": [], "player_info": "inventory", "player_target": null}

Q: Where did I put my torches?
A: {"entities": [], "player_info": "placements", "player_target": "torch"}

Q: Where's my chest with the emeralds?
A: {"entities": [], "player_info": "containers", "player_target": "emerald"}

Q: What am I wearing?
A: {"entities": [], "player_info": "equipment", "player_target": null}

Q: Do I have any potion effects active?
A: {"entities": [], "player_info": "effects", "player_target": null}

Q: How much health do I have left?
A: {"entities": [], "player_info": "vitals", "player_target": null}

Q: Where am I right now?
A: {"entities": [], "player_info": "position", "player_target": null}

Q: Where's my bed?
A: {"entities": [], "player_info": "spawn_point", "player_target": null}

Q: Where did I last die?
A: {"entities": [], "player_info": "deaths", "player_target": null}

Q: Is it nighttime?
A: {"entities": [], "player_info": "game_time", "player_target": null}

Q: Have I found a village yet?
A: {"entities": [], "player_info": "structures", "player_target": "village"}

Q: What does a wither skeleton drop?
A: {"entities": ["Wither Skeleton"], "player_info": "none", "player_target": null}

Q: Where do I get gold?
A: {"entities": ["Gold"], "player_info": "none", "player_target": null}

Q: Hey how is it going?
A: {"entities": [], "player_info": "none", "player_target": null}
"""

ANSWER_SYSTEM_PROMPT = (
    "You are a helpful Minecraft assistant. Answer using ONLY the provided context. "
    "If the context does not cover the question, say you don't know rather than guessing. "
    "Keep answers short, concise, and spoken-friendly. Only use Java Edition mechanics and names, not Bedrock Edition. "
    "Omit any unnecessary text or numerical values unless they are directly relevant to the question. "
    "This answer is read aloud by text-to-speech, not displayed as text - never use lists, bullet points, "
    "line breaks, or markdown formatting; respond in plain spoken sentences only. "
    "When describing a crafting grid's shape, describe it the way a person would say it out loud "
    '("a torch in the middle with iron nuggets around it", "three wheat in a row", "stacked in a column") '
    "rather than reading out each grid cell one by one. "
    "Do not use emoji."
)


def warm_up_model(*, model: str = MODEL_NAME) -> None:
    """Force Ollama to load the model now rather than on the first real
    question - a cold model load can take a long time, and paying that cost
    during startup (while the user is likely not talking yet) is better
    than paying it on their first question."""
    ollama.chat(model=model, messages=[{"role": "user", "content": "hi"}], options={"num_predict": 1})


def route(question: str, *, model: str = MODEL_NAME) -> dict:
    """One constrained-JSON call: which entities, does this need player state."""
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        format=ROUTE_SCHEMA,
        options={"temperature": 0.1, "num_predict": 200},
    )
    return json.loads(response["message"]["content"])


def ensure_page(term: str) -> ResolvedTitle | None:
    """Resolve a term to a page and make sure wiki_prose is current for it.

    None if the term doesn't resolve to any page - the caller skips it
    rather than failing the whole turn over one bad entity.
    """
    try:
        resolved = resolve_title(term)
    except PageNotFound:
        return None

    if peek_stored_revid(resolved.title) != resolved.lastrevid:
        stale_cache = peek_cached_revid(resolved.title) != resolved.lastrevid
        raw = get_page(resolved.title, force_refresh=stale_cache)
        parsed = parse_page(raw.wikitext)
        store_page(title=resolved.title, pageid=resolved.pageid, revid=resolved.lastrevid, url=raw.url, page=parsed)

    return resolved


_COMPASS_DIRECTIONS = [
    "north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest",
]


def _bearing(from_x: float, from_z: float, to_x: float, to_z: float) -> tuple[str, float]:
    """8-way compass direction and horizontal (X/Z) distance from one point to
    another. North is -Z and east is +X, matching Minecraft's own axes -
    verified against the F3 debug screen's own facing readout, not assumed."""
    dx = to_x - from_x
    dz = to_z - from_z
    angle = math.degrees(math.atan2(dx, -dz)) % 360
    direction = _COMPASS_DIRECTIONS[round(angle / 45) % 8]
    distance = math.hypot(dx, dz)
    return direction, distance


def _location_text(loc: dict, position: dict | None) -> str:
    """"12, 65, -80 (northeast, about 40 blocks away)" if the player's current
    position is known and in the same dimension as loc, else just the
    coordinates and dimension name."""
    coords = f"{loc['x']:.0f}, {loc['y']:.0f}, {loc['z']:.0f}"
    if position and position["dim"] == loc["dim"]:
        direction, distance = _bearing(position["x"], position["z"], loc["x"], loc["z"])
        return f"{coords} ({direction}, about {distance:.0f} blocks away)"
    return f"{coords} in {loc['dim']}"


def _player_state_context(routed: dict) -> str | None:
    """Turn a routed player_info decision into a short text summary, straight
    from player_db - no LLM involved, these are exact lookups, not retrieval.

    None whenever there's nothing to say (category is "none", or player_db
    has no data yet, or a lookup fails) rather than raising - a missing
    Player DB fact should degrade the turn, not sink it, the same spirit as
    ensure_page() skipping an entity that fails to resolve.
    """
    info = routed.get("player_info", "none")
    target = routed.get("player_target")

    try:
        if info == "none":
            return None

        if info == "inventory" and not target:
            items = player_db.get_inventory()
            if not items:
                return "The player's inventory is empty."
            return "Inventory: " + ", ".join(f"{i['count']}x {i['item']}" for i in items)

        if info == "inventory":
            # "Do I have X" means "is X available to me at all" - carried OR
            # stored - not narrowly "in my hotbar/inventory right now". Checking
            # only find_item() was reporting "you have none" for an item that
            # was sitting untouched in a chest
            carried = player_db.find_item(target)
            stored = player_db.find_container(target)

            parts = [f"carrying {i['count']}x {i['item']}" for i in carried]
            for container in stored:
                for match in container["items"]:
                    if target.lower() in match["item"].lower():
                        parts.append(
                            f"{match['count']}x {match['item']} stored in a {container['kind']} at "
                            f"{container['x']:.0f}, {container['y']:.0f}, {container['z']:.0f}"
                        )

            if not parts:
                return f"The player has no {target}, carried or stored."
            return "The player has: " + "; ".join(parts) + "."

        if info == "equipment":
            equipment = player_db.get_equipment()
            if not equipment:
                return "The player has no equipment data available."
            return "Equipped: " + ", ".join(f"{slot}: {item}" for slot, item in equipment.items())

        if info == "effects":
            effects = player_db.get_effects()
            if not effects:
                return "The player has no active potion effects."
            return "Active effects: " + ", ".join(f"{e['effect']} (level {e['amplifier'] + 1})" for e in effects)

        if info == "vitals":
            vitals = player_db.get_vitals()
            if not vitals:
                return "No vitals data available yet."
            return (
                f"Health: {vitals['health']}/20, Hunger: {vitals['hunger']}/20, "
                f"XP level: {vitals['xp_level']}, Game mode: {vitals['game_mode']}."
            )

        if info == "position":
            position = player_db.get_position()
            if not position:
                return "No position data available yet."
            biome = f" in {position['biome']}" if position.get("biome") else ""
            return f"Player is at {position['x']:.0f}, {position['y']:.0f}, {position['z']:.0f} in {position['dim']}{biome}."

        if info == "spawn_point":
            spawn = player_db.get_spawn_point()
            if not spawn:
                return "The player has no spawn point set."
            base = f"Spawn point: {spawn['x']:.0f}, {spawn['y']:.0f}, {spawn['z']:.0f} in {spawn['dim']}."

            position = player_db.get_position()
            if not position:
                return base
            if position["dim"] != spawn["dim"]:
                return (
                    f"{base} The player is currently in {position['dim']}, a different "
                    "dimension, so a walking direction can't be given from here."
                )
            direction, distance = _bearing(position["x"], position["z"], spawn["x"], spawn["z"])
            return f"{base} It is {direction} of the player's current position, about {distance:.0f} blocks away."

        if info == "deaths":
            last = player_db.get_last_death()
            if not last:
                return "The player has not died yet."
            cause = f" (cause: {last['cause']})" if last.get("cause") else ""
            position = player_db.get_position()
            return f"Last death: {_location_text(last, position)}{cause}."

        if info == "game_time":
            game_time = player_db.get_game_time()
            if not game_time:
                return "No game time data available yet."
            time_of_day = "night" if game_time["is_night"] else "day"
            return f"It is currently {time_of_day} (day {game_time['day_count']})."

        if info == "containers":
            if not target:
                return None
            found = player_db.find_container(target)
            if not found:
                return f"No known container with {target} was found."
            position = player_db.get_position()
            locations = "; ".join(f"{_location_text(c, position)} ({c['kind']})" for c in found)
            return f"Containers with {target}: {locations}"

        if info == "placements":
            if not target:
                return None
            found = player_db.find_placements(target)
            if not found:
                return f"No recorded placements of {target} were found."
            position = player_db.get_position()
            locations = "; ".join(_location_text(p, position) for p in found)
            return f"{target} placed at: {locations}"

        if info == "structures":
            found = player_db.get_visited_structures(target)
            if not found:
                return f"No {target + ' ' if target else ''}structures have been discovered yet."
            position = player_db.get_position()
            locations = "; ".join(f"{s['kind']} at {_location_text(s, position)}" for s in found)
            return f"Discovered structures: {locations}"

    except Exception as exc:  # player_db unreachable/unexpected shape
        print(f"orchestrator: player_db lookup failed for {info!r}: {exc}")
        return None

    return None


def gather_context(question: str, routed: dict, *, n_results: int = N_RESULTS) -> list[str]:
    """Turn a routing decision into retrieved context chunks."""
    chunks: list[str] = []

    for term in routed.get("entities", []):
        try:
            resolved = ensure_page(term)
        except Exception as exc:
            print(f"orchestrator: couldn't resolve/ingest {term!r}: {exc}")  # shouldn't sink the whole turn
            continue
        if resolved is None:
            continue
        chunks.extend(query_prose(resolved.title, question, n_results=n_results))

    player_context = _player_state_context(routed)
    if player_context:
        chunks.append(player_context)

    return chunks


def _answer_messages(question: str, chunks: list[str]) -> list[dict]:
    context = (
        "\n\n---\n\n".join(chunks) if chunks
        # Explicit that this is a retrieval gap, not evidence the thing
        # doesn't exist - a real failure mode without this: asked "where do
        # I get gold?" with empty context, the model answered "you don't
        # get gold in Minecraft" instead of saying it didn't know.
        else "Nothing was retrieved for this question. This does not mean the answer is no or that the "
             "thing doesn't exist - it means no matching information was found. Say you don't know."
    )
    return [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]


def ask(question: str, *, model: str = MODEL_NAME, n_results: int = N_RESULTS) -> str:
    """Route, ensure, retrieve, answer - the whole synchronous pipeline for one turn."""
    routed = route(question, model=model)
    chunks = gather_context(question, routed, n_results=n_results)
    response = ollama.chat(model=model, messages=_answer_messages(question, chunks))
    return response["message"]["content"]


def ask_stream(question: str, *, model: str = MODEL_NAME, n_results: int = N_RESULTS):
    """Same pipeline as ask(), but yields the answer as it's generated instead
    of returning it all at once - lets a voice pipeline start speaking the
    first sentence while later ones are still being generated."""
    routed = route(question, model=model)
    chunks = gather_context(question, routed, n_results=n_results)
    for part in ollama.chat(model=model, messages=_answer_messages(question, chunks), stream=True):
        yield part["message"]["content"]


def _load_prompts(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _run_one(question: str, *, show_routing: bool) -> None:
    routed = route(question)
    if show_routing:
        print(f"routed: {routed}")

    chunks = gather_context(question, routed)
    print(f"retrieved {len(chunks)} chunk(s)")

    response = ollama.chat(model=MODEL_NAME, messages=_answer_messages(question, chunks))
    print(f"\n{response['message']['content']}")


if __name__ == "__main__":
    import argparse
    import sys

    # in case the console is set to a non-UTF-8 code page
    # (LLM output might have emoji or other non-ASCII characters), avoid a UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Ask the wiki-backed assistant one question, or a batch from a file")
    parser.add_argument("question", nargs="?", help="A single question to ask")
    parser.add_argument("--batch", type=Path, help="Text file with one prompt per line (# lines are comments)")
    parser.add_argument("--show-routing", action="store_true", help="Print the router's decision first")
    args = parser.parse_args()

    if args.batch:
        prompts = _load_prompts(args.batch)
        for i, question in enumerate(prompts, 1):
            print(f"\n{'=' * 70}\n[{i}/{len(prompts)}] {question}\n{'=' * 70}")
            try:
                _run_one(question, show_routing=args.show_routing)
            except Exception as exc:  # bad prompt shouldn't kill the batch
                print(f"ERROR: {exc}")
    elif args.question:
        _run_one(args.question, show_routing=args.show_routing)
    else:
        parser.error("provide a question, or --batch <file>")
