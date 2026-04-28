from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feishu-messaging-card-builder",
        description="Feishu Messaging Card Builder command line interface.",
    )
    subparsers = parser.add_subparsers(dest="command")

    for name in ("process-fixture", "update-card", "inspect-state"):
        subparsers.add_parser(name, help=f"Placeholder for {name}.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
