from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


LABEL_MAP = {
    0: {"name": "background", "color": [0, 0, 0, 0]},
    1: {"name": "benign",     "color": [0, 255, 0, 180]},
    2: {"name": "malignant",  "color": [255, 0, 0, 180]},
    3: {"name": "uncertain",  "color": [255, 255, 0, 180]},
}


class LabelClass(str, Enum):
    BENIGN = "benign"
    MALIGNANT = "malignant"
    UNCERTAIN = "uncertain"


class AnnotationFiles(BaseModel):
    mask: Optional[str] = None
    points: Optional[str] = None
    rois: Optional[str] = None


class ImageAnnotation(BaseModel):
    source_filename: str
    label: LabelClass = LabelClass.UNCERTAIN
    annotation_files: AnnotationFiles = Field(default_factory=AnnotationFiles)
    annotator_id: str = "default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified: bool = False
    notes: str = ""
    original_shape: Optional[list[int]] = None
    voxel_spacing: Optional[list[float]] = None
    save_count: int = 0

    @field_validator("source_filename")
    @classmethod
    def filename_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_filename cannot be empty")
        return v


class PatientManifest(BaseModel):
    schema_version: str = "2.0.0"
    patient_id: str
    label_map: dict[str, str] = Field(
        default_factory=lambda: {str(k): v["name"] for k, v in LABEL_MAP.items()}
    )
    annotations: dict[str, ImageAnnotation] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def upsert_annotation(
        self,
        source_filename: str,
        saved_files: dict[str, str],
        shape: Optional[list[int]] = None,
        spacing: Optional[list[float]] = None,
    ) -> None:
        af = AnnotationFiles(**saved_files)

        if source_filename in self.annotations:
            entry = self.annotations[source_filename]
            existing = entry.annotation_files.model_dump(exclude_none=True)
            existing.update(saved_files)
            entry.annotation_files = AnnotationFiles(**existing)
            entry.updated_at = datetime.now(timezone.utc)
            entry.save_count += 1
            if shape and entry.original_shape is None:
                entry.original_shape = shape
            if spacing and entry.voxel_spacing is None:
                entry.voxel_spacing = spacing
        else:
            entry = ImageAnnotation(
                source_filename=source_filename,
                annotation_files=af,
                original_shape=shape,
                voxel_spacing=spacing,
                save_count=1,
            )
            self.annotations[source_filename] = entry

        self.last_modified = datetime.now(timezone.utc)


def migrate_v1_manifest(data: dict, patient_id: str = "") -> PatientManifest:
    pid = data.get("patient_id") or patient_id or "unknown"
    created = data.get("created_at")
    if isinstance(created, str):
        try:
            created_dt = datetime.fromisoformat(created)
        except (ValueError, TypeError):
            created_dt = datetime.now(timezone.utc)
    else:
        created_dt = datetime.now(timezone.utc)

    annotations: dict[str, ImageAnnotation] = {}
    for file_entry in data.get("files", []):
        source = file_entry.get("source", "")
        if not source:
            continue
        ann_files = file_entry.get("annotations", {})
        sc = file_entry.get("save_count", 1)
        last_saved = file_entry.get("last_saved")
        if isinstance(last_saved, str):
            try:
                updated = datetime.fromisoformat(last_saved)
            except (ValueError, TypeError):
                updated = datetime.now(timezone.utc)
        else:
            updated = datetime.now(timezone.utc)

        annotations[source] = ImageAnnotation(
            source_filename=source,
            annotation_files=AnnotationFiles(**ann_files),
            save_count=sc,
            created_at=created_dt,
            updated_at=updated,
        )

    return PatientManifest(
        schema_version="2.0.0",
        patient_id=pid,
        annotations=annotations,
        created_at=created_dt,
    )
