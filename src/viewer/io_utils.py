import numpy as np
import nibabel as nib
import imageio.v3 as iio
import json
from datetime import datetime, timezone
from pathlib import Path

def find_patient_path(patient_id, root_dir):
    search_paths = [
        Path(f"{root_dir}/MAMA/PROCESSED_DATA/{patient_id}"),
        Path(f"{root_dir}/PROSTATA/PROCESSED_DATA/{patient_id}"),
    ]
    return next((path for path in search_paths if path.exists()), None)

def load_nifti_volume(file_path):
    nifti_obj = nib.load(file_path)
    volume_data = nifti_obj.get_fdata()
    return volume_data, nifti_obj.affine


def load_nifti_mask(file_path):
    nifti_obj = nib.load(file_path)
    mask_data = np.asarray(nifti_obj.dataobj, dtype=np.uint16)
    return mask_data, nifti_obj.affine


def load_2d_image(file_path):
    return iio.imread(file_path)


def save_nifti_mask(data, affine, output_path):
    if data.dtype != np.uint16:
        data = data.astype(np.uint16)
    mask_nifti = nib.Nifti1Image(data, affine)
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
    return {"patient_id": None, "created_at": None, "files": []}


def update_manifest_entry(manifest, source_filename, saved_files, patient_id=None):
    now = datetime.now(timezone.utc).isoformat()

    if manifest.get('patient_id') is None and patient_id:
        manifest['patient_id'] = patient_id
    if manifest.get('created_at') is None:
        manifest['created_at'] = now

    manifest['last_modified'] = now

    existing = next(
        (f for f in manifest['files'] if f['source'] == source_filename),
        None
    )

    entry_data = {
        'source': source_filename,
        'annotations': saved_files,
        'last_saved': now,
        'annotation_types': list(saved_files.keys()),
    }

    if existing:
        existing.update(entry_data)
        existing['save_count'] = existing.get('save_count', 0) + 1
    else:
        entry_data['save_count'] = 1
        manifest['files'].append(entry_data)

    return manifest