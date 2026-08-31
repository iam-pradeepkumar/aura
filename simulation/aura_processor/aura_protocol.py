"""ESP32 CSI frame format — matches firmware/common/aura_protocol.h (18 bytes)."""

from __future__ import annotations

import struct

AURA_MAGIC = 0x41555241
HEADER_FMT = "<IBBBBIbBHH"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def unpack_header(data: bytes, offset: int = 0) -> tuple:
    """Return (magic, version, node_id, link_id, reserved, ts_ms, rssi, channel, sc_count, payload_bytes)."""
    return struct.unpack_from(HEADER_FMT, data, offset)


def header_fields(data: bytes, offset: int = 0) -> dict:
    magic, version, node_id, link_id, reserved, ts_ms, rssi, channel, sc_count, payload_bytes = unpack_header(
        data, offset
    )
    return {
        "magic": magic,
        "version": version,
        "node_id": node_id,
        "link_id": link_id,
        "reserved": reserved,
        "timestamp_ms": ts_ms,
        "rssi": rssi,
        "channel": channel,
        "subcarrier_count": sc_count,
        "payload_bytes": payload_bytes,
    }
