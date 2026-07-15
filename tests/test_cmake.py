"""Unit tests for vitis_cmake: the config-string, path, and CMake-file helpers."""

import pytest

from vitis_cmake import (
    bool_to_cmake_flag,
    create_symlink,
    edit_cmake_variable,
    expand_path_variables,
    format_debug_level,
    format_optimization_level,
    parse_multiline_paths,
    render_template,
)


class TestFormatOptimizationLevel:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("none", ""),
            ("", ""),
            ("None", ""),
            ("O0", "-O0"),
            ("O2", "-O2"),
            ("O3", "-O3"),
            ("2", "-O2"),
            ("0", "-O0"),
            ("-O2", "-O2"),
            ("-O0", "-O0"),
            ("  O2  ", "-O2"),
        ],
    )
    def test_levels(self, raw, expected):
        assert format_optimization_level(raw) == expected

    @pytest.mark.parametrize("raw", ["Os", "os", "OS", "-Os", "-os"])
    def test_size_optimization_never_uppercased(self, raw):
        # Regression guard: -Os was once emitted as -OS, which the ARM gcc
        # front end rejects. It must always normalize to exactly "-Os".
        assert format_optimization_level(raw) == "-Os"


class TestFormatDebugLevel:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("none", ""),
            ("", ""),
            ("g3", "-g3"),
            ("g1", "-g1"),
            ("3", "-g3"),
            ("-g3", "-g3"),
            ("  g2 ", "-g2"),
        ],
    )
    def test_levels(self, raw, expected):
        assert format_debug_level(raw) == expected


def test_bool_to_cmake_flag():
    assert bool_to_cmake_flag(True, "-Wall") == "-Wall"
    assert bool_to_cmake_flag(False, "-Wall") == ""


class TestParseMultilinePaths:
    def test_comma_separated(self):
        assert parse_multiline_paths("a,b,c") == ["a", "b", "c"]

    def test_newline_separated(self):
        assert parse_multiline_paths("a\nb\nc") == ["a", "b", "c"]

    def test_mixed_with_whitespace(self):
        assert parse_multiline_paths("a,\n  b ,\nc\n") == ["a", "b", "c"]

    def test_empty_and_blank(self):
        assert parse_multiline_paths("") == []
        assert parse_multiline_paths(" , ,\n\n") == []


class TestExpandPathVariables:
    def test_cmake_var_is_kept_literal(self):
        # ${CMAKE_*} must survive for CMake to evaluate, only slashes normalize.
        assert expand_path_variables("${CMAKE_SOURCE_DIR}/lscript.ld") == "${CMAKE_SOURCE_DIR}/lscript.ld"

    def test_xilinx_var_is_kept_literal(self):
        assert expand_path_variables("${XILINX_VITIS}/x") == "${XILINX_VITIS}/x"

    def test_project_dir_expands(self, monkeypatch):
        monkeypatch.setattr("vitis_cmake.get_workspace_root", lambda: "/ws")
        assert expand_path_variables("${PROJECT_DIR}/a") == "/ws/a"

    def test_parent_dir_expands(self, monkeypatch):
        monkeypatch.setattr("vitis_cmake.get_src_root", lambda: "/src")
        assert expand_path_variables("${PARENT_DIR}/a") == "/src/a"

    def test_vitis_install_dir_expands(self, monkeypatch):
        monkeypatch.setattr("vitis_cmake.get_vitis_install_dir", lambda: "/vitis")
        assert expand_path_variables("${VITIS_INSTALL_DIR}/inc") == "/vitis/inc"

    def test_backslashes_normalized(self):
        assert expand_path_variables("a\\b\\c") == "a/b/c"


def test_edit_cmake_variable_single_line(tmp_path):
    f = tmp_path / "UserConfig.cmake"
    f.write_text("set(USER_COMPILE_OPTIMIZATION_LEVEL -O0)\nset(OTHER keep_me)\n")
    edit_cmake_variable(str(f), "USER_COMPILE_OPTIMIZATION_LEVEL", "-O2")
    content = f.read_text()
    assert "set(USER_COMPILE_OPTIMIZATION_LEVEL -O2)" in content
    assert "set(OTHER keep_me)" in content  # other variables untouched


def test_edit_cmake_variable_multiline(tmp_path):
    f = tmp_path / "UserConfig.cmake"
    f.write_text('set(USER_INCLUDE_DIRECTORIES\n"old"\n)\n')
    edit_cmake_variable(str(f), "USER_INCLUDE_DIRECTORIES", '\n"a"\n"b"\n')
    content = f.read_text()
    assert '"a"' in content and '"b"' in content
    assert '"old"' not in content


def test_render_template(tmp_path):
    t = tmp_path / "launch.json.template"
    t.write_text('{"name": "{{config_name}}", "reset": {{reset_system}}}')
    out = render_template(str(t), {"config_name": "dbg", "reset_system": True})
    assert '"name": "dbg"' in out
    assert '"reset": true' in out  # Python bool lowered to JSON bool


def test_create_symlink_or_copy(tmp_path):
    # On Linux CI this is a symlink; on Windows without developer mode it falls
    # back to a copy. Either way the destination must exist afterwards.
    src = tmp_path / "src.c"
    src.write_text("int main(void) { return 0; }")
    link = tmp_path / "link.c"
    assert create_symlink(str(src), str(link)) is True
    assert link.exists()
