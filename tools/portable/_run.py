"""Run a user script with this package's Python binding on the import path."""

import runpy
import sys
from pathlib import Path


if len(sys.argv) < 2:
    sys.exit("Usage: python.cmd SCRIPT.py [arguments ...]")
script = Path(sys.argv[1]).resolve()
if not script.is_file():
    sys.exit(f"Script does not exist: {script}")
sys.path.insert(0, str(script.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = [str(script), *sys.argv[2:]]
runpy.run_path(str(script), run_name="__main__")
