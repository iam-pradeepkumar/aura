"""Temporal confirmation — suppress empty-area false positives in live sensing."""

from __future__ import annotations


class OccupancyConfirmFilter:
    """
    Require fused targets to appear in consecutive frames before reporting.

    Empty-area CSI noise often flickers for 1–2 frames; real walkers persist.
    """

    def __init__(
        self,
        confirm_frames: int = 5,
        clear_frames: int = 2,
        min_node_votes: int = 2,
        min_confidence: float = 0.48,
    ):
        self.confirm_frames = max(1, confirm_frames)
        self.clear_frames = max(1, clear_frames)
        self.min_node_votes = min_node_votes
        self.min_confidence = min_confidence
        self._hit_streak = 0
        self._empty_streak = 0

    def reset(self) -> None:
        self._hit_streak = 0
        self._empty_streak = 0

    def _qualify(self, fused: list[dict]) -> list[dict]:
        return [
            t for t in fused
            if int(t.get("node_votes", 0)) >= self.min_node_votes
            and float(t.get("confidence", 0)) >= self.min_confidence
        ]

    def apply(self, fused: list[dict]) -> list[dict]:
        qualified = self._qualify(fused)
        if not qualified:
            self._empty_streak += 1
            self._hit_streak = 0
            return []

        self._empty_streak = 0
        self._hit_streak += 1
        if self._hit_streak >= self.confirm_frames:
            return qualified
        return []

    def should_reset_tracker(self) -> bool:
        return self._empty_streak >= self.clear_frames
