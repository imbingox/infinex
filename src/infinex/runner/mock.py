import hashlib
import json
import random
import zipfile
from pathlib import Path
from typing import Any


def verify_bundle(path: Path) -> dict[str, Any]:
    required = {
        "manifest.json",
        "strategy.py",
        "config.schema.json",
        "defaults.json",
        "checksums.json",
    }
    with zipfile.ZipFile(path) as bundle:
        names = set(bundle.namelist())
        missing = required - names
        if missing:
            raise ValueError(f"Bundle is missing files: {', '.join(sorted(missing))}")
        checksums = json.loads(bundle.read("checksums.json"))
        for name, expected in checksums.items():
            actual = hashlib.sha256(bundle.read(name)).hexdigest()
            if actual != expected:
                raise ValueError(f"Bundle checksum mismatch for {name}")
        return json.loads(bundle.read("manifest.json"))


def deterministic_backtest(
    *,
    strategy_version_id: str,
    config_hash: str,
    dataset: str,
    start_time: str | None,
    end_time: str | None,
) -> dict[str, Any]:
    seed_material = "|".join(
        [strategy_version_id, config_hash, dataset, start_time or "", end_time or ""]
    )
    seed_hex = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    randomizer = random.Random(int(seed_hex[:16], 16))
    equity = 100_000.0
    peak = equity
    max_drawdown = 0.0
    equity_curve: list[dict[str, float | int]] = [{"step": 0, "equity": equity}]
    returns: list[float] = []

    for step in range(1, 91):
        daily_return = randomizer.gauss(0.0007, 0.008)
        returns.append(daily_return)
        equity *= 1 + daily_return
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak
        max_drawdown = max(max_drawdown, drawdown)
        equity_curve.append({"step": step, "equity": round(equity, 2)})

    mean_return = sum(returns) / len(returns)
    variance = sum((item - mean_return) ** 2 for item in returns) / max(1, len(returns) - 1)
    volatility = variance**0.5
    sharpe = mean_return / volatility * (252**0.5) if volatility else 0.0
    total_return = equity / 100_000.0 - 1
    trade_count = 20 + int(seed_hex[16:20], 16) % 100

    return {
        "engine": "deterministic-mock-v1",
        "seed_sha256": seed_hex,
        "metrics": {
            "starting_balance": 100_000.0,
            "ending_balance": round(equity, 2),
            "total_return": round(total_return, 6),
            "max_drawdown": round(max_drawdown, 6),
            "sharpe_ratio": round(sharpe, 4),
            "trade_count": trade_count,
        },
        "equity_curve": equity_curve,
    }
