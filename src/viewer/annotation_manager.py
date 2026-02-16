import numpy as np

class AnnotationManager:
    def __init__(self, viewer):
        self.viewer = viewer
        self.annotations = {}
        self.active_filename = None

    def activate_for_image(self, filename, reference_shape):
        if self.active_filename and self.active_filename in self.annotations:
            ann = self.annotations[self.active_filename]
            for key in ['labels', 'points', 'shapes']:
                if ann[key] is not None:
                    ann[key].visible = False

        self.active_filename = filename

        if filename in self.annotations:
            ann = self.annotations[filename]
            for key in ['labels', 'points', 'shapes']:
                if ann[key] is not None:
                    ann[key].visible = True
            return

        suffix = filename.replace('.nii.gz', '').replace('.nii', '').replace('.png', '')

        is_3d = len(reference_shape) >= 3

        labels_layer = self.viewer.add_labels(
            np.zeros(reference_shape, dtype=np.uint16),
            name=f"Mask_{suffix}"
        )

        points_layer = self.viewer.add_points(
            name=f"Points_{suffix}",
            face_color='red',
            size=10
        )

        shapes_layer = self.viewer.add_shapes(
            name=f"ROI_{suffix}",
            edge_color='yellow',
            face_color='transparent',
            edge_width=3
        )

        self.annotations[filename] = {
            'labels': labels_layer,
            'points': points_layer,
            'shapes': shapes_layer,
            'is_3d': is_3d,
            'shape': reference_shape
        }

    def get_active_annotations(self):
        if self.active_filename and self.active_filename in self.annotations:
            return self.annotations[self.active_filename]
        return None

    def has_segmentation_data(self):
        ann = self.get_active_annotations()
        return ann is not None and np.any(ann['labels'].data > 0)

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

    def load_existing_mask(self, filename, mask_data):
        if filename in self.annotations:
            self.annotations[filename]['labels'].data = mask_data

    def load_existing_points(self, filename, points_data):
        if filename in self.annotations:
            self.annotations[filename]['points'].data = points_data

    def load_existing_rois(self, filename, shapes_data, shape_types):
        if filename in self.annotations:
            layer = self.annotations[filename]['shapes']
            layer.data = []
            for shape, shape_type in zip(shapes_data, shape_types):
                layer.add(shape, shape_type=shape_type)