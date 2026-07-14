"""
Shared helpers for editing generated CMake files and resolving configuration paths.

These functions are used by the create, update, and build flows. They were
originally defined as module-private helpers inside ``vitis_application`` and
imported across modules. Collecting them here gives every caller easy access.

None of these functions use the Vitis client, so they are exercised directly
by the unit tests.
"""

import os
import platform
import re
import shutil
from typing import Any, Dict, List

from vitis_logging import Logger
from vitis_paths import (
    get_src_root,
    get_vitis_install_dir,
    get_workspace_root,
    normalize_path,
)

log = Logger("cmake")


def edit_cmake_variable(file_path: str, variable_name: str, new_value: str) -> None:
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


def parse_multiline_paths(config_value: str) -> List[str]:
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


def expand_path_variables(path: str) -> str:
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


def create_symlink(src_path: str, link_path: str) -> bool:
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


def create_folder_symlink(src_folder: str, link_name: str, project_src_dir: str) -> bool:
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

                        if create_symlink(src_file, dest_file):
                            file_count += 1

            log.info(f"Created directory structure for {link_name}/ with {file_count} file symlinks")
            return True

    except Exception as e:
        log.warning(f"Failed to create folder symlink {link_name}/: {e}")
        return False


def bool_to_cmake_flag(enabled: bool, flag: str) -> str:
    """Convert boolean to CMake flag or empty string."""
    return flag if enabled else ""


def format_optimization_level(level: str) -> str:
    """
    Convert optimization level string to compiler flag.

    Args:
        level: Optimization level (none, O1, O2, O3, Os)

    Returns:
        Compiler flag (-O0, -O1, -O2, -O3, -Os) or empty string for none
    """
    level = level.strip()
    level_lower = level.lower()

    if level_lower == "none" or not level:
        return ""
    elif level.startswith("-"):
        # If user provided dash, extract the part after it and normalize
        level_part = level[1:]
        level_lower_part = level_part.lower()
        if level_lower_part == "none" or not level_part:
            return ""
        elif level_lower_part == "os":
            return "-Os"
        elif level_lower_part.startswith("o"):
            return f"-{level_part.upper()}"
        else:
            return f"-O{level_part}"
    elif level_lower == "os":
        return "-Os"
    elif level_lower.startswith("o"):
        return f"-{level.upper()}"
    else:
        return f"-O{level}"


def format_debug_level(level: str) -> str:
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


def render_template(template_path: str, context: Dict[str, Any]) -> str:
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
