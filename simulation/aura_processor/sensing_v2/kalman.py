"""2D Kalman position filter for sensing_v2.

Informed by techniques described in wifi-densepose-mat / spatial-ai fusion,
reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

import numpy as np


class Kalman2D:
    """Constant-velocity Kalman filter for (x, y) tracking."""

    def __init__(self, process_noise: float = 0.5, measurement_noise: float = 1.2):
        self.x = np.zeros(4)  # x, y, vx, vy
        self.P = np.eye(4) * 10.0
        self.q = process_noise
        self.r = measurement_noise
        self._initialized = False

    def reset(self, x: float, y: float) -> None:
        self.x = np.array([x, y, 0.0, 0.0])
        self.P = np.eye(4) * 5.0
        self._initialized = True

    def predict(self, dt: float) -> None:
        if not self._initialized:
            return
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ])
        G = np.array([[0.5 * dt * dt], [0.5 * dt * dt], [dt], [dt]]) * self.q
        Q = G @ G.T
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update(self, mx: float, my: float) -> tuple[float, float, float]:
        if not self._initialized:
            self.reset(mx, my)
            return mx, my, 0.0

        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        R = np.eye(2) * self.r
        z = np.array([mx, my])
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P
        vel = float(np.hypot(self.x[2], self.x[3]))
        return float(self.x[0]), float(self.x[1]), vel
