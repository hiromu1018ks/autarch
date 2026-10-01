import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "autarch" / "scripts"
EVALS_DIR = REPO_ROOT / "evals"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(EVALS_DIR))
