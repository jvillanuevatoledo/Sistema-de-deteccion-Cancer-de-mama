import numpy as np
import nibabel as nib
import imageio.v3 as iio
from pathlib import Path

class ImageLoader:
    def __init__(self, base_path):
        self.base_path = Path(base_path)

    def load_all_images(self):
        nifti_data = self._load_nifti_volumes()
        png_data = self._load_png_images()
        return nifti_data + png_data

    def _load_nifti_volumes(self):
        nifti_files = list(self.base_path.glob("*.nii.gz")) + list(self.base_path.glob("*.nii"))
        nifti_files = [f for f in nifti_files if not f.name.startswith('.')]

        loaded_images = []
        print(f"Cargando {len(nifti_files)} volúmenes...")
        for nii_file in nifti_files:
            try:
                img = nib.load(nii_file)
                data = img.get_fdata()

                image_info = {
                    'data': data,
                    'name': f"3D_{nii_file.stem}",
                    'filename': nii_file.name,
                    'type': '3D',
                    'colormap': 'gray',
                    'contrast_limits': [data.min(), data.max()],
                    'affine': img.affine
                }
                loaded_images.append(image_info)
                print(f"  {nii_file.name}")
            except Exception as e:
                print(f"Error en {nii_file.name}: {e}")

        return loaded_images

    def _load_png_images(self):
        png_files = [f for f in self.base_path.glob("*.png") if not f.name.startswith('.')]

        loaded_images = []
        for png_file in png_files:
            try:
                data = iio.imread(png_file)
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