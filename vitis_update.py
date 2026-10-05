"""
Vitis Project Update Module

This module provides functionality to update existing Vitis projects based on
configuration file changes, without recreating components from scratch.
"""

import argparse
import configparser
import os
import re
import shutil
from typing import Any


from vitis_logging import Logger
from vitis_paths import read_config, PROJECTS_PATH, TOP_PATH
from vitis_platform import VitisPlatformDomain
from vitis_cmake import (
    parse_multiline_paths, expand_path_variables, create_symlink,
    create_folder_symlink, apply_compiler_config, apply_linker_config
)


vitis_client = Any

log = Logger("update")


class ProjectUpdater:
    """Updates an existing Vitis project based on configuration file changes."""

    def __init__(self, client: vitis_client, args: argparse.Namespace) -> None:
        log.info(f"Initializing ProjectUpdater for {args.name}")
        self.__client = client
        self.__project_name = args.name
        self.__config_folder = os.path.join(TOP_PATH, args.name)
        self.__config_top = read_config(self.__config_folder, "vitis")
        self.__update_platform_only = getattr(args, 'platform', False)
        self.__update_application_only = getattr(args, 'application', False)
        self.__no_build = getattr(args, 'no_build', False)

        # Verify project exists
        self.__verify_project_exists()

    def __verify_project_exists(self) -> None:
        """Verify the project workspace exists."""
        platform_name = f"{self.__config_top.get('platform', 'NAME')}_platform"
        platform_path = os.path.join(PROJECTS_PATH, platform_name)

        if not os.path.exists(platform_path):
            raise FileNotFoundError(
                f"Platform project not found: {platform_path}\n"
                f"Run './Vitis/Do CREATE {self.__project_name}' first to create the project."
            )

    def update(self) -> None:
        """Execute the update process."""
        log.info(f"Beginning project update for {self.__project_name}")

        # Determine what to update
        update_platform = not self.__update_application_only
        update_applications = not self.__update_platform_only

        if update_platform:
            self.__update_platform()

        if update_applications:
            self.__update_applications()

        if not self.__no_build:
            self.__rebuild()

        log.info(f"Project update completed for {self.__project_name}")

    def __update_platform(self) -> None:
        """Update platform and domain configurations."""
        log.info("Updating platform...")

        platform_name = self.__config_top.get('platform', 'NAME')
        platform_config_name = self.__config_top.get('platform', 'CONFIG')
        platform_config = read_config(self.__config_folder, platform_config_name)

        # Get existing platform component
        platform = self.__client.get_component(
            name=f"{platform_name}_platform"
        )

        if platform is None:
            raise RuntimeError(f"Could not retrieve platform: {platform_name}_platform")

        # Update each domain
        self.__update_domains(platform, platform_config)

    def __update_domains(self, platform, platform_config: configparser.ConfigParser) -> None:
        """Update all domains in the platform."""
        platform_name = self.__config_top.get('platform', 'NAME')

        # Get primary domain
        domain_name = platform_config.get("domain", "NAME")
        domain_config_name = platform_config.get("domain", "CONFIG")
        domain_config = read_config(self.__config_folder, domain_config_name)
        processor = platform_config.get("domain", "PROCESSOR_INSTANCE")

        self.__update_single_domain(platform_name, domain_name, processor, domain_config)

        # Handle additional domains
        additional_domains = [s for s in platform_config.sections()
                             if re.match(r"domain_\d+", s)]

        for section in sorted(additional_domains):
            domain_name = platform_config.get(section, "NAME")
            domain_config_name = platform_config.get(section, "CONFIG")
            domain_config = read_config(self.__config_folder, domain_config_name)
            processor = platform_config.get(section, "PROCESSOR_INSTANCE")
            self.__update_single_domain(platform_name, domain_name, processor, domain_config)

    def __update_single_domain(self, platform_name: str, domain_name: str,
                               processor: str,
                               domain_config: configparser.ConfigParser) -> None:
        """Update a single domain with current configuration."""
        log.info(f"Updating domain: {domain_name}")

        # Create a VitisPlatformDomain wrapper to reuse configure logic
        domain_wrapper = VitisPlatformDomain(
            client=self.__client,
            platform_name=f"{platform_name}_platform",
            name=domain_name,
            display_name=domain_config.get("domain", "DISPLAY_NAME", fallback=domain_name),
            processor_instance=processor,
            config=domain_config,
            workspace_path=PROJECTS_PATH
        )

        # Re-run configuration (libraries, drivers, etc.)
        domain_wrapper.configure()

        log.info(f"Domain {domain_name} updated successfully")

    def __update_applications(self) -> None:
        """Update all applications."""
        # Primary application
        if self.__config_top.has_section('application'):
            self.__update_single_application('application')

        # Additional applications
        application_sections = [s for s in self.__config_top.sections()
                               if re.match(r"application_\d+", s)]

        for section in sorted(application_sections):
            self.__update_single_application(section)

    def __update_single_application(self, section: str) -> None:
        """Update a single application."""
        if not self.__config_top.has_option(section, 'NAME'):
            log.warning(f"Application section [{section}] missing NAME, skipping")
            return

        app_name = self.__config_top.get(section, 'NAME')
        app_config_name = self.__config_top.get(section, 'CONFIG')

        log.info(f"Updating application: {app_name}")

        # Verify application exists
        app_path = os.path.join(PROJECTS_PATH, app_name)
        if not os.path.exists(app_path):
            log.error(f"Application not found: {app_path}")
            return

        # Create ApplicationUpdater for this app
        updater = ApplicationUpdater(
            client=self.__client,
            name=app_name,
            config_folder=self.__config_folder,
            config=app_config_name,
            workspace_path=PROJECTS_PATH
        )
        updater.update()

    def __rebuild(self) -> None:
        """Rebuild the project after updates."""
        log.info("Rebuilding project...")

        platform_name = self.__config_top.get('platform', 'NAME')

        # Rebuild platform
        platform = self.__client.get_component(
            name=f"{platform_name}_platform"
        )
        if platform:
            log.info("Rebuilding platform...")
            platform.build()

        # Rebuild applications
        if self.__config_top.has_section('application'):
            app_name = self.__config_top.get('application', 'NAME')
            app = self.__client.get_component(name=app_name)
            if app:
                log.info(f"Rebuilding application: {app_name}")
                app.build()

        # Rebuild additional applications
        application_sections = [s for s in self.__config_top.sections()
                               if re.match(r"application_\d+", s)]

        for section in sorted(application_sections):
            if self.__config_top.has_option(section, 'NAME'):
                app_name = self.__config_top.get(section, 'NAME')
                app = self.__client.get_component(name=app_name)
                if app:
                    log.info(f"Rebuilding application: {app_name}")
                    app.build()


class ApplicationUpdater:
    """Updates an existing Vitis application based on configuration changes."""

    def __init__(self, client: vitis_client, name: str, config_folder: str,
                 config: str, workspace_path: str) -> None:
        self.__client = client
        self.__name = name
        self.__config_folder = config_folder
        self.__config = read_config(config_folder, config)
        self.__workspace_path = workspace_path
        self.__project_src_dir = os.path.join(workspace_path, name, "src")

    def update(self) -> None:
        """Update the application configuration."""
        log.info(f"Updating application {self.__name}")

        # Update sources (symlinks)
        self.__update_source_files()
        self.__update_source_folders()

        # Update UserConfig.cmake and the linker script symlink
        self.__update_userconfig()

        log.info(f"Application {self.__name} update complete")

    def __update_source_files(self) -> None:
        """Update individual source file symlinks.

        Always scans for existing file symlinks and removes stale ones,
        even if source_files is not configured (empty desired set).
        """
        # Build desired file set (may be empty if source_files not configured)
        desired_files = {}
        if self.__config.has_option("compiler", "source_files"):
            sources = self.__config.get("compiler", "source_files").strip()
            if sources:
                source_list = parse_multiline_paths(sources)
                expanded_sources = [expand_path_variables(s) for s in source_list]
                desired_files = {os.path.basename(s): s for s in expanded_sources}

        # Get current symlinks for source files
        current_file_symlinks = self.__get_current_file_symlinks()

        # Remove stale file symlinks (files not in desired set)
        for link_name in list(current_file_symlinks.keys()):
            if link_name not in desired_files:
                link_path = os.path.join(self.__project_src_dir, link_name)
                self.__remove_symlink(link_path, f"source file {link_name}")

        # Add new symlinks
        for filename, source_path in desired_files.items():
            symlink_path = os.path.join(self.__project_src_dir, filename)
            if not os.path.exists(symlink_path) and not os.path.islink(symlink_path):
                log.info(f"Adding source file: {filename}")
                create_symlink(source_path, symlink_path)

    def __update_source_folders(self) -> None:
        """Update source folder symlinks.

        Always scans for existing folder symlinks and removes stale ones,
        even if source_folders is not configured (empty desired set).
        """
        # Build desired folder set (may be empty if source_folders not configured)
        desired_folders = {}
        if self.__config.has_option("compiler", "source_folders"):
            folders = self.__config.get("compiler", "source_folders").strip()
            if folders:
                folder_list = parse_multiline_paths(folders)
                expanded_folders = [expand_path_variables(f) for f in folder_list]
                desired_folders = {os.path.basename(f): f for f in expanded_folders}

        # Get current folder symlinks
        current_folder_symlinks = self.__get_current_folder_symlinks()

        log.debug(f"Current folder symlinks: {list(current_folder_symlinks.keys())}")
        log.debug(f"Desired folder symlinks: {list(desired_folders.keys())}")

        # Remove stale folder symlinks (folders not in desired set)
        for link_name in list(current_folder_symlinks.keys()):
            if link_name not in desired_folders:
                link_path = os.path.join(self.__project_src_dir, link_name)
                self.__remove_symlink(link_path, f"source folder {link_name}")

        # Add new folder symlinks
        for folder_name, folder_path in desired_folders.items():
            if folder_name not in current_folder_symlinks:
                log.info(f"Adding source folder: {folder_name}")
                create_folder_symlink(folder_path, folder_name, self.__project_src_dir)

    def __get_current_file_symlinks(self) -> dict:
        """Get current file symlinks in project src directory."""
        symlinks: dict = {}
        if not os.path.exists(self.__project_src_dir):
            return symlinks

        for item in os.listdir(self.__project_src_dir):
            item_path = os.path.join(self.__project_src_dir, item)
            # Check if it's a file (symlink or actual file)
            if os.path.isfile(item_path) or (os.path.islink(item_path) and not os.path.isdir(item_path)):
                # Check if it's a source file (not lscript.ld or cmake files)
                if item.endswith(('.c', '.S', '.h')):
                    if os.path.islink(item_path):
                        symlinks[item] = os.readlink(item_path)
                    else:
                        symlinks[item] = item_path

        return symlinks

    def __get_current_folder_symlinks(self) -> dict:
        """Get current folder symlinks in project src directory."""
        symlinks: dict = {}
        if not os.path.exists(self.__project_src_dir):
            return symlinks

        # Known non-source directories to ignore
        ignore_dirs = {'.cache', '.compile_commands', 'linker_files', 'build'}

        for item in os.listdir(self.__project_src_dir):
            item_path = os.path.join(self.__project_src_dir, item)
            if item in ignore_dirs:
                continue
            if os.path.islink(item_path) and os.path.isdir(item_path):
                symlinks[item] = os.readlink(item_path)
            elif os.path.isdir(item_path) and not os.path.islink(item_path):
                # Could be a recreated folder structure (Windows fallback)
                # Only include if it contains source files
                has_sources = False
                for root, dirs, files in os.walk(item_path):
                    if any(f.endswith(('.c', '.S')) for f in files):
                        has_sources = True
                        break
                if has_sources:
                    symlinks[item] = item_path

        return symlinks

    def __remove_symlink(self, path: str, description: str) -> None:
        """Remove a symlink or directory."""
        try:
            if os.path.islink(path):
                os.remove(path)
                log.info(f"Removed stale symlink: {description}")
            elif os.path.isdir(path):
                shutil.rmtree(path)
                log.info(f"Removed stale directory: {description}")
            elif os.path.isfile(path):
                os.remove(path)
                log.info(f"Removed stale file: {description}")
        except Exception as e:
            log.warning(f"Failed to remove {description}: {e}")

    def __update_userconfig(self) -> None:
        """Update UserConfig.cmake and the linker script symlink with current configuration.

        Calls the same functions as Do CREATE, so every [compiler] and [linker]
        key that CREATE applies is applied here too.
        """
        userconfig_path = os.path.join(self.__project_src_dir, "UserConfig.cmake")

        if not os.path.exists(userconfig_path):
            log.warning(f"UserConfig.cmake not found: {userconfig_path}")
            return

        apply_compiler_config(userconfig_path, self.__config)
        apply_linker_config(userconfig_path, self.__config)

        log.info("UserConfig.cmake updated")
