"""Stand-in for the Fabric mod - connects to a running player_ingest.py
server and sends sample NDJSON events, so the whole pipeline (and the
orchestrator reading from it) can be exercised without Minecraft running.

Usage:
    python player_ingest.py &              # start the server once
    python player_simulate.py               # send player_events_sample.jsonl
    python player_simulate.py my_events.jsonl --delay 0.5
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import websockets

DEFAULT_EVENTS_FILE = Path(__file__).resolve().parent / "player_events_sample.jsonl"


def _load_events(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line for line in (l.strip() for l in lines) if line and not line.startswith("#")]


async def send_events(uri: str, events_file: Path, *, delay: float) -> None:
    events = _load_events(events_file)
    async with websockets.connect(uri) as ws:
        for i, line in enumerate(events, 1):
            await ws.send(line)
            print(f"[{i}/{len(events)}] sent: {line[:80]}{'...' if len(line) > 80 else ''}")
            if delay:
                await asyncio.sleep(delay)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send sample player events to a running player_ingest.py server")
    parser.add_argument("events_file", type=Path, nargs="?", default=DEFAULT_EVENTS_FILE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=25585)
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds to wait between events")
    args = parser.parse_args()

    asyncio.run(send_events(f"ws://{args.host}:{args.port}", args.events_file, delay=args.delay))
