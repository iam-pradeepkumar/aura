"""Optional local MQTT publisher for sensing_v2 outputs.

Informed by techniques described in spatial-ai (MQTT / Home Assistant),
reimplemented for ESP32 CSI in AURA. Local broker only — no cloud dependency.
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)


class MqttSensingBridge:
    """Publish sensing snapshots to a local Mosquitto broker."""

    def __init__(self, broker: str = "127.0.0.1", port: int = 1883, topic_prefix: str = "aura/sensing"):
        self.broker = broker
        self.port = port
        self.topic_prefix = topic_prefix.rstrip("/")
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt not installed — MQTT bridge disabled")
            return False

        try:
            self._client = mqtt.Client()
            self._client.connect(self.broker, self.port, keepalive=30)
            self._client.loop_start()
            self._connected = True
            return True
        except Exception as exc:
            logger.debug("MQTT connect failed: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    def _publish(self, topic: str, payload: dict) -> None:
        if not self._connected or self._client is None:
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=0)
        except Exception as exc:
            logger.debug("MQTT publish failed: %s", exc)

    def publish_frame(self, frame: dict) -> None:
        ts = frame.get("timestamp", time.time())
        prefix = self.topic_prefix

        self._publish(
            f"{prefix}/zone/count",
            {"count": frame.get("target_count", 0), "timestamp": ts},
        )

        for t in frame.get("targets", []):
            tid = t.get("id", 0)
            self._publish(
                f"{prefix}/target/{tid}/position",
                {
                    "x_m": t.get("x_m"),
                    "y_m": t.get("y_m"),
                    "confidence": t.get("confidence"),
                    "timestamp": ts,
                },
            )
            self._publish(
                f"{prefix}/target/{tid}/vitals",
                {
                    "resp_bpm": t.get("respiration_bpm"),
                    "hr_bpm": t.get("heartbeat_bpm"),
                    "resp_confidence": t.get("resp_confidence"),
                    "hr_confidence": t.get("hr_confidence"),
                    "timestamp": ts,
                },
            )
            triage = t.get("suggested_triage")
            if triage:
                self._publish(
                    f"{prefix}/target/{tid}/triage",
                    {
                        "suggested": triage,
                        "confidence": t.get("triage_confidence"),
                        "timestamp": ts,
                    },
                )

        for evt in frame.get("distress_events", []):
            self._publish(f"{prefix}/events/{evt.get('type', 'unknown')}", {**evt, "timestamp": ts})
