"""Tests for the UserConfig.cmake settings that Do CREATE and Do UPDATE apply.

Both commands write an application config's [compiler] and [linker] keys with
vitis_cmake.apply_compiler_config() and apply_linker_config().
"""

import configparser
import re

import pytest

from vitis_application import VitisApplication
from vitis_cmake import apply_compiler_config, apply_linker_config
from vitis_update import ApplicationUpdater


# The set() lines of the UserConfig.cmake that Vitis 2024.1 generates for a new
# application component, with the template's default values and line layout.
TEMPLATE = '''\
set(USER_COMPILE_DEFINITIONS
""
)
set(USER_UNDEFINED_SYMBOLS
"__clang__"
)
set(USER_INCLUDE_DIRECTORIES
)
set(USER_COMPILE_WARNINGS_ALL -Wall)
set(USER_COMPILE_WARNINGS_EXTRA -Wextra)
set(USER_COMPILE_WARNINGS_AS_ERRORS )
set(USER_COMPILE_WARNINGS_CHECK_SYNTAX_ONLY )
set(USER_COMPILE_WARNINGS_PEDANTIC )
set(USER_COMPILE_WARNINGS_PEDANTIC_AS_ERRORS )
set(USER_COMPILE_WARNINGS_INHIBIT_ALL )
set(USER_COMPILE_OPTIMIZATION_LEVEL -O0)
set(USER_COMPILE_OPTIMIZATION_OTHER_FLAGS )
set(USER_COMPILE_DEBUG_LEVEL -g3)
set(USER_COMPILE_DEBUG_OTHER_FLAGS )
set(USER_COMPILE_VERBOSE )
set(USER_COMPILE_ANSI )
set(USER_COMPILE_OTHER_FLAGS )
set(USER_LINK_NO_START_FILES )
set(USER_LINK_NO_DEFAULT_LIBS )
set(USER_LINK_NO_STDLIB )
set(USER_LINK_OMIT_ALL_SYMBOL_INFO )
set(USER_LINK_LIBRARIES
)
set(USER_LINK_DIRECTORIES
)
set(USER_LINKER_SCRIPT "${CMAKE_SOURCE_DIR}/lscript.ld")
set(USER_LINK_OTHER_FLAGS
)
'''

COMPILER_CONFIG = """
[compiler]
compile_definitions = DEBUG, BOARD=2
undefined_symbols = __clang__, __linux__
include_directories = /inc/a,
                      /inc/b
optimization_level = Os
optimization_other_flags = -ffunction-sections -fdata-sections
debug_level = g2
debug_other_flags = -gdwarf-4
warnings_all = true
warnings_extra = false
warnings_as_errors = true
warnings_check_syntax_only = true
warnings_pedantic = true
warnings_pedantic_as_errors = true
warnings_inhibit_all = true
verbose = true
ansi = true
other_flags = -fno-common
"""

LINKER_CONFIG = """
[linker]
no_start_files = true
no_default_libs = true
no_stdlib = true
omit_all_symbol_info = true
libraries = m, mylib
link_directories = /lib/a,
                   /lib/b
linker_script = {linker_script}
other_flags = -Wl,--gc-sections
"""

LINKER_SCRIPT_TEXT = "/* custom linker script */"


def parse_config(text):
    """Parse config text the way vitis_paths.read_config() parses a .conf file."""
    config = configparser.ConfigParser(comment_prefixes=("#",))
    config.read_string(text)
    return config


def read_cmake_variable(path, name):
    """Return the value of set(<name> ...) in a CMake file, with whitespace collapsed."""
    match = re.search(rf"set\({name}\s+([^)]*)\)", path.read_text())
    assert match, f"set({name} ...) not found in {path}"
    return " ".join(match.group(1).split())


@pytest.fixture
def userconfig(tmp_path):
    """A fresh UserConfig.cmake in <tmp>/src, as Vitis generates it."""
    src = tmp_path / "src"
    src.mkdir()
    path = src / "UserConfig.cmake"
    path.write_text(TEMPLATE)
    return path


@pytest.fixture
def linker_script(tmp_path):
    path = tmp_path / "custom.ld"
    path.write_text(LINKER_SCRIPT_TEXT)
    return path


@pytest.mark.parametrize(
    "variable, expected",
    [
        ("USER_COMPILE_DEFINITIONS", '"DEBUG" "BOARD=2"'),
        ("USER_UNDEFINED_SYMBOLS", '"__clang__" "__linux__"'),
        ("USER_INCLUDE_DIRECTORIES", '"/inc/a" "/inc/b"'),
        ("USER_COMPILE_OPTIMIZATION_LEVEL", "-Os"),
        ("USER_COMPILE_OPTIMIZATION_OTHER_FLAGS", "-ffunction-sections -fdata-sections"),
        ("USER_COMPILE_DEBUG_LEVEL", "-g2"),
        ("USER_COMPILE_DEBUG_OTHER_FLAGS", "-gdwarf-4"),
        ("USER_COMPILE_WARNINGS_ALL", "-Wall"),
        ("USER_COMPILE_WARNINGS_EXTRA", ""),  # false clears the template's -Wextra
        ("USER_COMPILE_WARNINGS_AS_ERRORS", "-Werror"),
        ("USER_COMPILE_WARNINGS_CHECK_SYNTAX_ONLY", "-fsyntax-only"),
        ("USER_COMPILE_WARNINGS_PEDANTIC", "-pedantic"),
        ("USER_COMPILE_WARNINGS_PEDANTIC_AS_ERRORS", "-pedantic-errors"),
        ("USER_COMPILE_WARNINGS_INHIBIT_ALL", "-w"),
        ("USER_COMPILE_VERBOSE", "-v"),
        ("USER_COMPILE_ANSI", "-ansi"),
        ("USER_COMPILE_OTHER_FLAGS", "-fno-common"),
    ],
)
def test_apply_compiler_config(userconfig, variable, expected):
    apply_compiler_config(str(userconfig), parse_config(COMPILER_CONFIG))
    assert read_cmake_variable(userconfig, variable) == expected


@pytest.mark.parametrize(
    "variable, expected",
    [
        ("USER_LINK_NO_START_FILES", "-nostartfiles"),
        ("USER_LINK_NO_DEFAULT_LIBS", "-nodefaultlibs"),
        ("USER_LINK_NO_STDLIB", "-nostdlib"),
        ("USER_LINK_OMIT_ALL_SYMBOL_INFO", "-s"),
        ("USER_LINK_LIBRARIES", '"m" "mylib"'),
        ("USER_LINK_DIRECTORIES", '"/lib/a" "/lib/b"'),
        ("USER_LINKER_SCRIPT", '"${CMAKE_SOURCE_DIR}/lscript.ld"'),
        ("USER_LINK_OTHER_FLAGS", "-Wl,--gc-sections"),
    ],
)
def test_apply_linker_config(userconfig, linker_script, variable, expected):
    config = parse_config(LINKER_CONFIG.format(linker_script=linker_script.as_posix()))
    apply_linker_config(str(userconfig), config)
    assert read_cmake_variable(userconfig, variable) == expected


def test_linker_script_is_linked_next_to_userconfig(userconfig, linker_script):
    config = parse_config(LINKER_CONFIG.format(linker_script=linker_script.as_posix()))
    apply_linker_config(str(userconfig), config)
    # A symlink where the OS allows one, otherwise a copy
    assert (userconfig.parent / "lscript.ld").read_text() == LINKER_SCRIPT_TEXT


def test_absent_keys_leave_userconfig_unchanged(userconfig):
    config = parse_config("[compiler]\n[linker]\n")
    apply_compiler_config(str(userconfig), config)
    apply_linker_config(str(userconfig), config)
    assert userconfig.read_text() == TEMPLATE


def test_empty_compile_definitions_clear_earlier_ones(userconfig):
    apply_compiler_config(str(userconfig), parse_config("[compiler]\ncompile_definitions = QEMU_SIM\n"))
    assert read_cmake_variable(userconfig, "USER_COMPILE_DEFINITIONS") == '"QEMU_SIM"'

    apply_compiler_config(str(userconfig), parse_config("[compiler]\ncompile_definitions =\n"))
    assert read_cmake_variable(userconfig, "USER_COMPILE_DEFINITIONS") == ""


def test_update_writes_the_same_userconfig_as_create(tmp_path, linker_script):
    # Regression: UPDATE used to skip the *_other_flags keys, four of the seven
    # warning switches, verbose, ansi, the [linker] switches, [linker] other_flags
    # and USER_LINKER_SCRIPT, so it never wrote -Wl,--gc-sections.
    top = tmp_path / "Top"
    top.mkdir()
    conf = COMPILER_CONFIG + LINKER_CONFIG.format(linker_script=linker_script.as_posix())
    (top / "app.conf").write_text(conf)

    workspace = tmp_path / "Projects"
    for name in ("created", "updated"):
        src = workspace / name / "src"
        src.mkdir(parents=True)
        (src / "UserConfig.cmake").write_text(TEMPLATE)

    VitisApplication(client=None, name="created", description="", config_folder=str(top),
                     config="app", workspace_path=str(workspace)).configure()
    ApplicationUpdater(client=None, name="updated", config_folder=str(top),
                       config="app", workspace_path=str(workspace)).update()

    created = workspace / "created" / "src" / "UserConfig.cmake"
    updated = workspace / "updated" / "src" / "UserConfig.cmake"
    assert updated.read_text() == created.read_text()
    assert read_cmake_variable(updated, "USER_LINK_OTHER_FLAGS") == "-Wl,--gc-sections"
    assert read_cmake_variable(updated, "USER_COMPILE_OPTIMIZATION_OTHER_FLAGS") == \
        "-ffunction-sections -fdata-sections"
