"""
pytest conftest: add project root to sys.path so `app.*` and `ingest.*`
imports resolve without a package install step.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
