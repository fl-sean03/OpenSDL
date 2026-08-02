from __future__ import annotations
import shutil
from pathlib import Path

root = Path(__file__).parents[1] / "examples" / "simulated-color-mixing" / ".opensdl"
if root.exists():
    shutil.rmtree(root)
print(f"reset {root}")
