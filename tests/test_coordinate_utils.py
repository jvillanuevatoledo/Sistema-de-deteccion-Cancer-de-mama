import numpy as np

from coordinate_utils import array_to_world, world_to_array


class TestArrayToWorld:
    def test_identity_passthrough(self, identity_affine):
        coords = np.array([[1.0, 2.0, 3.0]])
        result = array_to_world(coords, identity_affine)
        np.testing.assert_array_almost_equal(result, coords)

    def test_scaling(self, scaled_affine):
        coords = np.array([[2.0, 4.0, 6.0]])
        result = array_to_world(coords, scaled_affine)
        expected = np.array([[11.0, 22.0, 33.0]])
        np.testing.assert_array_almost_equal(result, expected)

    def test_1d_input(self, identity_affine):
        coords = np.array([5.0, 6.0, 7.0])
        result = array_to_world(coords, identity_affine)
        np.testing.assert_array_almost_equal(result, [[5.0, 6.0, 7.0]])

    def test_2d_coords(self, identity_affine):
        coords = np.array([[10.0, 20.0]])
        result = array_to_world(coords, identity_affine)
        assert result.shape == (1, 2)
        np.testing.assert_array_almost_equal(result, [[10.0, 20.0]])

    def test_multiple_points(self, identity_affine):
        coords = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        result = array_to_world(coords, identity_affine)
        np.testing.assert_array_almost_equal(result, coords)


class TestWorldToArray:
    def test_identity_passthrough(self, identity_affine):
        coords = np.array([[1.0, 2.0, 3.0]])
        result = world_to_array(coords, identity_affine)
        np.testing.assert_array_almost_equal(result, coords)

    def test_inverse_of_scaling(self, scaled_affine):
        world = np.array([[11.0, 22.0, 33.0]])
        result = world_to_array(world, scaled_affine)
        expected = np.array([[2.0, 4.0, 6.0]])
        np.testing.assert_array_almost_equal(result, expected)

    def test_1d_input(self, identity_affine):
        coords = np.array([3.0, 4.0, 5.0])
        result = world_to_array(coords, identity_affine)
        np.testing.assert_array_almost_equal(result, [[3.0, 4.0, 5.0]])


class TestRoundTrip:
    def test_array_world_array(self, scaled_affine):
        original = np.array([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0]])
        world = array_to_world(original, scaled_affine)
        recovered = world_to_array(world, scaled_affine)
        np.testing.assert_array_almost_equal(recovered, original)

    def test_world_array_world(self, scaled_affine):
        original = np.array([[15.0, 25.0, 35.0]])
        arr = world_to_array(original, scaled_affine)
        recovered = array_to_world(arr, scaled_affine)
        np.testing.assert_array_almost_equal(recovered, original)

    def test_2d_roundtrip(self, scaled_affine):
        original = np.array([[5.0, 10.0]])
        world = array_to_world(original, scaled_affine)
        recovered = world_to_array(world, scaled_affine)
        np.testing.assert_array_almost_equal(recovered, original, decimal=5)
