"""Make the wiki/ modules importable as bare names (import parse, import store, ...).

Matches how the modules already import each other (e.g. store.py's
`from fetch import _slugify` fallback) - no __init__.py anywhere in this
codebase, so tests use the same sys.path approach rather than a different
convention just for tests.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def wikitext():
    """Load a fixture's raw wikitext by name, e.g. wikitext("diamond_sword")."""

    def _load(name: str) -> str:
        data = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
        return data["wikitext"]

    return _load
