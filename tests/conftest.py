import sys
from pathlib import Path

# Make scripts/ importable as a top-level module for the tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
