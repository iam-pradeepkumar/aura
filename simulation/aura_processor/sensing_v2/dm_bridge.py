"""Bridge CSI triage suggestions to DM Console pending queue.

Preserves human-in-the-loop approval — never auto-broadcasts.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_severity_map = {
    "immediate": "critical",
    "delayed": "warning",
    "minor": "advisory",
}

_recent_keys: dict[str, float] = {}
_COOLDOWN_SEC = 120.0


def _cooldown_key(target_id: int, triage: str) -> str:
    return f"{target_id}:{triage}"


def enqueue_triage_suggestion(
    target: dict,
    *,
    min_confidence: float = 0.55,
    area_label: str = "search zone",
) -> bool:
    """Enqueue a pending DM alert for operator approval. Returns True if enqueued."""
    triage = target.get("suggested_triage")
    conf = float(target.get("triage_confidence", 0) or 0)
    if not triage or conf < min_confidence:
        return False

    tid = int(target.get("id", 0))
    key = _cooldown_key(tid, triage)
    now = time.time()
    if now - _recent_keys.get(key, 0) < _COOLDOWN_SEC:
        return False

    try:
        from disaster_alert.models import AlertType, DisasterAlert, Severity
        from disaster_alert.service import get_queue
    except Exception:
        logger.debug("DM queue unavailable — skipping triage enqueue")
        return False

    sev_name = _severity_map.get(triage, "advisory")
    severity = Severity(sev_name)
    x = target.get("x_m", 0)
    y = target.get("y_m", 0)
    resp = target.get("respiration_bpm", 0)
    title = f"CSI survivor suggestion — {triage.upper()} — {area_label}"
    message = (
        f"Suggested START triage: {triage}. "
        f"Position ({x:.1f}, {y:.1f}) m. "
        f"Resp {resp:.0f} BPM (confidence {conf:.0%}). "
        f"Requires operator approval before broadcast."
    )

    try:
        get_queue().enqueue(
            DisasterAlert(
                alert_type=AlertType.TEST,
                severity=severity,
                title=title,
                message=message,
                source="aura_sensing_v2",
                metadata={
                    "target_id": tid,
                    "x_m": x,
                    "y_m": y,
                    "suggested_triage": triage,
                    "triage_confidence": conf,
                    "respiration_bpm": resp,
                },
            )
        )
        _recent_keys[key] = now
        return True
    except RuntimeError:
        logger.debug("DM engine not initialized — triage suggestion not enqueued")
        return False
