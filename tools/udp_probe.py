#!/usr/bin/env python3
"""Quick UDP diagnostic — show which ESP32 boards send CSI and their node IDs."""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor.wireless import DEFAULT_UDP_PORT, WirelessReceiver


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe AURA UDP CSI packets")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()

    rx = WirelessReceiver(port=args.port)
    try:
        rx.start()
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Stop the dashboard Live Hardware session first (only one UDP listener).", file=sys.stderr)
        sys.exit(1)
    print(f"Listening on UDP :{args.port} for {args.seconds:.0f}s")
    print("Power on TX + RX boards. Hotspot must be AURA_HUB / aura2026.\n")

    start = time.time()
    try:
        while time.time() - start < args.seconds:
            time.sleep(1.0)
            sources = rx.recent_sources(timeout_sec=5.0)
            warnings = rx.duplicate_node_warnings()
            print(f"\r[{time.time() - start:4.0f}s] devices={rx.connected_device_count()} "
                  f"node_ids={len(rx.active_nodes())}   ", end="", flush=True)
            if sources and int(time.time() - start) % 5 == 0:
                print()
                for row in sources:
                    print(f"  {row['ip']:>15}  node_id={row['node_id']}  packets={row['packets']}")
                for w in warnings:
                    print(f"  WARNING: {w}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        rx.stop()

    print("\n\nSummary")
    print("-------")
    sources = rx.recent_sources(timeout_sec=5.0)
    if not sources:
        print("No CSI packets received.")
        print("- Check hotspot gateway IP (Ubuntu often 10.42.0.1)")
        print("- git pull and re-flash RX firmware (auto-uses DHCP gateway)")
        print("- Power on TX probe first")
        return

    by_id: dict[int, list[str]] = defaultdict(list)
    for row in sources:
        by_id[row["node_id"] or 0].append(row["ip"])

    for nid in sorted(by_id):
        ips = by_id[nid]
        print(f"Node ID {nid}: {len(ips)} device(s) -> {', '.join(ips)}")

    warnings = rx.duplicate_node_warnings()
    if warnings:
        print("\nFix required:")
        for w in warnings:
            print(f"  - {w}")
        print("\nRe-flash each board (one at a time):")
        print("  cd ~/aura/firmware/aura_rx")
        print("  AURA_NODE_ID=1 idf.py -b 115200 build flash -p /dev/ttyUSB0")
        print("  AURA_NODE_ID=2 idf.py -b 115200 build flash -p /dev/ttyUSB0")
        print("  ... etc for nodes 3 and 4")
    elif len(sources) == 4 and len(by_id) == 4:
        print("\nAll 4 nodes look correct.")


if __name__ == "__main__":
    main()
