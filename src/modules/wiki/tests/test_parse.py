"""Tests for parse.py - the pure wikitext -> ParsedPage transformation.

Two tiers, deliberately: small hand-crafted snippets pin down one rendering
rule at a time (fast to read, fast to point at the actual cause on
failure); the fixture-based tests at the bottom regression-test whole real
pages against the specific bugs found and fixed while building this
module, using the exact wikitext that exposed each one.
"""

from parse import _cell_text, parse_page


def _only_section(page, title):
    matches = [s for s in page.sections if s.title == title]
    assert len(matches) == 1, f"expected exactly one {title!r} section, got {[s.title for s in page.sections]}"
    return matches[0]


# --- inline value templates: {{hp|7}} should render "7", not vanish --------

def test_hp_template_renders_its_value():
    page = parse_page("== Usage ==\nThe sword deals {{hp|7}} damage.")
    text = _only_section(page, "Usage").text
    assert "7 damage" in text
    assert "{{hp" not in text


def test_jebe_template_renders_both_editions():
    page = parse_page("== Usage ==\nDurability: {{jebe|1561|1562}}.")
    assert "1561 (Java) / 1562 (Bedrock)" in _only_section(page, "Usage").text


def test_in_template_renders_edition_name():
    page = parse_page("== Usage ==\nOnly works {{in|je}}.")
    assert "Only works (Java Edition)." in _only_section(page, "Usage").text


def test_control_template_renders_action_name():
    page = parse_page("== Usage ==\nMilk it by {{control|using}} a bucket.")
    assert "by using a bucket" in _only_section(page, "Usage").text


def test_color_template_renders_hex_value():
    page = parse_page("== Usage ==\nTinted {{color|#3D57D6}} here.")
    assert "Tinted #3D57D6 here." in _only_section(page, "Usage").text


def test_load_advancements_keeps_the_names():
    page = parse_page("== Advancements ==\n{{load advancements|Two By Two;It Spreads}}")
    assert "Two By Two;It Spreads" in _only_section(page, "Advancements").text


def test_collapse_unwraps_its_content():
    page = parse_page("== Advancements ==\n{{collapse|content=Take Aim;Arbalistic}}")
    assert "Take Aim;Arbalistic" in _only_section(page, "Advancements").text


# --- deletion-vs-separator bugs: <br>/<ref> must not run text together ----

def test_br_tag_becomes_a_separator_not_nothing():
    page = parse_page("== Usage ==\nValues: 1<br>2<br/>3.")
    assert "1; 2; 3" in _only_section(page, "Usage").text


def test_ref_tag_is_stripped_not_inlined():
    page = parse_page("== Usage ==\nSharpness<ref>Mutually exclusive with Smite.</ref> is an enchantment.")
    text = _only_section(page, "Usage").text
    assert "Sharpness is an enchantment" in text
    assert "Mutually exclusive" not in text


# --- structured content: tables, infobox, drops ----------------------------

def test_wikitable_renders_as_markdown_with_row_labels():
    page = parse_page(
        "== Usage ==\n"
        '{| class="wikitable"\n'
        "!Edition\n!Damage\n"
        "|-\n|{{JE}}\n|7\n"
        "|-\n|{{BE}}\n|8\n"
        "|}"
    )
    text = _only_section(page, "Usage").text
    assert "| Edition | Damage |" in text
    assert "| Java Edition | 7 |" in text
    assert "| Bedrock Edition | 8 |" in text


def test_cell_text_handles_none_without_crashing():
    """Table.data() documents str | None as its cell type - a cell left
    empty by a rowspan/colspan gap is None, not "". Confirmed crashing
    (TypeError from wtp.parse(None)) on a real table on "The Nether" page
    before this was handled."""
    assert _cell_text(None) == ""


def test_infobox_becomes_markdown_in_summary():
    page = parse_page("{{Infobox item\n| durability = 100\n}}\nA test item.")
    assert "**Infobox item:**" in page.summary
    assert "**durability**: 100" in page.summary


def test_infobox_drops_image_fields():
    page = parse_page(
        "{{Infobox entity\n"
        "| group = Temperate\n| 1-1 = Cow.png\n| 1-1size = 500px\n"
        "| invimage = Cow Spawn Egg\n| health = 10\n}}\nA test mob."
    )
    assert "health" in page.summary
    for leaked in ("group", "1-1", "invimage", "Cow.png"):
        assert leaked not in page.summary


def test_infobox_drops_color_fields():
    page = parse_page("{{Infobox biome\n| grasscolor = #8EB971\n| temperature = 0.5\n}}\nA test biome.")
    assert "temperature" in page.summary
    assert "grasscolor" not in page.summary
    assert "#8EB971" not in page.summary


def test_droptable_unwraps_its_dropline_children():
    page = parse_page(
        "== Drops ==\n"
        "An adult drops:\n"
        "{{DropTable\n"
        "|{{DropLine|name=Coal|quantity=1-3}}\n"
        "|{{DropLine|name=Bone|quantity=0-2}}\n"
        "}}\n"
        "More text after."
    )
    text = _only_section(page, "Drops").text
    assert "Coal" in text
    assert "Bone" in text
    assert "More text after." in text


def test_structured_content_lands_in_place_not_at_section_end():
    """Regression test for the Cow bug: a table/template used to be
    collected separately and appended at the end of the whole level-2
    section, landing after a later, unrelated subsection instead of
    staying where it actually appeared in the source."""
    page = parse_page(
        "== Drops ==\n"
        "=== On death ===\n"
        "It drops:\n"
        "{{DropTable\n|{{DropLine|name=Leather|quantity=0-2}}\n}}\n"
        "Some more death text.\n\n"
        "=== Milking ===\n"
        "It can be milked."
    )
    text = _only_section(page, "Drops").text
    assert text.index("Leather") < text.index("Some more death text") < text.index("Milking")


def test_spawn_table_renders_rows_by_category():
    page = parse_page(
        "== Mobs ==\n"
        "{{Spawn table\n"
        "|edition=java\n"
        "|monster=\n"
        "{{Spawn row|Creeper|weight=100|size=4}}\n"
        "}}"
    )
    text = _only_section(page, "Mobs").text
    assert "Java Edition" in text
    assert "Creeper" in text
    assert "weight 100" in text


def test_blacklisted_section_is_excluded():
    page = parse_page("== History ==\nAdded in version 1.0.\n\n== Usage ==\nReal content.")
    titles = [s.title for s in page.sections]
    assert "History" not in titles
    assert "Usage" in titles


# --- regression tests against real cached pages ----------------------------

def test_diamond_sword_base_damage_is_readable(wikitext):
    page = parse_page(wikitext("diamond_sword"))
    assert "7 base damage (Java Edition) and 8 base damage (Bedrock Edition)" in _only_section(page, "Usage").text


def test_diamond_sword_durability_is_clean(wikitext):
    page = parse_page(wikitext("diamond_sword"))
    assert "1561 (Java) / 1562 (Bedrock)" in page.summary


def test_wither_skeleton_drops_include_the_full_drop_table(wikitext):
    page = parse_page(wikitext("wither_skeleton"))
    text = _only_section(page, "Drops").text
    for item in ("Coal", "Bone", "Wither Skeleton Skull"):
        assert item in text


def test_cow_drops_ordering_matches_the_source(wikitext):
    page = parse_page(wikitext("cow"))
    text = _only_section(page, "Drops").text
    assert text.index("Raw Beef") < text.index("Milking")


def test_cow_infobox_has_no_image_noise(wikitext):
    page = parse_page(wikitext("cow"))
    for leaked in ("1-1", "invimage", "group2", "Baby Cow"):
        assert leaked not in page.summary


def test_cow_advancements_render_readable_names(wikitext):
    page = parse_page(wikitext("cow"))
    assert "Two By Two" in _only_section(page, "Advancements").text


def test_cold_ocean_spawn_table_is_present(wikitext):
    page = parse_page(wikitext("cold_ocean"))
    text = _only_section(page, "Mobs").text
    assert "Creeper" in text
    assert "Java Edition" in text


def test_cold_ocean_infobox_has_no_color_fields(wikitext):
    page = parse_page(wikitext("cold_ocean"))
    assert "grasscolor" not in page.summary
    assert "#8EB971" not in page.summary


def test_the_nether_parses_without_crashing(wikitext):
    """The mob-spawn-by-block-light table on this page has inconsistent
    colspan totals across its rows (12+4=16 for one mob, 14+8=22 for
    another, against a 17-column header) - real, messy wikitext that
    produces the None table cells test_cell_text_handles_none_without_crashing
    guards against. This is the actual page that surfaced the bug."""
    page = parse_page(wikitext("the_nether"))
    assert len(page.sections) > 0
