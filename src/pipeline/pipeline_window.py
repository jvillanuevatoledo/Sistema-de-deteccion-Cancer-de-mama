from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pipeline_workers import UnifiedWorker


def _monospace_font() -> QFont:
    import platform
    system = platform.system()
    if system == "Darwin":
        name = "Menlo"
    elif system == "Windows":
        name = "Consolas"
    else:
        name = "DejaVu Sans Mono"
    return QFont(name, 11)


class _PipelinePanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._worker: UnifiedWorker | None = None
        self._salt = os.getenv("DICOM_SALT_SECRET", "").strip()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)


        grp_in = QGroupBox("Seleccionar carpeta con estudios DICOM")
        gl = QVBoxLayout(grp_in)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setPlaceholderText(
            "Carpeta de un paciente  ó  directorio con múltiples pacientes…"
        )
        self._input_edit.setReadOnly(True)
        row.addWidget(self._input_edit, stretch=1)
        btn_sel = QPushButton("Seleccionar…")
        btn_sel.clicked.connect(self._on_select_input)
        row.addWidget(btn_sel)
        gl.addLayout(row)

        self._mode_label = QLabel("")
        gl.addWidget(self._mode_label)
        layout.addWidget(grp_in)

        if not self._salt:
            warn = QLabel(
                "  Clave de anonimización no configurada.\n"
                "   Contacta al equipo de sistemas antes de continuar."
            )
            warn.setStyleSheet(
                "color:#c62828; font-weight:bold; padding:6px;"
                "border:1px solid #c62828; border-radius:4px;"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)


        self._phase_label = QLabel("")
        self._phase_label.setStyleSheet("font-weight:bold; color:#1565c0;")
        layout.addWidget(self._phase_label)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_monospace_font())
        layout.addWidget(self._log, stretch=1)

        brow = QHBoxLayout()
        brow.addStretch()
        self._btn_start = QPushButton("Iniciar procesamiento")
        self._btn_start.setEnabled(False)
        self._btn_start.clicked.connect(self._on_start)
        brow.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("Cancelar")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        brow.addWidget(self._btn_cancel)
        layout.addLayout(brow)

    def _on_select_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta DICOM")
        if not folder:
            return
        self._input_edit.setText(folder)

        p = Path(folder)
        subdirs = [
            d for d in p.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name not in ("ANONYMIZED", "NIFTI_CONVERTED", "PROCESSED_DATA")
        ]
        has_direct_dcm = bool(list(p.rglob("*.dcm"))[:1])
        has_sub_dcm = (
            any(list(d.rglob("*.dcm"))[:1] for d in subdirs[:5])
            if subdirs else False
        )

        if has_sub_dcm and len(subdirs) > 1:
            self._mode_label.setText(
                f"Modo LOTE — {len(subdirs)} pacientes detectados"
            )
            self._mode_label.setStyleSheet("color:#1565c0; font-weight:bold;")
            self._btn_start.setEnabled(bool(self._salt))
        elif has_direct_dcm:
            self._mode_label.setText("Modo INDIVIDUAL — 1 paciente")
            self._mode_label.setStyleSheet("color:#2e7d32; font-weight:bold;")
            self._btn_start.setEnabled(bool(self._salt))
        else:
            self._mode_label.setText("⚠ No se encontraron archivos DICOM")
            self._mode_label.setStyleSheet("color:#c62828; font-weight:bold;")
            self._btn_start.setEnabled(False)

    def _on_start(self):
        self._log.clear()
        self._phase_label.setText("")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        self._worker = UnifiedWorker(self._input_edit.text(), self._salt)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.phase.connect(self._on_phase)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._on_log("Cancelando… por favor espera.")

    def _on_phase(self, msg: str):
        self._phase_label.setText(msg)
        self._log.append(f"\n▶ {msg}")

    def _on_progress(self, cur: int, total: int):
        self._progress.setMaximum(total)
        self._progress.setValue(cur)

    def _on_log(self, msg: str):
        self._log.append(msg)

    def _on_done(self, ok: bool, msg: str):
        self._btn_start.setEnabled(bool(self._salt))
        self._btn_cancel.setEnabled(False)
        self._phase_label.setText("✓ Finalizado" if ok else "✗ Error")
        self._phase_label.setStyleSheet(
            "font-weight:bold; color:#2e7d32;" if ok else "font-weight:bold; color:#c62828;"
        )
        self._log.append(f"\n{'=' * 50}")
        self._log.append(msg)
        if self._worker is not None:
            self._worker.finished.connect(self._on_worker_finished)

    def _on_worker_finished(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None


class PipelineWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Pipeline de Preprocesamiento")
        self.setMinimumSize(QSize(700, 520))
        self.resize(800, 600)
        self.setCentralWidget(_PipelinePanel())

def open_pipeline():
    app = QApplication.instance()
    own_app = False
    if app is None:
        app = QApplication(sys.argv)
        own_app = True

    win = PipelineWindow()
    win.show()

    if own_app:
        app.exec()

if __name__ == "__main__":
    open_pipeline()