"""
Vitis Build Module - Provides ACTIVATE and BUILD commands.

ACTIVATE: Sets a project as "active" for IDE tooling (clangd IntelliSense)
BUILD: Builds a project using Vitis server or directly with Ninja
"""

import os
import platform
import re
import shutil
import subprocess
from typing import List, TypeVar

# Add package: Vitis Python CLI
# import vitis # type: ignore
vitis_client = TypeVar('vitis_client')

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

    project_dir = os.path.join(PROJECTS_PATH, project_name)
    if not os.path.exists(project_dir):
        log.error(f"Project not found: {project_dir}")
        log.error(f"Run './Vitis/Do CREATE {project_name}' first")
        return False

    compile_db_src = os.path.join(project_dir, "compile_commands.json")
    if not os.path.exists(compile_db_src):
        log.error(f"compile_commands.json not found: {compile_db_src}")
        log.error(f"Project must be built first. Run './Vitis/Do BUILD {project_name}'")
        return False

    config_folder = os.path.join(TOP_PATH, project_name)
    if not os.path.exists(config_folder):
        log.error(f"Configuration folder not found: {config_folder}")
        return False

    config = read_config(config_folder, "application")

    source_paths = []

    if config.has_option("compiler", "source_folders"):
        folders = config.get("compiler", "source_folders").strip()
        if folders:
            folder_list = _parse_multiline_paths(folders)
            expanded_folders = [_expand_path_variables(f) for f in folder_list]
            source_paths.extend(expanded_folders)

    if config.has_option("compiler", "source_files"):
        sources = config.get("compiler", "source_files").strip()
        if sources:
            source_list = _parse_multiline_paths(sources)
            expanded_sources = [_expand_path_variables(s) for s in source_list]
            source_paths.extend([os.path.dirname(f) for f in expanded_sources])

    source_paths.append(project_dir)

    if not source_paths:
        log.warning("No source paths found, using default common parent")
        common_parent = SRC_PATH
    else:
        common_parent = os.path.commonpath(source_paths)

    log.info(f"Common parent: {common_parent}")

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

    compile_db_dest = os.path.join(common_parent, "compile_commands.json")

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
        log.debug(f"Symlink not available ({e}), copying instead")
        try:
            shutil.copy2(compile_db_src, compile_db_dest)
            log.info(f"Copied compile_commands.json to {common_parent}")
        except Exception as e:
            log.error(f"Failed to copy compile_commands.json: {e}")
            return False

    log.info(f"Project '{project_name}' is now active")
    return True


class ProjectBuilder(object):
    """
    Build all components of a project (platform + applications).
    """

    def __init__(self, client: vitis_client, project_name: str): # pyright: ignore[reportInvalidTypeVarUse]
        """
        Initialize project builder.

        Args:
            client: Vitis client object
            project_name: Name of project (folder in Top/)
        """
        self.__client = client
        self.__project_name = project_name

        config_folder = os.path.join(TOP_PATH, project_name)
        if not os.path.exists(config_folder):
            raise FileNotFoundError(f"Project config not found: {config_folder}")

        self.__config_folder = config_folder
        self.__config_top = read_config(config_folder, "vitis")

        self.__platform = self.__load_platform()
        self.__applications = self.__load_applications()

    def __load_platform(self):
        """Load platform component for building."""
        from vitis_platform import VitisPlatform

        return VitisPlatform(
            client=self.__client,
            name=self.__config_top.get('platform', 'NAME'),
            description=self.__config_top.get('platform', 'DESCRIPTION'),
            config_folder=self.__config_folder,
            config=self.__config_top.get('platform', 'CONFIG'),
            workspace_path=PROJECTS_PATH
        )

    def __load_applications(self) -> List:
        """Load all application components for building."""
        from vitis_application import VitisApplication

        applications = []

        if self.__config_top.has_section('application'):
            app = self.__load_single_application('application')
            if app:
                applications.append(app)

        # Load additional applications (application_1, application_2, etc.)
        application_sections = [s for s in self.__config_top.sections()
                                if re.match(r"application_\d+", s)]

        for section in sorted(application_sections):
            app = self.__load_single_application(section)
            if app:
                applications.append(app)

        return applications

    def __load_single_application(self, section: str):
        """Load a single application from config section."""
        from vitis_application import VitisApplication

        if not self.__config_top.has_option(section, 'NAME'):
            log.warning(f"Application section [{section}] missing NAME, skipping")
            return None

        if not self.__config_top.has_option(section, 'CONFIG'):
            log.warning(f"Application section [{section}] missing CONFIG, skipping")
            return None

        app_name = self.__config_top.get(section, 'NAME')
        app_config = self.__config_top.get(section, 'CONFIG')
        app_description = self.__config_top.get(section, 'DESCRIPTION',
                                                 fallback=f"{app_name} application component")

        return VitisApplication(
            client=self.__client,
            name=app_name,
            description=app_description,
            config_folder=self.__config_folder,
            config=app_config,
            workspace_path=PROJECTS_PATH
        )

    def build(self) -> int:
        """
        Build all project components.

        Returns:
            Exit code (0 = success)
        """
        log.info(f"Building entire project: {self.__project_name}")

        log.info(f"Building platform...")
        try:
            platform_status = self.__platform.build()
            if platform_status != 0:
                log.error(f"Platform build failed with status: {platform_status}")
                return 1
        except Exception as e:
            log.error(f"Platform build failed: {e}")
            return 1

        for app in self.__applications:
            app_name = app._VitisApplication__name
            log.info(f"Building application {app_name}...")
            try:
                app_status = app.build()
                if app_status != 0:
                    log.error(f"Application {app_name} build failed with status: {app_status}")
                    return 1
            except Exception as e:
                log.error(f"Application {app_name} build failed: {e}")
                return 1

        log.info(f"Project {self.__project_name} build complete")
        return 0


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
        ninja_path = shutil.which("ninja")

        if not ninja_path:
            raise RuntimeError(
                "System Ninja not found in PATH. Install with:\n"
                "  Windows: choco install ninja  (or download from ninja-build.org)\n"
                "  Linux:   sudo apt-get install ninja-build\n"
                "  macOS:   brew install ninja"
            )

        # Verify version >= 1.5 (minimum required by generated build.ninja)
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

    cmake_cache = os.path.join(build_dir, "CMakeCache.txt")
    if not os.path.exists(cmake_cache):
        log.error(f"CMakeCache.txt not found in {build_dir}")
        log.error("Project must be created with Vitis first to configure CMake")
        return 1

    try:
        ninja_path = find_ninja_executable(use_system_ninja)
    except RuntimeError as e:
        log.error(str(e))
        return 1

    log.debug(f"Ninja path: {ninja_path}")

    if clean:
        log.info("Cleaning build artifacts...")
        log.debug(f"Executing command in '{build_dir}': {ninja_path} clean")
        clean_result = subprocess.run(
            [ninja_path, "clean"],
            cwd=build_dir,
            capture_output=False
        )
        if clean_result.returncode != 0:
            log.warning("Clean failed, continuing with build anyway")

    log.info("Running Ninja build...")
    log.debug(f"Executing command in '{build_dir}': {ninja_path}")
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

    project_dir = os.path.join(PROJECTS_PATH, project_name)
    if not os.path.exists(project_dir):
        log.error(f"Project not found: {project_dir}")
        log.error(f"Run './Vitis/Do CREATE {project_name}' first")
        return 1

    try:
        app = client.get_component(name=project_name)
        if app is None:
            log.error(f"Could not find component: {project_name}")
            return 1

        log.debug(f"Executing Vitis build in workspace '{PROJECTS_PATH}': application.build() for '{project_name}'")
        status = app.build()
        log.info(f"Build completed with status: {status}")

        return 0 if status == 0 else 1

    except Exception as e:
        log.error(f"Build failed: {e}")
        return 1


def build_project_all(client: vitis_client, project_name: str) -> int: # pyright: ignore[reportInvalidTypeVarUse]
    """
    Build entire project (platform + all applications).

    Args:
        client: Vitis client object
        project_name: Name of project (folder in Top/)

    Returns:
        Exit code (0 = success)
    """
    log.info(f"Building all components for project: {project_name}")

    try:
        builder = ProjectBuilder(client, project_name)
        return builder.build()
    except FileNotFoundError as e:
        log.error(str(e))
        return 1
    except Exception as e:
        log.error(f"Failed to build project: {e}")
        return 1


def build_project_all_ninja(
    project_name: str,
    clean: bool = False,
    use_system_ninja: bool = False
) -> int:
    """
    Build entire project (platform + all applications) using Ninja directly.

    This builds the full project in the correct order:
    1. All BSPs (one per domain)
    2. FSBL (if BOOT_COMPONENTS=true)
    3. All applications

    Args:
        project_name: Name of project (folder in Top/ and Projects/)
        clean: If True, clean before building
        use_system_ninja: If True, use system ninja; else use Vitis-bundled

    Returns:
        Exit code (0 = success)
    """
    log.info(f"Building full project with Ninja: {project_name}")

    try:
        ninja_path = find_ninja_executable(use_system_ninja)
    except RuntimeError as e:
        log.error(str(e))
        return 1

    config_folder = os.path.join(TOP_PATH, project_name)
    if not os.path.exists(config_folder):
        log.error(f"Project config not found: {config_folder}")
        return 1

    platform_dir = os.path.join(PROJECTS_PATH, f"{project_name}_platform")
    if not os.path.exists(platform_dir):
        log.error(f"Platform not found: {platform_dir}")
        log.error(f"Run './Vitis/Do CREATE {project_name}' first")
        return 1

    platform_config = read_config(config_folder, "platform")

    # Step 1: Build all BSPs (one per domain)
    log.info("Building BSPs (Board Support Packages)...")

    domains = []

    if platform_config.has_section('domain'):
        domains.append({
            'name': platform_config.get('domain', 'NAME'),
            'processor': platform_config.get('domain', 'PROCESSOR_INSTANCE')
        })

    # Add additional domains (domain_1, domain_2, etc.)
    domain_sections = [s for s in platform_config.sections()
                       if re.match(r"domain_\d+", s)]

    for section in sorted(domain_sections):
        if platform_config.has_option(section, 'NAME') and \
           platform_config.has_option(section, 'PROCESSOR_INSTANCE'):
            domains.append({
                'name': platform_config.get(section, 'NAME'),
                'processor': platform_config.get(section, 'PROCESSOR_INSTANCE')
            })

    if not domains:
        log.error("No domains found in platform.conf")
        return 1

    for i, domain in enumerate(domains):
        domain_name = domain['name']
        processor = domain['processor']

        log.info(f"Building BSP for domain {domain_name}...")

        # Construct BSP build directory path
        bsp_build_dir = os.path.join(
            platform_dir,
            processor,
            domain_name,
            "bsp", "libsrc", "build_configs", "gen_bsp"
        )

        if not os.path.exists(bsp_build_dir):
            log.error(f"BSP build directory not found: {bsp_build_dir}")
            return 1

        if not os.path.exists(os.path.join(bsp_build_dir, "build.ninja")):
            log.error(f"build.ninja not found in {bsp_build_dir}")
            return 1

        exit_code = _run_ninja_in_directory(
            ninja_path, bsp_build_dir, clean, f"BSP ({domain_name})"
        )
        if exit_code != 0:
            log.error(f"BSP build failed for domain {domain_name}")
            return exit_code

    # Step 2: Build FSBL (if BOOT_COMPONENTS is true)
    has_boot_components = platform_config.getboolean("boot", "BOOT_COMPONENTS", fallback=True)

    if has_boot_components:
        log.info("Building FSBL (First Stage Boot Loader)...")
        fsbl_build_dir = os.path.join(platform_dir, "zynq_fsbl", "build")

        if not os.path.exists(fsbl_build_dir):
            log.error(f"FSBL build directory not found: {fsbl_build_dir}")
            log.error("BOOT_COMPONENTS=true but FSBL directory missing")
            return 1

        exit_code = _run_ninja_in_directory(
            ninja_path, fsbl_build_dir, clean, "FSBL"
        )
        if exit_code != 0:
            log.error("FSBL build failed")
            return exit_code
    else:
        log.info("Skipping FSBL build (BOOT_COMPONENTS=false)")

    # Step 3: Build all applications
    log.info("Building applications...")

    vitis_config = read_config(config_folder, "vitis")

    app_names = []

    if vitis_config.has_section('application') and \
       vitis_config.has_option('application', 'NAME'):
        app_names.append(vitis_config.get('application', 'NAME'))

    # Find additional applications (application_1, application_2, etc.)
    application_sections = [s for s in vitis_config.sections()
                            if re.match(r"application_\d+", s)]

    for section in sorted(application_sections):
        if vitis_config.has_option(section, 'NAME'):
            app_names.append(vitis_config.get(section, 'NAME'))

    if not app_names:
        log.warning("No applications found in vitis.conf")
        return 0

    for app_name in app_names:
        log.info(f"Building application: {app_name}...")
        app_build_dir = os.path.join(PROJECTS_PATH, app_name, "build")

        if not os.path.exists(app_build_dir):
            log.error(f"Application build directory not found: {app_build_dir}")
            log.error(f"Application '{app_name}' may not have been created")
            return 1

        exit_code = _run_ninja_in_directory(
            ninja_path, app_build_dir, clean, f"Application {app_name}"
        )
        if exit_code != 0:
            log.error(f"Application {app_name} build failed")
            return exit_code

    log.info(f"Full project {project_name} build complete")
    return 0


def _run_ninja_in_directory(
    ninja_path: str,
    build_dir: str,
    clean: bool,
    component_name: str
) -> int:
    """
    Run ninja in a specific directory.

    Args:
        ninja_path: Path to ninja executable
        build_dir: Directory containing build.ninja
        clean: If True, run ninja clean first
        component_name: Human-readable component name for logging

    Returns:
        Exit code (0 = success)
    """
    build_ninja = os.path.join(build_dir, "build.ninja")
    if not os.path.exists(build_ninja):
        log.error(f"build.ninja not found in {build_dir}")
        return 1

    if clean:
        log.info(f"Cleaning {component_name}...")
        log.debug(f"Executing command in '{build_dir}': {ninja_path} clean")
        result = subprocess.run(
            [ninja_path, "clean"],
            cwd=build_dir,
            capture_output=False
        )
        if result.returncode != 0:
            log.warning(f"Clean failed for {component_name}, continuing anyway")

    log.info(f"Running ninja for {component_name}...")
    log.debug(f"Executing command in '{build_dir}': {ninja_path}")
    result = subprocess.run(
        [ninja_path],
        cwd=build_dir,
        capture_output=False
    )

    if result.returncode == 0:
        log.info(f"{component_name} build successful")
    else:
        log.error(f"{component_name} build failed with exit code: {result.returncode}")

    return result.returncode
