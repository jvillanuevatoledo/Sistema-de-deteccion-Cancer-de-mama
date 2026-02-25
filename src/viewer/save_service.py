import threading
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QTimer

import io_utils
from schemas import PatientManifest


@dataclass
class SaveRequest:
    source_filename: str
    data_to_save: dict[str, Any]
    existing_on_disk: dict[str, str]
    patient_id: str
    output_dir: Path
    affine: Any = None
    image_shape: Optional[list[int]] = None
    voxel_spacing: Optional[list[float]] = None


@dataclass
class SaveResult:
    success: bool
    message: str
    detail: str


class SaveService:
    def __init__(
        self,
        manifest: PatientManifest,
        manifest_path: Path,
    ):
        self._manifest = manifest
        self._manifest_path = manifest_path
        self._lock = threading.Lock()
        self._active = False
        self._result_queue: queue.Queue[SaveResult] = queue.Queue()
        self._timer = QTimer()
        self._timer.setInterval(100)
        self._on_success: Optional[Callable[[SaveResult], None]] = None
        self._on_error: Optional[Callable[[SaveResult], None]] = None

    @property
    def is_busy(self) -> bool:
        return self._active

    @property
    def manifest(self) -> PatientManifest:
        return self._manifest

    def start(
        self,
        on_success: Optional[Callable[[SaveResult], None]] = None,
        on_error: Optional[Callable[[SaveResult], None]] = None,
    ):
        self._on_success = on_success
        self._on_error = on_error
        self._timer.timeout.connect(self._poll_results)
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def submit(self, request: SaveRequest) -> bool:
        if self._active:
            return False
        self._active = True
        thread = threading.Thread(
            target=self._execute, args=(request,), daemon=True
        )
        thread.start()
        return True

    def _execute(self, req: SaveRequest):
        try:
            saved_files = {}

            if "mask" in req.data_to_save:
                m = req.data_to_save["mask"]
                io_utils.save_nifti_mask(m["data"], m["affine"], m["path"])
                saved_files["mask"] = m["path"].name

            if "points" in req.data_to_save:
                p = req.data_to_save["points"]
                io_utils.save_points_csv(p["data"], p["path"])
                saved_files["points"] = p["path"].name

            if "rois" in req.data_to_save:
                r = req.data_to_save["rois"]
                io_utils.save_rois_json(r["data"], r["types"], r["path"])
                saved_files["rois"] = r["path"].name

            saved_files.update(req.existing_on_disk)

            with self._lock:
                self._manifest.upsert_annotation(
                    req.source_filename,
                    saved_files,
                    shape=req.image_shape,
                    spacing=req.voxel_spacing,
                )
                io_utils.save_manifest(self._manifest, self._manifest_path)

            label_str = ", ".join(saved_files.keys())
            self._result_queue.put(
                SaveResult(
                    success=True,
                    message=f"Guardado: {req.source_filename} [{label_str}]",
                    detail=str(list(saved_files.values())),
                )
            )
        except Exception as e:
            self._result_queue.put(
                SaveResult(
                    success=False,
                    message=f"Error guardando: {e}",
                    detail=str(e),
                )
            )

    def _poll_results(self):
        while not self._result_queue.empty():
            try:
                result = self._result_queue.get_nowait()
                self._active = False
                if result.success and self._on_success:
                    self._on_success(result)
                elif not result.success and self._on_error:
                    self._on_error(result)
            except queue.Empty:
                break
