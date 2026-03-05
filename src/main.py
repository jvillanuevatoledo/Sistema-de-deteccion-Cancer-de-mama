from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")

_SRC_DIR = Path(__file__).resolve().parent
for _subdir in ("viewer", "preprocessing", "pipeline"):
    _p = str(_SRC_DIR / _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv
    load_dotenv(_SRC_DIR.parent / ".env")
except ImportError:
    pass

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Detección de Cáncer de Mama")
        self.setFixedSize(QSize(440, 340))

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(36, 28, 36, 28)

        title = QLabel("Sistema de Detección\nde Cáncer de Mama")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = QFont()
        tf.setPointSize(18)
        tf.setBold(True)
        title.setFont(tf)
        layout.addWidget(title)

        subtitle = QLabel("HRAEYP")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sf = QFont()
        sf.setPointSize(12)
        subtitle.setFont(sf)
        subtitle.setStyleSheet("color:#666;")
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        btn_pipe = QPushButton("Pipeline de Preprocesamiento")
        btn_pipe.setMinimumHeight(46)
        btn_pipe.setToolTip("Anonimizar DICOMs y convertir a NIfTI")
        btn_pipe.clicked.connect(self._open_pipeline)
        layout.addWidget(btn_pipe)

        btn_view = QPushButton("Visor de Anotaciones")
        btn_view.setMinimumHeight(46)
        btn_view.setToolTip("Abrir paciente y anotar imágenes médicas")
        btn_view.clicked.connect(self._open_viewer)
        layout.addWidget(btn_view)

        layout.addStretch()

        self._pipeline_win = None

    def _open_pipeline(self):
        from pipeline_window import PipelineWindow

        if self._pipeline_win is None or not self._pipeline_win.isVisible():
            self._pipeline_win = PipelineWindow()
        self._pipeline_win.show()
        self._pipeline_win.raise_()
        self._pipeline_win.activateWindow()

    def _open_viewer(self):
        from patient_browser import PatientBrowserDialog
        from PySide6.QtWidgets import QDialog

        dialog = PatientBrowserDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_patient:
            return

        patient = dialog.selected_patient
        base = dialog.base_dir
        viewer_script = str(_SRC_DIR / "viewer" / "medical_viewer.py")

        env = os.environ.copy()
        env["_LAUNCH_PATIENT_ID"] = patient.patient_id
        env["_LAUNCH_BASE_DIR"] = base

        subprocess.Popen(
            [sys.executable, viewer_script],
            cwd=str(_SRC_DIR / "viewer"),
            env=env,
        )


def main():
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
