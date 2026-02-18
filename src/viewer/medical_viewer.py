import os
os.environ["QT_API"] = "pyside6"

import threading
import queue
import napari
from PySide6.QtCore import QTimer
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

    manifest_cache = {'data': io_utils.load_manifest(manifest_path)}

    _save_lock = threading.Lock()
    _saving = {'active': False}

    
    _result_queue: queue.Queue = queue.Queue()

    
    _result_timer = QTimer()
    _result_timer.setInterval(100)

    def _process_save_results():
        while not _result_queue.empty():
            try:
                msg = _result_queue.get_nowait()
                if msg['type'] == 'success':
                    annotator.mark_saved()
                    _saving['active'] = False
                    viewer.status = msg['status']
                    print(msg['print'])
                elif msg['type'] == 'error':
                    _saving['active'] = False
                    viewer.status = msg['status']
                    print(msg['print'])
            except queue.Empty:
                break

    _result_timer.timeout.connect(_process_save_results)
    _result_timer.start()

    
    _visibility_pending = {'filename': None, 'shape': None}
    _debounce_timer = QTimer()
    _debounce_timer.setSingleShot(True)
    _debounce_timer.setInterval(300)

    def _execute_visibility_switch():
        fn = _visibility_pending['filename']
        shape = _visibility_pending['shape']
        if fn and fn != annotator.active_filename:
            annotator.activate_for_image(fn, shape)
            _load_existing_annotations(annotator, fn, output_dir)

    _debounce_timer.timeout.connect(_execute_visibility_switch)

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
        if not filename or filename == annotator.active_filename:
            return

        _visibility_pending['filename'] = filename
        _visibility_pending['shape'] = layer.data.shape
        _debounce_timer.start()  

    for layer in viewer.layers:
        if isinstance(layer, napari.layers.Image):
            layer.events.visible.connect(_on_visibility_change)

    @viewer.bind_key('s')
    def save_session(viewer_instance):
        active_layer = get_active_image_layer()

        if not active_layer:
            viewer.status = "No hay imagen visible para asociar anotaciones."
            return

        if not annotator.is_dirty():
            viewer.status = "Sin cambios pendientes — nada que guardar."
            return

        if _saving['active']:
            viewer.status = "Guardado en progreso, espera..."
            return

        source_filename = active_layer.metadata['filename']
        affine = active_layer.metadata.get('affine')

        if annotator.active_filename != source_filename:
            annotator.activate_for_image(source_filename, active_layer.data.shape)

        data_to_save = {}

        mask_path = output_dir / f"{source_filename}_mask.nii.gz"
        pts_path  = output_dir / f"{source_filename}_points.csv"
        roi_path  = output_dir / f"{source_filename}_rois.json"

        if annotator.is_dirty('labels') and annotator.has_segmentation_data():
            data_to_save['mask'] = {
                'data': annotator.get_segmentation_data().copy(),
                'affine': affine,
                'path': mask_path
            }

        if annotator.is_dirty('points') and annotator.has_points_data():
            data_to_save['points'] = {
                'data': annotator.get_points_data().copy(),
                'path': pts_path
            }

        if annotator.is_dirty('shapes') and annotator.has_roi_data():
            rois, types = annotator.get_roi_data()
            data_to_save['rois'] = {
                'data': [r.copy() for r in rois],
                'types': list(types),
                'path': roi_path
            }

        if not data_to_save:
            viewer.status = "Sin datos nuevos que guardar."
            annotator.mark_saved()
            return
        
        existing_on_disk = {
            'mask':   mask_path.name if mask_path.exists() and 'mask'   not in data_to_save else None,
            'points': pts_path.name  if pts_path.exists()  and 'points' not in data_to_save else None,
            'rois':   roi_path.name  if roi_path.exists()  and 'rois'   not in data_to_save else None,
        }
        existing_on_disk = {k: v for k, v in existing_on_disk.items() if v is not None}

        _saving['active'] = True
        viewer.status = f"Guardando anotaciones para {source_filename}..."

        def _background_save():
            try:
                saved_files = {}

                if 'mask' in data_to_save:
                    m = data_to_save['mask']
                    io_utils.save_nifti_mask(m['data'], m['affine'], m['path'])
                    saved_files['mask'] = m['path'].name

                if 'points' in data_to_save:
                    p = data_to_save['points']
                    io_utils.save_points_csv(p['data'], p['path'])
                    saved_files['points'] = p['path'].name

                if 'rois' in data_to_save:
                    r = data_to_save['rois']
                    io_utils.save_rois_json(r['data'], r['types'], r['path'])
                    saved_files['rois'] = r['path'].name

                saved_files.update(existing_on_disk)
                with _save_lock:
                    manifest = manifest_cache['data']
                    io_utils.update_manifest_entry(
                        manifest, source_filename, saved_files, patient_id
                    )
                    io_utils.save_manifest(manifest, manifest_path)
                    manifest_cache['data'] = manifest

                label_str = ', '.join(saved_files.keys())
                _result_queue.put({
                    'type': 'success',
                    'status': f"Guardado: {source_filename} [{label_str}]",
                    'print': (
                        f"Anotaciones guardadas para: {source_filename}\n"
                        f"Archivos: {list(saved_files.values())}"
                    )
                })

            except Exception as e:
                _result_queue.put({
                    'type': 'error',
                    'status': f"Error guardando: {e}",
                    'print': f"Error en guardado background: {e}"
                })

        thread = threading.Thread(target=_background_save, daemon=True)
        thread.start()

    napari.run()
    _result_timer.stop()
    _debounce_timer.stop()


def _load_existing_annotations(annotator, filename, output_dir):
    mask_path = output_dir / f"{filename}_mask.nii.gz"
    if mask_path.exists():
        try:
            mask_data, _ = io_utils.load_nifti_mask(mask_path)
            annotator.load_existing_mask(filename, mask_data)
            print(f"Máscara cargada: {mask_path.name}")
        except Exception as e:
            print(f"Error cargando máscara: {e}")

    pts_path = output_dir / f"{filename}_points.csv"
    if pts_path.exists():
        try:
            pts_data = io_utils.load_points_csv(pts_path)
            if pts_data.ndim == 1:
                pts_data = pts_data.reshape(1, -1)
            annotator.load_existing_points(filename, pts_data)
            print(f"Puntos cargados: {pts_path.name}")
        except Exception as e:
            print(f"Error cargando puntos: {e}")

    roi_path = output_dir / f"{filename}_rois.json"
    if roi_path.exists():
        try:
            shapes, types = io_utils.load_rois_json(roi_path)
            annotator.load_existing_rois(filename, shapes, types)
            print(f"ROIs cargados: {roi_path.name}")
        except Exception as e:
            print(f"Error cargando ROIs: {e}")


if __name__ == "__main__":
    start_viewer("ANONM0000002")