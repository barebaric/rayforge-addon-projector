"""
Projector window for displaying cutting area on external display.
"""

import logging
from gettext import gettext as _
from typing import TYPE_CHECKING, Optional

from gi.repository import Gdk, Gtk

from rayforge.context import get_context
from rayforge.ui_gtk.shared.gtk import apply_css
from .projector_surface import ProjectorSurface

if TYPE_CHECKING:
    from rayforge.ui_gtk.mainwindow import MainWindow

logger = logging.getLogger(__name__)

PROJECTOR_CSS = """
window.projector-window {
    background-color: black;
}
window.projector-window headerbar {
    background-color: #333;
    color: white;
}
window.projector-window button {
    color: white;
}
"""


class ProjectorWindow(Gtk.ApplicationWindow):
    _main_window: Optional["MainWindow"] = None

    @classmethod
    def set_main_window(cls, window: Optional["MainWindow"]):
        cls._main_window = window
        logger.debug(f"ProjectorWindow.set_main_window called with {window}")

    def __init__(self):
        super().__init__(
            title=_("Projector Mode"),
            default_width=1024,
            default_height=768,
            transient_for=None,
            modal=False,
            resizable=True,
        )

        self.add_css_class("projector-window")
        apply_css(PROJECTOR_CSS)

        self._is_fullscreen = False
        self._signal_ids = []
        self.surface: Optional[ProjectorSurface] = None

        logger.debug("ProjectorWindow.__init__ called")

        if self._main_window is None:
            logger.error(
                "Main window not set, cannot create projector surface"
            )
            return

        self._setup_ui()
        self._connect_signals()
        logger.debug("ProjectorWindow setup complete")

    def _setup_ui(self):
        assert self._main_window is not None, "Main window must be set"

        header = Gtk.HeaderBar()

        self.opacity_btn = Gtk.Button()
        self._update_opacity_button_icon(1.0)
        self.opacity_btn.connect("clicked", self._on_cycle_opacity)
        header.pack_start(self.opacity_btn)

        fullscreen_btn = Gtk.Button(label=_("Fullscreen"))
        fullscreen_btn.connect("clicked", self._on_fullscreen)
        header.pack_end(fullscreen_btn)

        self.set_titlebar(header)

        editor = self._main_window.doc_editor
        config = get_context().config
        machine = config.machine

        logger.debug(f"Creating ProjectorSurface with machine={machine}")

        self.surface = ProjectorSurface(
            editor=editor,
            machine=machine,
        )

        self.set_child(self.surface)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        self.surface.update_from_doc()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _connect_signals(self):
        assert self._main_window is not None, "Main window must be set"
        assert self.surface is not None, "Surface must be set"

        editor = self._main_window.doc_editor
        doc = editor.doc

        sig_id = doc.updated.connect(self._on_doc_changed)
        self._signal_ids.append((doc.updated, sig_id))

        sig_id = doc.descendant_added.connect(self._on_doc_changed)
        self._signal_ids.append((doc.descendant_added, sig_id))

        sig_id = doc.descendant_removed.connect(self._on_doc_changed)
        self._signal_ids.append((doc.descendant_removed, sig_id))

        sig_id = doc.descendant_updated.connect(self._on_doc_changed)
        self._signal_ids.append((doc.descendant_updated, sig_id))

        config = get_context().config
        if config.machine:
            sig_id = config.machine.wcs_updated.connect(self._on_wcs_updated)
            self._signal_ids.append((config.machine.wcs_updated, sig_id))

    def _on_doc_changed(self, sender, **kwargs):
        if self.surface:
            self.surface.update_from_doc()
            self.surface.queue_draw()

    def _on_wcs_updated(self, machine):
        if self.surface:
            self.surface.update_work_origin()
            self.surface.queue_draw()

    def _on_fullscreen(self, btn):
        if self._is_fullscreen:
            self.unfullscreen()
            self._is_fullscreen = False
            btn.set_label(_("Fullscreen"))
        else:
            self.fullscreen()
            self._is_fullscreen = True
            btn.set_label(_("Exit Fullscreen"))

    def _on_cycle_opacity(self, btn):
        opacities = [1.0, 0.8, 0.6, 0.4]
        current = self.get_opacity()
        try:
            idx = opacities.index(current)
            next_idx = (idx + 1) % len(opacities)
        except ValueError:
            next_idx = 0
        new_opacity = opacities[next_idx]
        self.set_opacity(new_opacity)
        self._update_opacity_button_icon(new_opacity)

    def _update_opacity_button_icon(self, opacity: float):
        labels = {
            1.0: _("100%"),
            0.8: _("80%"),
            0.6: _("60%"),
            0.4: _("40%"),
        }
        self.opacity_btn.set_label(labels.get(opacity, _("100%")))

    def close(self):
        for signal, sig_id in self._signal_ids:
            try:
                signal.disconnect(sig_id)
            except Exception:
                pass
        self._signal_ids.clear()

        if self.surface:
            self.surface.cleanup()

        super().close()
