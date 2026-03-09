import nibabel as nib
import numpy as np
from PIL import Image

from image_loader import ImageLoader


class TestImageLoaderNifti:
    def test_loads_single_nifti_gz(self, tmp_path, identity_affine):
        vol = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
        nib.save(nib.Nifti1Image(vol, identity_affine), tmp_path / "scan.nii.gz")

        results = ImageLoader(tmp_path).load_all_images()

        assert len(results) == 1
        r = results[0]
        assert r["name"] == "3D_scan.nii"
        assert r["filename"] == "scan.nii.gz"
        assert r["type"] == "3D"
        assert r["colormap"] == "gray"
        assert r["data"].shape == (2, 3, 4)
        assert r["affine"] is not None
        assert len(r["contrast_limits"]) == 2
        assert len(r["voxel_spacing"]) == 3

    def test_loads_plain_nii(self, tmp_path, identity_affine):
        nib.save(
            nib.Nifti1Image(np.zeros((2, 4, 4), dtype=np.float32), identity_affine),
            tmp_path / "volume.nii",
        )

        results = ImageLoader(tmp_path).load_all_images()

        assert len(results) == 1
        assert results[0]["filename"] == "volume.nii"

    def test_contrast_limits_match_2_and_98_percentiles(self, tmp_path, identity_affine):
        vol = np.linspace(0, 100, 100, dtype=np.float32).reshape(5, 5, 4)
        nib.save(nib.Nifti1Image(vol, identity_affine), tmp_path / "v.nii.gz")

        results = ImageLoader(tmp_path).load_all_images()
        r = results[0]

        np.testing.assert_almost_equal(
            r["contrast_limits"][0], float(np.percentile(vol, 2)), decimal=3
        )
        np.testing.assert_almost_equal(
            r["contrast_limits"][1], float(np.percentile(vol, 98)), decimal=3
        )

    def test_voxel_spacing_extracted_from_affine_diagonal(self, tmp_path, scaled_affine):
        nib.save(
            nib.Nifti1Image(np.zeros((2, 3, 4), dtype=np.float32), scaled_affine),
            tmp_path / "v.nii.gz",
        )

        results = ImageLoader(tmp_path).load_all_images()
        spacing = results[0]["voxel_spacing"]

        assert abs(spacing[0] - 0.5) < 1e-4
        assert abs(spacing[1] - 0.5) < 1e-4
        assert abs(spacing[2] - 0.5) < 1e-4

    def test_multiple_niftis_ordered_alphabetically(self, tmp_path, identity_affine):
        for name in ("c.nii.gz", "a.nii.gz", "b.nii.gz"):
            nib.save(
                nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.float32), identity_affine),
                tmp_path / name,
            )

        results = ImageLoader(tmp_path).load_all_images()

        assert [r["filename"] for r in results] == ["a.nii.gz", "b.nii.gz", "c.nii.gz"]

    def test_hidden_nifti_files_are_excluded(self, tmp_path, identity_affine):
        vol = np.zeros((2, 2, 2), dtype=np.float32)
        nib.save(nib.Nifti1Image(vol, identity_affine), tmp_path / ".hidden.nii.gz")
        nib.save(nib.Nifti1Image(vol, identity_affine), tmp_path / "visible.nii.gz")

        results = ImageLoader(tmp_path).load_all_images()

        assert len(results) == 1
        assert results[0]["filename"] == "visible.nii.gz"

    def test_name_prefix_is_3d(self, tmp_path, identity_affine):
        nib.save(
            nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.float32), identity_affine),
            tmp_path / "mri.nii.gz",
        )

        results = ImageLoader(tmp_path).load_all_images()

        assert results[0]["name"].startswith("3D_")

class TestImageLoaderPng:
    def test_loads_png_as_2d(self, tmp_path):
        img = np.arange(64, dtype=np.uint8).reshape(8, 8)
        Image.fromarray(img).save(tmp_path / "slice.png")

        results = ImageLoader(tmp_path).load_all_images()

        assert len(results) == 1
        r = results[0]
        assert r["name"] == "2D_slice"
        assert r["filename"] == "slice.png"
        assert r["type"] == "2D"
        assert r["affine"] is None

    def test_png_contrast_limits_low_is_less_than_high(self, tmp_path):
        img = np.arange(100, dtype=np.uint8).reshape(10, 10)
        Image.fromarray(img).save(tmp_path / "img.png")

        results = ImageLoader(tmp_path).load_all_images()

        r = results[0]
        assert r["contrast_limits"][0] < r["contrast_limits"][1]

    def test_name_prefix_is_2d(self, tmp_path):
        Image.fromarray(np.zeros((4, 4), dtype=np.uint8)).save(tmp_path / "photo.png")

        results = ImageLoader(tmp_path).load_all_images()

        assert results[0]["name"].startswith("2D_")


class TestImageLoaderEdgeCases:
    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert ImageLoader(tmp_path).load_all_images() == []

    def test_nifti_and_png_both_returned(self, tmp_path, identity_affine):
        nib.save(
            nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.float32), identity_affine),
            tmp_path / "vol.nii.gz",
        )
        Image.fromarray(np.zeros((4, 4), dtype=np.uint8)).save(tmp_path / "img.png")

        results = ImageLoader(tmp_path).load_all_images()

        assert {r["type"] for r in results} == {"3D", "2D"}

    def test_data_dtype_is_float32_for_nifti(self, tmp_path, identity_affine):
        vol = np.arange(8, dtype=np.int16).reshape(2, 2, 2)
        nib.save(nib.Nifti1Image(vol, identity_affine), tmp_path / "v.nii.gz")

        results = ImageLoader(tmp_path).load_all_images()

        assert results[0]["data"].dtype == np.float32
