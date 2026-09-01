# AURA Firmware

ESP32 firmware for offline disaster CSI sensing — no internet router required.

---

## Projects

| Folder | Role | Output |
|--------|------|--------|
| `aura_tx` | WiFi probe transmitter | 802.11 frames on **channel 6**, ~20 Hz |
| `aura_rx` | CSI receiver | Captures CSI → **WiFi UDP** to laptop hub |
| `common/aura_protocol.h` | Shared protocol | 18-byte header + I/Q payload |

---

## Requirements

- **ESP-IDF v5.1+** (tested with v5.1.4)
- Target chips: **ESP32-C6** (recommended), ESP32, ESP32-C3
- External 2.4 GHz antenna recommended for rubble/outdoor use

---

## Build & flash

```bash
. $IDF_PATH/export.sh

# Transmitter (1 board)
cd firmware/aura_tx
idf.py set-target esp32c6
idf.py build flash -p /dev/ttyUSB0 monitor

# Receiver — unique NODE_ID per board (one at a time, same USB port)
cd ../aura_rx
idf.py set-target esp32    # or esp32c6
AURA_NODE_ID=1 idf.py -b 115200 build flash -p /dev/ttyUSB0
AURA_NODE_ID=2 idf.py -b 115200 build flash -p /dev/ttyUSB0
AURA_NODE_ID=3 idf.py -b 115200 build flash -p /dev/ttyUSB0
AURA_NODE_ID=4 idf.py -b 115200 build flash -p /dev/ttyUSB0
```

Press `Ctrl+]` to exit monitor.

---

## Node ID

Set per board at flash time with the **`AURA_NODE_ID`** environment variable:

```bash
AURA_NODE_ID=2 idf.py -b 115200 build flash -p /dev/ttyUSB0
```

Do **not** use `-D CONFIG_AURA_NODE_ID=N` — CMake does not pick that up.  
Default in `aura_rx/main/main.c` is node 1 if `AURA_NODE_ID` is omitted.

**Label each physical board** with its ID — must match `node_positions` in `simulation/config.yaml`.

---

## Network configuration

RX nodes connect to laptop hotspot (defined in `common/aura_protocol.h`):

| Constant | Default |
|----------|---------|
| `AURA_HUB_SSID` | `AURA_HUB` |
| `AURA_HUB_PASS` | `aura2026` |
| `AURA_HUB_IP` | `192.168.4.1` |
| `AURA_UDP_PORT` | `5555` |
| `AURA_WIFI_CHANNEL` | `6` |
| `AURA_PROBE_INTERVAL_MS` | `50` (~20 Hz) |

Change `AURA_HUB_IP` if your hotspot gateway differs, then re-flash all RX nodes.

---

## CSI streaming (`aura_rx`)

`csi_stream.c` sends **one UDP datagram per frame**:

```
[18-byte aura_csi_header_t][I/Q payload]
```

Parsed by `simulation/aura_processor/wireless.py`.

Optional UART backup: set `CONFIG_AURA_USE_UART=1` in sdkconfig — recorded via `tools/record_session.py`.

---

## Protocol header (18 bytes)

```c
typedef struct __attribute__((packed)) {
    uint32_t magic;           // 0x41555241 "AURA"
    uint8_t  version;         // 1
    uint8_t  node_id;         // 1–255
    uint8_t  link_id;
    uint8_t  reserved;
    uint32_t timestamp_ms;
    int8_t   rssi;
    uint8_t  channel;
    uint16_t subcarrier_count;
    uint16_t payload_bytes;
} aura_csi_header_t;
```

Python struct format: `<IBBBBIbBHH` (see `simulation/aura_processor/aura_protocol.py`).

I/Q payload: int8 interleaved **Imaginary, Real** (Espressif CSI format).

---

## TX operation

`aura_tx` broadcasts periodic QoS data frames. No WiFi association required.  
Power from USB bank; place outside search perimeter.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| RX won't connect to hub | SSID/password match; 2.4 GHz hotspot enabled |
| No CSI in dashboard | TX powered; same channel 6; check UDP 5555 |
| Wrong node on map | Re-flash with correct `AURA_NODE_ID=N` |
| Flash fails / no serial data | Use `-b 115200`, hold BOOT, one board at a time |
| Build fails | Run `idf.py set-target esp32c6` after chip change |

---

## Related docs

- [docs/HARDWARE_SETUP.md](../docs/HARDWARE_SETUP.md) — full field deployment guide
- [docs/WIRELESS_AND_SIMULATION.md](../docs/WIRELESS_AND_SIMULATION.md) — protocol + live operation
