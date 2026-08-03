from __future__ import annotations
import argparse
from pathlib import Path
from opensdl_cli.scaffold import create_adapter

parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("--capability-id", required=True)
parser.add_argument("--destination", type=Path, default=Path("adapters"))
args = parser.parse_args()
print(
    create_adapter(args.destination / args.name, name=args.name, capability_id=args.capability_id)
)
