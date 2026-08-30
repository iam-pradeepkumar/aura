#!/usr/bin/env python3
"""Start the AURA web dashboard.

Usage:
  python dashboard/run.py
  python dashboard/run.py --port 5683
  PORT=5683 python dashboard/run.py
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn

DEFAULT_PORT = 8847


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def find_free_port(start: int = DEFAULT_PORT) -> int:
    for p in range(start, start + 50):
        if port_available(p):
            return p
    raise RuntimeError("No free port found in range")


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA web dashboard")
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=int(os.environ.get("PORT", DEFAULT_PORT)),
        help=f"HTTP port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    args = parser.parse_args()

    port = args.port
    if not port_available(port):
        alt = find_free_port(port + 1)
        print(f"ERROR: Port {port} is already in use.", file=sys.stderr)
        print(f"  Stop the other server, or run:  python dashboard/run.py --port {alt}", file=sys.stderr)
        sys.exit(1)

    print(f"AURA Dashboard → http://127.0.0.1:{port}")
    uvicorn.run(
        "dashboard.app:app",
        host=args.host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
