"""
Vitis Build Module - Provides ACTIVATE and BUILD commands.

ACTIVATE: Sets a project as "active" for IDE tooling (clangd IntelliSense)
BUILD: Builds a project using Vitis server or directly with Ninja
"""

import os
import platform
import shutil
import subprocess

from vitis_logging import Logger
from vitis_paths import (
    read_config, PROJECTS_PATH, TOP_PATH, SRC_PATH, get_vitis_root
)
from vitis_application import _parse_multiline_paths, _expand_path_variables

log = Logger("build")


def activate_project(project_name: str) -> bool:
    """
    Activate a project by updating .clangd and compile_commands.json at common parent.

    This makes the project "active" for IDE tooling like clangd IntelliSense.

    Args:
        project_name: Name of the project to activate

    Returns:
        True if activation successful, False otherwise
    """
    log.info(f"Activating project: {project_name}")

    # Verify project exists
    project_dir = os.path.join(PROJECTS_PATH, project_name)
    if not os.path.exists(project_dir):
        log.error(f"Project not found: {project_dir}")
        log.error(f"Run './Vitis/Do CREATE {project_name}' first")
        return False

    # Verify compile_commands.json exists
    compile_db_src = os.path.join(project_dir, "compile_commands.json")
    if not os.path.exists(compile_db_src):
        log.error(f"compile_commands.json not found: {compile_db_src}")
        log.error(f"Project must be built first. Run './Vitis/Do BUILD {project_name}'")
        return False

    # Read application.conf to get source paths
    config_folder = os.path.join(TOP_PATH, project_name)
    if not os.path.exists(config_folder):
        log.error(f"Configuration folder not found: {config_folder}")
        return False

    config = read_config(config_folder, "application")

    # Collect source paths
    source_paths = []

    # Add source folders from config
    if config.has_option("compiler", "source_folders"):
        folders = config.get("compiler", "source_folders").strip()
        if folders:
            folder_list = _parse_multiline_paths(folders)
            expanded_folders = [_expand_path_variables(f) for f in folder_list]
            source_paths.extend(expanded_folders)

    # Add source files directories from config
    if config.has_option("compiler", "source_files"):
        sources = config.get("compiler", "source_files").strip()
        if sources:
            source_list = _parse_multiline_paths(sources)
            expanded_sources = [_expand_path_variables(s) for s in source_list]
            source_paths.extend([os.path.dirname(f) for f in expanded_sources])

    # Add project directory
    source_paths.append(project_dir)

    if not source_paths:
        log.warning("No source paths found, using default common parent")
        common_parent = SRC_PATH
    else:
        # Find common parent of all source paths
        common_parent = os.path.commonpath(source_paths)

    log.info(f"Common parent: {common_parent}")

    # Create/update .clangd at common parent
    clangd_path = os.path.join(common_parent, ".clangd")
    clangd_content = """CompileFlags:
    Add: [-Wno-unknown-warning-option, -U__linux__, -U__clang__]
    Remove: [-m*, -f*]
"""

    try:
        with open(clangd_path, 'w') as f:
            f.write(clangd_content)
        log.debug(f"Created/updated .clangd at {clangd_path}")
    except Exception as e:
        log.error(f"Failed to create .clangd: {e}")
        return False

    # Create/update symlink to compile_commands.json
    compile_db_dest = os.path.join(common_parent, "compile_commands.json")

    # Remove old symlink/file if exists
    if os.path.exists(compile_db_dest) or os.path.islink(compile_db_dest):
        try:
            os.remove(compile_db_dest)
            log.debug(f"Removed existing compile_commands.json at {compile_db_dest}")
        except Exception as e:
            log.warning(f"Failed to remove old compile_commands.json: {e}")

    # Try to create symlink, fallback to copy if not supported
    try:
        rel_path = os.path.relpath(compile_db_src, common_parent)
        os.symlink(rel_path, compile_db_dest)
        log.info(f"Created symlink: {compile_db_dest} -> {rel_path}")
    except (OSError, NotImplementedError) as e:
        log.debug(f"Symlink not available ({e}), copying instead")
        try:
            shutil.copy2(compile_db_src, compile_db_dest)
            log.info(f"Copied compile_commands.json to {common_parent}")
        except Exception as e:
            log.error(f"Failed to copy compile_commands.json: {e}")
            return False

    log.info(f"Project '{project_name}' is now active")
    return True


def find_ninja_executable(use_system: bool) -> str:
    """
    Find Ninja executable - either system or Vitis-bundled.

    Args:
        use_system: If True, search PATH for system ninja; else use Vitis-bundled

    Returns:
        Path to ninja executable

    Raises:
        RuntimeError: If ninja not found or version too old
    """
    if use_system:
        # Search for system ninja in PATH
        ninja_path = shutil.which("ninja")

        if not ninja_path:
            raise RuntimeError(
                "System Ninja not found in PATH. Install with:\n"
                "  Windows: choco install ninja  (or download from ninja-build.org)\n"
                "  Linux:   sudo apt-get install ninja-build\n"
                "  macOS:   brew install ninja"
            )

        # Verify version ≥1.5 (minimum required by generated build.ninja)
        try:
            result = subprocess.run(
                [ninja_path, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            version_str = result.stdout.strip()

            # Parse version (format: X.Y.Z)
            version_parts = version_str.split('.')
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0

            if major < 1 or (major == 1 and minor < 5):
                raise RuntimeError(
                    f"System Ninja version {version_str} is too old.\n"
                    f"Minimum required: 1.5 (recommended: 1.11.1+)"
                )

            log.info(f"Using system Ninja {version_str} from {ninja_path}")

        except (subprocess.CalledProcessError, ValueError, IndexError) as e:
            log.warning(f"Could not verify Ninja version, proceeding anyway: {e}")

        return ninja_path

    else:
        # Use Vitis-bundled Ninja
        vitis_root, _ = get_vitis_root()
        system = platform.system()

        if system == "Windows":
            ninja_path = os.path.join(
                vitis_root, "tps", "win64", "lopper-1.1.0-packages",
                "min_sdk", "usr", "bin", "ninja.exe"
            )
        else:
            ninja_path = os.path.join(
                vitis_root, "tps", "lnx64", "lopper-1.1.0-packages",
                "min_sdk", "usr", "bin", "ninja"
            )

        if not os.path.exists(ninja_path):
            raise RuntimeError(
                f"Vitis-bundled Ninja not found at: {ninja_path}\n"
                f"Ensure Vitis is properly installed"
            )

        log.info("Using Vitis-bundled Ninja 1.11.1")
        return ninja_path


def build_project_ninja(project_name: str, clean: bool = False, use_system_ninja: bool = False) -> int:
    """
    Build a project directly using Ninja (no Vitis server required).

    Args:
        project_name: Name of the project to build
        clean: If True, clean before building
        use_system_ninja: If True, use system ninja from PATH; else use Vitis-bundled

    Returns:
        Exit code (0 = success)
    """
    log.info(f"Building project with Ninja: {project_name}")

    # Verify project exists
    project_dir = os.path.join(PROJECTS_PATH, project_name)
    build_dir = os.path.join(project_dir, "build")

    if not os.path.exists(project_dir):
        log.error(f"Project not found: {project_dir}")
        log.error(f"Run './Vitis/Do CREATE {project_name}' first")
        return 1

    if not os.path.exists(build_dir):
        log.error(f"Build directory not found: {build_dir}")
        log.error("Project must be created with Vitis first to generate build files")
        return 1

    # Check for CMakeCache.txt (indicates project was configured)
    cmake_cache = os.path.join(build_dir, "CMakeCache.txt")
    if not os.path.exists(cmake_cache):
        log.error(f"CMakeCache.txt not found in {build_dir}")
        log.error("Project must be created with Vitis first to configure CMake")
        return 1

    # Locate Ninja executable
    try:
        ninja_path = find_ninja_executable(use_system_ninja)
    except RuntimeError as e:
        log.error(str(e))
        return 1

    log.debug(f"Ninja path: {ninja_path}")

    # Clean if requested
    if clean:
        log.info("Cleaning build artifacts...")
        clean_result = subprocess.run(
            [ninja_path, "clean"],
            cwd=build_dir,
            capture_output=False
        )
        if clean_result.returncode != 0:
            log.warning("Clean failed, continuing with build anyway")

    # Run ninja build
    log.info("Running Ninja build...")
    result = subprocess.run(
        [ninja_path],
        cwd=build_dir,
        capture_output=False
    )

    if result.returncode == 0:
        log.info(f"Build successful: {project_name}.elf")
    else:
        log.error(f"Build failed with exit code: {result.returncode}")

    return result.returncode


def build_project_vitis(client, project_name: str) -> int:
    """
    Build a project using the Vitis server.

    Args:
        client: Vitis client object
        project_name: Name of the project to build

    Returns:
        Exit code (0 = success)
    """
    log.info(f"Building project with Vitis: {project_name}")

    # Verify project exists
    project_dir = os.path.join(PROJECTS_PATH, project_name)
    if not os.path.exists(project_dir):
        log.error(f"Project not found: {project_dir}")
        log.error(f"Run './Vitis/Do CREATE {project_name}' first")
        return 1

    try:
        # Get the application component
        app = client.get_component(name=project_name)
        if app is None:
            log.error(f"Could not find component: {project_name}")
            return 1

        # Build the application
        status = app.build()
        log.info(f"Build completed with status: {status}")

        return 0 if status == 0 else 1

    except Exception as e:
        log.error(f"Build failed: {e}")
        return 1
