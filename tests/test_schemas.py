import pytest
from datetime import datetime

from schemas import (
    LABEL_MAP,
    AnnotationFiles,
    ImageAnnotation,
    LabelClass,
    PatientManifest,
    migrate_v1_manifest,
)

class TestLabelMap:
    def test_keys_are_0_through_3(self):
        assert set(LABEL_MAP.keys()) == {0, 1, 2, 3}

    def test_each_entry_has_name_and_color(self):
        for k, v in LABEL_MAP.items():
            assert "name" in v, f"Falta 'name' en LABEL_MAP[{k}]"
            assert "color" in v, f"Falta 'color' en LABEL_MAP[{k}]"
            assert len(v["color"]) == 4, f"Color de LABEL_MAP[{k}] debe tener 4 canales (RGBA)"

    def test_background_is_transparent(self):
        assert LABEL_MAP[0]["name"] == "background"
        assert LABEL_MAP[0]["color"][3] == 0  

class TestLabelClass:
    def test_values(self):
        assert LabelClass.BENIGN.value == "benign"
        assert LabelClass.MALIGNANT.value == "malignant"
        assert LabelClass.UNCERTAIN.value == "uncertain"

    def test_from_string(self):
        assert LabelClass("benign") is LabelClass.BENIGN

class TestAnnotationFiles:
    def test_defaults_are_none(self):
        af = AnnotationFiles()
        assert af.mask is None
        assert af.points is None
        assert af.rois is None

    def test_partial_init(self):
        af = AnnotationFiles(mask="mask.nii.gz")
        assert af.mask == "mask.nii.gz"
        assert af.points is None


class TestImageAnnotation:
    def test_minimal_creation(self):
        ann = ImageAnnotation(source_filename="vol.nii.gz")
        assert ann.source_filename == "vol.nii.gz"
        assert ann.label == LabelClass.UNCERTAIN
        assert ann.save_count == 0

    def test_empty_filename_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ImageAnnotation(source_filename="")

    def test_whitespace_only_filename_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ImageAnnotation(source_filename="   ")

    def test_timestamps_are_utc(self):
        ann = ImageAnnotation(source_filename="x.nii")
        assert ann.created_at.tzinfo is not None
        assert ann.updated_at.tzinfo is not None


class TestPatientManifest:
    def test_default_schema_version(self):
        m = PatientManifest(patient_id="P001")
        assert m.schema_version == "2.0.0"

    def test_default_label_map(self):
        m = PatientManifest(patient_id="P001")
        assert "0" in m.label_map
        assert m.label_map["1"] == "benign"

    def test_upsert_creates_new_annotation(self):
        m = PatientManifest(patient_id="P001")
        m.upsert_annotation("vol.nii.gz", {"mask": "mask.nii.gz"})

        assert "vol.nii.gz" in m.annotations
        entry = m.annotations["vol.nii.gz"]
        assert entry.annotation_files.mask == "mask.nii.gz"
        assert entry.save_count == 1

    def test_upsert_updates_existing(self):
        m = PatientManifest(patient_id="P001")
        m.upsert_annotation("vol.nii.gz", {"mask": "mask.nii.gz"})
        m.upsert_annotation("vol.nii.gz", {"points": "pts.csv"})

        entry = m.annotations["vol.nii.gz"]
        assert entry.save_count == 2
        assert entry.annotation_files.mask == "mask.nii.gz"
        assert entry.annotation_files.points == "pts.csv"

    def test_upsert_preserves_shape_on_update(self):
        m = PatientManifest(patient_id="P001")
        m.upsert_annotation("v.nii.gz", {"mask": "m.nii.gz"}, shape=[4, 8, 8])
        m.upsert_annotation("v.nii.gz", {"points": "p.csv"}, shape=[99, 99, 99])
        assert m.annotations["v.nii.gz"].original_shape == [4, 8, 8]

    def test_upsert_updates_last_modified(self):
        m = PatientManifest(patient_id="P001")
        t0 = m.last_modified
        m.upsert_annotation("v.nii.gz", {"mask": "m.nii.gz"})
        assert m.last_modified >= t0

class TestMigrateV1:
    def test_empty_v1(self):
        result = migrate_v1_manifest({}, patient_id="PAC001")
        assert result.schema_version == "2.0.0"
        assert result.patient_id == "PAC001"
        assert result.annotations == {}

    def test_with_files(self):
        v1 = {
            "patient_id": "PAC002",
            "created_at": "2024-01-01T00:00:00+00:00",
            "files": [
                {
                    "source": "vol.nii.gz",
                    "annotations": {"mask": "mask.nii.gz"},
                    "save_count": 3,
                    "last_saved": "2024-06-15T12:00:00+00:00",
                }
            ],
        }
        result = migrate_v1_manifest(v1)
        assert result.patient_id == "PAC002"
        assert "vol.nii.gz" in result.annotations
        ann = result.annotations["vol.nii.gz"]
        assert ann.save_count == 3
        assert ann.annotation_files.mask == "mask.nii.gz"

    def test_missing_patient_id_uses_fallback(self):
        result = migrate_v1_manifest({"files": []}, patient_id="FALLBACK")
        assert result.patient_id == "FALLBACK"

    def test_missing_patient_id_no_fallback(self):
        result = migrate_v1_manifest({"files": []})
        assert result.patient_id == "unknown"

    def test_skips_entries_without_source(self):
        v1 = {"files": [{"annotations": {"mask": "m.nii.gz"}, "save_count": 1}]}
        result = migrate_v1_manifest(v1)
        assert len(result.annotations) == 0

    def test_invalid_date_uses_now(self):
        v1 = {"created_at": "not-a-date", "files": []}
        result = migrate_v1_manifest(v1)
        
        assert isinstance(result.created_at, datetime)