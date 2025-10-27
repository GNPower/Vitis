import argparse
import configparser
import json
import os
from pathlib import Path
import re
import sys
from typing import List, TypeVar, Dict, Any

# Add package: Vitis Python CLI
# import vitis # type: ignore
vitis_client = TypeVar('vitis_client')

from vitis_logging import Logger
from vitis_paths import read_config, parentdir, PROJECTS_PATH, HDL_DATA_PATH


log = Logger("application")

# Template path
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

    # Replace the value
    replacement = rf'\g<1>{new_value})'
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

    with open(file_path, 'w') as f:
        f.write(new_content)


def _bool_to_cmake_flag(enabled: bool, flag: str) -> str:
    """Convert boolean to CMake flag or empty string."""
    return flag if enabled else ""


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

    # Replace {{placeholders}}
    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        # Convert Python bool to JSON bool (lowercase)
        if isinstance(value, bool):
            value = str(value).lower()
        content = content.replace(placeholder, str(value))

    return content


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

        # Get config values with defaults
        config_name = self.__config.get("launch", "name", fallback=f"{self.__app_name}_{self.__name}")
        debug_type = self.__config.get("launch", "debug_type", fallback="baremetal-zynq")
        target_core = self.__config.get("target", "core", fallback="ps7_cortexa9_0")
        context = self.__config.get("target", "context", fallback="zynq")

        # Auto-detect paths if not specified
        # Use forward slashes for JSON compatibility (Windows/VSCode accept them)
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

        # Behavior settings
        reset_system = self.__config.getboolean("behavior", "reset_system", fallback=True)
        program_device = self.__config.getboolean("behavior", "program_device", fallback=True)
        reset_apu = self.__config.getboolean("behavior", "reset_apu", fallback=False)
        stop_at_entry = self.__config.getboolean("behavior", "stop_at_entry", fallback=False)
        reset_processor = self.__config.getboolean("behavior", "reset_processor", fallback=True)

        # Build context for template
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

        # Render template
        template_path = os.path.join(TEMPLATES_PATH, "launch.json.template")
        rendered = _render_template(template_path, context)

        # Parse as JSON to get the configuration object
        template_data = json.loads(rendered)
        return template_data["configurations"][0]


class VitisApplication(object):
    """Represents a Vitis application component with compiler, linker, and debug configurations."""

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

        # Add all launch configurations
        self.__add_launch_configs()

    def __add_launch_configs(self) -> None:
        """Parse and add all launch configurations from config."""
        # Add the default launch config
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

        # Build platform path
        platform_path = os.path.join(
            self.__workspace_path,
            f"{platform_name}_platform",
            "export",
            f"{platform_name}_platform",
            f"{platform_name}_platform.xpfm"
        )

        log.debug(f"Using platform: {platform_path}")
        log.debug(f"Targeting domain: {domain_name}")

        # Create application component
        # If template is empty/not specified, create bare application (no template parameter)
        # If template is specified, pass it to create from template
        if template:
            log.debug(f"Using template: {template}")
            self.__application = self.__client.create_app_component(
                name=self.__name,
                platform=platform_path,
                domain=domain_name,
                template=template
            )
        else:
            log.debug("Creating empty application (no template)")
            self.__application = self.__client.create_app_component(
                name=self.__name,
                platform=platform_path,
                domain=domain_name
            )

        log.info(f"Application component {self.__name} created successfully")

    def configure(self) -> None:
        """Configure the application's UserConfig.cmake and launch.json."""
        log.info(f"Configuring application {self.__name}")

        self.__configure_compiler()
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
        if self.__config.has_option("compiler.symbols", "defined"):
            defined = self.__config.get("compiler.symbols", "defined").strip()
            if defined:
                # Split by comma and format for CMake
                symbols = [s.strip() for s in defined.split(',')]
                value = '\n'.join(f'"{s}"' for s in symbols)
                _edit_cmake_variable(userconfig_path, "USER_COMPILE_DEFINITIONS", f"\n{value}\n")

        if self.__config.has_option("compiler.symbols", "undefined"):
            undefined = self.__config.get("compiler.symbols", "undefined").strip()
            if undefined:
                symbols = [s.strip() for s in undefined.split(',')]
                value = '\n'.join(f'"{s}"' for s in symbols)
                _edit_cmake_variable(userconfig_path, "USER_UNDEFINED_SYMBOLS", f"\n{value}\n")

        # Directories
        if self.__config.has_option("compiler.directories", "include_paths"):
            includes = self.__config.get("compiler.directories", "include_paths").strip()
            if includes:
                paths = [p.strip() for p in includes.split(',')]
                value = '\n'.join(f'"{p}"' for p in paths)
                _edit_cmake_variable(userconfig_path, "USER_INCLUDE_DIRECTORIES", f"\n{value}\n")

        # Optimization
        if self.__config.has_option("compiler.optimization", "level"):
            level = self.__config.get("compiler.optimization", "level")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_OPTIMIZATION_LEVEL", level)

        if self.__config.has_option("compiler.optimization", "other_flags"):
            flags = self.__config.get("compiler.optimization", "other_flags")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_OPTIMIZATION_OTHER_FLAGS", flags)

        # Debugging
        if self.__config.has_option("compiler.debugging", "level"):
            level = self.__config.get("compiler.debugging", "level")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_DEBUG_LEVEL", level)

        if self.__config.has_option("compiler.debugging", "other_flags"):
            flags = self.__config.get("compiler.debugging", "other_flags")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_DEBUG_OTHER_FLAGS", flags)

        # Warnings
        if self.__config.has_option("compiler.warnings", "all"):
            enabled = self.__config.getboolean("compiler.warnings", "all")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_ALL",
                               _bool_to_cmake_flag(enabled, "-Wall"))

        if self.__config.has_option("compiler.warnings", "extra"):
            enabled = self.__config.getboolean("compiler.warnings", "extra")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_EXTRA",
                               _bool_to_cmake_flag(enabled, "-Wextra"))

        if self.__config.has_option("compiler.warnings", "as_errors"):
            enabled = self.__config.getboolean("compiler.warnings", "as_errors")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_AS_ERRORS",
                               _bool_to_cmake_flag(enabled, "-Werror"))

        if self.__config.has_option("compiler.warnings", "check_syntax_only"):
            enabled = self.__config.getboolean("compiler.warnings", "check_syntax_only")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_CHECK_SYNTAX_ONLY",
                               _bool_to_cmake_flag(enabled, "-fsyntax-only"))

        if self.__config.has_option("compiler.warnings", "pedantic"):
            enabled = self.__config.getboolean("compiler.warnings", "pedantic")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_PEDANTIC",
                               _bool_to_cmake_flag(enabled, "-pedantic"))

        if self.__config.has_option("compiler.warnings", "pedantic_as_errors"):
            enabled = self.__config.getboolean("compiler.warnings", "pedantic_as_errors")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_PEDANTIC_AS_ERRORS",
                               _bool_to_cmake_flag(enabled, "-pedantic-errors"))

        if self.__config.has_option("compiler.warnings", "inhibit_all"):
            enabled = self.__config.getboolean("compiler.warnings", "inhibit_all")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_WARNINGS_INHIBIT_ALL",
                               _bool_to_cmake_flag(enabled, "-w"))

        # Misc
        if self.__config.has_option("compiler.misc", "verbose"):
            enabled = self.__config.getboolean("compiler.misc", "verbose")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_VERBOSE",
                               _bool_to_cmake_flag(enabled, "-v"))

        if self.__config.has_option("compiler.misc", "ansi"):
            enabled = self.__config.getboolean("compiler.misc", "ansi")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_ANSI",
                               _bool_to_cmake_flag(enabled, "-ansi"))

        if self.__config.has_option("compiler.misc", "other_flags"):
            flags = self.__config.get("compiler.misc", "other_flags")
            _edit_cmake_variable(userconfig_path, "USER_COMPILE_OTHER_FLAGS", flags)

        log.debug("Compiler settings configured successfully")

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
        if self.__config.has_option("linker.general", "no_start_files"):
            enabled = self.__config.getboolean("linker.general", "no_start_files")
            _edit_cmake_variable(userconfig_path, "USER_LINK_NO_START_FILES",
                               _bool_to_cmake_flag(enabled, "-nostartfiles"))

        if self.__config.has_option("linker.general", "no_default_libs"):
            enabled = self.__config.getboolean("linker.general", "no_default_libs")
            _edit_cmake_variable(userconfig_path, "USER_LINK_NO_DEFAULT_LIBS",
                               _bool_to_cmake_flag(enabled, "-nodefaultlibs"))

        if self.__config.has_option("linker.general", "no_stdlib"):
            enabled = self.__config.getboolean("linker.general", "no_stdlib")
            _edit_cmake_variable(userconfig_path, "USER_LINK_NO_STDLIB",
                               _bool_to_cmake_flag(enabled, "-nostdlib"))

        if self.__config.has_option("linker.general", "omit_symbols"):
            enabled = self.__config.getboolean("linker.general", "omit_symbols")
            _edit_cmake_variable(userconfig_path, "USER_LINK_OMIT_ALL_SYMBOL_INFO",
                               _bool_to_cmake_flag(enabled, "-s"))

        # Libraries
        if self.__config.has_option("linker.libraries", "libraries"):
            libs = self.__config.get("linker.libraries", "libraries").strip()
            if libs:
                lib_list = [l.strip() for l in libs.split(',')]
                value = '\n'.join(f'"{l}"' for l in lib_list)
                _edit_cmake_variable(userconfig_path, "USER_LINK_LIBRARIES", f"\n{value}\n")

        if self.__config.has_option("linker.libraries", "search_paths"):
            paths = self.__config.get("linker.libraries", "search_paths").strip()
            if paths:
                path_list = [p.strip() for p in paths.split(',')]
                value = '\n'.join(f'"{p}"' for p in path_list)
                _edit_cmake_variable(userconfig_path, "USER_LINK_DIRECTORIES", f"\n{value}\n")

        # Linker script
        if self.__config.has_option("linker.script", "file"):
            script = self.__config.get("linker.script", "file")
            _edit_cmake_variable(userconfig_path, "USER_LINKER_SCRIPT", f'"{script}"')

        # Misc linker flags
        if self.__config.has_option("linker.misc", "other_flags"):
            flags = self.__config.get("linker.misc", "other_flags")
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

        # Ensure directory exists
        os.makedirs(os.path.dirname(launch_json_path), exist_ok=True)

        # Load existing launch.json or create new
        if os.path.exists(launch_json_path):
            with open(launch_json_path, 'r') as f:
                launch_data = json.load(f)
        else:
            launch_data = {
                "version": "0.2.0",
                "configurations": []
            }

        # Generate configurations from all launch configs
        for launch_config in self.__launch_configs:
            new_config = launch_config.generate_launch_config()
            config_name = new_config["name"]

            # Check if configuration already exists
            existing_idx = None
            for idx, config in enumerate(launch_data["configurations"]):
                if config["name"] == config_name:
                    existing_idx = idx
                    break

            # Update existing or append new
            if existing_idx is not None:
                log.debug(f"Updating existing launch configuration: {config_name}")
                launch_data["configurations"][existing_idx] = new_config
            else:
                log.debug(f"Adding new launch configuration: {config_name}")
                launch_data["configurations"].append(new_config)

        # Write back to file
        with open(launch_json_path, 'w') as f:
            json.dump(launch_data, f, indent=2)

        log.debug("Launch settings configured successfully")

    def build(self) -> None:
        """Build the application component."""
        log.info(f"Building application {self.__name}")
        app = self.__client.get_component(name=self.__name)
        status = app.build()
        log.info(f"Application {self.__name} build completed with status: {status}")
        return status
