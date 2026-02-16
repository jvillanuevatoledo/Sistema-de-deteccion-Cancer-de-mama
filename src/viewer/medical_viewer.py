import os
os.environ["QT_API"] = "pyside6"

import napari
from image_loader import ImageLoader
from annotation_manager import AnnotationManager
import io_utils

def start_viewer(patient_id, base_dir="/Volumes/HRAEPY"):
    base_path = io_utils.find_patient_path(patient_id, base_dir)

    if not base_path:
        print(f"No se encontró el paciente: {patient_id}")
        return

    viewer = napari.Viewer(title=f"Annotator - Patient: {patient_id}")

    loader = ImageLoader(base_path)
    images = loader.load_all_images()

    if not images:
        viewer.close()
        return

    is_first = True
    for image_info in images:
        viewer.add_image(
            image_info['data'],
            name=image_info['name'],
            colormap=image_info['colormap'],
            contrast_limits=image_info['contrast_limits'],
            visible=is_first,
            metadata={
                'filename': image_info['filename'],
                'affine': image_info['affine']
            }
        )
        is_first = False

    annotator = AnnotationManager(viewer)
    output_dir = base_path / "ANNOTATIONS"
    output_dir.mkdir(exist_ok=True)
    manifest_path = output_dir / "manifest.json"

    def get_active_image_layer():
        return next(
            (l for l in viewer.layers
             if isinstance(l, napari.layers.Image) and l.visible),
            None
        )

    first_layer = get_active_image_layer()
    if first_layer:
        annotator.activate_for_image(
            first_layer.metadata['filename'],
            first_layer.data.shape
        )
        _load_existing_annotations(
            annotator, first_layer.metadata['filename'], output_dir
        )

    def _on_visibility_change(event):
        layer = event.source
        if not isinstance(layer, napari.layers.Image):
            return
        if not layer.visible:
            return
        filename = layer.metadata.get('filename')
        if filename and filename != annotator.active_filename:
            annotator.activate_for_image(filename, layer.data.shape)
            _load_existing_annotations(annotator, filename, output_dir)

    for layer in viewer.layers:
        if isinstance(layer, napari.layers.Image):
            layer.events.visible.connect(_on_visibility_change)

    @viewer.bind_key('s')
    def save_session(viewer_instance):
        active_layer = get_active_image_layer()

        if not active_layer:
            print("No hay imagen visible para asociar anotaciones.")
            return

        source_filename = active_layer.metadata['filename']
        affine = active_layer.metadata['affine']

        if annotator.active_filename != source_filename:
            annotator.activate_for_image(source_filename, active_layer.data.shape)

        saved_files = {}

        if annotator.has_segmentation_data():
            mask_path = output_dir / f"{source_filename}_mask.nii.gz"
            io_utils.save_nifti_mask(
                annotator.get_segmentation_data(), affine, mask_path
            )
            saved_files['mask'] = mask_path.name

        if annotator.has_points_data():
            pts_path = output_dir / f"{source_filename}_points.csv"
            io_utils.save_points_csv(
                annotator.get_points_data(), pts_path
            )
            saved_files['points'] = pts_path.name

        if annotator.has_roi_data():
            rois, types = annotator.get_roi_data()
            roi_path = output_dir / f"{source_filename}_rois.json"
            io_utils.save_rois_json(rois, types, roi_path)
            saved_files['rois'] = roi_path.name

        manifest = io_utils.load_manifest(manifest_path)
        existing = next(
            (f for f in manifest['files'] if f['source'] == source_filename),
            None
        )
        if existing:
            existing['annotations'] = saved_files
        else:
            manifest['files'].append({
                'source': source_filename,
                'annotations': saved_files
            })
        io_utils.save_manifest(manifest, manifest_path)

        print(f"Anotaciones guardadas para: {source_filename}")
        print(f"  Archivos: {list(saved_files.values())}")

    napari.run()


def _load_existing_annotations(annotator, filename, output_dir):
    import numpy as np

    mask_path = output_dir / f"{filename}_mask.nii.gz"
    if mask_path.exists():
        try:
            mask_data, _ = io_utils.load_nifti_volume(mask_path)
            annotator.load_existing_mask(filename, mask_data.astype(np.uint16))
            print(f"  Máscara cargada: {mask_path.name}")
        except Exception as e:
            print(f"  Error cargando máscara: {e}")

    pts_path = output_dir / f"{filename}_points.csv"
    if pts_path.exists():
        try:
            pts_data = io_utils.load_points_csv(pts_path)
            if pts_data.ndim == 1:
                pts_data = pts_data.reshape(1, -1)
            annotator.load_existing_points(filename, pts_data)
            print(f"  Puntos cargados: {pts_path.name}")
        except Exception as e:
            print(f"  Error cargando puntos: {e}")

    roi_path = output_dir / f"{filename}_rois.json"
    if roi_path.exists():
        try:
            shapes, types = io_utils.load_rois_json(roi_path)
            annotator.load_existing_rois(filename, shapes, types)
            print(f"  ROIs cargados: {roi_path.name}")
        except Exception as e:
            print(f"  Error cargando ROIs: {e}")


if __name__ == "__main__":
    start_viewer("ANONM0000002")