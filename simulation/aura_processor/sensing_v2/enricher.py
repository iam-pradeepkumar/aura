"""Post-tracker frame enrichment for sensing_v2."""

from __future__ import annotations

import time

from .dm_bridge import enqueue_triage_suggestion
from .events import TargetMotionHistory, detect_distress_events
from .mqtt_bridge import MqttSensingBridge
from .triage import suggest_triage, triage_label


class SensingV2Enricher:
    """Apply triage, distress events, DM bridge, and MQTT to tracked targets."""

    def __init__(self, config: dict):
        hw = config.get("hardware", {})
        v2 = hw.get("sensing_v2", {})
        self._v2 = v2
        self._dm_enabled = bool(hw.get("dm_bridge", {}).get("enabled", False))
        self._dm_min_conf = float(hw.get("dm_bridge", {}).get("min_confidence", 0.55))
        self._motion_history = TargetMotionHistory()
        self._resp_history: dict[int, list[float]] = {}
        self._mqtt: MqttSensingBridge | None = None

        mqtt_cfg = hw.get("mqtt", {})
        if bool(mqtt_cfg.get("enabled", False)):
            broker_url = str(mqtt_cfg.get("broker", "mqtt://127.0.0.1:1883"))
            host = broker_url.replace("mqtt://", "").split(":")[0] or "127.0.0.1"
            port = 1883
            if ":" in broker_url.replace("mqtt://", ""):
                try:
                    port = int(broker_url.split(":")[-1])
                except ValueError:
                    port = 1883
            self._mqtt = MqttSensingBridge(
                broker=host,
                port=port,
                topic_prefix=str(mqtt_cfg.get("topic_prefix", "aura/sensing")),
            )
            self._mqtt.connect()

    def enrich_targets(
        self,
        targets: list[dict],
        motion_score: float,
        baseline: float,
        t_sec: float | None = None,
    ) -> tuple[list[dict], list[dict]]:
        now = t_sec if t_sec is not None else time.time()
        fall_enabled = bool(self._v2.get("fall_detection", True))
        triage_enabled = bool(self._v2.get("triage_suggestions", True))
        all_events: list[dict] = []

        for t in targets:
            tid = int(t.get("id", 0))
            resp = float(t.get("respiration_bpm", 0) or 0)
            hist = self._resp_history.setdefault(tid, [])
            if resp > 0:
                hist.append(resp)
                self._resp_history[tid] = hist[-30:]

            events = []
            if fall_enabled:
                events = detect_distress_events(
                    tid,
                    motion_score,
                    baseline,
                    resp,
                    hist,
                    self._motion_history,
                    now,
                )
                t["distress_events"] = [e.__dict__ for e in events]
                all_events.extend(t["distress_events"])

            if triage_enabled:
                triage, tconf = suggest_triage(
                    resp_bpm=resp,
                    resp_confidence=float(t.get("resp_confidence", 0) or 0),
                    velocity_mps=float(t.get("velocity_mps", 0) or 0),
                    is_moving=bool(t.get("is_moving")),
                    presence_confidence=float(t.get("confidence", 0) or 0),
                    distress_events=events,
                    t_sec=now,
                )
                t["suggested_triage"] = triage
                t["triage_confidence"] = round(tconf, 2)
                t["triage_label"] = triage_label(triage)

            if self._dm_enabled and t.get("suggested_triage"):
                enqueue_triage_suggestion(t, min_confidence=self._dm_min_conf)

        return targets, all_events

    def publish_mqtt(self, frame: dict) -> None:
        if self._mqtt is not None:
            self._mqtt.publish_frame(frame)

    def close(self) -> None:
        if self._mqtt is not None:
            self._mqtt.disconnect()
