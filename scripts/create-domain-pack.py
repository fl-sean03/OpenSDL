from __future__ import annotations

import argparse
from pathlib import Path

from opensdl_cli.scaffold import create_domain_pack


parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("--destination", type=Path, default=Path("domain-packs"))
args = parser.parse_args()
print(create_domain_pack(args.destination / args.name, name=args.name))
