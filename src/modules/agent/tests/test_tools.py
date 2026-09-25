"""Structural sanity checks for tools.py - no live network/Ollama/DB calls.

Dispatch mechanics (unrecognized tool name, an underlying exception becoming
a tool-role error message) are exercised in test_orchestrator.py instead,
since that's where run_agent's dispatch loop actually lives - tools.py itself
is just the TOOLS list/TOOL_MAP and the wrapper functions, no dispatch logic.
"""

import inspect
from types import SimpleNamespace

import tools

_PATH_PARAM_NAMES = {"db_path", "cache_dir", "chroma_dir"}


def test_tool_map_matches_tools_by_name():
    assert tools.TOOL_MAP == {fn.__name__: fn for fn in tools.TOOLS}
    assert len(tools.TOOL_MAP) == len(tools.TOOLS)  # no duplicate names


def test_no_tool_exposes_a_path_parameter():
    for fn in tools.TOOLS:
        params = set(inspect.signature(fn).parameters)
        assert not (params & _PATH_PARAM_NAMES), f"{fn.__name__} exposes a path parameter: {params & _PATH_PARAM_NAMES}"


def test_every_tool_has_a_docstring():
    for fn in tools.TOOLS:
        assert fn.__doc__ and fn.__doc__.strip(), f"{fn.__name__} has no docstring"


def test_skills_are_zero_argument_and_return_nonempty_text():
    # tools.skills, not a separately bare-imported `skills` module - a bare
    # `import skills` here would load a second, distinct copy of the module
    # (different sys.modules key than tools.py's own qualified import),
    # whose functions are never `is`/`in`-equal to the ones in tools.TOOLS.
    assert tools.skills.SKILLS  # not accidentally empty
    for fn in tools.skills.SKILLS:
        assert fn in tools.TOOLS, f"{fn.__name__} is in skills.SKILLS but missing from tools.TOOLS"
        assert inspect.signature(fn).parameters == {}
        result = fn()
        assert isinstance(result, str) and result.strip()


def test_seed_pages_is_a_nonempty_list_of_strings():
    assert tools.SEED_PAGES
    assert all(isinstance(title, str) and title for title in tools.SEED_PAGES)


def test_wiki_page_search_caps_n_results_regardless_of_what_is_requested(monkeypatch):
    # Observed live: qwen3:14b explicitly requested n_results=10, got a large
    # result full of tables, and never got back to the player-state check it
    # still needed - a smaller default alone wouldn't help since the model
    # can (and did) override it.
    captured = {}

    monkeypatch.setattr(tools.orchestrator, "ensure_page", lambda title: SimpleNamespace(title=title))
    monkeypatch.setattr(
        tools.store, "query_prose",
        lambda page_title, query_text, *, n_results: captured.setdefault("n_results", n_results) or ["chunk"],
    )

    tools.wiki_page_search("Food", "a query", n_results=10)

    assert captured["n_results"] == tools._MAX_WIKI_RESULTS
