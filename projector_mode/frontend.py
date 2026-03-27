"""
Frontend entry point for projector mode addon.

Registers the projector window action and manages the window lifecycle.
"""

import logging
from gettext import gettext as _

from gi.repository import Gio

from rayforge.core.hooks import hookimpl
from rayforge.ui_gtk.action_registry import MenuPlacement
from .projector_window import ProjectorWindow

logger = logging.getLogger(__name__)

ADDON_NAME = "projector_mode"

_window: ProjectorWindow | None = None
_main_window = None


@hookimpl
def main_window_ready(main_window):
    """Store reference to main window for projector window creation."""
    global _main_window
    _main_window = main_window
    ProjectorWindow.set_main_window(main_window)


@hookimpl
def register_actions(action_registry):
    """Register toggle action for projector mode."""

    def on_activate(action, param) -> None:
        _toggle_projector_window()

    action = Gio.SimpleAction.new("toggle_projector_mode", None)
    action.connect("activate", on_activate)
    action_registry.register(
        action_name="toggle_projector_mode",
        action=action,
        addon_name=ADDON_NAME,
        label=_("Projector Mode"),
        menu=MenuPlacement(menu_id="machine", priority=100),
    )


@hookimpl
def on_unload():
    """Clean up projector window when addon is disabled."""
    global _window
    if _window:
        _window.destroy()
        _window = None


def _toggle_projector_window():
    global _window
    logger.debug(
        f"_toggle_projector_window called, _window={_window}, "
        f"visible={_window.get_visible() if _window else 'N/A'}"
    )
    if _window and _window.get_visible():
        _window.destroy()
        _window = None
    else:
        _window = ProjectorWindow()
        _window.present()
        logger.debug("ProjectorWindow presented")
