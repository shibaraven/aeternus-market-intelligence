import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AETERNUS_DISABLE_BACKGROUND_TASKS", "1")
os.environ.setdefault("AETERNUS_FRONTEND", str(ROOT / "frontend"))
os.environ.setdefault("AETERNUS_DATA", tempfile.mkdtemp(prefix="aeternus-tests-"))
