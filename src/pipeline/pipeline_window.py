from __future__ import annotations

import os
import shutil
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
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pipeline_workers import AnonymizeWorker, ConvertWorker


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

class _AnonymizeTab(QWidget):

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._worker: AnonymizeWorker | None = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        grp_in = QGroupBox("Entrada — Carpeta con DICOMs")
        gl = QVBoxLayout(grp_in)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setPlaceholderText(
            "Carpeta de un paciente  ó  directorio con múltiples pacientes…"
        )
        self._input_edit.setReadOnly(True)
        row.addWidget(self._input_edit, stretch=1)
        btn = QPushButton("Seleccionar…")
        btn.clicked.connect(self._on_select_input)
        row.addWidget(btn)
        gl.addLayout(row)

        self._mode_label = QLabel("")
        gl.addWidget(self._mode_label)
        layout.addWidget(grp_in)

        grp_cfg = QGroupBox("Configuración")
        cl = QVBoxLayout(grp_cfg)

        salt_row = QHBoxLayout()
        salt_row.addWidget(QLabel("Salt (clave secreta):"))
        self._salt_edit = QLineEdit()
        self._salt_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._salt_edit.setPlaceholderText("Clave para anonimización reproducible…")
        env_salt = os.getenv("DICOM_SALT_SECRET", "")
        if env_salt:
            self._salt_edit.setText(env_salt)
        salt_row.addWidget(self._salt_edit, stretch=1)

        btn_eye = QPushButton("👁")
        btn_eye.setFixedWidth(32)
        btn_eye.setCheckable(True)
        btn_eye.toggled.connect(
            lambda on: self._salt_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        salt_row.addWidget(btn_eye)
        cl.addLayout(salt_row)
        layout.addWidget(grp_cfg)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_monospace_font())
        layout.addWidget(self._log, stretch=1)

        brow = QHBoxLayout()
        brow.addStretch()
        self._btn_start = QPushButton("Iniciar Anonimización")
        self._btn_start.setEnabled(False)
        self._btn_start.clicked.connect(self._on_start)
        brow.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("Cancelar")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        brow.addWidget(self._btn_cancel)
        layout.addLayout(brow)

    def _on_select_input(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta DICOM"
        )
        if not folder:
            return
        self._input_edit.setText(folder)

        p = Path(folder)
        subdirs = [
            d
            for d in p.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name not in ("ANONYMIZED", "NIFTI_CONVERTED", "PROCESSED_DATA")
        ]
        has_direct_dcm = bool(list(p.rglob("*.dcm"))[:1])
        has_sub_dcm = any(
            list(d.rglob("*.dcm"))[:1] for d in subdirs[:5]
        ) if subdirs else False

        if has_sub_dcm and len(subdirs) > 1:
            self._mode_label.setText(
                f"Modo BATCH — {len(subdirs)} subcarpetas detectadas"
            )
            self._mode_label.setStyleSheet("color:#1565c0; font-weight:bold;")
            self._btn_start.setEnabled(True)
        elif has_direct_dcm:
            self._mode_label.setText("Modo INDIVIDUAL — 1 paciente")
            self._mode_label.setStyleSheet("color:#2e7d32; font-weight:bold;")
            self._btn_start.setEnabled(True)
        else:
            self._mode_label.setText("⚠ No se encontraron archivos DICOM")
            self._mode_label.setStyleSheet("color:#c62828; font-weight:bold;")
            self._btn_start.setEnabled(False)

    def _on_start(self):
        salt = self._salt_edit.text().strip()
        if not salt:
            QMessageBox.warning(
                self,
                "Salt requerido",
                "Ingresa una clave secreta para la anonimización.",
            )
            return

        self._log.clear()
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        self._worker = AnonymizeWorker(self._input_edit.text(), salt)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._on_log("Cancelando…")

    def _on_progress(self, cur: int, total: int):
        self._progress.setMaximum(total)
        self._progress.setValue(cur)

    def _on_log(self, msg: str):
        self._log.append(msg)

    def _on_done(self, ok: bool, msg: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._on_log(f"\n{'=' * 50}")
        self._on_log(msg)
        self._worker = None

class _ConvertTab(QWidget):

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._worker: ConvertWorker | None = None
        self._has_dcm2niix = shutil.which("dcm2niix") is not None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        dcm_path = shutil.which("dcm2niix")
        srow = QHBoxLayout()
        if dcm_path:
            lbl = QLabel(f"✓ dcm2niix: {dcm_path}")
            lbl.setStyleSheet("color:#2e7d32;")
        else:
            lbl = QLabel("✗ dcm2niix NO encontrado — instálalo antes de continuar")
            lbl.setStyleSheet("color:#c62828; font-weight:bold;")
        srow.addWidget(lbl)
        srow.addStretch()
        layout.addLayout(srow)

        grp_in = QGroupBox("Entrada — Carpeta ANONYMIZED")
        gl = QVBoxLayout(grp_in)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setPlaceholderText(
            "Carpeta que contiene subcarpetas ANON* con DICOMs…"
        )
        self._input_edit.setReadOnly(True)
        row.addWidget(self._input_edit, stretch=1)
        btn = QPushButton("Seleccionar…")
        btn.clicked.connect(self._on_select_input)
        row.addWidget(btn)
        gl.addLayout(row)

        self._info_label = QLabel("")
        gl.addWidget(self._info_label)
        layout.addWidget(grp_in)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_monospace_font())
        layout.addWidget(self._log, stretch=1)

        brow = QHBoxLayout()
        brow.addStretch()
        self._btn_start = QPushButton("Iniciar Conversión a NIfTI")
        self._btn_start.setEnabled(False)
        self._btn_start.clicked.connect(self._on_start)
        brow.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("Cancelar")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        brow.addWidget(self._btn_cancel)
        layout.addLayout(brow)

    def _on_select_input(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta ANONYMIZED"
        )
        if not folder:
            return
        self._input_edit.setText(folder)

        p = Path(folder)
        anon = [
            d
            for d in p.iterdir()
            if d.is_dir()
            and d.name.startswith("ANON")
            and not d.name.startswith(".")
        ]

        if anon:
            self._info_label.setText(
                f"{len(anon)} carpetas de pacientes anonimizados encontradas"
            )
            self._info_label.setStyleSheet("color:#2e7d32; font-weight:bold;")
            self._btn_start.setEnabled(self._has_dcm2niix)
        else:
            self._info_label.setText(
                "⚠ No se encontraron carpetas ANON* en este directorio"
            )
            self._info_label.setStyleSheet("color:#c62828; font-weight:bold;")
            self._btn_start.setEnabled(False)

    def _on_start(self):
        self._log.clear()
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        self._worker = ConvertWorker(self._input_edit.text())
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._on_log("Cancelando…")

    def _on_progress(self, cur: int, total: int):
        self._progress.setMaximum(total)
        self._progress.setValue(cur)

    def _on_log(self, msg: str):
        self._log.append(msg)

    def _on_done(self, ok: bool, msg: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._on_log(f"\n{'=' * 50}")
        self._on_log(msg)
        self._worker = None

class PipelineWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Pipeline de Preprocesamiento")
        self.setMinimumSize(QSize(700, 520))
        self.resize(800, 600)

        tabs = QTabWidget()
        tabs.addTab(_AnonymizeTab(), "  Anonimización  ")
        tabs.addTab(_ConvertTab(), "  Conversión NIfTI  ")
        self.setCentralWidget(tabs)

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
