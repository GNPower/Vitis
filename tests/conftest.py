"""Shared pytest fixtures.

The tests here exercise only the Vitis-free logic (string/path/CMake helpers),
so they run on any machine without an AMD Vitis install.
"""

import pytest

import vitis_paths


@pytest.fixture(autouse=True)
def reset_vitis_root_cache():
    """get_vitis_root() memoizes its result in module globals, clear it around
    every test so mocked detections do not leak between tests."""
    vitis_paths._VITIS_ROOT = None
    vitis_paths._VITIS_VERSION = None
    yield
    vitis_paths._VITIS_ROOT = None
    vitis_paths._VITIS_VERSION = None
