import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from infinex.control_plane.models import StrategyVersion
from infinex.control_plane.settings import get_settings


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(data: str) -> str:
    return sha256_bytes(data.encode("utf-8"))


def config_hash(config: dict[str, Any]) -> str:
    return sha256_text(canonical_json(config))


def source_snapshot_hash(
    source_code: str,
    entrypoint: str,
    runtime_version: str,
    config_schema: dict[str, Any],
    defaults: dict[str, Any],
) -> str:
    payload = {
        "source_code": source_code,
        "entrypoint": entrypoint,
        "runtime_version": runtime_version,
        "config_schema": config_schema,
        "defaults": defaults,
    }
    return sha256_text(canonical_json(payload))


def build_strategy_bundle(version: StrategyVersion, source_code: str) -> tuple[Path, str]:
    settings = get_settings()
    bundle_dir = settings.artifact_dir / "strategies" / version.strategy_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{version.id}.zip"

    manifest = {
        "strategy_id": version.strategy_id,
        "strategy_version_id": version.id,
        "version": version.version_label,
        "status": version.status,
        "entrypoint": version.entrypoint,
        "runtime_version": version.runtime_version,
        "config_schema_version": "1",
        "source_snapshot_sha256": version.source_snapshot_sha256,
        "source_ref": version.source_ref,
    }
    files = {
        "manifest.json": canonical_json(manifest).encode("utf-8"),
        "strategy.py": source_code.encode("utf-8"),
        "config.schema.json": canonical_json(version.config_schema).encode("utf-8"),
        "defaults.json": canonical_json(version.defaults).encode("utf-8"),
    }
    checksums = {name: sha256_bytes(content) for name, content in files.items()}
    files["checksums.json"] = canonical_json(checksums).encode("utf-8")

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)

    artifact_sha256 = sha256_bytes(bundle_path.read_bytes())
    return bundle_path, artifact_sha256
