"""
Placeholder for standalone project scaffolding.

A future entry point will create a bare project skeleton independently of the
full CREATE flow implemented in ``vitis_create``. It is not wired into ``Do``
yet.
"""

from typing import Any

from vitis_logging import Logger

vitis_client = Any

log = Logger("project")


def create_project(client: vitis_client, project_name: str) -> None:
    """Create a bare project scaffold. Not implemented yet (see ROADMAP.md)."""
    raise NotImplementedError(
        "create_project() is not implemented yet. Use 'Do CREATE <name>' for the full "
        "project-creation flow. Standalone scaffolding is tracked in ROADMAP.md."
    )
