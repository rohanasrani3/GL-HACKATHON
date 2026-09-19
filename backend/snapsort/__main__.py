"""CLI: python -m snapsort analyze <image> [--captured-at ISO] [--tz Asia/Hong_Kong]"""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from .models import get_client
from .pipeline import analyze


def main() -> None:
    p = argparse.ArgumentParser(prog="snapsort")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyze one screenshot and print proposals")
    a.add_argument("image", type=Path)
    a.add_argument("--captured-at", default=None)
    a.add_argument("--tz", default=None)
    a.add_argument("--locale", default="en-HK")
    args = p.parse_args()

    cap = datetime.fromisoformat(args.captured_at) if args.captured_at else None
    result = asyncio.run(analyze(get_client(), args.image.read_bytes(), cap, args.tz, args.locale))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
