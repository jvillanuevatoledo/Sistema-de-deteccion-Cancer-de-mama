import numpy as np

class AnnotationManager:
    _LAYER_KEYS = ('labels', 'points', 'shapes')

    def __init__(self, viewer):
        self.viewer = viewer
        self.annotations: dict[str, dict] = {}
        self.active_filename: str | None = None
        self._dirty: dict[str, dict[str, bool]] = {}
        self._has_mask_data: dict[str, bool] = {}

    def activate_for_image(self, filename: str, reference_shape: tuple):
        if self.active_filename and self.active_filename in self.annotations:
            ann = self.annotations[self.active_filename]
            for key in self._LAYER_KEYS:
                if ann[key] is not None:
                    ann[key].visible = False

        self.active_filename = filename

        if filename in self.annotations:
            ann = self.annotations[filename]
            for key in self._LAYER_KEYS:
                if ann[key] is not None:
                    ann[key].visible = True
            return

        suffix = filename.replace('.nii.gz', '').replace('.nii', '').replace('.png', '')
        ndim = len(reference_shape)
        is_3d = ndim >= 3

        labels_layer = self.viewer.add_labels(
            np.zeros(reference_shape, dtype=np.uint16),
            name=f"Mask_{suffix}"
        )

        points_layer = self.viewer.add_points(
            name=f"Points_{suffix}",
            face_color='red',
            size=10,
            ndim=ndim
        )

        shapes_layer = self.viewer.add_shapes(
            name=f"ROI_{suffix}",
            edge_color='yellow',
            face_color='transparent',
            edge_width=3,
            ndim=ndim
        )

        self.annotations[filename] = {
            'labels': labels_layer,
            'points': points_layer,
            'shapes': shapes_layer,
            'is_3d': is_3d,
            'shape': reference_shape
        }
        
        self._dirty[filename] = {'labels': False, 'points': False, 'shapes': False}
        self._has_mask_data[filename] = False
        
        self._connect_dirty_events(filename)

    def _connect_dirty_events(self, filename: str):
        ann = self.annotations[filename]
        def _on_labels_change(event, fn=filename):
            self._dirty[fn]['labels'] = True
            
            self._has_mask_data[fn] = True

        labels_layer = ann['labels']
        labels_layer.events.set_data.connect(_on_labels_change)
        
        if hasattr(labels_layer.events, 'paint'):
            labels_layer.events.paint.connect(_on_labels_change)

        def _on_points_change(event, fn=filename):
            self._dirty[fn]['points'] = True

        ann['points'].events.data.connect(_on_points_change)

        def _on_shapes_change(event, fn=filename):
            self._dirty[fn]['shapes'] = True

        ann['shapes'].events.data.connect(_on_shapes_change)
    
    def get_active_annotations(self):
        if self.active_filename and self.active_filename in self.annotations:
            return self.annotations[self.active_filename]
        return None

    def has_segmentation_data(self):
        ann = self.get_active_annotations()
        if ann is None:
            return False
        
        if self._has_mask_data.get(self.active_filename, False):
            return True
        
        return False

    def has_points_data(self):
        ann = self.get_active_annotations()
        return ann is not None and len(ann['points'].data) > 0

    def has_roi_data(self):
        ann = self.get_active_annotations()
        return ann is not None and len(ann['shapes'].data) > 0

    def get_segmentation_data(self):
        return self.annotations[self.active_filename]['labels'].data

    def get_points_data(self):
        return self.annotations[self.active_filename]['points'].data

    def get_roi_data(self):
        layer = self.annotations[self.active_filename]['shapes']
        return layer.data, layer.shape_type
    
    def is_dirty(self, layer_key: str | None = None) -> bool:
        if self.active_filename not in self._dirty:
            return False
        d = self._dirty[self.active_filename]
        if layer_key:
            return d.get(layer_key, False)
        return any(d.values())

    def mark_saved(self, layer_key: str | None = None):
        if self.active_filename not in self._dirty:
            return
        if layer_key:
            self._dirty[self.active_filename][layer_key] = False
        else:
            self._dirty[self.active_filename] = {
                'labels': False, 'points': False, 'shapes': False
            }

    def load_existing_mask(self, filename, mask_data):
        if filename in self.annotations:
            self.annotations[filename]['labels'].data = mask_data
            self._has_mask_data[filename] = np.any(mask_data > 0)
            self._dirty.setdefault(filename, {'labels': False, 'points': False, 'shapes': False})
            self._dirty[filename]['labels'] = False

    def load_existing_points(self, filename, points_data):
        if filename in self.annotations:
            self.annotations[filename]['points'].data = points_data
            self._dirty.setdefault(filename, {'labels': False, 'points': False, 'shapes': False})
            self._dirty[filename]['points'] = False

    def load_existing_rois(self, filename, shapes_data, shape_types):
        if filename not in self.annotations:
            return
        layer = self.annotations[filename]['shapes']
        
        if shapes_data and shape_types:
            layer.add(shapes_data, shape_type=shape_types)
        self._dirty.setdefault(filename, {'labels': False, 'points': False, 'shapes': False})
        self._dirty[filename]['shapes'] = False