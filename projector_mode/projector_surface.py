"""
Projector surface for rendering cutting area on projector display.

A simplified canvas that shows workpieces with ops overlays,
work origin, and machine extent frame - without selection handles,
grid, or camera overlay.
"""

import logging
from typing import TYPE_CHECKING, Optional, cast

import cairo
import numpy as np

from rayforge.core.layer import Layer
from rayforge.core.stock import StockItem
from rayforge.core.workpiece import WorkPiece
from rayforge.core.group import Group
from rayforge.machine.models.machine import Machine
from rayforge.ui_gtk.canvas.worldsurface import WorldSurface
from rayforge.ui_gtk.canvas2d.elements.layer import LayerElement
from rayforge.ui_gtk.canvas2d.elements.work_origin import WorkOriginElement
from rayforge.ui_gtk.canvas2d.elements.axis_extent_frame import (
    AxisExtentFrameElement,
)
from rayforge.ui_gtk.canvas2d.elements.workpiece import (
    WorkPieceElement,
    OPS_MARGIN_PX,
)

if TYPE_CHECKING:
    from rayforge.doceditor.editor import DocEditor

logger = logging.getLogger(__name__)


class ProjectorSurface(WorldSurface):
    """
    A simplified canvas for projector display.

    Shows workpieces with ops overlays, work origin, and machine extent frame.
    Does not include selection handles, grid, axis labels, or camera overlay.
    """

    def __init__(
        self,
        editor: "DocEditor",
        machine: Optional[Machine],
    ):
        self.editor = editor
        self.machine = None
        self._tabs_globally_visible = True

        width_mm, height_mm = 100.0, 100.0
        coordinate_space = None
        if machine:
            width_mm, height_mm = (
                float(machine.axis_extents[0]),
                float(machine.axis_extents[1]),
            )
            coordinate_space = machine.get_coordinate_space()

        super().__init__(
            width_mm=width_mm,
            height_mm=height_mm,
            show_grid=False,
            show_axis=False,
            coordinate_space=coordinate_space,
        )

        self.set_focus_on_click(False)

        self.root.background = (0, 0, 0, 1)

        self._work_origin_element = WorkOriginElement()
        self.root.add(self._work_origin_element)

        self._extent_frame_element = AxisExtentFrameElement()
        self._extent_frame_element.set_visible(False)
        self.root.add(self._extent_frame_element)

        self._tracked_axis_extents = (0.0, 0.0)

        self.set_machine(machine)

    @property
    def doc(self):
        return self.editor.doc

    def get_global_tab_visibility(self) -> bool:
        """Returns the current global visibility state for tab handles."""
        return self._tabs_globally_visible

    def are_workpieces_visible(self) -> bool:
        """Returns True if the workpiece base images should be visible."""
        return True

    def set_machine(self, machine: Optional[Machine]):
        if self.machine is machine:
            return

        if self.machine:
            self.machine.changed.disconnect(self._on_machine_changed)
            self.machine.wcs_updated.disconnect(self._on_wcs_updated)

        self.machine = machine

        if self.machine:
            self.machine.changed.connect(self._on_machine_changed)
            self.machine.wcs_updated.connect(self._on_wcs_updated)
            self._tracked_axis_extents = self.machine.axis_extents
            self.reset_view()
            self._on_wcs_updated(self.machine)
        else:
            self._tracked_axis_extents = (100.0, 100.0)
            self.set_size(100.0, 100.0)
            super().reset_view()

    def _on_machine_changed(self, machine: Optional[Machine]):
        if not machine:
            return

        extent_w, extent_h = machine.axis_extents
        if (extent_w, extent_h) != self._tracked_axis_extents:
            self._tracked_axis_extents = (extent_w, extent_h)
            self.reset_view()
        else:
            self._update_extent_frame()
            self._on_wcs_updated(machine)

    def _on_wcs_updated(self, machine: Machine):
        space = machine.get_coordinate_space()

        if machine.wcs_origin_is_workarea_origin:
            canvas_x, canvas_y = space.get_workarea_origin_in_machine()
        else:
            wcs_x, wcs_y, _ = machine.get_active_wcs_offset()
            canvas_x, canvas_y = self._machine_coords_to_canvas(wcs_x, wcs_y)

        self._work_origin_element.set_pos(canvas_x, canvas_y)
        self._work_origin_element.set_visible(True)
        self.queue_draw()

    def _machine_coords_to_canvas(
        self, m_x: float, m_y: float
    ) -> tuple[float, float]:
        if self.machine:
            space = self.machine.get_coordinate_space()
            if space.reverse_x:
                m_x = -m_x
            if space.reverse_y:
                m_y = -m_y
            return space.transform_point_to_world(m_x, m_y, space.extents)
        return m_x, m_y

    def update_work_origin(self):
        if self.machine:
            self._on_wcs_updated(self.machine)

    def reset_view(self):
        if not self.machine:
            self._tracked_axis_extents = (100, 100)
            self.set_size(100.0, 100.0)
            super().reset_view()
            return

        width_mm, height_mm = self.machine.axis_extents
        self._tracked_axis_extents = (width_mm, height_mm)
        self.set_size(float(width_mm), float(height_mm))

        space = self.machine.get_coordinate_space()
        self._work_origin_element.set_coordinate_space(space)

        self._update_extent_frame()

        super().reset_view()

    def _update_extent_frame(self):
        if not self.machine:
            self._extent_frame_element.set_visible(False)
            return

        extent_w, extent_h = self.machine.axis_extents

        if (extent_w, extent_h) != (self.width_mm, self.height_mm):
            self.set_size(float(extent_w), float(extent_h))

        self._extent_frame_element.set_size(float(extent_w), float(extent_h))
        self._extent_frame_element.set_pos(0.0, 0.0)
        self._extent_frame_element.set_visible(True)

        self.queue_draw()

    def update_from_doc(self):
        """
        Synchronizes the canvas elements with the document model.
        """
        doc = self.doc

        doc_layers_set = set(doc.layers)
        current_elements = {
            elem.data: elem for elem in self.find_by_type(LayerElement)
        }

        for layer, elem in current_elements.items():
            if layer not in doc_layers_set:
                elem.remove()

        for layer in doc.layers:
            if layer not in current_elements:
                self._create_and_add_layer_element(layer)

        layer_order_map = {layer: i for i, layer in enumerate(doc.layers)}

        def sort_key(element):
            if isinstance(element, LayerElement):
                return (
                    layer_order_map.get(element.data, len(layer_order_map))
                    + 100
                )
            if isinstance(element, WorkOriginElement):
                return -2
            if isinstance(element, AxisExtentFrameElement):
                return -1
            return 0

        self.root.children.sort(key=sort_key)

        self.queue_draw()

    def _create_and_add_layer_element(self, layer: Layer):
        layer_elem = ProjectorLayerElement(layer=layer, canvas=self)
        self.root.add(layer_elem)

    def cleanup(self):
        """Clean up resources when the surface is destroyed."""
        if self.machine:
            self.machine.changed.disconnect(self._on_machine_changed)
            self.machine.wcs_updated.disconnect(self._on_wcs_updated)


class ProjectorLayerElement(LayerElement):
    """
    A LayerElement variant for projector mode.

    Creates workpiece elements with bright colors for projection.
    """

    def sync_with_model(self, sender, origin=None, parent_of_origin=None):
        """
        Reconciles child elements with the layer model.
        """
        if not self.data or not self.canvas:
            logger.warning("sync_with_model: no data or canvas")
            return

        self.set_visible(self.data.visible)

        logger.debug(
            f"ProjectorLayerElement.sync_with_model: layer={self.data.name}"
        )

        model_items = {
            c
            for c in self.data.children
            if isinstance(c, (WorkPiece, Group, StockItem))
        }
        current_visual_elements = [
            elem
            for elem in self.children
            if elem.__class__.__name__
            in (
                "ProjectorWorkPieceElement",
                "WorkPieceElement",
                "GroupElement",
                "StockElement",
            )
        ]

        from rayforge.ui_gtk.canvas2d.elements.group import GroupElement
        from rayforge.ui_gtk.canvas2d.elements.stock import StockElement

        for elem in current_visual_elements[:]:
            if elem.data not in model_items:
                elem.remove()

        current_item_data = {elem.data for elem in self.children}
        items_to_add = model_items - current_item_data

        for item_data in items_to_add:
            new_elem = None
            if isinstance(item_data, WorkPiece):
                surface = cast(ProjectorSurface, self.canvas)
                new_elem = ProjectorWorkPieceElement(
                    workpiece=item_data,
                    view_manager=surface.editor.view_manager,
                    canvas=self.canvas,
                    selectable=False,
                )
            elif isinstance(item_data, Group):
                new_elem = GroupElement(
                    group=item_data,
                    canvas=self.canvas,
                    selectable=False,
                )
            elif isinstance(item_data, StockItem):
                new_elem = StockElement(
                    stock_item=item_data,
                    canvas=self.canvas,
                    selectable=False,
                )

            if new_elem:
                self.add(new_elem)

        if self.data.workflow is None:
            return

        from rayforge.ui_gtk.canvas2d.elements.step import StepElement

        current_step_elements = [
            elem for elem in self.children if isinstance(elem, StepElement)
        ]
        model_steps = set(self.data.workflow.steps)

        for elem in current_step_elements:
            if elem.data not in model_steps:
                elem.remove()

        current_step_data = {
            elem.data
            for elem in self.children
            if isinstance(elem, StepElement)
        }
        steps_to_add = model_steps - current_step_data

        for step_data in steps_to_add:
            surface = cast(ProjectorSurface, self.canvas)
            step_elem = StepElement(
                step=step_data,
                pipeline=surface.editor.pipeline,
                canvas=self.canvas,
            )
            self.add(step_elem)

        for elem in self.children:
            if isinstance(elem, StepElement):
                elem._update_sibling_ops_visibility()

        self.sort_children_by_z_order()
        self.canvas.queue_draw()


class ProjectorWorkPieceElement(WorkPieceElement):
    """
    A WorkPieceElement that draws only ops vectors with bright colors
    for projection. Does not draw the base image.
    """

    def __init__(self, *args, **kwargs):
        self._projector_cache = {}
        super().__init__(*args, **kwargs)
        self._base_image_visible = False

    def set_base_image_visible(self, visible: bool):
        """Base image is never visible in projector mode."""
        self._base_image_visible = False

    def _hydrate_from_cache(self) -> bool:
        """Use local projector cache instead of shared model cache."""
        cache = self._projector_cache
        if not cache:
            return False
        self._surface = cache.get("surface")
        self._artifact_cache = cache.get("artifact_cache", {}).copy()
        return self._surface is not None or len(self._artifact_cache) > 0

    def _update_model_view_cache(self):
        """Store in local projector cache instead of shared model cache."""
        self._projector_cache["surface"] = self._surface
        self._projector_cache["artifact_cache"] = self._artifact_cache

    def draw(self, ctx: cairo.Context):
        """Draw only ops overlays with bright colors, skip base image."""
        logger.debug(
            f"ProjectorWorkPieceElement.draw() called for '{self.data.name}'"
        )

        if not self.data.layer or not self.data.layer.workflow:
            logger.debug(f"No layer or workflow for '{self.data.name}'")
            return

        world_w, world_h = self.data.size
        if world_w < 1e-9 or world_h < 1e-9:
            logger.debug(f"Zero size workpiece '{self.data.name}'")
            return

        bright_green = (0.0, 1.0, 0.0, 1.0)

        for step in self.data.layer.workflow.steps:
            step_uid = step.uid
            if not self._ops_visibility.get(step_uid, True):
                continue

            surface = self._ops_surface_cache.get(step_uid)
            metadata = self._ops_metadata_cache.get(step_uid)

            if surface is None or metadata is None:
                view_handle = self.view_manager.get_view_handle(
                    self.data.uid, step.uid
                )
                if view_handle is not None:
                    from rayforge.pipeline.artifact import (
                        WorkPieceViewArtifact,
                    )

                    artifact = self.view_manager.store.get(view_handle)
                    if isinstance(artifact, WorkPieceViewArtifact):
                        try:
                            data = artifact.bitmap_data
                            if data is not None and data.size > 0:
                                new_data = np.copy(data)
                                height_px, width_px, _ = new_data.shape
                                stride = (
                                    cairo.ImageSurface.format_stride_for_width(
                                        cairo.FORMAT_ARGB32, width_px
                                    )
                                )
                                surface = cairo.ImageSurface.create_for_data(
                                    new_data,
                                    cairo.FORMAT_ARGB32,
                                    width_px,
                                    height_px,
                                    stride,
                                )
                                metadata = (
                                    artifact.bbox_mm,
                                    artifact.workpiece_size_mm,
                                )
                                self._ops_surface_cache[step_uid] = surface
                                self._ops_surface_data_cache[step_uid] = (
                                    new_data
                                )
                                self._ops_metadata_cache[step_uid] = metadata
                                logger.debug(
                                    f"ProjectorWorkPieceElement: got "
                                    f"surface {width_px}x{height_px}"
                                )
                        except Exception as e:
                            logger.debug(f"Error creating ops surface: {e}")

            if surface is None or metadata is None:
                continue

            bbox_mm, workpiece_size_mm = metadata
            if bbox_mm is None or workpiece_size_mm is None:
                continue

            try:
                view_x, view_y, view_w, view_h = bbox_mm

                if view_w < 1e-9 or view_h < 1e-9:
                    continue

                ref_w, ref_h = workpiece_size_mm

                scale_x = world_w / ref_w if ref_w > 1e-9 else 1.0
                scale_y = world_h / ref_h if ref_h > 1e-9 else 1.0

                if not (
                    abs(scale_x - 1.0) < 1e-6 and abs(scale_y - 1.0) < 1e-6
                ):
                    view_x *= scale_x
                    view_y *= scale_y
                    view_w *= scale_x
                    view_h *= scale_y

                surface_w_px = surface.get_width()
                surface_h_px = surface.get_height()

                ppm_x = (
                    (surface_w_px - 2 * OPS_MARGIN_PX) / view_w
                    if view_w > 1e-9
                    else 0
                )
                ppm_y = (
                    (surface_h_px - 2 * OPS_MARGIN_PX) / view_h
                    if view_h > 1e-9
                    else 0
                )

                if ppm_x <= 0 or ppm_y <= 0:
                    continue

                surface_w_world = surface_w_px / ppm_x
                surface_h_world = surface_h_px / ppm_y

                margin_w_world = OPS_MARGIN_PX / ppm_x
                margin_h_world = OPS_MARGIN_PX / ppm_y

                origin_x = view_x - margin_w_world
                origin_y = view_y - margin_h_world

                ctx.save()

                ctx.translate(origin_x / world_w, origin_y / world_h)
                ctx.scale(surface_w_world / world_w, surface_h_world / world_h)
                ctx.translate(0, 1)
                ctx.scale(1, -1)
                ctx.scale(1.0 / surface_w_px, 1.0 / surface_h_px)

                ctx.set_source_rgba(*bright_green)
                ctx.mask_surface(surface, 0, 0)
                ctx.fill()

                ctx.restore()
                logger.debug("ProjectorWorkPieceElement: drew green mask")
            except Exception as e:
                logger.debug(f"Error drawing ops overlay: {e}")

    def invalidate_and_rerender(self):
        """Clear local cache and re-render."""
        logger.debug(
            f"ProjectorWorkPieceElement: invalidating '{self.data.name}'"
        )
        self._rendered_ppm = 0.0
        self._artifact_cache.clear()
        self._ops_surface_cache.clear()
        self._ops_surface_data_cache.clear()
        self._ops_metadata_cache.clear()
        self._projector_cache.clear()

        if self.data.layer and self.data.layer.workflow:
            for step in self.data.layer.workflow.steps:
                self.clear_ops_surface(step.uid)

        self.trigger_update()

    def trigger_view_update(self, ppm: float = 0.0) -> bool:
        """Trigger re-render when resolution changes."""
        if ppm <= self._rendered_ppm:
            return False

        logger.debug(
            f"ProjectorWorkPieceElement: view update for '{self.data.name}'"
        )
        self._rendered_ppm = ppm
        super().trigger_update()
        return True
