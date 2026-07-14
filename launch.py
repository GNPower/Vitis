import argparse
import sys
from typing import Any

# Add package: Vitis Python CLI
import vitis  # type: ignore

from vitis_logging import Logger, cleanupLatestLog
from vitis_create import create_workspace, ProjectCreator
from vitis_build import (
    activate_project,
    build_project_all,
    build_project_all_ninja,
    build_project_ninja,
    build_project_vitis,
)
from vitis_update import ProjectUpdater

vitis_client = Any

log = Logger("launch")


def project_creator_wrapper(client: vitis_client, args: argparse.Namespace) -> None:
    creator = ProjectCreator(client, args)
    creator.create()


def create_platform_wrapper(args: argparse.Namespace) -> None:
    """Roadmap placeholder for standalone platform creation (see ROADMAP.md)."""
    log.error("CREATE_PLATFORM is not implemented yet. Use 'Do CREATE <name>'. See ROADMAP.md.")
    sys.exit(1)


def create_application_wrapper(args: argparse.Namespace) -> None:
    """Roadmap placeholder for standalone application creation (see ROADMAP.md)."""
    log.error("CREATE_APP is not implemented yet. Use 'Do CREATE <name>'. See ROADMAP.md.")
    sys.exit(1)


def activate_project_wrapper(args: argparse.Namespace) -> None:
    """Wrapper for ACTIVATE command (no Vitis client needed)."""
    success = activate_project(args.name)
    if not success:
        sys.exit(1)


def build_project_wrapper(args: argparse.Namespace, client: vitis_client = None) -> None:
    """Wrapper for BUILD command."""

    # Check if building entire project
    if args.all:
        # Determine build tool
        tools = args.tools

        if tools == "ninja":
            # Ninja-based full project build
            use_system = getattr(args, 'system_ninja', False)
            exit_code = build_project_all_ninja(
                args.name,
                clean=args.clean,
                use_system_ninja=use_system
            )
        else:
            # Vitis-based full project build
            if client is None:
                log.error("--all with --tools vitis requires Vitis client")
                sys.exit(1)
            exit_code = build_project_all(client, args.name)

        # Activate project after build (unless --no-activate)
        if exit_code == 0 and args.activate:
            success = activate_project(args.name)
            sys.exit(0 if success else 1)
        else:
            sys.exit(exit_code)

    # Single application build
    tools = args.tools

    if tools == "ninja":
        # Direct ninja build
        use_system = getattr(args, 'system_ninja', False)
        exit_code = build_project_ninja(args.name, clean=args.clean, use_system_ninja=use_system)
    else:
        # Vitis server build
        exit_code = build_project_vitis(client, args.name)

    # Activate the project after build (unless --no-activate)
    if exit_code == 0 and args.activate:
        activate_project(args.name)

    if exit_code != 0:
        sys.exit(exit_code)


def update_project_wrapper(client: vitis_client, args: argparse.Namespace) -> None:
    """Wrapper for UPDATE command."""
    updater = ProjectUpdater(client, args)
    updater.update()


def _needs_vitis_client(args: argparse.Namespace) -> bool:
    """Whether a command needs the Vitis client.

    A command opts out via ``needs_client=False``. Additionally, a ninja BUILD
    never needs the client because it runs the compiler directly.
    """
    if not getattr(args, 'needs_client', True):
        return False
    if args.command == 'BUILD' and args.tools == 'ninja':
        return False
    return True


def _dispatch(args: argparse.Namespace, client: vitis_client) -> None:
    """Call the selected command with the arguments its wrapper expects."""
    if args.command == 'BUILD':
        args.func(args=args, client=client)
    elif client is not None:
        args.func(client=client, args=args)
    else:
        args.func(args=args)


def launch_client() -> None:
    parser = argparse.ArgumentParser(
        prog="Vitis Workspace Builder"
    )
    subparser = parser.add_subparsers(dest='command')

    # CREATE command
    create = subparser.add_parser("CREATE", help="Creates a project and all constituent parts from configuration files")
    create.add_argument("name", type=str, help="Name of the project, must be a subfolder in the Top directory")
    create.set_defaults(func=project_creator_wrapper, needs_client=True)

    # CREATE_PLATFORM command (roadmap; not implemented yet)
    create_p = subparser.add_parser("CREATE_PLATFORM", help="Creates a platform project (not implemented yet)")
    create_p.add_argument("name", type=str, help="Base name of the platform project. '_platform' will be appended")
    create_p.set_defaults(func=create_platform_wrapper, needs_client=False)

    # CREATE_APP command (roadmap; not implemented yet)
    create_a = subparser.add_parser("CREATE_APP", help="Creates an application project (not implemented yet)")
    create_a.add_argument("name", type=str,
                          help="Base name of the application project. '_application' will be appended")
    create_a.add_argument("-p", "--platform", type=str,
                          help="Name of the platform project to reference, specified without the '_platform' suffix")
    create_a.set_defaults(func=create_application_wrapper, needs_client=False)

    # ACTIVATE command
    activate = subparser.add_parser("ACTIVATE", help="Sets a project as active for IDE tooling (clangd IntelliSense)")
    activate.add_argument("name", type=str, help="Name of the project to activate")
    activate.set_defaults(func=activate_project_wrapper, needs_client=False)

    # BUILD command
    build = subparser.add_parser("BUILD", help="Builds a project using Vitis server or directly with Ninja")
    build.add_argument("name", type=str, help="Name of the application to build, or project name with --all flag")
    build.add_argument("--tools", type=str, choices=["vitis", "ninja"], default="vitis",
                       help="Build tool to use: 'vitis' (default) or 'ninja' (direct, faster)")
    build.add_argument("--all", action="store_true",
                       help="Build entire project (platform + all applications)")
    build.add_argument("--clean", action="store_true", help="Clean before building (ninja only)")
    build.add_argument("--system-ninja", action="store_true", dest="system_ninja",
                       help="Use system ninja from PATH instead of Vitis-bundled (ninja builds, >=1.5)")
    build.add_argument("--no-activate", dest="activate", action="store_false", default=True,
                       help="Don't activate the project after building")
    build.set_defaults(func=build_project_wrapper, needs_client=True)

    # UPDATE command
    update = subparser.add_parser("UPDATE", help="Updates an existing project based on config file changes")
    update.add_argument("name", type=str, help="Name of the project to update")
    update.add_argument("--platform", action="store_true", help="Update platform/domains only")
    update.add_argument("--application", action="store_true", help="Update application(s) only")
    update.add_argument("--no-build", action="store_true", dest="no_build", help="Skip rebuild after updating")
    update.set_defaults(func=update_project_wrapper, needs_client=True)

    args = parser.parse_args()

    # No command provided: show help and exit non-zero.
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    needs_client = _needs_vitis_client(args)

    # Create Vitis client only when the command needs it, and dispose of it afterwards.
    client = None
    try:
        if needs_client:
            log.info("Creating the Vitis client")
            client = vitis.create_client()
            log.info("Creating SDK workspace")
            create_workspace(client)
        else:
            log.info(f"Running {args.command} (no Vitis client required)")
        _dispatch(args, client)
    finally:
        if client is not None:
            log.info("Disposing of Vitis client")
            vitis.dispose()


if __name__ == '__main__':
    cleanupLatestLog()

    try:
        launch_client()
    except SystemExit:
        raise
    except Exception as e:
        log.critical(f"The following error causes the Vitis client to exit:\n{e}")
        sys.exit(1)
    finally:
        log.info("Finished processing")
        sys.stdout.flush()
