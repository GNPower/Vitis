import configparser
import json
import os
import re
import shutil
from typing import Any, Dict, List

# Add package: Vitis Python CLI
# import vitis # type: ignore

from vitis_logging import Logger
from vitis_cmake import (
    apply_compiler_config,
    apply_linker_config,
    create_folder_symlink,
    create_symlink,
    expand_path_variables,
    parse_multiline_paths,
    render_template,
)
from vitis_paths import (
    read_config
)


vitis_client = Any

log = Logger("application")

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates")


class VitisDebugConfig(object):
    """Represents a single debug/launch configuration."""

    def __init__(self, client: vitis_client, app_name: str, platform_name: str, workspace_path: str,
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
            fsbl = (
                f"${{workspaceFolder}}/{self.__platform_name}_platform"
                f"/export/{self.__platform_name}_platform/sw/boot/fsbl.elf"
            )

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

        template_context = {
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
        rendered = render_template(template_path, template_context)

        template_data = json.loads(rendered)
        return template_data["configurations"][0]


class VitisApplication(object):
    """Represents a Vitis application component with compiler, linker, and debug configurations."""

    @property
    def name(self) -> str:
        """Public accessor for the application component name."""
        return self.__name

    def __init__(self, client: vitis_client, name: str, description: str, config_folder: str,
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
        userconfig_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "src",
            "UserConfig.cmake"
        )

        if not os.path.exists(userconfig_path):
            log.warning(f"UserConfig.cmake not found at {userconfig_path}, skipping compiler configuration")
            return

        apply_compiler_config(userconfig_path, self.__config)

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
                source_list = parse_multiline_paths(sources)
                expanded_sources = [expand_path_variables(s) for s in source_list]

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
                        create_symlink(source_file, symlink_path)
                else:
                    log.warning(f"Project src directory not found: {project_src_dir}")

        # Source folders - recursively include all .c and .S files
        if self.__config.has_option("compiler", "source_folders"):
            folders = self.__config.get("compiler", "source_folders").strip()
            if folders:
                folder_list = parse_multiline_paths(folders)
                expanded_folders = [expand_path_variables(f) for f in folder_list]

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

                        create_folder_symlink(folder_path, folder_name, project_src_dir)
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
        """Configure linker settings in UserConfig.cmake and link the linker script."""
        userconfig_path = os.path.join(
            self.__workspace_path,
            self.__name,
            "src",
            "UserConfig.cmake"
        )

        if not os.path.exists(userconfig_path):
            log.warning(f"UserConfig.cmake not found at {userconfig_path}, skipping linker configuration")
            return

        apply_linker_config(userconfig_path, self.__config)

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
                folder_list = parse_multiline_paths(folders)
                expanded_folders = [expand_path_variables(f) for f in folder_list]
                source_paths.extend(expanded_folders)

        if self.__config.has_option("compiler", "source_files"):
            sources = self.__config.get("compiler", "source_files").strip()
            if sources:
                source_list = parse_multiline_paths(sources)
                expanded_sources = [expand_path_variables(s) for s in source_list]
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
        log.debug(f"Vitis build in '{self.__workspace_path}': application.build() for '{self.__name}'")
        status = app.build()
        log.info(f"Application {self.__name} build completed with status: {status}")

        self.__create_common_clangd()

        return status
