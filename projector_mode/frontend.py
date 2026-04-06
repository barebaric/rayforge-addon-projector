"""
Frontend entry point for projector mode addon.

Registers the projector window action as a toggle in the view menu
and manages the window lifecycle.
"""

import logging
from gettext import gettext as _

from gi.repository import Gio, GLib

from rayforge.core.hooks import hookimpl
from rayforge.ui_gtk.action_registry import MenuPlacement
from .projector_window import ProjectorWindow

logger = logging.getLogger(__name__)

ADDON_NAME = "projector_mode"

_window: ProjectorWindow | None = None
_action: Gio.SimpleAction | None = None


@hookimpl
def main_window_ready(main_window):
    """Store reference to main window for projector window creation."""
    ProjectorWindow.set_main_window(main_window)


@hookimpl
def register_actions(action_registry):
    """Register toggle action for projector mode."""
    global _action

    ProjectorWindow.set_main_window(action_registry.window)

    action = Gio.SimpleAction.new_stateful(
        "toggle_projector_mode", None, GLib.Variant.new_boolean(False)
    )

    def on_change_state(action, value):
        is_visible = value.get_boolean()
        action.set_state(value)
        if is_visible:
            _show_projector_window()
        else:
            _hide_projector_window()

    action.connect("change-state", on_change_state)
    action_registry.register(
        action_name="toggle_projector_mode",
        action=action,
        addon_name=ADDON_NAME,
        label=_("Show Projector Dialog"),
        menu=MenuPlacement(menu_id="view", priority=50),
    )
    _action = action


@hookimpl
def on_unload():
    """Clean up projector window when addon is disabled."""
    global _window, _action
    if _window:
        _window.destroy()
        _window = None
    _action = None


def _show_projector_window():
    global _window
    if _window is None:
        _window = ProjectorWindow()
        _window.connect("close-request", _on_window_close_request)
    _window.present()
    logger.debug("ProjectorWindow presented")


def _hide_projector_window():
    global _window
    if _window:
        _window.destroy()
        _window = None


def _on_window_close_request(window):
    """Sync the toggle action state when window is closed by the user."""
    _hide_projector_window()
    if _action:
        _action.change_state(GLib.Variant.new_boolean(False))
    return True
