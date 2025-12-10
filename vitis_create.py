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
from vitis_paths import read_config, parentdir, PROJECTS_PATH, TOP_PATH
from vitis_platform import VitisPlatform
from vitis_application import VitisApplication


log = Logger("create")


def create_workspace(client: vitis_client) -> None: # pyright: ignore[reportInvalidTypeVarUse]
    log.info(f"Attempting to make workspace in {PROJECTS_PATH}")
    Path(os.path.join(parentdir, "Projects")).mkdir(parents=True, exist_ok=True)
    client.set_workspace( # type: ignore
        path=PROJECTS_PATH
    )


class ProjectCreator(object):

    def __init__(self, client: vitis_client, args: argparse.Namespace) -> None: # pyright: ignore[reportInvalidTypeVarUse]
        log.info(f"Defining a ProjectCreator with name {args.name}")
        self.__client = client
        self.__config_folder = os.path.join(TOP_PATH, args.name)
        self.__config_top = read_config(self.__config_folder, "vitis")
        self.__platform = None
        self.__applications: List[VitisApplication] = []       


    def create(self) -> None:
        log.info(f"Beginning Project creation...")
        self.__platform = VitisPlatform(
            self.__client,
            self.__config_top.get('platform', 'NAME'),
            self.__config_top.get('platform', 'DESCRIPTION'),
            self.__config_folder,
            self.__config_top.get('platform', 'CONFIG'),
            PROJECTS_PATH,
        )
        self.__platform.create()

        self.__create_applications()

        log.info("Building platform...")
        self.__platform.build()

        for app in self.__applications:
            log.info(f"Building application {app._VitisApplication__name}...") # type: ignore
            app.build()


    def __create_applications(self) -> None:
        """Create all applications defined in the configuration."""
        if self.__config_top.has_section('application'):
            self.__create_single_application('application')

        # Find all additional application sections (application_1, application_2, etc.)
        application_sections = [s for s in self.__config_top.sections()
                                if re.match(r"application_\d+", s)]

        for section in sorted(application_sections):
            self.__create_single_application(section)


    def __create_single_application(self, section: str) -> None:
        """Create a single application from a config section."""
        if not self.__config_top.has_option(section, 'NAME'):
            log.warning(f"Application section [{section}] missing required field 'NAME', skipping")
            return

        if not self.__config_top.has_option(section, 'CONFIG'):
            log.warning(f"Application section [{section}] missing required field 'CONFIG', skipping")
            return

        app_name = self.__config_top.get(section, 'NAME')
        app_config = self.__config_top.get(section, 'CONFIG')
        app_description = self.__config_top.get(section, 'DESCRIPTION',
                                                fallback=f"{app_name} application component")

        log.info(f"Creating application {app_name}")

        application = VitisApplication(
            client=self.__client,
            name=app_name,
            description=app_description,
            config_folder=self.__config_folder,
            config=app_config,
            workspace_path=PROJECTS_PATH,
        )

        application.create()
        application.configure()

        self.__applications.append(application)
        

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog="Vitis Workspace Builder"
    )
    parser.add_argument("name", type=str, help="Name of the project, must be a subfolder in the Top directory")
    args = parser.parse_args()
    project_creator = ProjectCreator(None, args)
    project_creator.create()
