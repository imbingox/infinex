import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "stamp_web_version.py"


def test_stamp_package_version_updates_only_version(tmp_path) -> None:
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    package_path = web_dir / "package.json"
    package_path.write_text(
        json.dumps(
            {
                "name": "infinex-web",
                "private": True,
                "version": "0.1.0",
                "scripts": {"build": "vite build"},
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "0.2.0"],
        cwd=tmp_path,
        check=True,
    )

    content = json.loads(package_path.read_text(encoding="utf-8"))
    assert content == {
        "name": "infinex-web",
        "private": True,
        "version": "0.2.0",
        "scripts": {"build": "vite build"},
    }
    assert package_path.read_text(encoding="utf-8").endswith("\n")
