"""Skills: named strategies for common question shapes, exposed as zero-argument
tools rather than always-present system-prompt text.

Each one's docstring is what the model sees in its tool schema - that's what
it reads to decide *when* to call it. The return value is short guidance
text, not game data - consulting a skill costs one hop but no game/wiki I/O.
"""

from __future__ import annotations


def skill_crafting_chain() -> str:
    """Consult this when a question needs walking a crafting dependency
    chain - e.g. "can I make X" where X or one of its ingredients might
    itself need crafting first. Returns strategy guidance, not game data."""
    return (
        "To resolve a crafting-chain question: (1) find the target item's "
        "recipe via wiki_page_search(target, 'crafting recipe ingredients'); "
        "(2) check ALL ingredients at once with one player_find_items(names) "
        "call, not one at a time; (3) for any ingredient not found, check "
        "whether THAT ingredient itself has a recipe (repeat step 1 on it) "
        "before concluding the player can't make it - a missing ingredient "
        "might itself be craftable from things the player already has."
    )


def skill_player_navigation() -> str:
    """Consult this when a question needs giving the player directions to a
    location - their bed, a death, a structure, a placed block, etc.
    Returns strategy guidance, not game data."""
    return (
        "Call player_position() for the player's current coordinates, and "
        "the relevant lookup (player_spawn_point, player_deaths, "
        "player_find_placements, player_visited_structures, ...) for the "
        "target's coordinates. If they're in different dimensions, say so "
        "plainly - a walking direction can't be given across dimensions. "
        "Otherwise describe direction in cardinal terms (e.g. northeast) "
        "and an approximate distance in blocks."
    )


def skill_category_lookup() -> str:
    """Consult this when checking whether the player has ANY item in a
    broad category (food, tools, ores, ...) rather than one specific named
    item - e.g. "do I have any food left?". Returns strategy guidance, not
    game data."""
    return (
        "Don't search player_find_items for the category word itself (e.g. "
        "'food') - real item names rarely contain it (a carried rabbit is "
        "food, but its item name doesn't contain the word 'food'). Two "
        "required steps, in order: (1) find specific item names in that "
        "category with a NARROW wiki_page_search query, e.g. "
        "wiki_page_search('Food', 'list of food item names') - keep it "
        "narrow so you get names back, not a full mechanics writeup; (2) "
        "pass ALL those specific names to ONE player_find_items(names) call "
        "- it already checks both inventory and every known container. Do "
        "not answer after step (1) alone - a list of what belongs to the "
        "category is not an answer to whether the player HAS one; step (2) "
        "is required before answering."
    )


def skill_wiki_search_strategy() -> str:
    """Consult this when a question uses vague or colloquial phrasing with
    no clear wiki page title (e.g. "the black monster in the nether" instead
    of a real mob name). Returns strategy guidance, not game data."""
    return (
        "Don't guess a title directly - call wiki_search_candidates with "
        "your best plain-language guess, then look at the returned titles "
        "and pick the one that actually matches what's being described "
        "(check one with wiki_page_overview first if it's not obvious). "
        "Results are ranked by keyword overlap, not concept match - the top "
        "result is not always right."
    )


SKILLS = [skill_crafting_chain, skill_player_navigation, skill_category_lookup, skill_wiki_search_strategy]
