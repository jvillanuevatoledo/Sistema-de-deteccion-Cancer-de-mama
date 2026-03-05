from __future__ import annotations

import gc
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import torch
from PIL import Image
from scipy.ndimage import binary_closing, generate_binary_structure
from skimage.morphology import remove_small_objects

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_CHECKPOINT_NAME = "sam2.1_hiera_tiny.pt"
_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"
_CHECKPOINT_URL = (
    "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt"
)


def _select_device() -> str:
    """
    Selecciona el dispositivo para SAM2.

    Prioridad: variable SAM2_DEVICE > CUDA > MPS (Apple Silicon) > CPU.
    """
    env_device = os.environ.get("SAM2_DEVICE", "").lower()
    if env_device in ("cpu", "cuda", "mps"):
        return env_device
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def download_checkpoint(
    dest: Path,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> None:
    """Descarga el checkpoint SAM2 Tiny (~38 MB) con barra de progreso opcional."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)

    class _ProgressHook:
        def __call__(self, block_num: int, block_size: int, total_size: int) -> None:
            if progress_cb and total_size > 0:
                pct = min(100, int(block_num * block_size * 100 / total_size))
                progress_cb(pct)

    print(f"[SAM2] Descargando checkpoint (~38 MB) → {dest}")
    urllib.request.urlretrieve(_CHECKPOINT_URL, dest, reporthook=_ProgressHook())
    print("[SAM2] Descarga completa.")


class SAM2Assistant:
    """
    Wrapper lazy de SAM2 Video Predictor para segmentar volúmenes 3D.

    La carga del modelo ocurre en el primer llamado a `segment_volume`,
    no al instanciar la clase, para no bloquear el arranque del visor.
    """

    def __init__(self) -> None:
        self._predictor = None
        self._device: Optional[str] = None

    @property
    def checkpoint_path(self) -> Path:
        return _MODELS_DIR / _CHECKPOINT_NAME

    def is_ready(self) -> bool:
        """True si el checkpoint ya está descargado."""
        return self.checkpoint_path.exists()

    def ensure_checkpoint(
        self, progress_cb: Optional[Callable[[int], None]] = None
    ) -> bool:
        """Descarga el checkpoint si no existe. Retorna True si está disponible."""
        if self.checkpoint_path.exists():
            return True
        try:
            download_checkpoint(self.checkpoint_path, progress_cb=progress_cb)
            return True
        except Exception as exc:
            print(f"[SAM2] Error al descargar checkpoint: {exc}")
            return False

    def _load_predictor(self) -> None:
        """Carga el modelo SAM2 (lazy). Solo se ejecuta una vez."""
        if self._predictor is not None:
            return

        if not self.ensure_checkpoint():
            raise RuntimeError(
                "No se pudo obtener el checkpoint de SAM2.\n"
                "Verifica tu conexión a internet o descárgalo manualmente en:\n"
                f"  {self.checkpoint_path}"
            )

        from sam2.build_sam import build_sam2_video_predictor

        device = _select_device()
        print(f"[SAM2] Cargando modelo en [{device}]…")

        try:
            self._predictor = build_sam2_video_predictor(
                _CONFIG,
                str(self.checkpoint_path),
                device=device,
            )
            self._device = device
        except Exception as exc:
            print(f"[SAM2] Fallo en {device} ({exc}), usando CPU.")
            self._predictor = build_sam2_video_predictor(
                _CONFIG,
                str(self.checkpoint_path),
                device="cpu",
            )
            self._device = "cpu"

        print(f"[SAM2] Modelo listo en [{self._device}].")

    def segment_volume(
        self,
        volume: np.ndarray,
        slice_idx: int,
        bbox_yx: tuple[int, int, int, int],
    ) -> np.ndarray:
        """
        Segmenta un tumor en todo el volumen 3D usando SAM2.

        Toma la bounding box dibujada en un slice y propaga la máscara
        hacia todos los slices del volumen (hacia arriba y hacia abajo).

        Args:
            volume:    Array 3D de shape (Z, Y, X), cualquier dtype numérico.
            slice_idx: Índice Z del slice donde se dibujó la bounding box.
            bbox_yx:   Tupla (row_min, col_min, row_max, col_max) en píxeles.

        Returns:
            mask_3d: Array bool de shape (Z, Y, X). True = tumor.
        """
        self._load_predictor()

        Z, H, W = volume.shape

        v_min = float(volume.min())
        v_max = float(volume.max())
        if v_max > v_min:
            vol_u8 = (
                (volume.astype(np.float32) - v_min) / (v_max - v_min) * 255
            ).astype(np.uint8)
        else:
            vol_u8 = np.zeros((Z, H, W), dtype=np.uint8)

        tmpdir = tempfile.mkdtemp(prefix="sam2_vol_")
        try:
            for z in range(Z):
                rgb = np.stack([vol_u8[z]] * 3, axis=-1)
                Image.fromarray(rgb).save(
                    os.path.join(tmpdir, f"{z:05d}.jpg"), quality=95
                )

            del vol_u8
            gc.collect()

            r0, c0, r1, c1 = bbox_yx
            r0 = max(0, min(int(r0), H - 1))
            c0 = max(0, min(int(c0), W - 1))
            r1 = max(0, min(int(r1), H - 1))
            c1 = max(0, min(int(c1), W - 1))
            box = np.array([c0, r0, c1, r1], dtype=np.float32)

            masks_all: dict[int, np.ndarray] = {}

            with torch.inference_mode():
                state = self._predictor.init_state(tmpdir)
                self._predictor.reset_state(state)

                self._predictor.add_new_points_or_box(
                    inference_state=state,
                    frame_idx=slice_idx,
                    obj_id=1,
                    box=box,
                )

                for fi, _, masks in self._predictor.propagate_in_video(
                    state, start_frame_idx=slice_idx
                ):
                    masks_all[fi] = masks[0, 0].cpu().numpy() > 0

                for fi, _, masks in self._predictor.propagate_in_video(
                    state, start_frame_idx=slice_idx, reverse=True
                ):
                    if fi not in masks_all:
                        masks_all[fi] = masks[0, 0].cpu().numpy() > 0

                self._predictor.reset_state(state)
            del state

            if self._device == "mps":
                torch.mps.synchronize()
                torch.mps.empty_cache()
            elif self._device == "cuda":
                torch.cuda.empty_cache()

            mask_3d = np.zeros((Z, H, W), dtype=bool)
            for z, m in masks_all.items():
                if 0 <= z < Z:
                    if m.shape == (H, W):
                        mask_3d[z] = m
                    else:
                        m_img = Image.fromarray(
                            m.astype(np.uint8) * 255
                        ).resize((W, H), Image.NEAREST)
                        mask_3d[z] = np.array(m_img) > 0
            del masks_all

            mask_3d = self._postprocess_mask(mask_3d)

            return mask_3d

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            gc.collect()

    @staticmethod
    def _postprocess_mask(mask_3d: np.ndarray) -> np.ndarray:
        """
        Post-procesado morfológico 3D sobre la máscara SAM.

        1. binary_closing (estructura 3D 6-conectada, 2 iteraciones):
           rellena agujeros pequeños entre slices donde SAM perdió
           el tumor por un frame.

        2. remove_small_objects (min_size adaptativo):
           elimina salpicaduras aisladas en tejido adyacente.
           El umbral es 2% del componente principal, con un mínimo
           de 50 vóxeles para no eliminar lesiones muy pequeñas.
        """
        total = int(mask_3d.sum())
        if total == 0:
            return mask_3d

        struct = generate_binary_structure(3, 1)
        closed = binary_closing(mask_3d, structure=struct, iterations=2)

        min_size = max(50, min(5000, int(total * 0.02)))
        cleaned = remove_small_objects(closed, min_size=min_size, connectivity=1)
        del closed

        return cleaned
