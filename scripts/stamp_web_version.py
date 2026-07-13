"""Stamp the release version into the Web package metadata."""

import json
import sys
from pathlib import Path
from typing import Any


def stamp_package_version(path: Path, version: str) -> None:
    package = _read_json(path)
    package["version"] = version
    path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return content


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: stamp_web_version.py <version>")

    stamp_package_version(Path("web/package.json"), sys.argv[1])


if __name__ == "__main__":
    main()
