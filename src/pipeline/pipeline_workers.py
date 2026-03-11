from __future__ import annotations

import shutil
import sys
from pathlib import Path

_PREPROCESSING_DIR = str(Path(__file__).resolve().parent.parent / "preprocessing")
if _PREPROCESSING_DIR not in sys.path:
    sys.path.insert(0, _PREPROCESSING_DIR)

import pydicom
from PySide6.QtCore import QThread, Signal

from dicom_processor import anonymize_dicom_ps315, is_patient_container_dir
from nifti_converter import SmartMedicalConverter

class AnonymizeWorker(QThread):
    progress = Signal(int, int)          
    log      = Signal(str)               
    done     = Signal(bool, str)         

    def __init__(
        self,
        input_dir: str,
        salt: str,
        output_dir: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.input_path = Path(input_dir)
        self.salt = salt
        self._output_dir = output_dir

    def run(self):
        try:
            if is_patient_container_dir(self.input_path):
                self._run_batch()
            else:
                self._run_single(self.input_path)
        except Exception as exc:
            self.done.emit(False, f"Error inesperado: {exc}")

    
    def _output_base(self) -> Path:
        if self._output_dir:
            return Path(self._output_dir)
        return self.input_path / "ANONYMIZED"

    def _run_batch(self):
        self.log.emit(f"Modo BATCH detectado en: {self.input_path}")

        patient_folders = sorted(
            d
            for d in self.input_path.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name not in ("ANONYMIZED", "NIFTI_CONVERTED", "PROCESSED_DATA")
            and not d.name.startswith("ANON")
        )

        if not patient_folders:
            self.done.emit(False, "No se encontraron carpetas de pacientes.")
            return

        out_base = self._output_base()
        out_base.mkdir(parents=True, exist_ok=True)

        total = len(patient_folders)
        self.log.emit(f"Pacientes encontrados: {total}")
        self.log.emit(f"Salida: {out_base}\n")

        ok = 0
        for idx, folder in enumerate(patient_folders):
            if self.isInterruptionRequested():
                self.done.emit(False, f"Cancelado. Procesados: {ok}/{total}")
                return

            pid = folder.name
            out = out_base / f"ANON{pid}"
            self.log.emit(f"[{idx + 1}/{total}] {pid}")

            count = self._anonymize_folder(folder, out, pid)
            if count > 0:
                ok += 1
                self.log.emit(f"  ✓ {count} archivos anonimizados")
            else:
                self.log.emit(f"  ✗ Sin archivos DICOM")

            self.progress.emit(idx + 1, total)

        self.done.emit(True, f"Completado: {ok}/{total} pacientes procesados.")

    def _run_single(self, folder: Path):
        self.log.emit(f"Modo INDIVIDUAL: {folder.name}")

        pid = folder.name
        out = self._output_base() / f"ANON{pid}"

        count = self._anonymize_folder(folder, out, pid)
        self.progress.emit(1, 1)

        if count > 0:
            self.done.emit(True, f"✓ {count} archivos anonimizados → {out}")
        else:
            self.done.emit(False, "No se encontraron archivos DICOM.")

    def _anonymize_folder(self, src: Path, dst: Path, pid: str) -> int:
        dst.mkdir(parents=True, exist_ok=True)

        dcm_files = [f for f in src.rglob("*.dcm") if not f.name.startswith(".")]
        if not dcm_files:
            return 0

        count = 0
        for dcm_file in dcm_files:
            if self.isInterruptionRequested():
                return count
            try:
                ds = pydicom.dcmread(dcm_file)
                ds_anon = anonymize_dicom_ps315(ds, self.salt, pid)

                rel = dcm_file.relative_to(src)
                save = dst / rel
                save.parent.mkdir(parents=True, exist_ok=True)
                ds_anon.save_as(save)
                count += 1
            except Exception as exc:
                self.log.emit(f"    Error en {dcm_file.name}: {exc}")

        return count

class ConvertWorker(QThread):
    progress = Signal(int, int)
    log      = Signal(str)
    done     = Signal(bool, str)

    def __init__(self, input_dir: str, parent=None):
        super().__init__(parent)
        self.input_dir = input_dir

    def run(self):
        try:
            converter = SmartMedicalConverter(self.input_dir)
        except RuntimeError as exc:
            self.done.emit(False, str(exc))
            return

        try:
            folders = converter.get_patient_folders()
            if not folders:
                self.done.emit(
                    False,
                    "No se encontraron carpetas de pacientes anonimizados (ANON*).",
                )
                return

            converter.output_path.mkdir(parents=True, exist_ok=True)

            total = len(folders)
            self.log.emit(f"Pacientes encontrados: {total}")
            self.log.emit(f"Entrada: {converter.input_path}")
            self.log.emit(f"Salida:  {converter.output_path}\n")

            stats = {"success": 0, "failed": 0}

            for idx, folder in enumerate(folders):
                if self.isInterruptionRequested():
                    self.done.emit(
                        False,
                        f"Cancelado. {stats['success']} OK, {stats['failed']} errores.",
                    )
                    return

                self.log.emit(f"[{idx + 1}/{total}] {folder.name}")
                success, modality, reason = converter.convert_patient(folder)

                if success:
                    stats["success"] += 1
                    self.log.emit(f"  ✓ [{modality}] {reason}")
                else:
                    stats["failed"] += 1
                    self.log.emit(f"  ✗ [{modality}] {reason}")

                self.progress.emit(idx + 1, total)

            
            if converter.temp_dir.exists():
                shutil.rmtree(converter.temp_dir, ignore_errors=True)

            self.done.emit(
                True,
                f"Completado: {stats['success']} OK, {stats['failed']} errores "
                f"de {total} pacientes.",
            )

        except Exception as exc:
            self.done.emit(False, f"Error inesperado: {exc}")


class UnifiedWorker(QThread):
    """Anonimiza y convierte en una sola pasada.

    Flujo interno:
    1. Anonimiza los DICOMs a una carpeta temporal ``_temp_anon`` dentro de
       la carpeta de entrada.
    2. Convierte los DICOMs anonimizados a NIfTI/PNG en ``PROCESSED_DATA/``.
    3. Borra la carpeta temporal (siempre, incluso si hubo error en fase 2).

    El usuario solo ve una barra de progreso unificada y jamás necesita
    conocer la existencia de la carpeta temporal.
    """

    progress = Signal(int, int)
    log      = Signal(str)
    phase    = Signal(str)
    done     = Signal(bool, str)

    def __init__(self, input_dir: str, salt: str, parent=None):
        super().__init__(parent)
        self.input_path = Path(input_dir)
        self.salt = salt

    def run(self):
        tmp = self.input_path / "_temp_anon"
        try:
            self.phase.emit("Fase 1/2 — Anonimizando DICOMs…")
            ok, n_patients = self._run_anonymize(tmp)
            if not ok:
                return        

            if self.isInterruptionRequested():
                self.done.emit(False, "Cancelado durante la anonimización.")
                return
            
            self.phase.emit("Fase 2/2 — Convirtiendo a NIfTI / PNG…")
            self._run_convert(tmp, n_patients)

        except Exception as exc:
            self.done.emit(False, f"Error inesperado: {exc}")
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    def _run_anonymize(self, tmp: Path) -> tuple[bool, int]:
        from pydicom import dcmread
        from dicom_processor import anonymize_dicom_ps315, is_patient_container_dir

        tmp.mkdir(parents=True, exist_ok=True)

        if is_patient_container_dir(self.input_path):
            patient_folders = sorted(
                d for d in self.input_path.iterdir()
                if d.is_dir()
                and not d.name.startswith(".")
                and d.name not in ("ANONYMIZED", "NIFTI_CONVERTED", "PROCESSED_DATA", "_temp_anon")
                and not d.name.startswith("ANON")
            )
            if not patient_folders:
                self.done.emit(False, "No se encontraron carpetas de pacientes.")
                return False, 0

            total = len(patient_folders)
            self.log.emit(f"Pacientes encontrados: {total}\n")
            ok = 0
            for idx, folder in enumerate(patient_folders):
                if self.isInterruptionRequested():
                    self.done.emit(False, f"Cancelado. Procesados: {ok}/{total}")
                    return False, 0
                pid = folder.name
                out = tmp / f"ANON{pid}"
                count = self._anonymize_folder(folder, out, pid, dcmread, anonymize_dicom_ps315)
                if count > 0:
                    ok += 1
                    self.log.emit(f"  ✓ [{idx+1}/{total}] {pid} — {count} archivos")
                else:
                    self.log.emit(f"  ✗ [{idx+1}/{total}] {pid} — sin archivos DICOM")
        
                self.progress.emit(idx + 1, total * 2)
            return True, total
        else:
            pid = self.input_path.name
            out = tmp / f"ANON{pid}"
            count = self._anonymize_folder(self.input_path, out, pid, dcmread, anonymize_dicom_ps315)
            self.progress.emit(1, 2)
            if count > 0:
                self.log.emit(f"  ✓ {pid} — {count} archivos anonimizados")
                return True, 1
            else:
                self.done.emit(False, "No se encontraron archivos DICOM.")
                return False, 0

    def _anonymize_folder(self, src, dst, pid, dcmread, anonymize_fn) -> int:
        dst.mkdir(parents=True, exist_ok=True)
        dcm_files = [f for f in src.rglob("*.dcm") if not f.name.startswith(".")]
        count = 0
        for dcm_file in dcm_files:
            if self.isInterruptionRequested():
                return count
            try:
                ds = dcmread(dcm_file)
                ds_anon = anonymize_fn(ds, self.salt, pid)
                rel = dcm_file.relative_to(src)
                save = dst / rel
                save.parent.mkdir(parents=True, exist_ok=True)
                ds_anon.save_as(save)
                count += 1
            except Exception as exc:
                self.log.emit(f"    Error en {dcm_file.name}: {exc}")
        return count

    def _run_convert(self, tmp: Path, n_patients: int):
        try:
            converter = SmartMedicalConverter(str(tmp))
        except RuntimeError as exc:
            self.done.emit(False, str(exc))
            return

        folders = converter.get_patient_folders()
        if not folders:
            self.done.emit(False, "No se pudieron leer los pacientes anonimizados.")
            return

        converter.output_path.mkdir(parents=True, exist_ok=True)
        total = len(folders)
        stats = {"success": 0, "failed": 0}

        for idx, folder in enumerate(folders):
            if self.isInterruptionRequested():
                self.done.emit(False, f"Cancelado. {stats['success']} OK, {stats['failed']} errores.")
                return

            success, modality, reason = converter.convert_patient(folder)
            if success:
                stats["success"] += 1
                self.log.emit(f"  ✓ [{modality}] {folder.name} — {reason}")
            else:
                stats["failed"] += 1
                self.log.emit(f"  ✗ [{modality}] {folder.name} — {reason}")

    
            self.progress.emit(n_patients + idx + 1, n_patients * 2)

        if converter.temp_dir.exists():
            shutil.rmtree(converter.temp_dir, ignore_errors=True)

        self.done.emit(
            True,
            f"Completado: {stats['success']} OK, {stats['failed']} errores de {total} pacientes.\n"
            f"Archivos guardados en: {converter.output_path}",
        )
