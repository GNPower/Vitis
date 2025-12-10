import argparse
import configparser
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from typing import List, TypeVar, Dict, Any

# Add package: Vitis Python CLI
# import vitis # type: ignore
vitis_client = TypeVar('vitis_client')

from vitis_logging import Logger
from vitis_paths import (
    read_config, parentdir, PROJECTS_PATH, HDL_DATA_PATH,
    get_vitis_install_dir, get_workspace_root, get_src_root, normalize_path
)


log = Logger("application")

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates")


def _edit_cmake_variable(file_path: str, variable_name: str, new_value: str) -> None:
    """
    Edit a CMake variable in UserConfig.cmake.

    Args:
        file_path: Path to UserConfig.cmake
        variable_name: Variable name (e.g., 'USER_COMPILE_OPTIMIZATION_LEVEL')
        new_value: New value to set
    """
    with open(file_path, 'r') as f:
        content = f.read()

    # Pattern to match: set(VARIABLE_NAME value)
    # Handles both single line and multi-line values
    pattern = rf'(set\({variable_name}\s+)([^\)]*)\)'

    replacement = rf'\g<1>{new_value})'
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

    with open(file_path, 'w') as f:
        f.write(new_content)


def _parse_multiline_paths(config_value: str) -> List[str]:
    """
    Parse multi-line, comma-separated path list.
    Supports mixed format: paths separated by newlines and/or commas.

    Args:
        config_value: Raw config value (may contain newlines and commas)

    Returns:
        List of cleaned, non-empty path strings
    """
    paths = [p.strip() for p in config_value.replace('\n', ',').split(',') if p.strip()]
    return paths


def _expand_path_variables(path: str) -> str:
    """
    Expand custom variables in path string.
    CMake variables (like ${CMAKE_SOURCE_DIR}) are kept literal for CMake evaluation.

    Supported custom variables:
    - ${VITIS_INSTALL_DIR} -> Vitis installation root
    - ${PROJECT_DIR} -> Workspace root
    - ${PARENT_DIR} -> Source root

    Args:
        path: Path potentially containing variables

    Returns:
        Path with custom variables expanded, forward slashes
    """
    expanded = path

    cmake_var_pattern = r'\$\{(CMAKE_|XILINX_)'
    if re.search(cmake_var_pattern, path):
        return normalize_path(path)

    if '${VITIS_INSTALL_DIR}' in expanded:
        expanded = expanded.replace('${VITIS_INSTALL_DIR}', get_vitis_install_dir())

    if '${PROJECT_DIR}' in expanded:
        expanded = expanded.replace('${PROJECT_DIR}', get_workspace_root())

    if '${PARENT_DIR}' in expanded:
        expanded = expanded.replace('${PARENT_DIR}', get_src_root())

    return normalize_path(expanded)


def _create_symlink(src_path: str, link_path: str) -> bool:
    """
    Create a symbolic link, with fallback to copy on Windows if permissions insufficient.

    Args:
        src_path: Source file path (must exist)
        link_path: Symlink path to create

    Returns:
        True if symlink/copy created successfully, False otherwise
    """
    try:
        if os.path.exists(link_path) or os.path.islink(link_path):
            log.debug(f"Symlink already exists: {link_path}")
            return True

        if not os.path.exists(src_path):
            log.warning(f"Source file does not exist: {src_path}")
            return False

        if platform.system() == 'Windows':
            try:
                # On Windows, try creating symlink (requires admin or developer mode)
                os.symlink(src_path, link_path)
                log.info(f"Created symlink: {os.path.basename(link_path)} -> {src_path}")
                return True
            except OSError:
                # Fallback to copy if symlink fails (permission issues)
                shutil.copy2(src_path, link_path)
                log.info(f"Created copy (symlink failed): {os.path.basename(link_path)} -> {src_path}")
                return True
        else:
            os.symlink(src_path, link_path)
            log.info(f"Created symlink: {os.path.basename(link_path)} -> {src_path}")
            return True

    except Exception as e:
        log.warning(f"Failed to create symlink {link_path}: {e}")
        return False


def _find_source_files_recursively(folder: str, extensions: List[str] = ['.c', '.S']) -> List[str]:
    """
    Recursively find source files in folder with given extensions.

    Args:
        folder: Directory to search recursively
        extensions: List of file extensions to include (default: ['.c', '.S'])

    Returns:
        List of absolute file paths matching the extensions
    """
    source_files = []

    if not os.path.exists(folder):
        log.warning(f"Folder does not exist: {folder}")
        return source_files

    if not os.path.isdir(folder):
        log.warning(f"Path is not a directory: {folder}")
        return source_files

    for root, dirs, files in os.walk(folder):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                source_files.append(os.path.join(root, file))

    log.debug(f"Found {len(source_files)} source files in {folder}")
    return source_files


def _create_folder_symlink(src_folder: str, link_name: str, project_src_dir: str) -> bool:
    """
    Create folder symlink with fallback to directory recreation.

    Tries to create a folder symlink first (preserves directory structure).
    If that fails (Windows permissions), falls back to recreating the directory
    structure with individual file symlinks.

    Args:
        src_folder: Source directory path (absolute)
        link_name: Name for the symlinked folder in project (basename only)
        project_src_dir: Project's src/ directory where symlink will be created

    Returns:
        True if successful, False otherwise
    """
    try:
        link_path = os.path.join(project_src_dir, link_name)

        if os.path.exists(link_path) or os.path.islink(link_path):
            log.debug(f"Folder symlink already exists: {link_path}")
            return True

        if not os.path.exists(src_folder):
            log.warning(f"Source folder does not exist: {src_folder}")
            return False

        if not os.path.isdir(src_folder):
            log.warning(f"Source path is not a directory: {src_folder}")
            return False

        try:
            os.symlink(src_folder, link_path, target_is_directory=True)
            log.info(f"Created folder symlink: {link_name}/ -> {src_folder}")
            return True

        except OSError as symlink_error:
            log.debug(f"Folder symlink failed ({symlink_error}), recreating directory structure")

            os.makedirs(link_path, exist_ok=True)

            file_count = 0
            for root, dirs, files in os.walk(src_folder):
                rel_path = os.path.relpath(root, src_folder)

                if rel_path == '.':
                    dest_dir = link_path
                else:
                    dest_dir = os.path.join(link_path, rel_path)
                    os.makedirs(dest_dir, exist_ok=True)

                for file in files:
                    if file.endswith(('.c', '.S')):
                        src_file = os.path.join(root, file)
                        dest_file = os.path.join(dest_dir, file)

                        if _create_symlink(src_file, dest_file):
                            file_count += 1

            log.info(f"Created directory structure for {link_name}/ with {file_count} file symlinks")
            return True

    except Exception as e:
        log.warning(f"Failed to create folder symlink {link_name}/: {e}")
        return False


def _bool_to_cmake_flag(enabled: bool, flag: str) -> str:
    """Convert boolean to CMake flag or empty string."""
    return flag if enabled else ""


def _format_optimization_level(level: str) -> str:
    """
    Convert optimization level string to compiler flag.

    Args:
        level: Optimization level (none, O1, O2, O3, Os)

    Returns:
        Compiler flag (-O0, -O1, -O2, -O3, -Os) or empty string for none
    """
    level = level.strip().lower()
    if level == "none" or not level:
        return ""
    elif level.startswith("-"):
        return level
    elif level.startswith("o"):
        return f"-{level.upper()}"
    else:
        return f"-O{level}"


def _format_debug_level(level: str) -> str:
    """
    Convert debug level string to compiler flag.

    Args:
        level: Debug level (none, g1, g2, g3)

    Returns:
        Compiler flag (-g1, -g2, -g3) or empty string for none
    """
    level = level.strip().lower()
    if level == "none" or not level:
        return ""
    elif level.startswith("-"):
        return level
    elif level.startswith("g"):
        return f"-{level}"
    else:
        return f"-g{level}"


def _render_template(template_path: str, context: Dict[str, Any]) -> str:
    """
    Render a template file with {{placeholder}} replacements.

    Args:
        template_path: Path to template file
        context: Dictionary of placeholder -> value mappings

    Returns:
        Rendered content
    """
    with open(template_path, 'r') as f:
        content = f.read()

    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        if isinstance(value, bool):
            value = str(value).lower()
        content = content.replace(placeholder, str(value))

    return content


class VitisDebugConfig(object):
    """Represents a single debug/launch configuration."""

    def __init__(self, client: vitis_client, app_name: str, platform_name: str, workspace_path: str, # pyright: ignore[reportInvalidTypeVarUse]
                 name: str, display_name: str, config: configparser.ConfigParser):
        self.__client = client
        self.__app_name = app_name
        self.__platform_name = platform_name
        self.__workspace_path = workspace_path
        self.__name = name
        self.__display_name = display_name
        self.__config = config

    def generate_launch_config(self) -> Dict[str, Any]:
        """
        Generate a launch.json configuration entry.

        Returns:
            Dictionary representing the launch configuration
        """
        log.info(f"Generating launch configuration: {self.__name}")

        config_name = self.__config.get("launch", "name", fallback=f"{self.__app_name}_{self.__name}")
        debug_type = self.__config.get("launch", "debug_type", fallback="baremetal-zynq")
        target_core = self.__config.get("target", "core", fallback="ps7_cortexa9_0")
        context = self.__config.get("target", "context", fallback="zynq")

        bitstream = self.__config.get("hardware", "bitstream", fallback="")
        if not bitstream:
            # Auto-detect: ${workspace}/${app_name}/_ide/bitstream/*.bit
            bitstream_dir = os.path.join(self.__workspace_path, self.__app_name, "_ide", "bitstream")
            if os.path.exists(bitstream_dir):
                bit_files = [f for f in os.listdir(bitstream_dir) if f.endswith('.bit')]
                if bit_files:
                    bitstream = f"${{workspaceFolder}}/{self.__app_name}/_ide/bitstream/{bit_files[0]}"

        fsbl = self.__config.get("hardware", "fsbl", fallback="")
        if not fsbl:
            # Auto-detect: ${workspace}/${platform}/export/${platform}/sw/boot/fsbl.elf
            fsbl = f"${{workspaceFolder}}/{self.__platform_name}_platform/export/{self.__platform_name}_platform/sw/boot/fsbl.elf"

        ps_init_tcl = self.__config.get("hardware", "ps_init_tcl", fallback="")
        if not ps_init_tcl:
            # Auto-detect: ${workspace}/${app_name}/_ide/psinit/ps7_init.tcl
            ps_init_tcl = f"${{workspaceFolder}}/{self.__app_name}/_ide/psinit/ps7_init.tcl"

        elf_file = f"${{workspaceFolder}}/{self.__app_name}/build/{self.__app_name}.elf"

        reset_system = self.__config.getboolean("behavior", "reset_system", fallback=True)
        program_device = self.__config.getboolean("behavior", "program_device", fallback=True)
        reset_apu = self.__config.getboolean("behavior", "reset_apu", fallback=False)
        stop_at_entry = self.__config.getboolean("behavior", "stop_at_entry", fallback=False)
        reset_processor = self.__config.getboolean("behavior", "reset_processor", fallback=True)

        context = {
            "config_name": config_name,
            "debug_type": debug_type,
            "context": context,
            "reset_system": reset_system,
            "program_device": program_device,
            "reset_apu": reset_apu,
            "bitstream_file": bitstream,
            "fsbl_file": fsbl,
            "ps_init_tcl": ps_init_tcl,
            "target_core": target_core,
            "reset_processor": reset_processor,
            "elf_file": elf_file,
            "stop_at_entry": stop_at_entry,
        }

        template_path = os.path.join(TEMPLATES_PATH, "launch.json.template")
        rendered = _render_template(template_path, context)

        template_data = json.loads(rendered)
        return template_data["configurations"][0]


class VitisApplication(object):
    """Represents a Vitis application component with compiler, linker, and debug configurations."""

    def __init__(self, client: vitis_client, name: str, description: str, config_folder: str, # pyright: ignore[reportInvalidTypeVarUse]
                 config: str, workspace_path: str):
        log.info(f"Defining an Application Component with name {name}")
        self.__client = client
        self.__name = name
        self.__description = description
        self.__config_folder = config_folder
        self.__config = read_config(config_folder, config)
        self.__workspace_path = workspace_path
        self.__application = None
        self.__launch_configs: List[VitisDebugConfig] = []

        self.__add_launch_configs()

    def __add_launch_configs(self) -> None:
        """Parse and add all launch configurations from config."""
        if self.__config.has_section("launch"):
            self.__add_launch_config(
                self.__config.get("launch", "NAME"),
                self.__config.get("launch", "DISPLAY_NAME"),
                read_config(self.__config_folder, self.__config.get("launch", "CONFIG")),
            )

        # Add all additional launch configs ([launch_1], [launch_2], etc.)
        additional_launches = [s for s in self.__config.sections() if re.match(r"launch_\d+", s)]
        for section in sorted(additional_launches):
            self.__add_launch_config(
                self.__config.get(section, "NAME"),
                self.__config.get(section, "DISPLAY_NAME"),
                read_config(self.__config_folder, self.__config.get(section, "CONFIG")),
            )

    def __add_launch_config(self, name: str, display_name: str, config: configparser.ConfigParser) -> None:
        """Add a launch configuration."""
        platform_name = self.__config.get("application", "PLATFORM")
        new_config = VitisDebugConfig(
            client=self.__client,
            app_name=self.__name,
            platform_name=platform_name,
            workspace_path=self.__workspace_path,
            name=name,
            display_name=display_name,
            config=config,
        )
        self.__launch_configs.append(new_config)

    def create(self) -> None:
        """Create the application component via Vitis API."""
        log.info(f"Attempting to create application component {self.__name}")

        platform_name = self.__config.get("application", "PLATFORM")
        domain_name = self.__config.get("application", "DOMAIN")
        template = self.__config.get("application", "TEMPLATE", fallback="")

        platform_path = os.path.join(
            self.__workspace_path,
            f"{platform_name}_platform",
            "export",
            f"{platform_name}_platform",
            f"{platform_name}_platform.xpfm"
        )

        log.debug(f"Using platform: {platform_path}")
        log.debug(f"Targeting domain: {domain_name}")

        # If template is empty/not specified, create bare application (no template parameter)
        if template:
            log.debug(f"Using template: {template}")
            self.__application = self.__client.create_app_component( # type: ignore
                name=self.__name,
                platform=platform_path,
                domain=domain_name,
                template=template
            )
        else:
            log.debug("Creating empty application (no template)")
            self.__application = self.__client.create_app_component( # type: ignore
                name=self.__name,
                platform=platform_path,
                domain=domain_name
            )

        log.info(f"Application component {self.__name} created successfully")

    def configure(self) -> None:
        """Configure the application's UserConfig.cmake and launch.json."""
        log.info(f"Configuring application {self.__name}")

        self.__configure_compiler()
        self.__configure_sources()
        self.__configure_cmake()
        self.__configure_linker()
        self.__configure_launch()

    def __configure_compiler(self) -> None:
        """Configure compiler settings in UserConfig.cmake."""
        log.debug("Configuring compiler settings")

        userconfig_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "src",
            "UserConfig.cmake"
        )

        if not os.path.exists(userconfig_path):
            log.warning(f"UserConfig.cmake not found at {userconfig_path}, skipping compiler configuration")
            return

        # Symbols
        if self.__config.has_option("compiler", "compile_definitions"):
            defined = self.__config.get("compiler", "compile_definitions").strip()
            if defined:
                symbols = [s.strip() for s in defined.split(',')]
                value = '\n'.join(f'"{s}"' for s in symbols)
                _edit_cmake_variable(userconfig_path, "USER_COMPILE_DEFINITIONS", f"\n{value}\n")

        if self.__config.has_option("compiler", "undefined_symbols"):
            undefined = self.__config.get("compiler", "undefined_symbols").strip()
            if undefined:
                symbols = [s.strip() for s in undefined.split(',')]
                value = '\n'.join(f'"{s}"' for s in symbols)
                _edit_cmake_variable(userconfig_path, "USER_UNDEFINED_SYMBOLS", f"\n{value}\n")

        # Directories
        if self.__config.has_option("compiler", "include_directories"):
            includes = self.__config.get("compiler", "include_directories").strip()
            if includes:
                paths = _parse_multiline_paths(includes)
                expanded_paths = [_expand_path_variables(p) for p in paths]
                value = '\n'.join(f'"{p}"' for p in expanded_paths)
                _edit_cmake_variable(userconfig_path, "USER_INCLUDE_DIRECTORIES", f"\n{value}\n")

        # Optimization
        if self.__config.has_option("compiler", "optimization_level"):
            level = self.__config.get("compiler", "optimization_level")
            formatted_level = _format_optimization_level(level)
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_OPTIMIZATION_LEVEL", formatted_level)

        if self.__config.has_option("compiler", "optimization_other_flags"):
            flags = self.__config.get("compiler", "optimization_other_flags")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_OPTIMIZATION_OTHER_FLAGS", flags)

        # Debugging
        if self.__config.has_option("compiler", "debug_level"):
            level = self.__config.get("compiler", "debug_level")
            formatted_level = _format_debug_level(level)
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_DEBUG_LEVEL", formatted_level)

        if self.__config.has_option("compiler", "debug_other_flags"):
            flags = self.__config.get("compiler", "debug_other_flags")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_DEBUG_OTHER_FLAGS", flags)

        # Warnings
        if self.__config.has_option("compiler", "warnings_all"):
            enabled = self.__config.getboolean("compiler", "warnings_all")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_ALL",
                               _bool_to_cmake_flag(enabled, "-Wall"))

        if self.__config.has_option("compiler", "warnings_extra"):
            enabled = self.__config.getboolean("compiler", "warnings_extra")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_EXTRA",
                               _bool_to_cmake_flag(enabled, "-Wextra"))

        if self.__config.has_option("compiler", "warnings_as_errors"):
            enabled = self.__config.getboolean("compiler", "warnings_as_errors")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_AS_ERRORS",
                               _bool_to_cmake_flag(enabled, "-Werror"))

        if self.__config.has_option("compiler", "warnings_check_syntax_only"):
            enabled = self.__config.getboolean("compiler", "warnings_check_syntax_only")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_CHECK_SYNTAX_ONLY",
                               _bool_to_cmake_flag(enabled, "-fsyntax-only"))

        if self.__config.has_option("compiler", "warnings_pedantic"):
            enabled = self.__config.getboolean("compiler", "warnings_pedantic")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_PEDANTIC",
                               _bool_to_cmake_flag(enabled, "-pedantic"))

        if self.__config.has_option("compiler", "warnings_pedantic_as_errors"):
            enabled = self.__config.getboolean("compiler", "warnings_pedantic_as_errors")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_PEDANTIC_AS_ERRORS",
                               _bool_to_cmake_flag(enabled, "-pedantic-errors"))

        if self.__config.has_option("compiler", "warnings_inhibit_all"):
            enabled = self.__config.getboolean("compiler", "warnings_inhibit_all")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_INHIBIT_ALL",
                               _bool_to_cmake_flag(enabled, "-w"))

        # Misc
        if self.__config.has_option("compiler", "verbose"):
            enabled = self.__config.getboolean("compiler", "verbose")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_VERBOSE",
                               _bool_to_cmake_flag(enabled, "-v"))

        if self.__config.has_option("compiler", "ansi"):
            enabled = self.__config.getboolean("compiler", "ansi")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_ANSI",
                               _bool_to_cmake_flag(enabled, "-ansi"))

        if self.__config.has_option("compiler", "other_flags"):
            flags = self.__config.get("compiler", "other_flags")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_OTHER_FLAGS", flags)

        log.debug("Compiler settings configured successfully")

    def __configure_sources(self) -> None:
        """Configure source files in UserConfig.cmake."""
        log.debug("Configuring source files")

        userconfig_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "src",
            "UserConfig.cmake"
        )

        if not os.path.exists(userconfig_path):
            log.warning(f"UserConfig.cmake not found at {userconfig_path}, skipping source configuration")
            return

        # Source files
        if self.__config.has_option("compiler", "source_files"):
            sources = self.__config.get("compiler", "source_files").strip()
            if sources:
                source_list = _parse_multiline_paths(sources)
                expanded_sources = [_expand_path_variables(s) for s in source_list]

                # These will be found by aux_source_directory() automatically
                project_src_dir = os.path.join(
                    self.__workspace_path,
                    self.__name,
                    "src"
                )

                if os.path.exists(project_src_dir):
                    log.debug(f"Creating symlinks in {project_src_dir} for Vitis IDE")
                    for source_file in expanded_sources:
                        filename = os.path.basename(source_file)
                        symlink_path = os.path.join(project_src_dir, filename)
                        _create_symlink(source_file, symlink_path)
                else:
                    log.warning(f"Project src directory not found: {project_src_dir}")

        # Source folders - recursively include all .c and .S files
        if self.__config.has_option("compiler", "source_folders"):
            folders = self.__config.get("compiler", "source_folders").strip()
            if folders:
                folder_list = _parse_multiline_paths(folders)
                expanded_folders = [_expand_path_variables(f) for f in folder_list]

                project_src_dir = os.path.join(
                    self.__workspace_path,
                    self.__name,
                    "src"
                )

                if os.path.exists(project_src_dir):
                    log.debug(f"Processing source folders for {project_src_dir}")
                    for folder_path in expanded_folders:
                        if not os.path.exists(folder_path):
                            log.warning(f"Source folder does not exist: {folder_path}")
                            continue

                        if not os.path.isdir(folder_path):
                            log.warning(f"Source folder path is not a directory: {folder_path}")
                            continue

                        folder_name = os.path.basename(folder_path)

                        _create_folder_symlink(folder_path, folder_name, project_src_dir)
                else:
                    log.warning(f"Project src directory not found: {project_src_dir}")

        log.debug("Source files configured successfully")

    def __configure_cmake(self) -> None:
        """Modify CMakeLists.txt to use recursive source discovery.

        Replaces aux_source_directory() with file(GLOB_RECURSE ...) to find
        source files in subdirectories.
        """
        log.debug("Configuring CMakeLists.txt for recursive source discovery")

        cmake_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "src",
            "CMakeLists.txt"
        )

        if not os.path.exists(cmake_path):
            log.warning(f"CMakeLists.txt not found at {cmake_path}, skipping CMake configuration")
            return

        with open(cmake_path, 'r') as f:
            content = f.read()

        old_pattern = r'aux_source_directory\(\$\{CMAKE_SOURCE_DIR\}\s+_sources\)'
        new_code = '''file(GLOB_RECURSE _sources
    FOLLOW_SYMLINKS
    ${CMAKE_SOURCE_DIR}/*.c
    ${CMAKE_SOURCE_DIR}/*.S
)'''

        new_content = re.sub(old_pattern, new_code, content)

        if new_content == content:
            log.debug("CMakeLists.txt already configured or pattern not found")
            return

        with open(cmake_path, 'w') as f:
            f.write(new_content)

        log.info("CMakeLists.txt modified to use recursive source discovery (GLOB_RECURSE)")

    def __configure_linker(self) -> None:
        """Configure linker settings in UserConfig.cmake."""
        log.debug("Configuring linker settings")

        userconfig_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "src",
            "UserConfig.cmake"
        )

        if not os.path.exists(userconfig_path):
            log.warning(f"UserConfig.cmake not found at {userconfig_path}, skipping linker configuration")
            return

        # General linker options
        if self.__config.has_option("linker", "no_start_files"):
            enabled = self.__config.getboolean("linker", "no_start_files")
            _edit_cmake_variable(userconfig_path, "USER_LINK_NO_START_FILES",
                               _bool_to_cmake_flag(enabled, "-nostartfiles"))

        if self.__config.has_option("linker", "no_default_libs"):
            enabled = self.__config.getboolean("linker", "no_default_libs")
            _edit_cmake_variable(userconfig_path, "USER_LINK_NO_DEFAULT_LIBS",
                               _bool_to_cmake_flag(enabled, "-nodefaultlibs"))

        if self.__config.has_option("linker", "no_stdlib"):
            enabled = self.__config.getboolean("linker", "no_stdlib")
            _edit_cmake_variable(userconfig_path, "USER_LINK_NO_STDLIB",
                               _bool_to_cmake_flag(enabled, "-nostdlib"))

        if self.__config.has_option("linker", "omit_all_symbol_info"):
            enabled = self.__config.getboolean("linker", "omit_all_symbol_info")
            _edit_cmake_variable(userconfig_path, "USER_LINK_OMIT_ALL_SYMBOL_INFO",
                               _bool_to_cmake_flag(enabled, "-s"))

        # Libraries
        if self.__config.has_option("linker", "libraries"):
            libs = self.__config.get("linker", "libraries").strip()
            if libs:
                lib_list = [l.strip() for l in libs.split(',')]
                value = '\n'.join(f'"{l}"' for l in lib_list)
                _edit_cmake_variable(userconfig_path, "USER_LINK_LIBRARIES", f"\n{value}\n")

        if self.__config.has_option("linker", "link_directories"):
            paths = self.__config.get("linker", "link_directories").strip()
            if paths:
                path_list = _parse_multiline_paths(paths)
                expanded_paths = [_expand_path_variables(p) for p in path_list]
                value = '\n'.join(f'"{p}"' for p in expanded_paths)
                _edit_cmake_variable(userconfig_path, "USER_LINK_DIRECTORIES", f"\n{value}\n")

        # Linker script
        if self.__config.has_option("linker", "linker_script"):
            script = self.__config.get("linker", "linker_script").strip()
            if script:
                expanded_script = _expand_path_variables(script)

                project_src_dir = os.path.join(
                    self.__workspace_path,
                    self.__name,
                    "src"
                )

                if os.path.exists(project_src_dir):
                    linker_script_symlink = os.path.join(project_src_dir, "lscript.ld")

                    if os.path.exists(linker_script_symlink) or os.path.islink(linker_script_symlink):
                        try:
                            os.remove(linker_script_symlink)
                            log.debug(f"Removed existing linker script at {linker_script_symlink}")
                        except Exception as e:
                            log.warning(f"Failed to remove existing linker script: {e}")

                    if _create_symlink(expanded_script, linker_script_symlink):
                        _edit_cmake_variable(userconfig_path, "USER_LINKER_SCRIPT",
                                           '"${CMAKE_SOURCE_DIR}/lscript.ld"')
                    else:
                        log.warning(f"Failed to create linker script symlink, using absolute path")
                        _edit_cmake_variable(userconfig_path, "USER_LINKER_SCRIPT", f'"{expanded_script}"')
                else:
                    log.warning(f"Project src directory not found: {project_src_dir}, using absolute path for linker script")
                    _edit_cmake_variable(userconfig_path, "USER_LINKER_SCRIPT", f'"{expanded_script}"')

        # Misc linker flags
        if self.__config.has_option("linker", "other_flags"):
            flags = self.__config.get("linker", "other_flags")
            _edit_cmake_variable(userconfig_path, "USER_LINK_OTHER_FLAGS", flags)

        log.debug("Linker settings configured successfully")

    def __configure_launch(self) -> None:
        """Configure debug/launch settings in launch.json."""
        log.debug("Configuring launch settings")

        launch_json_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "_ide",
            ".theia",
            "launch.json"
        )

        os.makedirs(os.path.dirname(launch_json_path), exist_ok=True)

        if os.path.exists(launch_json_path):
            with open(launch_json_path, 'r') as f:
                launch_data = json.load(f)
        else:
            launch_data = {
                "version": "0.2.0",
                "configurations": []
            }

        for launch_config in self.__launch_configs:
            new_config = launch_config.generate_launch_config()
            config_name = new_config["name"]

            existing_idx = None
            for idx, config in enumerate(launch_data["configurations"]):
                if config["name"] == config_name:
                    existing_idx = idx
                    break

            if existing_idx is not None:
                log.debug(f"Updating existing launch configuration: {config_name}")
                launch_data["configurations"][existing_idx] = new_config
            else:
                log.debug(f"Adding new launch configuration: {config_name}")
                launch_data["configurations"].append(new_config)

        with open(launch_json_path, 'w') as f:
            json.dump(launch_data, f, indent=2)

        log.debug("Launch settings configured successfully")

    def __create_common_clangd(self) -> None:
        """
        Create/update .clangd at common parent of all source directories.
        Also create/update symlink to compile_commands.json at common parent.
        This makes the current project the "active" one for linting.
        """
        log.debug("Creating/updating common .clangd configuration")

        source_paths = []

        if self.__config.has_option("compiler", "source_folders"):
            folders = self.__config.get("compiler", "source_folders").strip()
            if folders:
                folder_list = _parse_multiline_paths(folders)
                expanded_folders = [_expand_path_variables(f) for f in folder_list]
                source_paths.extend(expanded_folders)

        if self.__config.has_option("compiler", "source_files"):
            sources = self.__config.get("compiler", "source_files").strip()
            if sources:
                source_list = _parse_multiline_paths(sources)
                expanded_sources = [_expand_path_variables(s) for s in source_list]
                source_paths.extend([os.path.dirname(f) for f in expanded_sources])

        project_dir = os.path.join(self.__workspace_path, self.__name)
        source_paths.append(project_dir)

        if not source_paths:
            log.warning("No source paths found, cannot determine common parent")
            return

        common_parent = os.path.commonpath(source_paths)
        log.info(f"Common parent for source files: {common_parent}")

        clangd_path = os.path.join(common_parent, ".clangd")
        clangd_content = """CompileFlags:
    Add: [-Wno-unknown-warning-option, -U__linux__, -U__clang__]
    Remove: [-m*, -f*]
"""

        try:
            with open(clangd_path, 'w') as f:
                f.write(clangd_content)
            log.info(f"Created/updated .clangd at {clangd_path}")
        except Exception as e:
            log.warning(f"Failed to create .clangd at {clangd_path}: {e}")
            return

        compile_db_dest = os.path.join(common_parent, "compile_commands.json")
        compile_db_src = os.path.join(project_dir, "compile_commands.json")

        if not os.path.exists(compile_db_src):
            log.warning(f"compile_commands.json not found at {compile_db_src}")
            return

        if os.path.exists(compile_db_dest) or os.path.islink(compile_db_dest):
            try:
                os.remove(compile_db_dest)
                log.debug(f"Removed existing compile_commands.json at {compile_db_dest}")
            except Exception as e:
                log.warning(f"Failed to remove old compile_commands.json: {e}")

        try:
            rel_path = os.path.relpath(compile_db_src, common_parent)
            os.symlink(rel_path, compile_db_dest)
            log.info(f"Created symlink: {compile_db_dest} -> {rel_path}")
        except (OSError, NotImplementedError) as e:
            # Symlink not supported (Windows without admin) - copy instead
            log.debug(f"Symlink not available ({e}), copying instead")
            try:
                shutil.copy2(compile_db_src, compile_db_dest)
                log.info(f"Copied compile_commands.json to {common_parent}")
            except Exception as e:
                log.warning(f"Failed to copy compile_commands.json: {e}")

    def build(self) -> None:
        """Build the application component."""
        log.info(f"Building application {self.__name}")
        app = self.__client.get_component( # type: ignore
            name=self.__name
        )
        log.debug(f"Executing Vitis build in workspace '{self.__workspace_path}': application.build() for '{self.__name}'")
        status = app.build()
        log.info(f"Application {self.__name} build completed with status: {status}")

        self.__create_common_clangd()

        return status
