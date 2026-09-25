"""Make the agent/ modules importable as bare names (import tools, import
orchestrator, ...). Matches wiki/tests/conftest.py's and player/tests/
conftest.py's convention - no __init__.py anywhere in this codebase.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
