"""Local SQLite store for the player's own current state.

Inventory, equipment, effects, vitals (health/hunger/XP/game mode), and
position are each wholesale-replaced on every update - the mod pushes a
full snapshot, not a diff, so writing one is just "delete what was there,
insert what's here now." Same replace-not-diff pattern store.py already
uses for a page's Chroma chunks; no history is kept for these, only the
current value matters.

containers and placements are different on purpose: they're meant to
accumulate over time (many chests around a base, many torches placed), so
they're upserted/appended instead of replaced. That's what actually
answers "where did I put X" - a live snapshot of current state can't,
since the answer is necessarily about something in the past.

No embeddings, no Chroma, no semantic search anywhere in this module -
player state is queried exactly (get_inventory(), find_item("torch")),
never by similarity. The only thing this shares with wiki/store.py is the
SQLite ledger idea.

Item/effect ids are stored exactly as the mod would send them - Minecraft
registry ids like "minecraft:diamond_sword", not wiki page titles like
"Diamond Sword". Bridging those two naming schemes, if something ever
needs to cross-reference a player's inventory against the wiki, is the
orchestrator's problem, not this module's.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "player_db.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    slot INTEGER PRIMARY KEY,
    item TEXT NOT NULL,
    count INTEGER NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment (
    slot TEXT PRIMARY KEY,
    item TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS effects (
    effect TEXT PRIMARY KEY,
    amplifier INTEGER NOT NULL,
    duration_ticks INTEGER NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vitals (
    ts TEXT NOT NULL,
    health REAL NOT NULL,
    hunger INTEGER NOT NULL,
    saturation REAL NOT NULL,
    xp_level INTEGER NOT NULL,
    xp_progress INTEGER NOT NULL,  -- percent to next level (0-100), not the raw 0.0-1.0 fraction
    game_mode TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS position (
    ts TEXT NOT NULL,
    dim TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    biome TEXT
);

CREATE TABLE IF NOT EXISTS game_time (
    ts TEXT NOT NULL,
    day_time INTEGER NOT NULL,
    day_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS structures (
    kind TEXT NOT NULL,
    dim TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    z INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    PRIMARY KEY (dim, x, y, z)
);

CREATE TABLE IF NOT EXISTS containers (
    dim TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    z INTEGER NOT NULL,
    kind TEXT NOT NULL,
    items_json TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (dim, x, y, z)
);

CREATE TABLE IF NOT EXISTS placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    dim TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    z INTEGER NOT NULL,
    item TEXT NOT NULL,
    action TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spawn_point (
    ts TEXT NOT NULL,
    dim TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS deaths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    dim TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    cause TEXT
);
"""

# Placements worth remembering are functional/locatable blocks a player might
# lose track of and ask about - not ordinary building material. Logging every
# block placed during a large build would be almost entirely noise (nobody
# asks "where's my 4000th stone block") and, if a future mod doesn't also
# filter at the source, unnecessary write/network volume for a fast build.
# Deliberately an allowlist, not a denylist - erring toward missing an item
# type over accumulating junk. Chests/barrels/shulker boxes are NOT here on
# purpose: those are already covered by write_container(), triggered on
# open/close rather than placement.
_NOTABLE_PLACEMENT_EXACT = {
    "minecraft:torch", "minecraft:soul_torch", "minecraft:lantern", "minecraft:soul_lantern",
    "minecraft:crafting_table", "minecraft:furnace", "minecraft:blast_furnace", "minecraft:smoker",
    "minecraft:anvil", "minecraft:chipped_anvil", "minecraft:damaged_anvil",
    "minecraft:enchanting_table", "minecraft:brewing_stand", "minecraft:smithing_table",
    "minecraft:cartography_table", "minecraft:fletching_table", "minecraft:grindstone",
    "minecraft:stonecutter", "minecraft:loom",
    "minecraft:beacon", "minecraft:conduit", "minecraft:lodestone", "minecraft:respawn_anchor",
    "minecraft:ender_chest",
}
_NOTABLE_PLACEMENT_SUFFIXES = ("_bed",)


def is_notable_placement(item: str) -> bool:
    """Whether a placed/broken block is worth remembering - see the
    allowlist comment above for why this filters at all."""
    return item in _NOTABLE_PLACEMENT_EXACT or item.endswith(_NOTABLE_PLACEMENT_SUFFIXES)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(conn: sqlite3.Connection, kind: str, data: dict) -> None:
    conn.execute("INSERT INTO events (ts, kind, data_json) VALUES (?, ?, ?)", (_now(), kind, json.dumps(data)))


# --- writes: one per event kind -------------------------------------------

def write_inventory(slots: list[dict], *, db_path: Path = DEFAULT_DB_PATH) -> None:
    """slots: [{"slot": int, "item": str, "count": int}, ...] - a full snapshot."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "inventory", {"slots": slots})
        conn.execute("DELETE FROM inventory")
        conn.executemany(
            "INSERT INTO inventory (slot, item, count, ts) VALUES (?, ?, ?, ?)",
            [(s["slot"], s["item"], s["count"], ts) for s in slots],
        )


def write_equipment(slots: dict[str, str | None], *, db_path: Path = DEFAULT_DB_PATH) -> None:
    """slots: {"mainhand": "minecraft:diamond_sword", "offhand": None, ...}."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "equipment", {"slots": slots})
        conn.execute("DELETE FROM equipment")
        conn.executemany(
            "INSERT INTO equipment (slot, item, ts) VALUES (?, ?, ?)",
            [(slot, item, ts) for slot, item in slots.items() if item],
        )


def write_effects(effects: list[dict], *, db_path: Path = DEFAULT_DB_PATH) -> None:
    """effects: [{"id": str, "amplifier": int, "duration": int}, ...] - active effects only, so an
    expired one is simply absent from the next snapshot rather than needing to be cleared."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "effects", {"effects": effects})
        conn.execute("DELETE FROM effects")
        conn.executemany(
            "INSERT INTO effects (effect, amplifier, duration_ticks, ts) VALUES (?, ?, ?, ?)",
            [(e["id"], e["amplifier"], e["duration"], ts) for e in effects],
        )


def write_vitals(
    *,
    health: float,
    hunger: int,
    saturation: float,
    xp_level: int,
    xp_progress: int,  # percent to next level (0-100)
    game_mode: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    ts = _now()
    payload = {
        "health": health, "hunger": hunger, "saturation": saturation,
        "xp_level": xp_level, "xp_progress": xp_progress, "game_mode": game_mode,
    }
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "vitals", payload)
        conn.execute("DELETE FROM vitals")
        conn.execute(
            "INSERT INTO vitals (ts, health, hunger, saturation, xp_level, xp_progress, game_mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, health, hunger, saturation, xp_level, xp_progress, game_mode),
        )


def write_position(
    *, dim: str, x: float, y: float, z: float, biome: str | None = None, db_path: Path = DEFAULT_DB_PATH,
) -> None:
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "position", {"dim": dim, "pos": [x, y, z], "biome": biome})
        conn.execute("DELETE FROM position")
        conn.execute(
            "INSERT INTO position (ts, dim, x, y, z, biome) VALUES (?, ?, ?, ?, ?, ?)", (ts, dim, x, y, z, biome),
        )


def write_game_time(*, day_time: int, day_count: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    """day_time: ticks within the current day (0-23999). day_count: total
    elapsed in-game days since the world was created. Wholesale replace,
    like position/vitals - only the current moment matters, no history."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "game_time", {"day_time": day_time, "day_count": day_count})
        conn.execute("DELETE FROM game_time")
        conn.execute("INSERT INTO game_time (ts, day_time, day_count) VALUES (?, ?, ?)", (ts, day_time, day_count))


def write_structure_visit(*, kind: str, dim: str, x: int, y: int, z: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Records a structure as discovered. dim/x/y/z should be the structure's
    own stable reference point (Minecraft's StructureStart bounding-box
    origin), not the player's position at the moment of detection - a
    village or fortress spans a wide area, and keying on the player's
    ever-changing coordinates within it would record the same discovery
    over and over instead of recognizing it as one. INSERT OR IGNORE means
    a re-visit is a no-op - first_seen is preserved from the original."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "structure_visit", {"kind": kind, "dim": dim, "pos": [x, y, z]})
        conn.execute(
            "INSERT OR IGNORE INTO structures (kind, dim, x, y, z, first_seen) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, dim, x, y, z, ts),
        )


def write_container(
    *, dim: str, x: int, y: int, z: int, kind: str, items: list[dict], db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """items: [{"item": str, "count": int}, ...] - no slot index. A chest's
    slot layout is arbitrary (whichever slot the player happened to use)
    and nothing reads it - find_container() only ever substring-searches
    the whole blob, regardless of position within it. Upserted by location -
    unlike the snapshot tables above, many containers coexist and all need remembering."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "container", {"dim": dim, "pos": [x, y, z], "kind": kind, "items": items})
        conn.execute(
            "INSERT INTO containers (dim, x, y, z, kind, items_json, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(dim, x, y, z) DO UPDATE SET "
            "kind=excluded.kind, items_json=excluded.items_json, last_seen=excluded.last_seen",
            (dim, x, y, z, kind, json.dumps(items), ts),
        )


def write_placement(
    *, dim: str, x: int, y: int, z: int, item: str, action: str, db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """action: "place" | "break". Appended, not replaced - a log, not a snapshot.

    Silently ignored for anything that isn't is_notable_placement() - see
    the allowlist comment above _NOTABLE_PLACEMENT_EXACT for why. Applies to
    both place and break: find_placements() only ever looks at 'place' rows,
    so logging a break for an item that was never worth logging placed would
    just be waste with no query that could ever use it.
    """
    if not is_notable_placement(item):
        return
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "placement", {"dim": dim, "pos": [x, y, z], "item": item, "action": action})
        conn.execute(
            "INSERT INTO placements (ts, dim, x, y, z, item, action) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, dim, x, y, z, item, action),
        )


def write_spawn_point(*, dim: str, x: float, y: float, z: float, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Wholesale replace, like position - only the current spawn point (last
    bed slept in / respawn anchor activated) matters, not its history."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "spawn_point", {"dim": dim, "pos": [x, y, z]})
        conn.execute("DELETE FROM spawn_point")
        conn.execute("INSERT INTO spawn_point (ts, dim, x, y, z) VALUES (?, ?, ?, ?, ?)", (ts, dim, x, y, z))


def write_death(
    *, dim: str, x: float, y: float, z: float, cause: str | None = None, db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Appended, not replaced - unlike vanilla Minecraft's own single
    last-death memory (what the recovery compass reads), a full history
    costs nothing extra here: deaths are rare compared to block placements,
    and "how many times have I died in the Nether" is a real enough
    question to keep for free rather than overwriting on each new death."""
    ts = _now()
    with closing(_connect(db_path)) as conn, conn:
        _log_event(conn, "death", {"dim": dim, "pos": [x, y, z], "cause": cause})
        conn.execute(
            "INSERT INTO deaths (ts, dim, x, y, z, cause) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, dim, x, y, z, cause),
        )


# --- reads: the canned queries the orchestrator calls ----------------------

def get_inventory(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT slot, item, count FROM inventory ORDER BY slot").fetchall()
    return [{"slot": r[0], "item": r[1], "count": r[2]} for r in rows]


def find_item(name_substring: str, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Substring match against item ids, e.g. find_item("diamond")."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT slot, item, count FROM inventory WHERE item LIKE ? ORDER BY slot",
            (f"%{name_substring}%",),
        ).fetchall()
    return [{"slot": r[0], "item": r[1], "count": r[2]} for r in rows]


def get_equipment(db_path: Path = DEFAULT_DB_PATH) -> dict[str, str]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT slot, item FROM equipment").fetchall()
    return {r[0]: r[1] for r in rows}


def get_effects(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT effect, amplifier, duration_ticks FROM effects").fetchall()
    return [{"effect": r[0], "amplifier": r[1], "duration_ticks": r[2]} for r in rows]


def get_vitals(db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT health, hunger, saturation, xp_level, xp_progress, game_mode FROM vitals"
        ).fetchone()
    if row is None:
        return None
    return {
        "health": row[0], "hunger": row[1], "saturation": row[2],
        "xp_level": row[3], "xp_progress": row[4], "game_mode": row[5],
    }


def get_position(db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT dim, x, y, z, biome FROM position").fetchone()
    if row is None:
        return None
    return {"dim": row[0], "x": row[1], "y": row[2], "z": row[3], "biome": row[4]}


def get_game_time(db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT day_time, day_count FROM game_time").fetchone()
    if row is None:
        return None
    # 13000-23000 is a simple approximation of "dark enough to worry about
    # mobs", not the real spawn-mechanic threshold (that's light-level
    # based, not time-based) - good enough for a spoken "is it night" answer.
    return {"day_time": row[0], "day_count": row[1], "is_night": 13000 <= row[0] < 23000}


def get_visited_structures(
    kind_substring: str | None = None, db_path: Path = DEFAULT_DB_PATH, limit: int = 20,
) -> list[dict]:
    """All discovered structures, optionally filtered by kind (e.g. "village"), most recently found first."""
    query = "SELECT kind, dim, x, y, z, first_seen FROM structures"
    params: list = []
    if kind_substring:
        query += " WHERE kind LIKE ?"
        params.append(f"%{kind_substring}%")
    query += " ORDER BY first_seen DESC LIMIT ?"
    params.append(limit)
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(query, params).fetchall()
    return [{"kind": r[0], "dim": r[1], "x": r[2], "y": r[3], "z": r[4], "first_seen": r[5]} for r in rows]


def has_visited_structure(kind_substring: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    return len(get_visited_structures(kind_substring, db_path=db_path, limit=1)) > 0


def get_spawn_point(db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT dim, x, y, z FROM spawn_point").fetchone()
    if row is None:
        return None
    return {"dim": row[0], "x": row[1], "y": row[2], "z": row[3]}


def get_deaths(db_path: Path = DEFAULT_DB_PATH, limit: int = 5) -> list[dict]:
    """Most recent deaths first."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT ts, dim, x, y, z, cause FROM deaths ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"ts": r[0], "dim": r[1], "x": r[2], "y": r[3], "z": r[4], "cause": r[5]} for r in rows]


def get_last_death(db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    deaths = get_deaths(db_path=db_path, limit=1)
    return deaths[0] if deaths else None


def find_container(name_substring: str, db_path: Path = DEFAULT_DB_PATH, limit: int = 5) -> list[dict]:
    """Containers whose last-known contents mention this item, most recently seen first."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT dim, x, y, z, kind, items_json, last_seen FROM containers "
            "WHERE items_json LIKE ? ORDER BY last_seen DESC LIMIT ?",
            (f"%{name_substring}%", limit),
        ).fetchall()
    return [
        {"dim": r[0], "x": r[1], "y": r[2], "z": r[3], "kind": r[4], "items": json.loads(r[5]), "last_seen": r[6]}
        for r in rows
    ]


def find_placements(name_substring: str, db_path: Path = DEFAULT_DB_PATH, limit: int = 5) -> list[dict]:
    """Most recent place events (not breaks) for this item, one entry per
    distinct location. Doesn't check whether it was later broken again -
    good enough for "where did I put X", not exact inventory.

    Deduped by (dim, x, y, z): the same spot can show up more than once in
    the raw log, which looks like the mod double-firing its placement event.
    Keeps the most recent row per location (rows already come back in ts DESC order).
    """
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT ts, dim, x, y, z, item FROM placements WHERE action = 'place' AND item LIKE ? "
            "ORDER BY ts DESC LIMIT ?",
            (f"%{name_substring}%", limit * 4),  # extra headroom to absorb duplicate rows before deduping
        ).fetchall()

    seen: set[tuple] = set()
    results = []
    for r in rows:
        location = (r[1], r[2], r[3], r[4])
        if location in seen:
            continue
        seen.add(location)
        results.append({"ts": r[0], "dim": r[1], "x": r[2], "y": r[3], "z": r[4], "item": r[5]})
        if len(results) >= limit:
            break
    return results
