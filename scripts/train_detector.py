from __future__ import annotations

import argparse
from pathlib import Path

from mmengine.config import Config
from mmengine.runner import Runner
from mmdet.utils import register_all_modules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train bag detector with MMDetection."
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/rtmdet_bag.py"),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.config.exists():
        raise FileNotFoundError(
            f"Config not found: {args.config}"
        )

    register_all_modules(
        init_default_scope=True,
    )

    config = Config.fromfile(args.config)

    runner = Runner.from_cfg(config)

    runner.train()


if __name__ == "__main__":
    main()