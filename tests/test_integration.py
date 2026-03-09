import nibabel as nib
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock

import io_utils
import save_service as _save_service_mod
from coordinate_utils import array_to_world, world_to_array
from image_loader import ImageLoader
from patient_browser import ANNOTATIONS_SUBDIR, scan_base_directory
from schemas import PatientManifest


@pytest.fixture
def mock_qtimer(monkeypatch):
    monkeypatch.setattr(_save_service_mod, "QTimer", MagicMock)

class TestFullAnnotationRoundTrip:
    def test_mask_points_rois_written_and_restored(self, tmp_path, identity_affine):
        mask = np.zeros((4, 8, 8), dtype=np.uint16)
        mask[1, 2:6, 2:6] = 1
        points = np.array([[1.0, 3.0, 3.0], [2.0, 5.0, 5.0]])
        shapes = [np.array([[0.0, 0.0], [0.0, 5.0], [5.0, 5.0], [5.0, 0.0]])]
        types = ["rectangle"]

        io_utils.save_nifti_mask(mask, identity_affine, str(tmp_path / "mask.nii.gz"))
        io_utils.save_points_csv(points, str(tmp_path / "pts.csv"))
        io_utils.save_rois_json(shapes, types, str(tmp_path / "rois.json"))

        loaded_mask, _ = io_utils.load_nifti_mask(str(tmp_path / "mask.nii.gz"))
        loaded_pts = io_utils.load_points_csv(str(tmp_path / "pts.csv"))
        loaded_shapes, loaded_types = io_utils.load_rois_json(str(tmp_path / "rois.json"))

        np.testing.assert_array_equal(loaded_mask, mask)
        np.testing.assert_array_almost_equal(loaded_pts, points)
        assert loaded_types == types
        np.testing.assert_array_almost_equal(loaded_shapes[0], shapes[0])

    def test_label_values_survive_nifti_roundtrip(self, tmp_path, identity_affine):
        mask = np.zeros((4, 8, 8), dtype=np.uint16)
        mask[0, :, :] = 0
        mask[1, :, :] = 1
        mask[2, :, :] = 2
        mask[3, :, :] = 3

        io_utils.save_nifti_mask(mask, identity_affine, str(tmp_path / "labels.nii.gz"))
        loaded, _ = io_utils.load_nifti_mask(str(tmp_path / "labels.nii.gz"))

        for label in (0, 1, 2, 3):
            assert label in loaded


class TestManifestMultipleSessionLifecycle:
    def test_save_count_persists_across_reloads(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"

        m = PatientManifest(patient_id="P001")
        m.upsert_annotation("vol.nii.gz", {"mask": "m.nii.gz"})
        io_utils.save_manifest(m, str(manifest_path))

        loaded = io_utils.load_manifest(str(manifest_path), "P001")
        loaded.upsert_annotation("vol.nii.gz", {"points": "p.csv"})
        io_utils.save_manifest(loaded, str(manifest_path))

        final = io_utils.load_manifest(str(manifest_path), "P001")
        assert final.annotations["vol.nii.gz"].save_count == 2
        assert final.annotations["vol.nii.gz"].annotation_files.mask == "m.nii.gz"
        assert final.annotations["vol.nii.gz"].annotation_files.points == "p.csv"

    def test_manifest_holds_multiple_images_after_persistence(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        image_names = [f"scan_{i}.nii.gz" for i in range(5)]

        m = PatientManifest(patient_id="P002")
        for name in image_names:
            m.upsert_annotation(name, {"mask": f"m_{name}"})
        io_utils.save_manifest(m, str(manifest_path))

        loaded = io_utils.load_manifest(str(manifest_path), "P002")
        assert len(loaded.annotations) == 5
        for name in image_names:
            assert name in loaded.annotations

    def test_schema_version_preserved_through_resave(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"

        m = PatientManifest(patient_id="P003")
        io_utils.save_manifest(m, str(manifest_path))
        loaded = io_utils.load_manifest(str(manifest_path), "P003")

        assert loaded.schema_version == "2.0.0"

    def test_v1_manifest_upgraded_and_resaved_as_v2(self, tmp_path):
        import json

        manifest_path = tmp_path / "manifest.json"
        v1 = {
            "patient_id": "OLD",
            "created_at": "2024-01-01T00:00:00+00:00",
            "files": [
                {
                    "source": "img.nii.gz",
                    "annotations": {"mask": "m.nii.gz"},
                    "save_count": 1,
                    "last_saved": "2024-06-01T00:00:00+00:00",
                }
            ],
        }
        with open(manifest_path, "w") as f:
            json.dump(v1, f)

        loaded = io_utils.load_manifest(str(manifest_path), "OLD")
        loaded.upsert_annotation("img.nii.gz", {"points": "p.csv"})
        io_utils.save_manifest(loaded, str(manifest_path))

        final = io_utils.load_manifest(str(manifest_path), "OLD")
        assert final.schema_version == "2.0.0"
        assert final.annotations["img.nii.gz"].save_count == 2


class TestSaveServiceExecute:
    def test_writes_all_file_types_and_updates_manifest(
        self, tmp_path, identity_affine, mock_qtimer
    ):
        from save_service import SaveRequest, SaveService

        manifest = PatientManifest(patient_id="PAT01")
        manifest_path = tmp_path / "manifest.json"
        service = SaveService(manifest, manifest_path)

        mask_data = np.zeros((4, 8, 8), dtype=np.uint16)
        mask_data[2, 3:6, 3:6] = 2

        req = SaveRequest(
            source_filename="scan.nii.gz",
            data_to_save={
                "mask": {
                    "data": mask_data,
                    "affine": identity_affine,
                    "path": tmp_path / "mask.nii.gz",
                },
                "points": {
                    "data": np.array([[1.0, 2.0, 3.0]]),
                    "path": tmp_path / "pts.csv",
                },
                "rois": {
                    "data": [np.array([[0.0, 0.0], [0.0, 5.0], [5.0, 5.0], [5.0, 0.0]])],
                    "types": ["rectangle"],
                    "path": tmp_path / "rois.json",
                },
            },
            existing_on_disk={},
            patient_id="PAT01",
            output_dir=tmp_path,
            image_shape=[4, 8, 8],
            voxel_spacing=[1.0, 1.0, 1.0],
        )

        service._execute(req)

        assert (tmp_path / "mask.nii.gz").exists()
        assert (tmp_path / "pts.csv").exists()
        assert (tmp_path / "rois.json").exists()

        result = service._result_queue.get_nowait()
        assert result.success is True

        assert "scan.nii.gz" in manifest.annotations
        entry = manifest.annotations["scan.nii.gz"]
        assert entry.save_count == 1
        assert entry.original_shape == [4, 8, 8]
        assert manifest_path.exists()

    def test_saved_mask_data_matches_original(self, tmp_path, identity_affine, mock_qtimer):
        from save_service import SaveRequest, SaveService

        manifest = PatientManifest(patient_id="P_VERIFY")
        service = SaveService(manifest, tmp_path / "manifest.json")

        original_mask = np.zeros((4, 8, 8), dtype=np.uint16)
        original_mask[1, 2:6, 2:6] = 1
        original_mask[2, 3:5, 3:5] = 2

        req = SaveRequest(
            source_filename="vol.nii.gz",
            data_to_save={
                "mask": {
                    "data": original_mask,
                    "affine": identity_affine,
                    "path": tmp_path / "mask.nii.gz",
                }
            },
            existing_on_disk={},
            patient_id="P_VERIFY",
            output_dir=tmp_path,
        )
        service._execute(req)

        loaded_mask, _ = io_utils.load_nifti_mask(str(tmp_path / "mask.nii.gz"))
        np.testing.assert_array_equal(loaded_mask, original_mask)

    def test_existing_files_recorded_in_manifest(self, tmp_path, identity_affine, mock_qtimer):
        from save_service import SaveRequest, SaveService

        manifest = PatientManifest(patient_id="P_EXIST")
        service = SaveService(manifest, tmp_path / "manifest.json")

        req = SaveRequest(
            source_filename="vol.nii.gz",
            data_to_save={},
            existing_on_disk={"mask": "old_mask.nii.gz", "points": "old_pts.csv"},
            patient_id="P_EXIST",
            output_dir=tmp_path,
        )
        service._execute(req)

        result = service._result_queue.get_nowait()
        assert result.success is True
        entry = manifest.annotations["vol.nii.gz"]
        assert entry.annotation_files.mask == "old_mask.nii.gz"
        assert entry.annotation_files.points == "old_pts.csv"

    def test_failed_write_produces_error_result(self, tmp_path, identity_affine, mock_qtimer):
        from save_service import SaveRequest, SaveService

        service = SaveService(PatientManifest(patient_id="P"), tmp_path / "m.json")

        req = SaveRequest(
            source_filename="s.nii.gz",
            data_to_save={
                "mask": {
                    "data": np.zeros((2, 2, 2), dtype=np.uint16),
                    "affine": identity_affine,
                    "path": Path("/nonexistent/dir/mask.nii.gz"),
                }
            },
            existing_on_disk={},
            patient_id="P",
            output_dir=tmp_path,
        )

        service._execute(req)

        result = service._result_queue.get_nowait()
        assert result.success is False
        assert result.detail != ""

class TestPatientScanWithManifest:
    def test_scan_finds_patient_and_manifest_loads_correctly(
        self, tmp_path, identity_affine
    ):
        proc = tmp_path / "MAMA" / "PROCESSED_DATA" / "P001"
        proc.mkdir(parents=True)
        nib.save(
            nib.Nifti1Image(np.zeros((2, 4, 4), dtype=np.float32), identity_affine),
            proc / "vol.nii.gz",
        )
        ann_dir = proc / ANNOTATIONS_SUBDIR
        ann_dir.mkdir()

        m = PatientManifest(patient_id="P001")
        m.upsert_annotation("vol.nii.gz", {"mask": "mask.nii.gz"})
        io_utils.save_manifest(m, str(ann_dir / "manifest.json"))

        patients = scan_base_directory(tmp_path)
        assert len(patients) == 1
        p = patients[0]
        assert p.has_annotations is True

        manifest = io_utils.load_manifest(
            str(p.path / ANNOTATIONS_SUBDIR / "manifest.json"), p.patient_id
        )
        assert isinstance(manifest, PatientManifest)
        assert "vol.nii.gz" in manifest.annotations

    def test_patient_without_manifest_gets_empty_manifest(
        self, tmp_path, identity_affine
    ):
        proc = tmp_path / "MAMA" / "PROCESSED_DATA" / "P002"
        proc.mkdir(parents=True)
        nib.save(
            nib.Nifti1Image(np.zeros((2, 4, 4), dtype=np.float32), identity_affine),
            proc / "vol.nii.gz",
        )

        patients = scan_base_directory(tmp_path)
        assert len(patients) == 1
        p = patients[0]

        manifest = io_utils.load_manifest(
            str(p.path / ANNOTATIONS_SUBDIR / "manifest.json"), p.patient_id
        )
        assert isinstance(manifest, PatientManifest)
        assert manifest.annotations == {}

class TestImageLoaderWithCoordinateTransform:
    def test_nifti_affine_enables_voxel_world_roundtrip(self, tmp_path, scaled_affine):
        nib.save(
            nib.Nifti1Image(np.zeros((4, 8, 8), dtype=np.float32), scaled_affine),
            tmp_path / "vol.nii.gz",
        )

        results = ImageLoader(tmp_path).load_all_images()
        affine = results[0]["affine"]

        voxel_coords = np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 6.0]])
        world = array_to_world(voxel_coords, affine)
        recovered = world_to_array(world, affine)

        np.testing.assert_array_almost_equal(recovered, voxel_coords, decimal=5)

    def test_world_coords_from_nifti_origin_match_expected_offset(
        self, tmp_path, scaled_affine
    ):
        nib.save(
            nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.float32), scaled_affine),
            tmp_path / "vol.nii.gz",
        )

        results = ImageLoader(tmp_path).load_all_images()
        affine = results[0]["affine"]

        origin = array_to_world(np.array([[0.0, 0.0, 0.0]]), affine)

        np.testing.assert_array_almost_equal(origin, [[10.0, 20.0, 30.0]])
