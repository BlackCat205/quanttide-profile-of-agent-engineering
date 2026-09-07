#!/usr/bin/env python3
"""Repository entrypoint; the portable engine and specification live in the skill."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/second-brain-init/scripts"))
from engine import cli

if __name__ == "__main__":
    raise SystemExit(cli())
