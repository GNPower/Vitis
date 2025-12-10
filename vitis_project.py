import argparse
from functools import partial
import inspect
import os
from pathlib import Path
import shutil
import sys
from typing import TypeVar

# Add package: Vitis Python CLI
import vitis # type: ignore
vitis_client = TypeVar('vitis_client')

from vitis_logging import Logger
from Vitis.vitis_paths import parentdir, PROJECTS_PATH, HDL_DATA_PATH


log = Logger("project")


def create_project(client: vitis_client, project_name: str) -> None: # pyright: ignore[reportInvalidTypeVarUse]
    # TODO: this
    pass
