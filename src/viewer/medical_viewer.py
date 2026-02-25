import os
os.environ["QT_API"] = "pyside6"

import napari
from PySide6.QtCore import QTimer, QObject, QEvent
from PySide6.QtWidgets import QMessageBox
from image_loader import ImageLoader
from annotation_manager import AnnotationManager
from save_service import SaveService, SaveRequest
import io_utils


def _get_active_image_layer(viewer):
    return next(
        (l for l in viewer.layers
         if isinstance(l, napari.layers.Image) and l.visible),
        None,
    )


def start_viewer(patient_id, base_dir="/Volumes/HRAEPY"):
    base_path = io_utils.find_patient_path(patient_id, base_dir)

    if not base_path:
        print(f"No se encontro el paciente: {patient_id}")
        return

    viewer = napari.Viewer(title=f"Annotator - Patient: {patient_id}")

    loader = ImageLoader(base_path)
    images = loader.load_all_images()

    if not images:
        viewer.close()
        return

    for idx, image_info in enumerate(images):
        viewer.add_image(
            image_info['data'],
            name=image_info['name'],
            colormap=image_info['colormap'],
            contrast_limits=image_info['contrast_limits'],
            visible=(idx == 0),
            metadata={
                'filename': image_info['filename'],
                'affine': image_info['affine'],
                'voxel_spacing': image_info.get('voxel_spacing')
            }
        )

    annotator = AnnotationManager(viewer)
    output_dir = base_path / "ANNOTATIONS"
    output_dir.mkdir(exist_ok=True)
    manifest_path = output_dir / "manifest.json"

    manifest = io_utils.load_manifest(manifest_path, patient_id)

    saver = SaveService(manifest, manifest_path)

    def on_save_success(result):
        annotator.mark_saved()
        viewer.status = result.message
        print(result.detail)

    def on_save_error(result):
        viewer.status = result.message
        print(result.detail)

    saver.start(on_success=on_save_success, on_error=on_save_error)

    from schemas import LABEL_MAP, LabelClass
    guide_lines = []
    for lv, info in LABEL_MAP.items():
        if lv == 0:
            continue
        guide_lines.append(f"  Label {lv} = {info['name'].upper()}")
    guide_text = "\n".join(guide_lines)
    print("\n" + "=" * 40)
    print("  GUIA DE LABELS PARA ANOTACION")
    print("=" * 40)
    print(guide_text)
    print("=" * 40)
    print("  [S] Guardar  |  Cambiar label: +/-")
    print("  Clasificar CASO: Ctrl+1=Benigno | Ctrl+2=Maligno | Ctrl+3=Incierto")
    print("=" * 40 + "\n")
    viewer.status = "Pinta: 1=BENIGNO(verde) 2=MALIGNO(rojo) | Clasifica caso: Ctrl+1/2/3 | [S] Guardar"

    debounce_timer = QTimer()
    debounce_timer.setSingleShot(True)
    debounce_timer.setInterval(300)
    pending = {'filename': None, 'shape': None}

    def execute_switch():
        fn = pending['filename']
        shape = pending['shape']
        if fn and fn != annotator.active_filename:
            if annotator.is_dirty():
                old = annotator.active_filename or "?"
                print(f"\nCambios sin guardar en: {old}")
                print("    Regresa a esa imagen y presiona [S] para guardar.")
                viewer.status = f"Sin guardar: {old} — regresa y presiona [S]"

            if annotator.active_filename:
                for layer in viewer.layers:
                    if (
                        isinstance(layer, napari.layers.Image)
                        and layer.metadata.get('filename') == annotator.active_filename
                    ):
                        layer.visible = False
                        break

            first_time = fn not in annotator.annotations
            annotator.activate_for_image(fn, shape)
            if first_time:
                _load_existing_annotations(annotator, fn, output_dir)

    debounce_timer.timeout.connect(execute_switch)

    first_layer = _get_active_image_layer(viewer)
    if first_layer:
        annotator.activate_for_image(
            first_layer.metadata['filename'],
            first_layer.data.shape
        )
        _load_existing_annotations(
            annotator, first_layer.metadata['filename'], output_dir
        )

    def on_visibility_change(event):
        layer = event.source
        if not isinstance(layer, napari.layers.Image) or not layer.visible:
            return
        filename = layer.metadata.get('filename')
        if not filename or filename == annotator.active_filename:
            return
        pending['filename'] = filename
        pending['shape'] = layer.data.shape
        debounce_timer.start()

    for layer in viewer.layers:
        if isinstance(layer, napari.layers.Image):
            layer.events.visible.connect(on_visibility_change)

    @viewer.bind_key('s')
    def save_session(viewer_instance):
        active_layer = _get_active_image_layer(viewer)

        if not active_layer:
            viewer.status = "No hay imagen visible para asociar anotaciones."
            return

        if not annotator.is_dirty():
            viewer.status = "Sin cambios pendientes."
            return

        if saver.is_busy:
            viewer.status = "Guardado en progreso, espera..."
            return

        source_filename = active_layer.metadata['filename']
        affine = active_layer.metadata.get('affine')

        if annotator.active_filename != source_filename:
            annotator.activate_for_image(source_filename, active_layer.data.shape)

        data_to_save = {}

        stem = source_filename.replace('.nii.gz', '').replace('.nii', '')
        mask_path = output_dir / f"{stem}_mask.nii.gz"
        pts_path  = output_dir / f"{stem}_points.csv"
        roi_path  = output_dir / f"{stem}_rois.json"

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

        existing_on_disk = {}
        if mask_path.exists() and 'mask' not in data_to_save:
            existing_on_disk['mask'] = mask_path.name
        if pts_path.exists() and 'points' not in data_to_save:
            existing_on_disk['points'] = pts_path.name
        if roi_path.exists() and 'rois' not in data_to_save:
            existing_on_disk['rois'] = roi_path.name

        image_shape = list(active_layer.data.shape)

        voxel_spacing = active_layer.metadata.get('voxel_spacing')

        request = SaveRequest(
            source_filename=source_filename,
            data_to_save=data_to_save,
            existing_on_disk=existing_on_disk,
            patient_id=patient_id,
            output_dir=output_dir,
            affine=affine,
            image_shape=image_shape,
            voxel_spacing=voxel_spacing,
        )
        viewer.status = f"Guardando anotaciones para {source_filename}..."
        saver.submit(request)

    class _CloseGuard(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Close and annotator.is_dirty():
                reply = QMessageBox.question(
                    obj,
                    "Cambios sin guardar",
                    "Hay anotaciones sin guardar que se perderán.\n"
                    "¿Realmente deseas salir?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    event.ignore()
                    return True
            return False

    _CASE_LABELS = {
        'Control-1': LabelClass.BENIGN,
        'Control-2': LabelClass.MALIGNANT,
        'Control-3': LabelClass.UNCERTAIN,
    }

    def _make_case_label_handler(label_cls):
        def _handler(viewer_instance):
            fn = annotator.active_filename
            if not fn:
                viewer.status = "No hay imagen activa."
                return
            with saver._lock:
                m = saver.manifest
                if fn not in m.annotations:
                    viewer.status = "Guarda primero antes de clasificar el caso."
                    return
                m.annotations[fn].label = label_cls
                io_utils.save_manifest(m, manifest_path)
            viewer.status = f"Caso '{fn}' clasificado como: {label_cls.value.upper()}"
            print(f"[Clasificación] {fn} → {label_cls.value}")
        return _handler

    for key, cls in _CASE_LABELS.items():
        viewer.bind_key(key, _make_case_label_handler(cls))

    try:
        _guard = _CloseGuard()
        viewer.window._qt_window.installEventFilter(_guard)
    except Exception:
        pass

    napari.run()
    saver.stop()
    debounce_timer.stop()


def _resolve_path(output_dir, filename, suffix):
    """Devuelve la ruta correcta del artefacto, con compatibilidad hacia atrás."""
    stem = filename.replace('.nii.gz', '').replace('.nii', '')
    new_path = output_dir / f"{stem}{suffix}"
    if new_path.exists():
        return new_path
    old_path = output_dir / f"{filename}{suffix}"
    if old_path.exists():
        return old_path
    return new_path


def _load_existing_annotations(annotator, filename, output_dir):
    mask_path = _resolve_path(output_dir, filename, "_mask.nii.gz")
    if mask_path.exists():
        try:
            mask_data, _ = io_utils.load_nifti_mask(mask_path)
            annotator.load_existing_mask(filename, mask_data)
            print(f"Máscara cargada: {mask_path.name}")
        except Exception as e:
            print(f"Error cargando máscara: {e}")

    pts_path = _resolve_path(output_dir, filename, "_points.csv")
    if pts_path.exists():
        try:
            pts_data = io_utils.load_points_csv(pts_path)
            if pts_data.ndim == 1:
                pts_data = pts_data.reshape(1, -1)
            annotator.load_existing_points(filename, pts_data)
            print(f"Puntos cargados: {pts_path.name}")
        except Exception as e:
            print(f"Error cargando puntos: {e}")

    roi_path = _resolve_path(output_dir, filename, "_rois.json")
    if roi_path.exists():
        try:
            shapes, types = io_utils.load_rois_json(roi_path)
            annotator.load_existing_rois(filename, shapes, types)
            print(f"ROIs cargados: {roi_path.name}")
        except Exception as e:
            print(f"Error cargando ROIs: {e}")


if __name__ == "__main__":
    from patient_browser import select_patient

    choice = select_patient()
    if choice:
        patient_id, base_dir = choice
        start_viewer(patient_id, base_dir=base_dir)
    else:
        print("No se seleccionó ningún paciente.")