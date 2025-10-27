import argparse
from functools import partial
import sys
from typing import TypeVar

# Add package: Vitis Python CLI
import vitis  # type: ignore
vitis_client = TypeVar('vitis_client')

from vitis_logging import *
from vitis_create import create_workspace, ProjectCreator


def project_creator_wrapper(client: vitis_client, args: argparse.Namespace) -> None:
    creator = ProjectCreator(client, args)
    creator.create()


def create_platform_wrapper(client: vitis_client, args: argparse.Namespace) -> None:
    pass


def create_application_wrapper(client: vitis_client, args: argparse.Namespace) -> None:
    pass


def launch_client():
    parser = argparse.ArgumentParser(
        prog="Vitis Workspace Builder"
    )
    subparser = parser.add_subparsers()

    create = subparser.add_parser("CREATE", help="Creates a project and all constituant parts from configuration files")
    create.add_argument("name", type=str, help="Name of the project, must be a subfolder in the Top directory")
    create.set_defaults(func=project_creator_wrapper)

    create_p = subparser.add_parser("CREATE_PLATFORM", help="Creates a platform project")
    create_p.add_argument("name", type=str, help="Base name of the platform project. '_platform' will be appended")
    create_p.set_defaults(func=create_platform_wrapper)

    create_a = subparser.add_parser("CREATE_APP", help="Creates an application project")
    create_a.add_argument("name", type=str, help="Base name of the application project. '_application' will be appended")
    create_a.add_argument("-p", "--platform", type=str, help="Name of the platform project to reference, specified without the '_platform' suffix")
    create_a.set_defaults(func=create_application_wrapper)

    args = parser.parse_args()

    # Create a Vitis client object
    log.info("Creating the Vitis client")
    client = vitis.create_client() 

    log.info("Creating SDK workspace")
    create_workspace(client)
    
    args.func(client=client, args=args)


if __name__ == '__main__':
    cleanupLatestLog()
    log = Logger("launch")

    try:
        launch_client()
    except Exception as e:
        log.critical(f"The following error causes the Vitis client to exit:\n{e}")

    log.info("Finished processing, disposing of Vitis client")
    sys.stdout.flush()
    vitis.dispose()
