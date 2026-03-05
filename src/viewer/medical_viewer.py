import os
os.environ["QT_API"] = "pyside6"

import numpy as np
import napari
from PySide6.QtCore import QThread, QTimer, QObject, QEvent, Signal, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QMessageBox
from image_loader import ImageLoader
from annotation_manager import AnnotationManager
from save_service import SaveService, SaveRequest
import io_utils

import traceback
import warnings
warnings.filterwarnings("ignore", message=".*resource_tracker.*leaked semaphore.*")


class _SamWorker(QThread):
    """Worker que ejecuta SAM2 en segundo plano para no bloquear napari."""

    result_ready = Signal(object)   # emite np.ndarray bool 3D
    error = Signal(str)

    def __init__(self, assistant, volume: np.ndarray, slice_idx: int,
                 bbox_yx: tuple) -> None:
        super().__init__()
        self._assistant = assistant
        self.volume = volume
        self.slice_idx = slice_idx
        self.bbox_yx = bbox_yx

    def run(self) -> None:
        try:
            mask = self._assistant.segment_volume(
                self.volume, self.slice_idx, self.bbox_yx
            )
            self.result_ready.emit(mask)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.volume = None  # liberar memoria del volumen


def _get_active_image_layer(viewer):
    return next(
        (l for l in viewer.layers
         if isinstance(l, napari.layers.Image) and l.visible),
        None,
    )


def start_viewer(patient_id, base_dir=None):
    if base_dir is None:
        base_dir = os.environ.get("BASE_DIR", "/Volumes/HRAEPY")
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
    print("  [B] SAM2 — dibuja bbox → segmenta tumor en 3D automáticamente")
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
            if event.type() == QEvent.Type.Close:
                worker = _sam_state.get('worker')
                if worker is not None and worker.isRunning():
                    worker.wait(3000)
                if annotator.is_dirty():
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
        return _handler

    for key, cls in _CASE_LABELS.items():
        viewer.bind_key(key, _make_case_label_handler(cls))


    from sam_assistant import SAM2Assistant
    from napari.utils.colormaps import DirectLabelColormap

    _sam = SAM2Assistant()
    _sam_state: dict = {
        'bbox_layer': None,
        'proposal_layer': None,
        'worker': None,
        'transpose_mask': False,  # True si transpusimos (H,W,D)→(D,H,W) para SAM
    }

    def _sam_remove_layer(key: str) -> None:
        layer = _sam_state.get(key)
        if layer is not None:
            try:
                viewer.layers.remove(layer)
            except Exception:
                pass
            _sam_state[key] = None

    def _sam_cleanup() -> None:
        _sam_remove_layer('bbox_layer')
        _sam_remove_layer('proposal_layer')

    def _extract_bbox(bl) -> tuple | None:
        """Extrae (r0, c0, r1, c1) del último rectángulo. None si no es válido.

        napari almacena los vértices como (dim0, dim1, ..., dimN) donde:
          3D (H,W,D): col0=Y(rows), col1=X(cols), col2=Z(slice) ← ÚLTIMO es slider
          4D (T,H,W,D): col0=T, col1=Y, col2=X, col3=Z
        Los ejes MOSTRADOS son siempre los penúltimos dos (nd-3 y nd-2).
        El último eje (nd-1) es el slider/slice actual — NO coordenada espacial.
        """
        try:
            if len(bl.data) == 0:
                return None
            shape_data = bl.data[-1]
            if shape_data.shape[0] < 4:
                return None
            nd = shape_data.shape[1]
            # nd-3 = Y (rows), nd-2 = X (cols), nd-1 = Z slice (ignorar)
            y_coords = shape_data[:, nd - 3]
            x_coords = shape_data[:, nd - 2]
            r0, r1 = int(y_coords.min()), int(y_coords.max())
            c0, c1 = int(x_coords.min()), int(x_coords.max())
            return (r0, c0, r1, c1)
        except Exception:
            return None

    def _sam_launch_from_bbox() -> None:
        """Lee el rectángulo de la capa bbox y lanza el worker SAM2."""
        bl = _sam_state.get('bbox_layer')
        if bl is None:
            viewer.status = "Primero presiona [B] y dibuja un rectángulo."
            return

        bbox = _extract_bbox(bl)
        if bbox is None:
            viewer.status = "No hay rectángulo dibujado. Dibuja uno y presiona [Enter]."
            return

        r0, c0, r1, c1 = bbox
        if (r1 - r0) < 5 or (c1 - c0) < 5:
            viewer.status = "Rectángulo demasiado pequeño — dibuja uno más grande."
            return

        active_layer = _get_active_image_layer(viewer)
        if active_layer is None:
            viewer.status = "No hay imagen activa."
            _sam_cleanup()
            return

        try:
            data = active_layer.data
            ndim = data.ndim
            step = viewer.dims.current_step

            if ndim == 3:
                slice_idx = int(step[ndim - 1])
                volume = np.moveaxis(np.asarray(data), -1, 0)
                _sam_state['transpose_mask'] = True
            elif ndim == 4:
                slice_idx = int(step[ndim - 1])
                volume = np.moveaxis(np.asarray(data[int(step[0])]), -1, 0)
                _sam_state['transpose_mask'] = True
            else:
                viewer.status = f"Dimensiones {ndim}D no soportadas por SAM."
                _sam_cleanup()
                return

            viewer.status = "⏳ SAM2 procesando…"

            worker = _SamWorker(_sam, volume, slice_idx, (r0, c0, r1, c1))
            worker.result_ready.connect(_on_sam_result)
            worker.error.connect(_on_sam_error)
            _sam_state['worker'] = worker
            worker.start()

        except Exception as exc:
            print(f"[SAM2] Error: {exc}")
            viewer.status = f"SAM error: {exc}"
            _sam_cleanup()

    def _on_sam_result(mask_3d: np.ndarray) -> None:
        worker = _sam_state.get('worker')
        if worker is not None:
            worker.wait(2000)
            worker.deleteLater()
        _sam_state['worker'] = None
        _sam_remove_layer('bbox_layer')
        _sam_remove_layer('proposal_layer')

        if _sam_state.get('transpose_mask'):
            mask_3d = np.moveaxis(mask_3d, 0, -1)  # (D,H,W) → (H,W,D)
            _sam_state['transpose_mask'] = False

        true_count = int(mask_3d.sum())
        if true_count == 0:
            viewer.status = "SAM no detectó tumor en esa región. Intenta con otro rectángulo."
            return

        proposal = viewer.add_labels(
            mask_3d.astype(np.uint8),
            name="[SAM] Propuesta",
            opacity=0.55,
        )
        try:
            proposal.colormap = DirectLabelColormap(
                color_dict={0: [0, 0, 0, 0], 1: [0.0, 1.0, 1.0, 0.7],
                            None: [0, 0, 0, 0]}
            )
        except Exception:
            pass
        _sam_state['proposal_layer'] = proposal

        ann = annotator.get_active_annotations()
        label_val = 1
        label_name = "BENIGN"
        if ann is not None:
            label_val = ann['labels'].selected_label
            info = LABEL_MAP.get(label_val)
            label_name = info['name'].upper() if info else str(label_val)

        viewer.status = (
            f"SAM listo \u2713  |  Label: {label_val} ({label_name})  |  "
            f"[Enter] Aceptar  |  [Esc] Descartar  |  [+/-] Cambiar label"
        )

    def _on_sam_error(msg: str) -> None:
        worker = _sam_state.get('worker')
        if worker is not None:
            worker.wait(2000)
            worker.deleteLater()
        _sam_state['worker'] = None
        _sam_remove_layer('bbox_layer')
        viewer.status = f"SAM error: {msg}"
        print(f"[SAM2] Error: {msg}")

    def _sam_accept() -> None:
        """Acepta la propuesta y la escribe en la capa de labels."""
        prop = _sam_state.get('proposal_layer')
        if prop is None:
            return
        ann = annotator.get_active_annotations()
        if ann is None:
            viewer.status = "No hay capa de anotaci\u00f3n activa."
            _sam_remove_layer('proposal_layer')
            return

        try:
            labels_layer = ann['labels']
            label_val = labels_layer.selected_label

            mask = np.asarray(prop.data) > 0
            new_data = np.array(labels_layer.data)
            new_data[mask] = label_val

            # La propuesta se remueve ANTES de asignar datos para evitar
            # conflicto en el render loop con ambas capas activas.
            _sam_state['proposal_layer'] = None
            try:
                viewer.layers.remove(prop)
            except Exception:
                pass
            del prop, mask

            labels_layer.data = new_data
            del new_data

            annotator._dirty[annotator.active_filename]['labels'] = True
            annotator._has_mask_data[annotator.active_filename] = True

            info = LABEL_MAP.get(label_val)
            label_name = info['name'].upper() if info else str(label_val)
            viewer.status = f"\u2713 SAM aceptado \u2014 {label_name} (label {label_val}) | [S] Guardar"

        except Exception as exc:
            print(f"[SAM2] Error al aceptar propuesta: {exc}")
            traceback.print_exc()
            viewer.status = f"Error al aceptar: {exc}"
            _sam_remove_layer('proposal_layer')

    @viewer.bind_key('b')
    def start_sam_bbox(viewer_instance) -> None:
        """[B] Activar modo bbox SAM2."""
        if _sam_state.get('worker') is not None:
            viewer.status = "SAM ya está procesando, espera."
            return
        if _sam_state.get('proposal_layer') is not None:
            viewer.status = "Propuesta pendiente: [Enter] aceptar o [Esc] descartar."
            return
        _sam_remove_layer('bbox_layer')

        active_layer = _get_active_image_layer(viewer)
        if active_layer is None:
            viewer.status = "No hay imagen activa."
            return

        bbox_layer = viewer.add_shapes(
            name="[SAM] BBox",
            edge_color='yellow',
            face_color=[1.0, 1.0, 0.0, 0.08],
            edge_width=2,
            ndim=active_layer.data.ndim,
        )
        bbox_layer.mode = 'add_rectangle'
        _sam_state['bbox_layer'] = bbox_layer
        viewer.layers.selection.active = bbox_layer
        viewer.status = (
            "[SAM] Dibuja un rectángulo alrededor del tumor → "
            "luego presiona [Enter] para segmentar"
        )

    _qt_win = viewer.window._qt_window

    def _on_enter_shortcut() -> None:
        if _sam_state.get('worker') is not None:
            viewer.status = "SAM procesando, espera\u2026"
            return
        if _sam_state.get('proposal_layer') is not None:
            _sam_accept()
        elif _sam_state.get('bbox_layer') is not None:
            _sam_launch_from_bbox()

    def _on_escape_shortcut() -> None:
        if (
            _sam_state.get('proposal_layer') is not None
            or _sam_state.get('bbox_layer') is not None
        ):
            _sam_cleanup()
            viewer.status = "SAM descartado."

    _sc_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), _qt_win)
    _sc_enter.setContext(Qt.ShortcutContext.WindowShortcut)
    _sc_enter.activated.connect(_on_enter_shortcut)

    _sc_escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), _qt_win)
    _sc_escape.setContext(Qt.ShortcutContext.WindowShortcut)
    _sc_escape.activated.connect(_on_escape_shortcut)


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
        except Exception as e:
            print(f"Error cargando máscara: {e}")

    pts_path = _resolve_path(output_dir, filename, "_points.csv")
    if pts_path.exists():
        try:
            pts_data = io_utils.load_points_csv(pts_path)
            if pts_data.ndim == 1:
                pts_data = pts_data.reshape(1, -1)
            annotator.load_existing_points(filename, pts_data)
        except Exception as e:
            print(f"Error cargando puntos: {e}")

    roi_path = _resolve_path(output_dir, filename, "_rois.json")
    if roi_path.exists():
        try:
            shapes, types = io_utils.load_rois_json(roi_path)
            annotator.load_existing_rois(filename, shapes, types)
        except Exception as e:
            print(f"Error cargando ROIs: {e}")


if __name__ == "__main__":
    _env_pid = os.environ.get("_LAUNCH_PATIENT_ID")
    _env_base = os.environ.get("_LAUNCH_BASE_DIR")

    if _env_pid and _env_base:
        start_viewer(_env_pid, base_dir=_env_base)
    else:
        from patient_browser import select_patient

        choice = select_patient()
        if choice:
            patient_id, base_dir = choice
            start_viewer(patient_id, base_dir=base_dir)
        else:
            print("No se seleccionó ningún paciente.")