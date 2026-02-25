import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import io_utils


class ImageLoader:
    def __init__(self, base_path, max_workers: int = 6):
        self.base_path = Path(base_path)
        self.max_workers = max_workers

    def load_all_images(self):
        nifti_data = self._load_nifti_volumes()
        png_data = self._load_png_images()
        return nifti_data + png_data

    def _load_nifti_volumes(self):
        nifti_files = list(self.base_path.glob("*.nii.gz")) + list(self.base_path.glob("*.nii"))
        nifti_files = sorted([f for f in nifti_files if not f.name.startswith('.')])

        print(f"Cargando {len(nifti_files)} volúmenes en paralelo (workers={self.max_workers})...")

        def _load_one(nii_file):
            data, affine = io_utils.load_nifti_volume(nii_file)
            p_low, p_high = np.percentile(data, [2, 98])
            spacing = np.abs(np.diag(affine[:3, :3])).tolist()
            return {
                'data': data,
                'name': f"3D_{nii_file.stem}",
                'filename': nii_file.name,
                'type': '3D',
                'colormap': 'gray',
                'contrast_limits': [float(p_low), float(p_high)],
                'affine': affine,
                'voxel_spacing': spacing
            }

        results: dict = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_file = {pool.submit(_load_one, f): f for f in nifti_files}
            for future in as_completed(future_to_file):
                nii_file = future_to_file[future]
                try:
                    info = future.result()
                    results[nii_file.name] = info
                    print(f"  {nii_file.name} — shape={info['data'].shape}")
                except Exception as e:
                    print(f"Error en {nii_file.name}: {e}")

        return [results[f.name] for f in nifti_files if f.name in results]

    def _load_png_images(self):
        png_files = sorted([f for f in self.base_path.glob("*.png") if not f.name.startswith('.')])

        loaded_images = []
        for png_file in png_files:
            try:
                data = io_utils.load_2d_image(png_file)
                image_info = {
                    'data': data,
                    'name': f"2D_{png_file.stem}",
                    'filename': png_file.name,
                    'type': '2D',
                    'colormap': 'gray',
                    'contrast_limits': [np.percentile(data, 2), np.percentile(data, 98)],
                    'affine': None
                }
                loaded_images.append(image_info)
                print(f"  {png_file.name}")
            except Exception as e:
                print(f"Error en {png_file.name}: {e}")

        return loaded_images