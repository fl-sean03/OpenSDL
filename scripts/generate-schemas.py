from __future__ import annotations

import argparse
import filecmp
import tempfile
from pathlib import Path

from opensdl_cli.schemas import generate_all_json_schemas

ROOT = Path(__file__).parents[1]
DESTINATION = ROOT / "packages" / "schemas" / "jsonschema"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        generated = generate_all_json_schemas(DESTINATION)
        print(f"generated {len(generated)} schemas in {DESTINATION}")
        return
    with tempfile.TemporaryDirectory() as temporary:
        candidate = Path(temporary)
        generate_all_json_schemas(candidate)
        expected = sorted(path.name for path in DESTINATION.glob("*.json"))
        actual = sorted(path.name for path in candidate.glob("*.json"))
        if expected != actual:
            raise SystemExit(f"schema file set differs: committed={expected}, generated={actual}")
        changed = [
            name
            for name in expected
            if not filecmp.cmp(DESTINATION / name, candidate / name, shallow=False)
        ]
        if changed:
            raise SystemExit(f"generated schemas are stale: {changed}")
        print("generated schemas are current")


if __name__ == "__main__":
    main()
