from pathlib import Path

import numpy as np
import pytest

from patient_browser import (
    ANNOTATIONS_SUBDIR,
    PatientInfo,
    _scan_patient,
    scan_base_directory,
)

class TestScanPatient:
    def test_returns_none_for_nonexistent_dir(self, tmp_path):
        result = _scan_patient(tmp_path / "nope", "MAMA")
        assert result is None

    def test_returns_none_for_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        result = _scan_patient(f, "MAMA")
        assert result is None

    def test_returns_none_for_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        result = _scan_patient(d, "MAMA")
        assert result is None

    def test_counts_nifti_files(self, tmp_path):
        d = tmp_path / "PAC001"
        d.mkdir()
        (d / "vol1.nii.gz").touch()
        (d / "vol2.nii").touch()
        (d / "readme.txt").touch() 

        info = _scan_patient(d, "MAMA")
        assert info is not None
        assert info.nifti_count == 2
        assert info.png_count == 0

    def test_counts_png_files(self, tmp_path):
        d = tmp_path / "PAC002"
        d.mkdir()
        (d / "img1.png").touch()
        (d / "img2.PNG").touch() 

        info = _scan_patient(d, "PROSTATA")
        assert info is not None
        assert info.png_count >= 1 

    def test_detects_annotations(self, tmp_path):
        d = tmp_path / "PAC003"
        d.mkdir()
        (d / "vol.nii.gz").touch()
        ann = d / ANNOTATIONS_SUBDIR
        ann.mkdir()
        (ann / "mask.nii.gz").touch()

        info = _scan_patient(d, "MAMA")
        assert info is not None
        assert info.has_annotations is True
        assert info.annotation_count == 1

    def test_no_annotations_dir(self, tmp_path):
        d = tmp_path / "PAC004"
        d.mkdir()
        (d / "vol.nii.gz").touch()

        info = _scan_patient(d, "MAMA")
        assert info is not None
        assert info.has_annotations is False
        assert info.annotation_count == 0

    def test_empty_annotations_dir(self, tmp_path):
        d = tmp_path / "PAC005"
        d.mkdir()
        (d / "vol.nii.gz").touch()
        (d / ANNOTATIONS_SUBDIR).mkdir()

        info = _scan_patient(d, "MAMA")
        assert info is not None
        assert info.has_annotations is False

    def test_skips_hidden_files(self, tmp_path):
        d = tmp_path / "PAC006"
        d.mkdir()
        (d / ".DS_Store").touch()
        (d / "vol.nii.gz").touch()

        info = _scan_patient(d, "MAMA")
        assert info is not None
        assert info.nifti_count == 1

    def test_excludes_manifest_from_annotation_count(self, tmp_path):
        d = tmp_path / "PAC007"
        d.mkdir()
        (d / "vol.nii.gz").touch()
        ann = d / ANNOTATIONS_SUBDIR
        ann.mkdir()
        (ann / "manifest.json").touch()
        (ann / "mask.nii.gz").touch()

        info = _scan_patient(d, "MAMA")
        assert info is not None
    
        assert info.annotation_count == 1

    def test_patient_id_is_dir_name(self, tmp_path):
        d = tmp_path / "MY_PATIENT"
        d.mkdir()
        (d / "data.nii.gz").touch()
        info = _scan_patient(d, "MAMA")
        assert info.patient_id == "MY_PATIENT"


class TestScanBaseDirectory:
    def test_finds_patients_across_categories(self, tmp_path):    
        m_proc = tmp_path / "MAMA" / "PROCESSED_DATA"
        m_proc.mkdir(parents=True)
        p1 = m_proc / "P1"
        p1.mkdir()
        (p1 / "vol.nii.gz").touch()

        pr_proc = tmp_path / "PROSTATA" / "PROCESSED_DATA"
        pr_proc.mkdir(parents=True)
        p2 = pr_proc / "P2"
        p2.mkdir()
        (p2 / "vol.nii.gz").touch()

        patients = scan_base_directory(tmp_path)
        ids = {p.patient_id for p in patients}
        assert ids == {"P1", "P2"}

    def test_empty_base_returns_empty(self, tmp_path):
        patients = scan_base_directory(tmp_path)
        assert patients == []

    def test_ignores_hidden_categories(self, tmp_path):
        hidden = tmp_path / ".hidden" / "PROCESSED_DATA"
        hidden.mkdir(parents=True)
        p = hidden / "P1"
        p.mkdir()
        (p / "v.nii.gz").touch()

        patients = scan_base_directory(tmp_path)
        assert patients == []

    def test_ignores_dollar_categories(self, tmp_path):
        dollar = tmp_path / "$RECYCLE.BIN" / "PROCESSED_DATA"
        dollar.mkdir(parents=True)

        patients = scan_base_directory(tmp_path)
        assert patients == []

    def test_skips_category_without_processed_data(self, tmp_path):
        (tmp_path / "MAMA").mkdir() 
        patients = scan_base_directory(tmp_path)
        assert patients == []

class TestPatientInfo:
    def test_defaults(self):
        info = PatientInfo(
            patient_id="P",
            category="MAMA",
            path=Path("/tmp/P"),
        )
        assert info.nifti_count == 0
        assert info.png_count == 0
        assert info.has_annotations is False
        assert info.annotation_count == 0
