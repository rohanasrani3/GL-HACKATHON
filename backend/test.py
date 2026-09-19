"""Try any picture against the model and see what it produces.

    .venv/Scripts/python test.py                  # opens a file picker
    .venv/Scripts/python test.py path/to/pic.png  # or pass a path
    .venv/Scripts/python test.py pic.png --captured-at 2026-09-19T14:00:00+08:00

Prints (1) the raw JSON the model returned and (2) the final proposals after date resolution.
Set MODEL_PROVIDER / OLLAMA_MODEL in .env to switch models.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from snapsort.models import get_client
from snapsort.pipeline import analyze


class RecordingClient:
    """Wraps the real client so we can print the model's raw output too."""

    def __init__(self, inner):
        self.inner = inner
        self.name = inner.name
        self.raw = None

    async def extract(self, *args):
        self.raw = await self.inner.extract(*args)
        return self.raw


def pick_file() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Pick a screenshot",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        root.destroy()
        return Path(path) if path else None
    except Exception:  # noqa: BLE001 - no display available
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", type=Path)
    ap.add_argument("--captured-at", default=None, help="ISO time the screenshot was taken (default: now)")
    ap.add_argument("--tz", default=None)
    args = ap.parse_args()

    image = args.image or pick_file()
    if not image or not image.exists():
        sys.exit("No image given. Usage: python test.py path/to/pic.png")

    client = RecordingClient(get_client())
    cap = datetime.fromisoformat(args.captured_at) if args.captured_at else None
    print(f"Analyzing {image.name} with {client.name} ... (can take a minute on this laptop)\n")

    result = asyncio.run(analyze(client, image.read_bytes(), cap, args.tz))

    print("=== Raw model output ===")
    print(json.dumps(client.raw.model_dump(), indent=2, ensure_ascii=False) if client.raw else "(none)")
    print("\n=== Final result (what the phone gets) ===")
    print(result.model_dump_json(indent=2))
    print("\n=== Summary ===")
    if result.proposals:
        for p in result.proposals:
            pl = p.payload
            print(f"  + {pl.title} | {pl.start} -> {pl.end} | {pl.location.name or '-'} | confidence {p.confidence}")
    else:
        print(f"  (nothing to add: {result.skipped_reason})")
    print(f"  latency {result.latency_ms} ms")


if __name__ == "__main__":
    main()
