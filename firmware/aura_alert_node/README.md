# AURA Alert Node — single ESP32 hazard monitor

**Only ONE board** runs this firmware. All rescue nodes use `aura_rx`.

## Role

- Connects to community/public WiFi (`disaster_alert/config.yaml` → `wifi_modes`)
- Polls lightweight hazard APIs (Open-Meteo; USGS via laptop engine)
- Serves `http://<node-ip>:8080/alert` for nearby phones
- On WiFi loss → can join `AURA_HUB` for coordination

## Flash

```bash
chmod +x tools/flash_alert_node.sh
./tools/flash_alert_node.sh /dev/ttyUSB0
```

## Laptop engine

The dashboard at `/manage` runs the primary API poller and DM approval queue.
The alert node supplements LAN broadcast when on the same WiFi.

## Hardware count

| Board | Firmware | Qty |
|-------|----------|-----|
| TX | aura_tx | 1 |
| Rescue RX | aura_rx | 4 |
| Alert monitor | aura_alert_node | **1 only** |
