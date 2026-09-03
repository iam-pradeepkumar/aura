"""Temporal confirmation — suppress empty-area false positives in live sensing."""

from __future__ import annotations


class OccupancyConfirmFilter:
    """
    Require fused targets to appear in consecutive frames before reporting.

    Real walkers persist; brief noise flickers 1–2 frames. Motion-consensus
    targets (multinode motion, weak XY) need one extra confirmation frame.
    """

    def __init__(
        self,
        confirm_frames: int = 3,
        clear_frames: int = 2,
        min_node_votes: int = 2,
        min_confidence: float = 0.38,
        consensus_extra_frames: int = 1,
    ):
        self.confirm_frames = max(1, confirm_frames)
        self.clear_frames = max(1, clear_frames)
        self.min_node_votes = min_node_votes
        self.min_confidence = min_confidence
        self.consensus_extra_frames = max(0, consensus_extra_frames)
        self._hit_streak = 0
        self._empty_streak = 0

    def reset(self) -> None:
        self._hit_streak = 0
        self._empty_streak = 0

    def _qualify(self, fused: list[dict]) -> list[dict]:
        out = []
        for t in fused:
            votes = int(t.get("node_votes", 0))
            conf = float(t.get("confidence", 0))
            is_consensus = bool(t.get("motion_consensus"))
            min_v = self.min_node_votes
            min_c = self.min_confidence
            if is_consensus:
                min_c = max(min_c, 0.40)
            if votes >= min_v and conf >= min_c:
                out.append(t)
            elif votes >= 2 and conf >= min_c * 0.9:
                out.append(t)
        return out

    def _need_frames(self, qualified: list[dict]) -> int:
        if any(t.get("motion_consensus") for t in qualified):
            return self.confirm_frames + self.consensus_extra_frames
        return self.confirm_frames

    def apply(self, fused: list[dict]) -> list[dict]:
        qualified = self._qualify(fused)
        if not qualified:
            self._empty_streak += 1
            self._hit_streak = 0
            return []

        self._empty_streak = 0
        self._hit_streak += 1
        if self._hit_streak >= self._need_frames(qualified):
            return qualified
        return []

    def should_reset_tracker(self) -> bool:
        return self._empty_streak >= self.clear_frames
