import argparse
import json
import signal
import time
from pathlib import Path
from typing import Any

from infinex.runner.mock import deterministic_backtest, verify_bundle


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True), flush=True)


def run_live(args: argparse.Namespace) -> int:
    stopping = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    emit(
        "live_runner_started",
        deployment_id=args.deployment_id,
        generation=args.generation,
    )
    while not stopping:
        time.sleep(0.5)
    emit(
        "live_runner_stopped",
        deployment_id=args.deployment_id,
        generation=args.generation,
    )
    return 0


def run_backtest(args: argparse.Namespace) -> int:
    manifest = verify_bundle(args.bundle)
    result = deterministic_backtest(
        strategy_version_id=args.strategy_version_id,
        config_hash=args.config_hash,
        dataset=args.dataset,
        start_time=args.start_time,
        end_time=args.end_time,
    )
    result["manifest"] = {
        "strategy_id": manifest.get("strategy_id"),
        "strategy_version_id": manifest.get("strategy_version_id"),
        "runtime_version": manifest.get("runtime_version"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    emit("backtest_runner_succeeded", output=str(args.output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Infinex isolated mock runner")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    live = subparsers.add_parser("live")
    live.add_argument("--deployment-id", required=True)
    live.add_argument("--generation", type=int, required=True)
    live.set_defaults(handler=run_live)

    backtest = subparsers.add_parser("backtest")
    backtest.add_argument("--strategy-version-id", required=True)
    backtest.add_argument("--config-hash", required=True)
    backtest.add_argument("--dataset", required=True)
    backtest.add_argument("--bundle", type=Path, required=True)
    backtest.add_argument("--output", type=Path, required=True)
    backtest.add_argument("--start-time")
    backtest.add_argument("--end-time")
    backtest.set_defaults(handler=run_backtest)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
