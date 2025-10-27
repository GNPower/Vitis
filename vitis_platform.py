import argparse
import configparser
from functools import partial
import inspect
import os
from pathlib import Path
import re
import shutil
import sys
from typing import List, TypeVar

# Add package: Vitis Python CLI
# import vitis # type: ignore
vitis_client = TypeVar('vitis_client')

from vitis_logging import Logger
from vitis_paths import read_config, parentdir, PROJECTS_PATH, HDL_DATA_PATH, get_library_path, get_driver_path


log = Logger("platform")


def _edit_bsp_yaml_value(bsp_yaml_path: str, param_name: str, new_value: str) -> None:
    """
    Directly edit a value in bsp.yaml file.

    This is a workaround for the broken domain.set_config() API in Vitis 2024.1.

    Args:
        bsp_yaml_path: Path to the bsp.yaml file
        param_name: Parameter name (e.g., 'proc_extra_compiler_flags', 'standalone_stdin')
        new_value: New value to set
    """
    with open(bsp_yaml_path, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    in_target_param = False

    for line in lines:
        # Check if we're in the target parameter section
        if f'{param_name}:' in line and param_name in line:
            in_target_param = True
            new_lines.append(line)
        elif in_target_param and 'value:' in line:
            # Replace the value line
            indent = len(line) - len(line.lstrip())
            new_lines.append(' ' * indent + f"value: '{new_value}'")
            in_target_param = False
        else:
            new_lines.append(line)

    # Mark config as needing regeneration
    final_lines = []
    for line in new_lines:
        if line.startswith('config:'):
            final_lines.append('config: reconfig')
        else:
            final_lines.append(line)

    with open(bsp_yaml_path, 'w') as f:
        f.write('\n'.join(final_lines))


class VitisPlatformDomain(object):

    def __init__(self, client: vitis_client, platform_name: str, name: str, display_name: str, processor_instance: str, config: configparser.ConfigParser, workspace_path: str):
        self.__client = client
        self.__platform_name = platform_name
        self.__name = name
        self.__display_name = display_name
        self.__processor_instance = processor_instance
        self.__config = config
        self.__workspace_path = workspace_path

    def __get_bsp_yaml_path(self) -> str:
        """Get the path to the bsp.yaml file for this domain."""
        return os.path.join(
            self.__workspace_path,
            self.__platform_name,
            self.__processor_instance,
            f"{self.__name}",
            "bsp",
            "bsp.yaml"
        )
    

    def create(self) -> None:
        platform = self.__client.get_component(name=self.__platform_name)
        status = platform.add_domain(
            cpu = self.__processor_instance, 
            os = self.__config.get("domain", "OS"), 
            name = self.__name, 
            display_name = self.__display_name,
        )


    def configure(self) -> None:
        """Configure the domain with compiler, OS, library, and driver settings."""
        log.info(f"Configuring domain {self.__name}")

        # Get the domain object
        platform = self.__client.get_component(name=self.__platform_name)
        domain = platform.get_domain(name=self.__name)

        # Configure each aspect if present in config
        self.__configure_compiler(domain)
        self.__configure_os(domain)
        self.__configure_libraries(domain)
        self.__configure_drivers(domain)

        # Regenerate the BSP to apply all configuration changes
        try:
            log.debug(f"Regenerating BSP for domain {self.__name}")
            domain.regenerate()
            log.info(f"Successfully regenerated BSP for domain {self.__name}")
        except Exception as e:
            log.error(f"Failed to regenerate BSP for domain {self.__name}: {e}")


    def __configure_compiler(self, domain) -> None:
        """Configure compiler settings using direct YAML editing (workaround for broken API)."""
        if not self.__config.has_section("compiler"):
            return

        if self.__config.has_option("compiler", "flags"):
            flags = self.__config.get("compiler", "flags")
            log.debug(f"Setting compiler flags: {flags}")
            try:
                # WORKAROUND: domain.set_config() is broken in Vitis 2024.1
                bsp_yaml_path = self.__get_bsp_yaml_path()
                _edit_bsp_yaml_value(bsp_yaml_path, "proc_extra_compiler_flags", f" {flags}")
                log.debug(f"Successfully set compiler flags: {flags}")
            except Exception as e:
                log.error(f"Failed to set compiler flags '{flags}': {e}")
                raise


    def __configure_os(self, domain) -> None:
        """Configure OS/BSP settings using direct YAML editing (workaround for broken API)."""
        if not self.__config.has_section("os"):
            return

        os_name = self.__config.get("domain", "OS")
        bsp_yaml_path = self.__get_bsp_yaml_path()

        # Configure stdin
        if self.__config.has_option("os", "stdin"):
            stdin = self.__config.get("os", "stdin")
            log.debug(f"Setting stdin to {stdin}")
            try:
                # WORKAROUND: domain.set_config() is broken in Vitis 2024.1
                _edit_bsp_yaml_value(bsp_yaml_path, f"{os_name}_stdin", stdin)
                log.debug(f"Successfully set stdin to {stdin}")
            except Exception as e:
                log.error(f"Failed to set stdin to '{stdin}': {e}")
                raise

        # Configure stdout
        if self.__config.has_option("os", "stdout"):
            stdout = self.__config.get("os", "stdout")
            log.debug(f"Setting stdout to {stdout}")
            try:
                # WORKAROUND: domain.set_config() is broken in Vitis 2024.1
                _edit_bsp_yaml_value(bsp_yaml_path, f"{os_name}_stdout", stdout)
                log.debug(f"Successfully set stdout to {stdout}")
            except Exception as e:
                log.error(f"Failed to set stdout to '{stdout}': {e}")
                raise


    def __configure_libraries(self, domain) -> None:
        """Configure libraries from numbered [library_N] sections."""
        # Find all library sections
        library_sections = [s for s in self.__config.sections() if re.match(r"library_\d+", s)]

        for section in sorted(library_sections):
            # Validate required field: name
            if not self.__config.has_option(section, "name"):
                log.warning(f"Library section [{section}] missing required field 'name', skipping")
                continue

            lib_name = self.__config.get(section, "name")

            # Check if library has a version (external library)
            if self.__config.has_option(section, "version"):
                lib_version = self.__config.get(section, "version")
                try:
                    lib_path = get_library_path(lib_name, lib_version)
                    log.debug(f"Adding library {lib_name}_{lib_version} from {lib_path}")
                    domain.set_lib(lib_name=lib_name, path=lib_path)
                    log.debug(f"Successfully added library {lib_name}_{lib_version}")
                except FileNotFoundError as e:
                    log.error(f"Failed to add library {lib_name}_{lib_version}: {e}")
                    continue
                except Exception as e:
                    log.error(f"Failed to set library {lib_name}_{lib_version}: {e}")
                    continue

            # Check if library should be enabled/disabled (built-in library)
            elif self.__config.has_option(section, "enabled"):
                enabled = self.__config.getboolean(section, "enabled")
                if not enabled:
                    try:
                        log.debug(f"Removing library {lib_name}")
                        domain.remove_lib(lib_name=lib_name)
                        log.debug(f"Successfully removed library {lib_name}")
                    except Exception as e:
                        log.error(f"Failed to remove library {lib_name}: {e}")
                        continue

            # Configure library parameters (param_* options)
            for option in self.__config.options(section):
                if option.startswith("param_"):
                    param_name = option[6:]  # Remove 'param_' prefix
                    param_value = self.__config.get(section, option)
                    log.debug(f"Setting {lib_name} parameter {param_name} = {param_value}")
                    try:
                        # WORKAROUND: domain.set_config() is broken in Vitis 2024.1
                        bsp_yaml_path = self.__get_bsp_yaml_path()
                        _edit_bsp_yaml_value(bsp_yaml_path, param_name, param_value)
                        log.debug(f"Successfully set {lib_name} parameter {param_name} = {param_value}")
                    except Exception as e:
                        log.error(f"Failed to set {lib_name} parameter {param_name}: {e}")
                        continue


    def __configure_drivers(self, domain) -> None:
        """Configure driver versions from numbered [driver_N] sections."""
        # Find all driver sections
        driver_sections = [s for s in self.__config.sections() if re.match(r"driver_\d+", s)]

        for section in sorted(driver_sections):
            # Validate required fields: name and version
            if not self.__config.has_option(section, "name"):
                log.warning(f"Driver section [{section}] missing required field 'name', skipping")
                continue

            if not self.__config.has_option(section, "version"):
                log.warning(f"Driver section [{section}] missing required field 'version', skipping")
                continue

            driver_name = self.__config.get(section, "name")
            driver_version = self.__config.get(section, "version")

            try:
                driver_path = get_driver_path(driver_name, driver_version)
                log.debug(f"Updating driver {driver_name} to version {driver_version}")
                domain.update_path(
                    option="DRIVER",
                    name=driver_name,
                    new_path=driver_path
                )
                log.debug(f"Successfully updated driver {driver_name} to version {driver_version}")
            except FileNotFoundError as e:
                log.error(f"Failed to update driver {driver_name}_{driver_version}: {e}")
            except Exception as e:
                log.error(f"Failed to update driver {driver_name} to version {driver_version}: {e}")


    def build(self) -> None:
        """Build the domain BSP."""
        log.info(f"Building domain {self.__name}")
        platform = self.__client.get_component(name=self.__platform_name)
        domain = platform.get_domain(name=self.__name)
        status = domain.build()
        log.info(f"Domain {self.__name} build completed with status: {status}")
        return status



class VitisPlatform(object):

    def __init__(self, client: vitis_client, name: str, description: str, config_folder: str, config: str, workspace_path: str) -> None:
        log.info(f"Defining a Platform Project with name {name}")
        self.__client = client
        self.__name = name
        self.__description = description
        self.__config_folder = config_folder
        self.__config = read_config(config_folder, config)
        self.__workspace_path = workspace_path
        self.__platform = None
        self.__domains: List[VitisPlatformDomain] = []
        # Add the default domain
        self.__add_domain(
            self.__config.get("domain", "NAME"),
            self.__config.get("domain", "DISPLAY_NAME"),
            self.__config.get("domain", "PROCESSOR_INSTANCE"),
            read_config(self.__config_folder, self.__config.get("domain", "CONFIG")),
        )
        # Add all additional domains
        additional_domains = [name for name in list(self.__config.sections()) if re.match("domain_\d+", name)]
        for domain in additional_domains:
            self.__add_domain(
                self.__config.get(domain, "NAME"),
                self.__config.get(domain, "DISPLAY_NAME"),
                self.__config.get(domain, "PROCESSOR_INSTANCE"),
                read_config(self.__config_folder, self.__config.get(domain, "CONFIG")),
            )



    def __source_xsa(self) -> None:
        xsa_path = os.path.join(HDL_DATA_PATH, f"{self.__config.get('flow', 'XSA')}.xsa")
        log.debug(f"Sourcing the platfrom project from XSA file {xsa_path}")

        # Only skip boot BSP creation if explicitly set to false
        has_boot_components = self.__config.getboolean("boot", "BOOT_COMPONENTS", fallback=True)

        # Get the first domain info to pass to platform creation
        # This ensures the domain is properly exported for applications
        first_domain_name = self.__config.get("domain", "NAME")
        first_domain_os = self.__domains[0]._VitisPlatformDomain__config.get("domain", "OS")
        first_domain_cpu = self.__config.get("domain", "PROCESSOR_INSTANCE")

        self.__platform = self.__client.create_platform_component(
            name = f"{self.__name}_platform",
            hw_design = xsa_path,
            os = first_domain_os,
            cpu = first_domain_cpu,
            domain_name = first_domain_name,
            no_boot_bsp = not has_boot_components,
        )


    def __source_fixed(self):
        raise NotImplementedError("Creating a platform project from a fixed source not yet supported")


    def __source_platform(self):
        raise NotImplementedError("Creating a platform project from an existing platform project no yet supported")


    def __source_map(self, source: str) -> None:
        source_map = {
            "xsa": self.__source_xsa,
            "fixed": self.__source_fixed,
            "platform": self.__source_platform,
        }
        source_map[source]()

    
    def __add_domain(self, name: str, display_name: str, processor_instance: str, config: configparser.ConfigParser) -> None:
        new_domain = VitisPlatformDomain(
            client = self.__client,
            platform_name = f"{self.__name}_platform",
            name = name,
            display_name = display_name,
            processor_instance = processor_instance,
            config = config,
            workspace_path = self.__workspace_path,
        )
        self.__domains.append(new_domain)     


    def __create_fsbl(self) -> None:
        has_boot_components = self.__config.getboolean("boot", "BOOT_COMPONENTS")
        if has_boot_components:
            self.__platform.generate_boot_bsp(target_processor="")
        else:
            raise NotImplementedError("Ability to add custom FSBLs not yet supported")


    def create(self) -> None:
        log.info(f"Attempting to create platform project {self.__name}")
        # Create the platform from its source
        # Note: create_platform_component() automatically creates the first domain
        # when os, cpu, and domain_name parameters are provided
        self.__source_map(self.__config.get("flow", "SOURCE"))

        # Create additional platform domains (if any)
        # Skip index 0 since the first domain is already created by create_platform_component()
        for i in range(1, len(self.__domains)):
            self.__domains[i].create()

        # Get the platform component
        self.__platform = self.__client.get_component(name=f"{self.__name}_platform")

        # Configure all domains (including the first one)
        for domain in self.__domains:
            domain.configure()


    def build(self) -> None:
        """Build the platform and all domains."""
        log.info(f"Building platform {self.__name}")
        platform = self.__client.get_component(name=f"{self.__name}_platform")
        status = platform.build()
        log.info(f"Platform {self.__name} build completed with status: {status}")
        return status
