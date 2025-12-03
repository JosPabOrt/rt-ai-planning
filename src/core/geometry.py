from typing import Tuple
import numpy as np


def compute_centroid(mask: np.ndarray,
                     spacing: Tuple[float, float, float]) -> Tuple[float, float, float]:
    idx = np.argwhere(mask)
    if idx.size == 0:
        return (0.0, 0.0, 0.0)

    mean_idx = idx.mean(axis=0)  # (z, y, x)
    dz, dy, dx = spacing
    centroid_mm = (
        float(mean_idx[0] * dz),
        float(mean_idx[1] * dy),
        float(mean_idx[2] * dx),
    )
    return centroid_mm


def compute_volume_cc(mask: np.ndarray,
                      spacing: Tuple[float, float, float]) -> float:
    dz, dy, dx = spacing
    voxel_vol_mm3 = float(dz * dy * dx)
    num_voxels = int(mask.sum())
    vol_mm3 = num_voxels * voxel_vol_mm3
    return vol_mm3 / 1000.0
