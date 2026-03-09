import json

import nibabel as nib
import numpy as np
import pytest

import io_utils
from schemas import PatientManifest

class TestNiftiMask:
    def test_save_load_roundtrip(self, tmp_path, sample_mask, identity_affine):
        path = tmp_path / "mask.nii.gz"
        io_utils.save_nifti_mask(sample_mask, identity_affine, str(path))

        loaded, aff = io_utils.load_nifti_mask(str(path))
        np.testing.assert_array_equal(loaded, sample_mask)
        np.testing.assert_array_almost_equal(aff, identity_affine)

    def test_non_uint16_gets_cast(self, tmp_path, identity_affine):
        data = np.ones((2, 3, 3), dtype=np.float64)
        path = tmp_path / "cast.nii.gz"
        io_utils.save_nifti_mask(data, identity_affine, str(path))

        loaded, _ = io_utils.load_nifti_mask(str(path))
        assert loaded.dtype == np.uint16
        np.testing.assert_array_equal(loaded, 1)


class TestNiftiVolume:
    def test_basic_float_volume(self, tmp_path, identity_affine):
        vol = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
        nib.save(nib.Nifti1Image(vol, identity_affine), tmp_path / "vol.nii.gz")

        loaded, aff = io_utils.load_nifti_volume(str(tmp_path / "vol.nii.gz"))
        assert loaded.dtype == np.float32
        np.testing.assert_array_almost_equal(loaded, vol)

class TestPointsCsv:
    def test_roundtrip(self, tmp_path):
        pts = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        path = tmp_path / "points.csv"
        io_utils.save_points_csv(pts, str(path))

        loaded = io_utils.load_points_csv(str(path))
        np.testing.assert_array_almost_equal(loaded, pts)

    def test_csv_header(self, tmp_path):
        pts = np.array([[0, 0, 0]])
        path = tmp_path / "pts.csv"
        io_utils.save_points_csv(pts, str(path))

        with open(path) as f:
            header = f.readline().strip()
        assert header == "z,y,x"

class TestRoisJson:
    def test_roundtrip(self, tmp_path):
        shapes = [
            np.array([[0, 0], [0, 5], [5, 5], [5, 0]]),
            np.array([[1, 1], [1, 3], [3, 3], [3, 1]]),
        ]
        types = ["rectangle", "polygon"]

        path = tmp_path / "rois.json"
        io_utils.save_rois_json(shapes, types, str(path))

        loaded_shapes, loaded_types = io_utils.load_rois_json(str(path))
        assert loaded_types == types
        assert len(loaded_shapes) == 2
        np.testing.assert_array_almost_equal(loaded_shapes[0], shapes[0])

    def test_json_structure(self, tmp_path):
        shapes = [np.array([[0, 0, 0], [1, 1, 1]])]
        types = ["line"]
        path = tmp_path / "rois.json"
        io_utils.save_rois_json(shapes, types, str(path))

        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["type"] == "line"
        assert data[0]["ndim"] == 3
        assert "vertices" in data[0]

class TestManifest:
    def test_save_load_v2_roundtrip(self, tmp_path):
        m = PatientManifest(patient_id="PAC001")
        m.upsert_annotation("vol.nii.gz", {"mask": "mask.nii.gz"})

        path = tmp_path / "manifest.json"
        io_utils.save_manifest(m, str(path))

        loaded = io_utils.load_manifest(str(path), patient_id="PAC001")
        assert isinstance(loaded, PatientManifest)
        assert loaded.patient_id == "PAC001"
        assert "vol.nii.gz" in loaded.annotations

    def test_load_missing_file_returns_empty(self, tmp_path):
        result = io_utils.load_manifest(str(tmp_path / "nope.json"), "P99")
        assert isinstance(result, PatientManifest)
        assert result.patient_id == "P99"
        assert result.annotations == {}

    def test_load_v1_migrates(self, tmp_path):
        v1_data = {
            "patient_id": "OLD",
            "created_at": "2024-01-01T00:00:00+00:00",
            "files": [
                {
                    "source": "img.nii.gz",
                    "annotations": {"mask": "m.nii.gz"},
                    "save_count": 2,
                    "last_saved": "2024-06-01T00:00:00+00:00",
                }
            ],
        }
        path = tmp_path / "manifest.json"
        with open(path, "w") as f:
            json.dump(v1_data, f)

        loaded = io_utils.load_manifest(str(path), "OLD")
        assert loaded.schema_version == "2.0.0"
        assert "img.nii.gz" in loaded.annotations

    def test_atomic_write_cleans_up_on_error(self, tmp_path, monkeypatch):
        """Si json.dump falla, no debe quedar archivo .tmp residual."""
        import io_utils as mod

        def _bad_dump(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(json, "dump", _bad_dump)

        with pytest.raises(RuntimeError, match="boom"):
            io_utils.save_manifest({"x": 1}, str(tmp_path / "m.json"))

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_save_manifest_creates_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "manifest.json"
        io_utils.save_manifest(PatientManifest(patient_id="X"), str(nested))
        assert nested.exists()

class TestUpdateManifestEntry:
    def test_with_patient_manifest(self):
        m = PatientManifest(patient_id="P")
        io_utils.update_manifest_entry(m, "vol.nii.gz", {"mask": "m.nii.gz"})
        assert "vol.nii.gz" in m.annotations

    def test_with_raw_dict_new_entry(self):
        d = {"patient_id": None, "created_at": None, "last_modified": None, "files": []}
        result = io_utils.update_manifest_entry(d, "vol.nii.gz", {"mask": "m.nii.gz"}, patient_id="P1")
        assert result["patient_id"] == "P1"
        assert len(result["files"]) == 1
        assert result["files"][0]["save_count"] == 1

    def test_with_raw_dict_updates_existing(self):
        d = {
            "patient_id": "P",
            "created_at": "2024-01-01",
            "last_modified": None,
            "files": [
                {"source": "a.nii.gz", "annotations": {}, "save_count": 1}
            ],
        }
        io_utils.update_manifest_entry(d, "a.nii.gz", {"mask": "mask.nii.gz"})
        assert d["files"][0]["save_count"] == 2
        assert d["files"][0]["annotations"] == {"mask": "mask.nii.gz"}

class TestFindPatientPath:
    def test_finds_mama_patient(self, patient_tree):
        result = io_utils.find_patient_path("PAC001", str(patient_tree))
        assert result is not None
        assert result.name == "PAC001"

    def test_returns_none_for_missing(self, patient_tree):
        result = io_utils.find_patient_path("NOEXISTE", str(patient_tree))
        assert result is None
