#!/usr/bin/env python3
"""Start the AURA Command Center.

Usage:
  python dashboard/run.py
  PORT=10000 python dashboard/run.py
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


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA Command Center")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=int(os.environ.get("PORT", DEFAULT_PORT)),
        help=f"HTTP port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    args = parser.parse_args()

    port = args.port
    if not os.environ.get("PORT") and not port_available(port):
        print(f"ERROR: Port {port} is in use.", file=sys.stderr)
        sys.exit(1)

    print(f"AURA Command Center → http://127.0.0.1:{port}/")
    uvicorn.run("dashboard.app:app", host=args.host, port=port, reload=False)


if __name__ == "__main__":
    main()
