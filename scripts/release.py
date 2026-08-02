from __future__ import annotations
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
parser = argparse.ArgumentParser(description="Verify a synchronized workspace version before release")
parser.add_argument("version")
args = parser.parse_args()
pattern = re.compile(r'(?m)^version = "[^"]+"$')
changed = []
for path in [ROOT / "pyproject.toml", *ROOT.glob("**/pyproject.toml")]:
    text = path.read_text(encoding="utf-8")
    updated = pattern.sub(f'version = "{args.version}"', text, count=1)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        changed.append(str(path.relative_to(ROOT)))
print(f"updated {len(changed)} project versions to {args.version}")
print("run the full test, schema, migration, and build checks before tagging")
