from unittest.mock import patch

import numpy as np
from sam_assistant import SAM2Assistant, _select_device

class TestSelectDevice:
    def test_env_var_cpu(self, monkeypatch):
        monkeypatch.setenv("SAM2_DEVICE", "cpu")
        assert _select_device() == "cpu"

    def test_env_var_cuda(self, monkeypatch):
        monkeypatch.setenv("SAM2_DEVICE", "cuda")
        assert _select_device() == "cuda"

    def test_env_var_mps(self, monkeypatch):
        monkeypatch.setenv("SAM2_DEVICE", "mps")
        assert _select_device() == "mps"

    def test_env_var_invalid_falls_through(self, monkeypatch):
        monkeypatch.setenv("SAM2_DEVICE", "tpu")
        result = _select_device()
        assert result in ("cuda", "mps", "cpu")

    def test_no_env_no_gpu_returns_cpu(self, monkeypatch):
        monkeypatch.delenv("SAM2_DEVICE", raising=False)
        with patch("torch.cuda.is_available", return_value=False), \
             patch("torch.backends.mps.is_available", return_value=False):
            assert _select_device() == "cpu"

    def test_cuda_available(self, monkeypatch):
        monkeypatch.delenv("SAM2_DEVICE", raising=False)
        with patch("torch.cuda.is_available", return_value=True):
            assert _select_device() == "cuda"

    def test_mps_available(self, monkeypatch):
        monkeypatch.delenv("SAM2_DEVICE", raising=False)
        with patch("torch.cuda.is_available", return_value=False), \
             patch("torch.backends.mps.is_available", return_value=True):
            assert _select_device() == "mps"

class TestPostprocessMask:
    def test_empty_mask_returns_empty(self):
        mask = np.zeros((10, 32, 32), dtype=bool)
        result = SAM2Assistant._postprocess_mask(mask)
        assert result.sum() == 0

    def test_preserves_large_component(self):
        mask = np.zeros((10, 32, 32), dtype=bool)
        mask[3:8, 5:25, 5:25] = True
        result = SAM2Assistant._postprocess_mask(mask)
        assert result.sum() > 0

    def test_removes_small_isolated_blobs(self):
        mask = np.zeros((10, 64, 64), dtype=bool)
        mask[2:6, 10:50, 10:50] = True
        mask[8, 60, 60] = True
        result = SAM2Assistant._postprocess_mask(mask)
        assert result[8, 60, 60] == False
        assert result[3, 20, 20] == True

    def test_binary_closing_fills_gap(self):
        mask = np.zeros((10, 20, 20), dtype=bool)
        mask[3, 5:15, 5:15] = True
        mask[4, 5:15, 5:15] = False 
        mask[5, 5:15, 5:15] = True
        result = SAM2Assistant._postprocess_mask(mask)
        assert result[4, 10, 10] == True

    def test_output_is_bool(self):
        mask = np.zeros((5, 16, 16), dtype=bool)
        mask[2, 4:12, 4:12] = True
        result = SAM2Assistant._postprocess_mask(mask)
        assert result.dtype == bool

class TestSAM2AssistantProperties:
    def test_checkpoint_path_is_path(self):
        assistant = SAM2Assistant()
        assert isinstance(assistant.checkpoint_path, type(assistant.checkpoint_path))
        assert assistant.checkpoint_path.name == "sam2.1_hiera_tiny.pt"

    def test_is_ready_false_when_no_checkpoint(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "sam_assistant._MODELS_DIR", tmp_path / "nonexistent"
        )
        assistant = SAM2Assistant()
        assert assistant.is_ready() is False
