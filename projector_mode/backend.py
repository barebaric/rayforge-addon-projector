"""
Backend entry point for projector mode addon.

This module exists to satisfy the addon system's requirement for a backend
module. All actual functionality is in the frontend.
"""

from rayforge.core.hooks import hookimpl

ADDON_NAME = "projector_mode"


@hookimpl
def register_actions(action_registry):
    pass
