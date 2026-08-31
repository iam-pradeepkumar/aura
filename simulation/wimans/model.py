"""Lightweight PyTorch MLP for WiMANS multi-task sensing."""

from __future__ import annotations

import torch
from torch import nn


class WimansMLP(nn.Module):
    def __init__(self, in_dim: int, count_classes: int = 6, n_slots: int = 6, n_locs: int = 5):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.BatchNorm1d(in_dim),
            nn.Linear(in_dim, 512),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
        )
        self.count_head = nn.Linear(256, count_classes)
        self.identity_head = nn.Linear(256, n_slots)
        self.location_head = nn.Linear(256, n_slots * n_locs)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        h = self.backbone(x)
        return {
            "count": self.count_head(h),
            "identity": self.identity_head(h),
            "location": self.location_head(h),
        }
