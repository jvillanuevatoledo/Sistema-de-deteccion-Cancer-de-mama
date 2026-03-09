import sys
from pathlib import Path

import numpy as np
import pytest

_VIEWER_DIR = str(Path(__file__).resolve().parent.parent / "src" / "viewer")
if _VIEWER_DIR not in sys.path:
    sys.path.insert(0, _VIEWER_DIR)

@pytest.fixture
def identity_affine():
    return np.eye(4)

@pytest.fixture
def scaled_affine():
    """Affine con voxel spacing 0.5 mm y offset (10, 20, 30)."""
    aff = np.diag([0.5, 0.5, 0.5, 1.0])
    aff[:3, 3] = [10.0, 20.0, 30.0]
    return aff

@pytest.fixture
def sample_volume():
    """Volumen 3D pequeño (4, 8, 8) con valores float32."""
    rng = np.random.default_rng(42)
    return rng.random((4, 8, 8), dtype=np.float32) * 1000

@pytest.fixture
def sample_mask():
    """Máscara uint16 con etiquetas 0, 1 y 2."""
    mask = np.zeros((4, 8, 8), dtype=np.uint16)
    mask[1, 2:5, 2:5] = 1
    mask[2, 3:6, 3:6] = 2
    return mask

@pytest.fixture
def patient_tree(tmp_path):
    """
    Crea una estructura de directorios típica:

        tmp/MAMA/PROCESSED_DATA/PAC001/
            volume.nii.gz
            img.png
            ANNOTATIONS/
                mask.nii.gz
    """
    import nibabel as nib

    base = tmp_path
    proc = base / "MAMA" / "PROCESSED_DATA" / "PAC001"
    proc.mkdir(parents=True)

    vol = np.zeros((2, 4, 4), dtype=np.float32)
    nib.save(nib.Nifti1Image(vol, np.eye(4)), proc / "volume.nii.gz")

    from PIL import Image
    Image.fromarray(np.zeros((4, 4), dtype=np.uint8)).save(proc / "img.png")

    ann_dir = proc / "ANNOTATIONS"
    ann_dir.mkdir()
    mask = np.zeros((2, 4, 4), dtype=np.uint16)
    nib.save(nib.Nifti1Image(mask, np.eye(4)), ann_dir / "mask.nii.gz")

    return base