import numpy as np
import nibabel as nib
import imageio.v3 as iio
import json
from pathlib import Path

def find_patient_path(patient_id, root_dir):
    search_paths = [
        Path(f"{root_dir}/MAMA/PROCESSED_DATA/{patient_id}"),
        Path(f"{root_dir}/PROSTATA/PROCESSED_DATA/{patient_id}"),
    ]
    return next((path for path in search_paths if path.exists()), None)

def get_valid_files(base_path, extension):
    files = list(base_path.glob(f"*.{extension}"))
    return sorted([f for f in files if not f.name.startswith('.')])

def load_nifti_volume(file_path):
    nifti_obj = nib.load(file_path)
    volume_data = nifti_obj.get_fdata()
    return volume_data, nifti_obj.affine

def load_2d_image(file_path):
    return iio.imread(file_path)

def save_nifti_mask(data, affine, output_path):
    mask_nifti = nib.Nifti1Image(data.astype(np.uint16), affine)
    nib.save(mask_nifti, output_path)

def save_points_csv(data, output_path):
    np.savetxt(output_path, data, delimiter=",", header="z,y,x", comments='')

def load_points_csv(file_path):
    return np.loadtxt(file_path, delimiter=",", skiprows=1)

def save_rois_json(data, shape_types, output_path):
    roi_metadata = []
    for shape_type, vertices in zip(shape_types, data):
        roi_info = {
            "type": shape_type,
            "vertices": vertices.tolist(),
            "ndim": vertices.shape[1] if len(vertices.shape) > 1 else 2
        }
        roi_metadata.append(roi_info)
    
    with open(output_path, "w") as f:
        json.dump(roi_metadata, f, indent=4)

def load_rois_json(file_path):
    with open(file_path, "r") as f:
        roi_metadata = json.load(f)
    shapes = [np.array(r["vertices"]) for r in roi_metadata]
    types = [r["type"] for r in roi_metadata]
    return shapes, types

def save_manifest(manifest_data, output_path):
    with open(output_path, "w") as f:
        json.dump(manifest_data, f, indent=4, ensure_ascii=False)

def load_manifest(manifest_path):
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            return json.load(f)
    return {"files": []}