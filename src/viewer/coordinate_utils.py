import numpy as np


def array_to_world(coords: np.ndarray, affine: np.ndarray) -> np.ndarray:
    if coords.ndim == 1:
        coords = coords.reshape(1, -1)
    n = coords.shape[0]
    dim = coords.shape[1]

    if dim < 3:
        padded = np.zeros((n, 3))
        padded[:, :dim] = coords
    else:
        padded = coords[:, :3]

    homogeneous = np.hstack([padded, np.ones((n, 1))])
    world = (affine @ homogeneous.T).T
    return world[:, :dim]


def world_to_array(coords: np.ndarray, affine: np.ndarray) -> np.ndarray:
    if coords.ndim == 1:
        coords = coords.reshape(1, -1)
    n = coords.shape[0]
    dim = coords.shape[1]
    inv_affine = np.linalg.inv(affine)

    if dim < 3:
        padded = np.zeros((n, 3))
        padded[:, :dim] = coords
    else:
        padded = coords[:, :3]

    homogeneous = np.hstack([padded, np.ones((n, 1))])
    array_coords = (inv_affine @ homogeneous.T).T
    return array_coords[:, :dim]
