"""Unit tests for spatial alignment and temporal stacking."""

import numpy as np
import pytest
from services.ingestion.consumer import SpatialAlignmentProcessor


def test_spatial_alignment_temporal_pairing():
    processor = SpatialAlignmentProcessor()

    # Create synthetic 6-band stacks for T0 and T1
    t0_stack = np.ones((6, 256, 256), dtype=np.float32) * 0.2
    t1_stack = np.ones((6, 256, 256), dtype=np.float32) * 0.8

    temporal_pair = processor.create_prithvi_temporal_pair(t0_stack, t1_stack)

    # Shape must be (2, 6, H, W) for Prithvi foundation model
    assert temporal_pair.shape == (2, 6, 256, 256)
    assert np.isclose(temporal_pair[0].mean(), 0.2)
    assert np.isclose(temporal_pair[1].mean(), 0.8)


def test_cloud_and_water_masking():
    processor = SpatialAlignmentProcessor()
    tensor = np.ones((6, 10, 10), dtype=np.float32)

    # Mask with cloud (9) at (0, 0) and water (6) at (1, 1)
    scl_mask = np.zeros((10, 10), dtype=np.int32)
    scl_mask[0, 0] = 9  # High probability cloud
    scl_mask[1, 1] = 6  # Water

    masked = processor.apply_cloud_and_water_mask(tensor, scl_mask)
    assert masked[0, 0, 0] == 0.0
    assert masked[0, 1, 1] == 0.0
    assert masked[0, 5, 5] == 1.0  # Clear pixel unaffected
