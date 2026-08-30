# AURA Firmware

## Targets

| Project | Role |
|---------|------|
| `aura_tx` | Offline WiFi probe transmitter (channel 6) |
| `aura_rx` | CSI receiver — streams binary over UART @ 921600 baud |

## Build (ESP-IDF v5.1+)

```bash
. $IDF_PATH/export.sh

# Transmitter
cd aura_tx && idf.py set-target esp32c6 && idf.py build flash monitor

# Receiver (set unique node ID per board)
cd ../aura_rx && idf.py set-target esp32c6 && idf.py build flash monitor
```

## Node ID

Set via compile flag:

```bash
idf.py -D CONFIG_AURA_NODE_ID=2 build flash
```

Or edit `#define CONFIG_AURA_NODE_ID` in `aura_rx/main/main.c`.

## Protocol

See `common/aura_protocol.h` for binary frame format consumed by `tools/record_session.py`.
