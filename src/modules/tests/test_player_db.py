"""Tests for player_db.py - pure local SQLite, no networking, so these run
the same way as wiki/tests/test_store.py: real I/O against a tmp_path, no
mocking needed.
"""

import player_db


def test_inventory_round_trip(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    slots = [{"slot": 0, "item": "minecraft:diamond", "count": 12}, {"slot": 1, "item": "minecraft:stick", "count": 3}]
    player_db.write_inventory(slots, db_path=db_path)
    assert player_db.get_inventory(db_path=db_path) == slots


def test_inventory_write_replaces_not_merges(tmp_path):
    """A full snapshot replaces the last one - it's not a diff/merge."""
    db_path = tmp_path / "player.sqlite3"
    player_db.write_inventory([{"slot": 0, "item": "minecraft:diamond", "count": 12}], db_path=db_path)
    player_db.write_inventory([{"slot": 0, "item": "minecraft:iron_ingot", "count": 5}], db_path=db_path)

    inventory = player_db.get_inventory(db_path=db_path)
    assert inventory == [{"slot": 0, "item": "minecraft:iron_ingot", "count": 5}]


def test_find_item_matches_by_substring(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_inventory(
        [
            {"slot": 0, "item": "minecraft:diamond", "count": 12},
            {"slot": 1, "item": "minecraft:diamond_sword", "count": 1},
            {"slot": 2, "item": "minecraft:stick", "count": 3},
        ],
        db_path=db_path,
    )
    found = player_db.find_item("diamond", db_path=db_path)
    assert {f["item"] for f in found} == {"minecraft:diamond", "minecraft:diamond_sword"}


def test_equipment_round_trip_skips_empty_slots(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_equipment(
        {"mainhand": "minecraft:diamond_sword", "offhand": None, "head": "minecraft:iron_helmet"},
        db_path=db_path,
    )
    assert player_db.get_equipment(db_path=db_path) == {
        "mainhand": "minecraft:diamond_sword",
        "head": "minecraft:iron_helmet",
    }


def test_effects_round_trip_and_expiry_by_absence(tmp_path):
    """An effect wearing off just means it's not in the next snapshot - no
    separate 'remove' event needed."""
    db_path = tmp_path / "player.sqlite3"
    player_db.write_effects([{"id": "minecraft:speed", "amplifier": 1, "duration": 200}], db_path=db_path)
    assert player_db.get_effects(db_path=db_path) == [
        {"effect": "minecraft:speed", "amplifier": 1, "duration_ticks": 200}
    ]

    player_db.write_effects([], db_path=db_path)
    assert player_db.get_effects(db_path=db_path) == []


def test_vitals_round_trip(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_vitals(
        health=18.0, hunger=15, saturation=3.0, xp_level=12, xp_progress=0.4, game_mode="survival",
        db_path=db_path,
    )
    vitals = player_db.get_vitals(db_path=db_path)
    assert vitals["health"] == 18.0
    assert vitals["game_mode"] == "survival"
    assert vitals["xp_level"] == 12


def test_vitals_is_none_before_any_write(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    assert player_db.get_vitals(db_path=db_path) is None


def test_position_round_trip_latest_only(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_position(dim="minecraft:overworld", x=10.0, y=64.0, z=-5.0, biome="minecraft:plains", db_path=db_path)
    player_db.write_position(dim="minecraft:the_nether", x=1.0, y=80.0, z=1.0, biome="minecraft:nether_wastes", db_path=db_path)

    position = player_db.get_position(db_path=db_path)
    assert position == {"dim": "minecraft:the_nether", "x": 1.0, "y": 80.0, "z": 1.0, "biome": "minecraft:nether_wastes"}


def test_position_biome_is_optional(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_position(dim="minecraft:overworld", x=0.0, y=64.0, z=0.0, db_path=db_path)
    assert player_db.get_position(db_path=db_path)["biome"] is None


def test_container_upsert_keeps_other_locations(tmp_path):
    """Unlike inventory/position/etc., containers accumulate - many chests
    coexist, and writing one's contents must not erase another's."""
    db_path = tmp_path / "player.sqlite3"
    player_db.write_container(
        dim="minecraft:overworld", x=10, y=64, z=-5, kind="minecraft:chest",
        items=[{"item": "minecraft:diamond", "count": 5}], db_path=db_path,
    )
    player_db.write_container(
        dim="minecraft:overworld", x=20, y=64, z=-5, kind="minecraft:barrel",
        items=[{"item": "minecraft:torch", "count": 64}], db_path=db_path,
    )

    found = player_db.find_container("diamond", db_path=db_path)
    assert len(found) == 1
    assert found[0]["x"] == 10

    found_torch = player_db.find_container("torch", db_path=db_path)
    assert len(found_torch) == 1
    assert found_torch[0]["kind"] == "minecraft:barrel"


def test_container_reopen_updates_same_location(tmp_path):
    """Re-opening the same chest after taking something out updates its
    contents in place rather than creating a duplicate row."""
    db_path = tmp_path / "player.sqlite3"
    player_db.write_container(
        dim="minecraft:overworld", x=10, y=64, z=-5, kind="minecraft:chest",
        items=[{"item": "minecraft:diamond", "count": 5}], db_path=db_path,
    )
    player_db.write_container(
        dim="minecraft:overworld", x=10, y=64, z=-5, kind="minecraft:chest",
        items=[{"item": "minecraft:diamond", "count": 2}], db_path=db_path,
    )

    found = player_db.find_container("diamond", db_path=db_path)
    assert len(found) == 1
    assert found[0]["items"] == [{"item": "minecraft:diamond", "count": 2}]


def test_find_placements_only_returns_places_not_breaks(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_placement(dim="minecraft:overworld", x=1, y=70, z=1, item="minecraft:torch", action="place", db_path=db_path)
    player_db.write_placement(dim="minecraft:overworld", x=2, y=70, z=2, item="minecraft:torch", action="break", db_path=db_path)

    found = player_db.find_placements("torch", db_path=db_path)
    assert len(found) == 1
    assert found[0]["x"] == 1


def test_find_placements_orders_most_recent_first(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    for x in (1, 2, 3):
        player_db.write_placement(dim="minecraft:overworld", x=x, y=70, z=0, item="minecraft:torch", action="place", db_path=db_path)

    found = player_db.find_placements("torch", db_path=db_path, limit=2)
    assert [f["x"] for f in found] == [3, 2]


def test_is_notable_placement_recognizes_functional_blocks():
    assert player_db.is_notable_placement("minecraft:torch")
    assert player_db.is_notable_placement("minecraft:crafting_table")
    assert player_db.is_notable_placement("minecraft:red_bed")  # colored bed variant, suffix match


def test_is_notable_placement_rejects_ordinary_building_material():
    assert not player_db.is_notable_placement("minecraft:stone")
    assert not player_db.is_notable_placement("minecraft:oak_planks")
    assert not player_db.is_notable_placement("minecraft:glass")


def test_write_placement_silently_ignores_ordinary_blocks(tmp_path):
    """A build of thousands of stone/plank placements shouldn't leave a
    single row behind - see is_notable_placement's docstring for why."""
    db_path = tmp_path / "player.sqlite3"
    for i in range(50):
        player_db.write_placement(dim="minecraft:overworld", x=i, y=70, z=0, item="minecraft:stone", action="place", db_path=db_path)

    with player_db._connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM placements").fetchone()[0]
    assert count == 0


def test_write_placement_keeps_notable_blocks_among_ordinary_ones(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_placement(dim="minecraft:overworld", x=0, y=70, z=0, item="minecraft:stone", action="place", db_path=db_path)
    player_db.write_placement(dim="minecraft:overworld", x=1, y=70, z=0, item="minecraft:torch", action="place", db_path=db_path)
    player_db.write_placement(dim="minecraft:overworld", x=2, y=70, z=0, item="minecraft:dirt", action="place", db_path=db_path)

    found = player_db.find_placements("torch", db_path=db_path)
    assert len(found) == 1
    assert found[0]["x"] == 1


def test_spawn_point_round_trip_latest_only(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_spawn_point(dim="minecraft:overworld", x=5.0, y=64.0, z=5.0, db_path=db_path)
    player_db.write_spawn_point(dim="minecraft:overworld", x=100.0, y=70.0, z=-20.0, db_path=db_path)

    assert player_db.get_spawn_point(db_path=db_path) == {
        "dim": "minecraft:overworld", "x": 100.0, "y": 70.0, "z": -20.0,
    }


def test_spawn_point_is_none_before_any_write(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    assert player_db.get_spawn_point(db_path=db_path) is None


def test_deaths_accumulate_unlike_vanillas_single_last_death_memory(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_death(dim="minecraft:overworld", x=1.0, y=64.0, z=1.0, cause="minecraft:fall", db_path=db_path)
    player_db.write_death(dim="minecraft:the_nether", x=2.0, y=70.0, z=2.0, cause="minecraft:lava", db_path=db_path)

    deaths = player_db.get_deaths(db_path=db_path)
    assert len(deaths) == 2
    assert deaths[0]["cause"] == "minecraft:lava"  # most recent first


def test_get_last_death_returns_the_most_recent_one(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_death(dim="minecraft:overworld", x=1.0, y=64.0, z=1.0, cause="minecraft:fall", db_path=db_path)
    player_db.write_death(dim="minecraft:the_nether", x=2.0, y=70.0, z=2.0, cause="minecraft:lava", db_path=db_path)

    assert player_db.get_last_death(db_path=db_path)["cause"] == "minecraft:lava"


def test_get_last_death_is_none_before_any_death(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    assert player_db.get_last_death(db_path=db_path) is None


def test_game_time_round_trip(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_game_time(day_time=1000, day_count=5, db_path=db_path)
    game_time = player_db.get_game_time(db_path=db_path)
    assert game_time["day_time"] == 1000
    assert game_time["day_count"] == 5
    assert game_time["is_night"] is False


def test_game_time_is_night_flag(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    day_cases = [(0, False), (6000, False), (12999, False), (13000, True), (18000, True), (22999, True), (23000, False)]
    for day_time, expected_is_night in day_cases:
        player_db.write_game_time(day_time=day_time, day_count=1, db_path=db_path)
        assert player_db.get_game_time(db_path=db_path)["is_night"] is expected_is_night, f"day_time={day_time}"


def test_game_time_is_none_before_any_write(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    assert player_db.get_game_time(db_path=db_path) is None


def test_structure_visit_is_recorded(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_structure_visit(kind="minecraft:village_plains", dim="minecraft:overworld", x=100, y=70, z=200, db_path=db_path)

    found = player_db.get_visited_structures(db_path=db_path)
    assert len(found) == 1
    assert found[0]["kind"] == "minecraft:village_plains"


def test_structure_revisit_does_not_duplicate(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_structure_visit(kind="minecraft:village_plains", dim="minecraft:overworld", x=100, y=70, z=200, db_path=db_path)
    player_db.write_structure_visit(kind="minecraft:village_plains", dim="minecraft:overworld", x=100, y=70, z=200, db_path=db_path)

    found = player_db.get_visited_structures(db_path=db_path)
    assert len(found) == 1


def test_get_visited_structures_filters_by_kind(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    player_db.write_structure_visit(kind="minecraft:village_plains", dim="minecraft:overworld", x=100, y=70, z=200, db_path=db_path)
    player_db.write_structure_visit(kind="minecraft:fortress", dim="minecraft:the_nether", x=10, y=60, z=10, db_path=db_path)

    villages = player_db.get_visited_structures("village", db_path=db_path)
    assert len(villages) == 1
    assert villages[0]["kind"] == "minecraft:village_plains"


def test_has_visited_structure(tmp_path):
    db_path = tmp_path / "player.sqlite3"
    assert not player_db.has_visited_structure("fortress", db_path=db_path)

    player_db.write_structure_visit(kind="minecraft:fortress", dim="minecraft:the_nether", x=10, y=60, z=10, db_path=db_path)
    assert player_db.has_visited_structure("fortress", db_path=db_path)


def test_events_table_logs_everything(tmp_path):
    """events is the append-only source of truth - every write, regardless
    of kind, should leave a row there too."""
    db_path = tmp_path / "player.sqlite3"
    player_db.write_inventory([{"slot": 0, "item": "minecraft:diamond", "count": 1}], db_path=db_path)
    player_db.write_position(dim="minecraft:overworld", x=0.0, y=64.0, z=0.0, db_path=db_path)

    with player_db._connect(db_path) as conn:
        kinds = [row[0] for row in conn.execute("SELECT kind FROM events ORDER BY id")]
    assert kinds == ["inventory", "position"]
