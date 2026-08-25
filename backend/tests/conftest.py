import sys
from pathlib import Path

# Make the backend package importable regardless of invocation directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
