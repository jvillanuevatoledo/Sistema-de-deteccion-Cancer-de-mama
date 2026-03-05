from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

def _default_base_dir() -> str:
    env = os.environ.get("BASE_DIR")
    if env:
        return env
    import platform
    system = platform.system()
    if system == "Darwin":
        return "/Volumes/HRAEPY"
    elif system == "Windows":
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            candidate = Path(f"{letter}:/HRAEPY")
            if candidate.exists():
                return str(candidate)
        return str(Path.home() / "HRAEPY")
    else: 
        for candidate in (
            Path("/mnt/HRAEPY"),
            Path("/media") / os.getenv("USER", "user") / "HRAEPY",
        ):
            if candidate.exists():
                return str(candidate)
        return str(Path.home() / "HRAEPY")


DEFAULT_BASE_DIR = _default_base_dir()
CATEGORY_DIRS = ("MAMA", "PROSTATA")
PROCESSED_SUBDIR = "PROCESSED_DATA"
ANNOTATIONS_SUBDIR = "ANNOTATIONS"
VALID_EXTENSIONS = {".nii", ".nii.gz", ".png"}

@dataclass
class PatientInfo:
    patient_id: str
    category: str
    path: Path
    nifti_count: int = 0
    png_count: int = 0
    has_annotations: bool = False
    annotation_count: int = 0


def _scan_patient(patient_dir: Path, category: str) -> Optional[PatientInfo]:
    if not patient_dir.is_dir():
        return None

    nifti_count = 0
    png_count = 0
    for f in patient_dir.iterdir():
        if f.name.startswith("."):
            continue
        name_lower = f.name.lower()
        if name_lower.endswith(".nii.gz") or name_lower.endswith(".nii"):
            nifti_count += 1
        elif name_lower.endswith(".png"):
            png_count += 1

    ann_dir = patient_dir / ANNOTATIONS_SUBDIR
    has_ann = ann_dir.is_dir() and any(ann_dir.iterdir())

    ann_count = 0
    if has_ann:
        ann_count = sum(
            1
            for f in ann_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
            and f.name != "manifest.json"
        )

    if nifti_count == 0 and png_count == 0:
        return None

    return PatientInfo(
        patient_id=patient_dir.name,
        category=category,
        path=patient_dir,
        nifti_count=nifti_count,
        png_count=png_count,
        has_annotations=has_ann,
        annotation_count=ann_count,
    )


def scan_base_directory(base_dir: str | Path) -> list[PatientInfo]:
    base = Path(base_dir)
    patients: list[PatientInfo] = []

    for category in sorted(base.iterdir()):
        if not category.is_dir() or category.name.startswith((".", "$")):
            continue
        processed = category / PROCESSED_SUBDIR
        if not processed.is_dir():
            continue
        for patient_dir in sorted(processed.iterdir()):
            info = _scan_patient(patient_dir, category.name)
            if info:
                patients.append(info)

    return patients

class PatientBrowserDialog(QDialog):
    _COL_PATIENT = 0
    _COL_NIFTI = 1
    _COL_STATUS = 2

    def __init__(self, base_dir: str = DEFAULT_BASE_DIR, parent: QWidget | None = None):
        super().__init__(parent)
        self._base_dir = base_dir
        self._selected_patient: Optional[PatientInfo] = None
        self._patients: list[PatientInfo] = []

        self._init_ui()
        self._load_patients()

    def _init_ui(self):
        self.setWindowTitle("Seleccionar Paciente")
        self.setMinimumSize(QSize(620, 460))
        self.resize(700, 520)

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(10)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Directorio base:"))
        self._dir_edit = QLineEdit(self._base_dir)
        self._dir_edit.setReadOnly(True)
        dir_layout.addWidget(self._dir_edit, stretch=1)
        btn_browse = QPushButton("Cambiar…")
        btn_browse.clicked.connect(self._on_change_dir)
        dir_layout.addWidget(btn_browse)
        root_layout.addLayout(dir_layout)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Buscar:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filtrar por ID de paciente…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self._search_edit, stretch=1)
        root_layout.addLayout(search_layout)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Paciente", "Archivos", "Estado"])
        self._tree.setColumnCount(3)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        root_layout.addWidget(self._tree, stretch=1)

        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        root_layout.addWidget(self._info_label)

        self._button_box = QDialogButtonBox()
        self._btn_open = self._button_box.addButton(
            "Abrir paciente", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._btn_open.setEnabled(False)
        self._button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        root_layout.addWidget(self._button_box)

    def _load_patients(self):
        base = Path(self._base_dir)
        if not base.exists():
            QMessageBox.warning(
                self,
                "Directorio no encontrado",
                f"No se encontró el directorio:\n{self._base_dir}\n\n"
                "Conecta la unidad externa o selecciona otro directorio.",
            )
            return

        self._patients = scan_base_directory(base)
        self._populate_tree(self._patients)

    def _populate_tree(self, patients: list[PatientInfo]):
        self._tree.clear()

        categories: dict[str, QTreeWidgetItem] = {}
        for p in patients:
            if p.category not in categories:
                cat_item = QTreeWidgetItem([p.category])
                cat_font = QFont()
                cat_font.setBold(True)
                cat_font.setPointSize(cat_font.pointSize() + 1)
                cat_item.setFont(0, cat_font)
                cat_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                )
                self._tree.addTopLevelItem(cat_item)
                categories[p.category] = cat_item

            parent = categories[p.category]
            child = QTreeWidgetItem()
            child.setText(self._COL_PATIENT, p.patient_id)

            parts = []
            if p.nifti_count:
                parts.append(f"{p.nifti_count} NIfTI")
            if p.png_count:
                parts.append(f"{p.png_count} PNG")
            child.setText(self._COL_NIFTI, " · ".join(parts))

            if p.has_annotations:
                child.setText(self._COL_STATUS, f"✓ {p.annotation_count} anot.")
                child.setForeground(self._COL_STATUS, QColor("#2e7d32"))
            else:
                child.setText(self._COL_STATUS, "Sin anotar")
                child.setForeground(self._COL_STATUS, QColor("#9e9e9e"))

            child.setData(0, Qt.ItemDataRole.UserRole, p)
            parent.addChild(child)

        self._tree.expandAll()
        total = len(patients)
        cats = len(categories)
        self._info_label.setText(
            f"{total} paciente{'s' if total != 1 else ''} en "
            f"{cats} categoría{'s' if cats != 1 else ''}"
        )

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        if not text:
            self._populate_tree(self._patients)
            return
        filtered = [
            p for p in self._patients if text in p.patient_id.lower()
        ]
        self._populate_tree(filtered)

    def _on_change_dir(self):
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar directorio base",
            self._base_dir,
        )
        if new_dir:
            self._base_dir = new_dir
            self._dir_edit.setText(new_dir)
            self._load_patients()

    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        if not items:
            self._btn_open.setEnabled(False)
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        self._btn_open.setEnabled(data is not None)

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is not None:
            self._selected_patient = data
            self.accept()

    def _on_accept(self):
        items = self._tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            QMessageBox.information(
                self,
                "Selección inválida",
                "Selecciona un paciente, no una categoría.",
            )
            return
        self._selected_patient = data
        self.accept()

    @property
    def selected_patient(self) -> Optional[PatientInfo]:
        return self._selected_patient

    @property
    def base_dir(self) -> str:
        return self._base_dir


def select_patient(base_dir: str = DEFAULT_BASE_DIR) -> Optional[tuple[str, str]]:
    app = QApplication.instance()
    own_app = False
    if app is None:
        app = QApplication(sys.argv)
        own_app = True

    dialog = PatientBrowserDialog(base_dir)
    result = dialog.exec()

    if result == QDialog.DialogCode.Accepted and dialog.selected_patient:
        patient = dialog.selected_patient
        chosen_base = dialog.base_dir
        if own_app:
            app.quit()
        return patient.patient_id, chosen_base

    if own_app:
        app.quit()
    return None

if __name__ == "__main__":
    choice = select_patient()
    if choice:
        pid, bdir = choice
        print(f"Seleccionado: {pid}  (base: {bdir})")
    else:
        print("Cancelado.")
