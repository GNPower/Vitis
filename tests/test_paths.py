"""Unit tests for vitis_paths: Vitis detection, version checking, and library/driver
path resolution. All subprocess and filesystem access is mocked or uses tmp dirs,
so no AMD Vitis install is required."""

import subprocess

import pytest

import vitis_paths
from vitis_paths import (
    get_driver_path,
    get_library_path,
    get_vitis_root,
    normalize_path,
)


def test_normalize_path():
    assert normalize_path("a\\b\\c") == "a/b/c"
    assert normalize_path("a/b/c") == "a/b/c"


class _FakeProc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.returncode = 0


def _fake_which(cli_path):
    """Return a subprocess.run replacement that reports `cli_path` as the vitis CLI."""
    def run(cmd, capture_output, text, check):
        return _FakeProc(cli_path + "\n")
    return run


class TestGetVitisRoot:
    def test_xilinx_direct_layout(self, monkeypatch):
        # .../Xilinx/<version>/bin/vitis
        monkeypatch.setattr(subprocess, "run", _fake_which("/opt/Xilinx/2024.1/bin/vitis"))
        root, version = get_vitis_root()
        assert version == "2024.1"
        assert "Xilinx" in root and "2024.1" in root

    def test_xilinx_vitis_layout(self, monkeypatch):
        # .../Xilinx/Vitis/<version>/bin/vitis
        monkeypatch.setattr(subprocess, "run", _fake_which("/opt/Xilinx/Vitis/2024.1/bin/vitis"))
        root, version = get_vitis_root()
        assert version == "2024.1"
        assert "Vitis" in root and "2024.1" in root

    def test_newer_version_accepted(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_which("/opt/Xilinx/2025.1/bin/vitis"))
        _, version = get_vitis_root()
        assert version == "2025.1"

    def test_old_version_rejected(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_which("/opt/Xilinx/2023.2/bin/vitis"))
        with pytest.raises(RuntimeError, match="not supported"):
            get_vitis_root()

    def test_unparseable_version(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fake_which("/opt/Xilinx/nope/bin/vitis"))
        with pytest.raises(RuntimeError, match="Could not parse Vitis version"):
            get_vitis_root()

    def test_vitis_not_on_path(self, monkeypatch):
        def run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "which vitis")
        monkeypatch.setattr(subprocess, "run", run)
        with pytest.raises(RuntimeError, match="not found"):
            get_vitis_root()

    def test_result_is_cached(self, monkeypatch):
        calls = {"n": 0}

        def run(cmd, capture_output, text, check):
            calls["n"] += 1
            return _FakeProc("/opt/Xilinx/2024.1/bin/vitis\n")

        monkeypatch.setattr(subprocess, "run", run)
        get_vitis_root()
        get_vitis_root()
        assert calls["n"] == 1  # detection runs once, then memoized


class TestLibraryAndDriverPaths:
    def _fake_root(self, monkeypatch, root):
        monkeypatch.setattr(vitis_paths, "get_vitis_root", lambda: (str(root), "2024.1"))

    def test_library_found_in_thirdparty(self, tmp_path, monkeypatch):
        self._fake_root(monkeypatch, tmp_path)
        lib = tmp_path / "data" / "embeddedsw" / "ThirdParty" / "sw_services" / "openamp_v2023_2"
        lib.mkdir(parents=True)
        assert get_library_path("openamp", "v2023_2") == str(lib)

    def test_library_found_in_lib_bsp(self, tmp_path, monkeypatch):
        self._fake_root(monkeypatch, tmp_path)
        lib = tmp_path / "data" / "embeddedsw" / "lib" / "bsp" / "xilffs_v5_2"
        lib.mkdir(parents=True)
        assert get_library_path("xilffs", "v5_2") == str(lib)

    def test_library_missing_raises(self, tmp_path, monkeypatch):
        self._fake_root(monkeypatch, tmp_path)
        with pytest.raises(FileNotFoundError, match="not found"):
            get_library_path("does_not_exist", "v1_0")

    def test_driver_found(self, tmp_path, monkeypatch):
        self._fake_root(monkeypatch, tmp_path)
        drv = tmp_path / "data" / "embeddedsw" / "XilinxProcessorIPLib" / "drivers" / "ttcps_v3_19"
        drv.mkdir(parents=True)
        assert get_driver_path("ttcps", "v3_19") == str(drv)

    def test_driver_missing_raises(self, tmp_path, monkeypatch):
        self._fake_root(monkeypatch, tmp_path)
        with pytest.raises(FileNotFoundError, match="not found"):
            get_driver_path("does_not_exist", "v1_0")
