"""WebSocket server that receives NDJSON player-state events from the
Fabric mod and writes them into player_db.py.

Python hosts the server - the mod connects out as a client, not the other
way around. Decided so this listener, and everything it writes, can be
developed and tested without Minecraft running at all: a script pretending
to be the mod is enough (see simulate.py). If the mod hosted the server
instead, nothing on the Python side could be exercised without the game
open.

handle_event() is the dispatch logic, deliberately separate from the
WebSocket transport loop around it, so it's unit-testable with a plain
dict and no networking - the same separation wiki/parse.py keeps between
pure text transformation and the fetch that gets it the input.
"""

from __future__ import annotations

import asyncio
import functools
import json
from pathlib import Path

import websockets

try:
    from . import player_db
except ImportError:
    import player_db

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 25585


def handle_event(event: dict, *, db_path: Path = player_db.DEFAULT_DB_PATH) -> None:
    """Dispatch one parsed event dict to the matching player_db writer."""
    kind = event.get("kind")

    if kind == "inventory":
        player_db.write_inventory(event["slots"], db_path=db_path)
    elif kind == "equipment":
        player_db.write_equipment(event["slots"], db_path=db_path)
    elif kind == "effects":
        player_db.write_effects(event["effects"], db_path=db_path)
    elif kind == "vitals":
        player_db.write_vitals(
            health=event["health"],
            hunger=event["hunger"],
            saturation=event["saturation"],
            xp_level=event["xp_level"],
            xp_progress=event["xp_progress"],
            game_mode=event["game_mode"],
            db_path=db_path,
        )
    elif kind == "position":
        x, y, z = event["pos"]
        player_db.write_position(dim=event["dim"], x=x, y=y, z=z, biome=event.get("biome"), db_path=db_path)
    elif kind == "game_time":
        player_db.write_game_time(day_time=event["day_time"], day_count=event["day_count"], db_path=db_path)
    elif kind == "structure_visit":
        x, y, z = event["pos"]
        player_db.write_structure_visit(kind=event["structure_kind"], dim=event["dim"], x=x, y=y, z=z, db_path=db_path)
    elif kind == "container":
        x, y, z = event["pos"]
        player_db.write_container(
            dim=event["dim"], x=x, y=y, z=z, kind=event["container_kind"], items=event["items"], db_path=db_path,
        )
    elif kind == "placement":
        x, y, z = event["pos"]
        player_db.write_placement(
            dim=event["dim"], x=x, y=y, z=z, item=event["item"], action=event["action"], db_path=db_path,
        )
    elif kind == "spawn_point":
        x, y, z = event["pos"]
        player_db.write_spawn_point(dim=event["dim"], x=x, y=y, z=z, db_path=db_path)
    elif kind == "death":
        x, y, z = event["pos"]
        player_db.write_death(dim=event["dim"], x=x, y=y, z=z, cause=event.get("cause"), db_path=db_path)
    else:
        print(f"player_ingest: unknown event kind {kind!r}, ignoring")


async def _handle_connection(websocket, *, db_path: Path) -> None:
    try:
        async for message in websocket:
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                print(f"player_ingest: bad JSON, ignoring: {message!r}")
                continue
            try:
                handle_event(event, db_path=db_path)
            except Exception as exc:  # noqa: BLE001 - one bad event shouldn't drop the connection
                print(f"player_ingest: failed to handle {event.get('kind')!r}: {exc}")
    except websockets.ConnectionClosed:
        # Expected, not an error: this fires whenever the client goes away
        # without a clean close handshake - which is every time Minecraft's
        # process exits, since nothing in the mod sends a close frame on
        # shutdown. Confirmed via a real reproduction (abrupt transport
        # abort) that an unhandled ConnectionClosedError here only kills
        # this one connection's task, not the server - but "connection
        # handler failed" plus a full traceback reads as a crash regardless,
        # for something that happens on every single normal game exit.
        print("player_ingest: client disconnected")


async def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, db_path: Path = player_db.DEFAULT_DB_PATH):
    """Returns the running Server - caller is responsible for shutting it down
    (async with, or .close()). Split from run_forever() so tests can start/stop it."""
    handler = functools.partial(_handle_connection, db_path=db_path)
    return await websockets.serve(handler, host, port)


async def run_forever(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, db_path: Path = player_db.DEFAULT_DB_PATH) -> None:
    server = await serve(host, port, db_path=db_path)
    async with server:
        print(f"player_ingest: listening on ws://{host}:{port}")
        await asyncio.Future()  # run until cancelled


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Player-state WebSocket ingest server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    try:
        asyncio.run(run_forever(args.host, args.port))
    except KeyboardInterrupt:
        pass
