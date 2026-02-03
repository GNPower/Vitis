import argparse
from functools import partial
import sys
from typing import TypeVar

# Add package: Vitis Python CLI
import vitis  # type: ignore
vitis_client = TypeVar('vitis_client')

from vitis_logging import *
from vitis_create import create_workspace, ProjectCreator
from vitis_build import activate_project, build_project_ninja, build_project_vitis, build_project_all, build_project_all_ninja
from vitis_update import ProjectUpdater


def project_creator_wrapper(client: vitis_client, args: argparse.Namespace) -> None: # pyright: ignore[reportInvalidTypeVarUse]
    creator = ProjectCreator(client, args)
    creator.create()


def create_platform_wrapper(client: vitis_client, args: argparse.Namespace) -> None: # pyright: ignore[reportInvalidTypeVarUse]
    pass


def create_application_wrapper(client: vitis_client, args: argparse.Namespace) -> None: # pyright: ignore[reportInvalidTypeVarUse]
    pass


def activate_project_wrapper(args: argparse.Namespace) -> None:
    """Wrapper for ACTIVATE command (no Vitis client needed)."""
    success = activate_project(args.name)
    if not success:
        sys.exit(1)


def build_project_wrapper(args: argparse.Namespace, client: vitis_client = None) -> None: # pyright: ignore[reportInvalidTypeVarUse]
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


def update_project_wrapper(client: vitis_client, args: argparse.Namespace) -> None:  # pyright: ignore[reportInvalidTypeVarUse]
    """Wrapper for UPDATE command."""
    updater = ProjectUpdater(client, args)
    updater.update()


def launch_client():
    parser = argparse.ArgumentParser(
        prog="Vitis Workspace Builder"
    )
    subparser = parser.add_subparsers(dest='command')

    # CREATE command
    create = subparser.add_parser("CREATE", help="Creates a project and all constituant parts from configuration files")
    create.add_argument("name", type=str, help="Name of the project, must be a subfolder in the Top directory")
    create.set_defaults(func=project_creator_wrapper, needs_client=True)

    # CREATE_PLATFORM command
    create_p = subparser.add_parser("CREATE_PLATFORM", help="Creates a platform project")
    create_p.add_argument("name", type=str, help="Base name of the platform project. '_platform' will be appended")
    create_p.set_defaults(func=create_platform_wrapper, needs_client=True)

    # CREATE_APP command
    create_a = subparser.add_parser("CREATE_APP", help="Creates an application project")
    create_a.add_argument("name", type=str, help="Base name of the application project. '_application' will be appended")
    create_a.add_argument("-p", "--platform", type=str, help="Name of the platform project to reference, specified without the '_platform' suffix")
    create_a.set_defaults(func=create_application_wrapper, needs_client=True)

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
                       help="Use system ninja from PATH instead of Vitis-bundled (requires ninja >=1.5, ninja builds only)")
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

    # Check if command was provided
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    needs_client = getattr(args, 'needs_client', True)

    # Special case: BUILD with --tools ninja doesn't need client
    if args.command == 'BUILD' and args.tools == 'ninja':
        needs_client = False

    if needs_client:
        # Create a Vitis client object
        log.info("Creating the Vitis client")
        client = vitis.create_client()

        log.info("Creating SDK workspace")
        create_workspace(client)

        # Call with client for commands that need it
        if args.command == 'BUILD':
            args.func(args=args, client=client)
        else:
            args.func(client=client, args=args)
    else:
        # Commands that don't need Vitis client
        log.info(f"Running {args.command} (no Vitis client required)")
        if args.command == 'BUILD':
            args.func(args=args, client=None)
        else:
            args.func(args=args)


if __name__ == '__main__':
    cleanupLatestLog()
    log = Logger("launch")
    _vitis_client_created = False

    try:
        # Check if command needs Vitis client before launching
        import sys as _sys
        _args = _sys.argv[1:] if len(_sys.argv) > 1 else []
        _command = _args[0] if _args else None
        _needs_vitis = True

        if _command == 'ACTIVATE':
            _needs_vitis = False
        elif _command == 'BUILD' and '--tools' in _args:
            _tools_idx = _args.index('--tools')
            if _tools_idx + 1 < len(_args) and _args[_tools_idx + 1] == 'ninja':
                _needs_vitis = False

        launch_client()
        _vitis_client_created = _needs_vitis
    except Exception as e:
        log.critical(f"The following error causes the Vitis client to exit:\n{e}")
        _vitis_client_created = True

    log.info("Finished processing")
    sys.stdout.flush()

    if _vitis_client_created:
        log.info("Disposing of Vitis client")
        vitis.dispose()
