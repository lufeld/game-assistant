"""Make player_db.py / player_ingest.py importable as bare names (import player_db, ...).

Same approach as wiki/tests/conftest.py, one level up: no __init__.py
anywhere in this codebase, so tests use sys.path rather than a different
import convention just for tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
