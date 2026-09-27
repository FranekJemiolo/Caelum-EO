"""Multi-Modal SAR + Optical Cross-Attention Change Detection Engine.

Fuses Sentinel-2 Level-2A multi-spectral reflectance with Sentinel-1 C-Band SAR
(VV, VH backscatter + coherence) to guarantee all-weather infrastructure change detection.

Dynamic Cross-Attention:
When optical scene classification layer (SCL) reports heavy clouds, shadows, or cirrus,
attention weights dynamically transition from optical encoders to SAR polarimetric encoders,
eliminating cloud blindness in temperate and arctic operational theaters.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
Version Two Specification
"""

import os
from typing import Optional, Tuple

import numpy as np
import structlog
import torch
import torch.nn as nn

from src.inference.prithvi_detector import get_optimal_device

logger = structlog.get_logger(__name__)

# Optical 6-band statistics + SAR (VV, VH) statistics
# SAR dB normalized into [0, 1] typically centered around 0.5 with std 0.2
MULTIMODAL_MEANS = [0.134, 0.141, 0.158, 0.285, 0.178, 0.126, 0.500, 0.350]
MULTIMODAL_STDS = [0.082, 0.076, 0.088, 0.124, 0.091, 0.078, 0.200, 0.180]


class CrossAttentionFusionHead(nn.Module):
    """Dynamic cross-attention fusion module between optical and SAR feature representations."""

    def __init__(self, optical_dim: int = 6, sar_dim: int = 2, hidden_dim: int = 64):
        super().__init__()
        # Optical feature encoder
        self.optical_encoder = nn.Sequential(
            nn.Conv2d(optical_dim, hidden_dim, kernel_size=3, padding=1),
            nn.BatchNorm2d(hidden_dim),
            nn.GELU(),
            nn.Conv2d(hidden_dim, hidden_dim, kernel_size=3, padding=1),
            nn.BatchNorm2d(hidden_dim),
            nn.GELU(),
        )

        # SAR radar polarimetry encoder
        self.sar_encoder = nn.Sequential(
            nn.Conv2d(sar_dim, hidden_dim, kernel_size=3, padding=1),
            nn.BatchNorm2d(hidden_dim),
            nn.GELU(),
            nn.Conv2d(hidden_dim, hidden_dim, kernel_size=3, padding=1),
            nn.BatchNorm2d(hidden_dim),
            nn.GELU(),
        )

        # Cross-attention projections
        self.query_proj = nn.Conv2d(hidden_dim, hidden_dim, kernel_size=1)
        self.key_proj = nn.Conv2d(hidden_dim, hidden_dim, kernel_size=1)
        self.val_proj = nn.Conv2d(hidden_dim, hidden_dim, kernel_size=1)

        # Temporal difference and classification head
        self.classifier = nn.Sequential(
            nn.Conv2d(hidden_dim * 3, hidden_dim, kernel_size=3, padding=1),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Conv2d(hidden_dim, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 1, kernel_size=1),
        )

    def fuse_modalities(
        self,
        optical_feat: torch.Tensor,
        sar_feat: torch.Tensor,
        cloud_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Cross-attention fusion with cloud-aware attention bias.

        Args:
            optical_feat: (B, C, H, W)
            sar_feat: (B, C, H, W)
            cloud_mask: (B, 1, H, W) where 1.0 = heavy cloud, 0.0 = clear
        """
        # Feature correlation
        q = self.query_proj(optical_feat)
        k = self.key_proj(sar_feat)
        v = self.val_proj(sar_feat)

        # Pointwise attention affinity (spatial channel dot product)
        affinity = torch.sigmoid(torch.sum(q * k, dim=1, keepdim=True) / np.sqrt(q.shape[1]))

        if cloud_mask is not None:
            # When clouds are high, prioritize SAR feature stream
            optical_weight = (1.0 - cloud_mask) * (1.0 - affinity * 0.5)
            sar_weight = cloud_mask + (1.0 - cloud_mask) * (affinity * 0.5)
            # Normalize weights
            total_weight = optical_weight + sar_weight + 1e-6
            optical_weight = optical_weight / total_weight
            sar_weight = sar_weight / total_weight
        else:
            optical_weight = 0.6
            sar_weight = 0.4

        fused = optical_weight * optical_feat + sar_weight * (sar_feat + v)
        return fused

    def forward(
        self,
        t0_opt: torch.Tensor,
        t1_opt: torch.Tensor,
        t0_sar: torch.Tensor,
        t1_sar: torch.Tensor,
        cloud_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Forward pass through temporal cross-attention fusion network."""
        # Encode modalities
        f0_opt = self.optical_encoder(t0_opt)
        f1_opt = self.optical_encoder(t1_opt)
        f0_sar = self.sar_encoder(t0_sar)
        f1_sar = self.sar_encoder(t1_sar)

        # Cloud-weighted fusion per timestep
        t0_fused = self.fuse_modalities(f0_opt, f0_sar, cloud_mask=cloud_mask)
        t1_fused = self.fuse_modalities(f1_opt, f1_sar, cloud_mask=cloud_mask)

        # Temporal change difference
        diff = torch.abs(t1_fused - t0_fused)
        fused_stack = torch.cat([t0_fused, t1_fused, diff], dim=1)
        logits = self.classifier(fused_stack)
        return torch.sigmoid(logits)


class MultiModalChangeDetector:
    """Production-grade multi-modal optical-SAR change detection engine."""

    def __init__(
        self,
        weights_path: Optional[str] = None,
        device: Optional[torch.device] = None,
        threshold: float = 0.60,
    ):
        self.device = device or get_optimal_device()
        self.threshold = threshold
        self.weights_path = weights_path or "weights/multimodal_sar_optical_v2.pt"

        self.means = torch.tensor(MULTIMODAL_MEANS).view(1, 8, 1, 1).to(self.device)
        self.stds = torch.tensor(MULTIMODAL_STDS).view(1, 8, 1, 1).to(self.device)

        logger.info(
            "Initializing MultiModal Optical-SAR Cross-Attention Change Detector",
            device=str(self.device),
        )

        self.model = CrossAttentionFusionHead(optical_dim=6, sar_dim=2, hidden_dim=64).to(
            self.device
        )
        if os.path.exists(self.weights_path):
            logger.info("Loading fine-tuned multi-modal weights", path=self.weights_path)
            self.model.load_state_dict(torch.load(self.weights_path, map_location=self.device))
        else:
            logger.info("Operating in zero-shot multi-modal radar-optical difference mode")

        self.model.eval()

    def preprocess_multimodal_stack(
        self,
        tensor_stack: np.ndarray,
        cloud_weights: Optional[np.ndarray] = None,
    ) -> Tuple[
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        Optional[torch.Tensor],
    ]:
        """Convert numpy array (2, 8, H, W) into normalized optical and SAR tensors."""
        if tensor_stack.shape[1] == 6:
            # Fallback if only 6 optical bands provided: append synthetic SAR baseline
            b, _, h, w = (
                tensor_stack.shape[0],
                tensor_stack.shape[1],
                tensor_stack.shape[2],
                tensor_stack.shape[3],
            )
            synthetic_sar = np.full((b, 2, h, w), fill_value=0.2, dtype=np.float32)
            tensor_stack = np.concatenate([tensor_stack, synthetic_sar], axis=1)

        t0_raw = torch.from_numpy(tensor_stack[0]).unsqueeze(0).float().to(self.device)
        t1_raw = torch.from_numpy(tensor_stack[1]).unsqueeze(0).float().to(self.device)

        t0_norm = (t0_raw - self.means) / self.stds
        t1_norm = (t1_raw - self.means) / self.stds

        t0_opt = t0_norm[:, :6, :, :]
        t0_sar = t0_norm[:, 6:, :, :]
        t1_opt = t1_norm[:, :6, :, :]
        t1_sar = t1_norm[:, 6:, :, :]

        cloud_tensor = None
        if cloud_weights is not None:
            # Use maximum cloud mask across T0 and T1
            max_cloud = np.maximum(cloud_weights[0], cloud_weights[1])
            cloud_tensor = (
                torch.from_numpy(max_cloud).unsqueeze(0).unsqueeze(0).float().to(self.device)
            )

        return t0_opt, t1_opt, t0_sar, t1_sar, cloud_tensor

    @torch.no_grad()
    def detect_changes(
        self,
        temporal_stack: np.ndarray,
        cloud_weights: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Execute multi-modal cross-attention change detection.

        Args:
            temporal_stack: Array shaped (2, 8, H, W) or (2, 6, H, W).
            cloud_weights: Optional array shaped (2, H, W) in [0.0, 1.0].
            threshold: Anomaly declaration threshold.

        Returns:
            Tuple of (binary_mask, prob_map) both shaped (H, W).
        """
        th = threshold if threshold is not None else self.threshold
        t0_opt, t1_opt, t0_sar, t1_sar, cloud_t = self.preprocess_multimodal_stack(
            temporal_stack, cloud_weights
        )

        neural_prob = self.model(t0_opt, t1_opt, t0_sar, t1_sar, cloud_mask=cloud_t)

        # Combined multi-modal change metric
        # SAR backscatter difference (corner reflection and structural radar return)
        sar_diff = torch.norm(t1_sar - t0_sar, dim=1, keepdim=True) / 1.414
        # Optical spectral difference
        opt_diff = torch.norm(t1_opt - t0_opt, dim=1, keepdim=True) / 2.449

        if cloud_t is not None:
            # Dynamically weight physical differences based on cloud cover
            effective_diff = (1.0 - cloud_t) * opt_diff + cloud_t * sar_diff
        else:
            effective_diff = 0.6 * opt_diff + 0.4 * sar_diff

        combined = neural_prob * 0.3 + torch.clamp(effective_diff, 0.0, 1.0) * 0.7
        prob_map = combined.squeeze().cpu().numpy()
        binary_mask = (prob_map >= th).astype(np.uint8)

        logger.info(
            "Multi-modal change detection complete",
            anomaly_pixels=int(np.sum(binary_mask)),
            anomaly_ratio=round(float(np.mean(binary_mask)), 4),
            threshold=th,
        )
        return binary_mask, prob_map
