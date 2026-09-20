"""Tests for player_ingest.py.

handle_event() (the dispatch logic) is tested directly with plain dicts -
no networking involved, same as testing parse.py's functions with plain
strings. One end-to-end test also exercises the actual WebSocket server,
since that transport layer is new code too and deserves at least one real
check that bytes-over-a-socket actually reach the database.
"""

import asyncio
import json

import player_db
import player_ingest

TEST_PORT = 25599


def test_handle_event_dispatches_inventory(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {"kind": "inventory", "slots": [{"slot": 0, "item": "minecraft:diamond", "count": 1}]},
        db_path=db_path,
    )
    assert player_db.get_inventory(db_path=db_path) == [{"slot": 0, "item": "minecraft:diamond", "count": 1}]


def test_handle_event_dispatches_vitals(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {
            "kind": "vitals", "health": 20.0, "hunger": 20, "saturation": 5.0,
            "xp_level": 0, "xp_progress": 0.0, "game_mode": "survival",
        },
        db_path=db_path,
    )
    assert player_db.get_vitals(db_path=db_path)["health"] == 20.0


def test_handle_event_dispatches_position(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {"kind": "position", "dim": "minecraft:overworld", "pos": [1.0, 64.0, 2.0], "biome": "minecraft:plains"},
        db_path=db_path,
    )
    assert player_db.get_position(db_path=db_path) == {
        "dim": "minecraft:overworld", "x": 1.0, "y": 64.0, "z": 2.0, "biome": "minecraft:plains",
    }


def test_handle_event_dispatches_game_time(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event({"kind": "game_time", "day_time": 14000, "day_count": 3}, db_path=db_path)
    game_time = player_db.get_game_time(db_path=db_path)
    assert game_time["day_count"] == 3
    assert game_time["is_night"] is True


def test_handle_event_dispatches_structure_visit(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {"kind": "structure_visit", "structure_kind": "minecraft:fortress", "dim": "minecraft:the_nether", "pos": [10, 60, 10]},
        db_path=db_path,
    )
    assert player_db.has_visited_structure("fortress", db_path=db_path)


def test_handle_event_dispatches_container(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {
            "kind": "container", "dim": "minecraft:overworld", "pos": [10, 64, -5], "container_kind": "minecraft:chest",
            "items": [{"item": "minecraft:diamond", "count": 3}],
        },
        db_path=db_path,
    )
    found = player_db.find_container("diamond", db_path=db_path)
    assert found and found[0]["x"] == 10


def test_handle_event_dispatches_placement(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {"kind": "placement", "dim": "minecraft:overworld", "pos": [1, 70, 1], "item": "minecraft:torch", "action": "place"},
        db_path=db_path,
    )
    found = player_db.find_placements("torch", db_path=db_path)
    assert found and found[0]["x"] == 1


def test_handle_event_dispatches_spawn_point(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {"kind": "spawn_point", "dim": "minecraft:overworld", "pos": [5.0, 64.0, 5.0]},
        db_path=db_path,
    )
    assert player_db.get_spawn_point(db_path=db_path) == {"dim": "minecraft:overworld", "x": 5.0, "y": 64.0, "z": 5.0}


def test_handle_event_dispatches_death(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event(
        {"kind": "death", "dim": "minecraft:the_nether", "pos": [1.0, 70.0, 1.0], "cause": "minecraft:lava"},
        db_path=db_path,
    )
    assert player_db.get_last_death(db_path=db_path)["cause"] == "minecraft:lava"


def test_handle_event_ignores_unknown_kind(tmp_path, capsys):
    db_path = tmp_path / "player.sqlite3"
    player_ingest.handle_event({"kind": "something_new"}, db_path=db_path)  # must not raise
    assert "unknown event kind" in capsys.readouterr().out


def test_websocket_server_receives_and_persists_events(tmp_path):
    """Real end-to-end check: connect a client, send NDJSON over an actual
    socket, confirm it lands in the database - the one thing the dispatch
    unit tests above can't cover on their own."""
    import websockets

    db_path = tmp_path / "player.sqlite3"

    async def scenario():
        server = await player_ingest.serve("127.0.0.1", TEST_PORT, db_path=db_path)
        try:
            async with websockets.connect(f"ws://127.0.0.1:{TEST_PORT}") as ws:
                await ws.send(json.dumps(
                    {"kind": "inventory", "slots": [{"slot": 0, "item": "minecraft:diamond", "count": 7}]}
                ))
                await ws.send(json.dumps(
                    {"kind": "position", "dim": "minecraft:overworld", "pos": [1.0, 64.0, 2.0]}
                ))
                await asyncio.sleep(0.1)  # let the server task finish processing both messages
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())

    assert player_db.get_inventory(db_path=db_path) == [{"slot": 0, "item": "minecraft:diamond", "count": 7}]
    assert player_db.get_position(db_path=db_path) == {
        "dim": "minecraft:overworld", "x": 1.0, "y": 64.0, "z": 2.0, "biome": None,
    }
