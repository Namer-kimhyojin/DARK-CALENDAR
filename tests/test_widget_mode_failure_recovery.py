# -*- coding: utf-8 -*-
"""A failed widget-mode opening leaves the main window usable and retryable."""

from unittest.mock import patch

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.widgets.widget_mode_coordinator import (
    WidgetModeCoordinator,
    WidgetModeState,
)
from tests.test_widget_mode_coordinator import _Host


@pytest.mark.parametrize("show_before_failure", [False, True])
def test_failed_opening_preserves_main_visibility_resume_setting_and_allows_retry(
    show_before_failure,
):
    host = _Host()
    host.show()
    coordinator = WidgetModeCoordinator(host)
    original_show = coordinator.controller.show_widget
    before_resume = host.settings.value("widget_mode_resume")
    before_overlays = host.settings.value("overlay_instances")

    def fail_opening(filter_mode):
        if show_before_failure:
            original_show(filter_mode)
            coordinator.controller._load_timer.start(5000)
        raise RuntimeError("synthetic widget opening failure")

    try:
        with (
            patch.object(coordinator.controller, "show_widget", side_effect=fail_opening),
            pytest.raises(RuntimeError, match="synthetic widget opening failure"),
        ):
            coordinator.enter("work")
        assert coordinator.state is WidgetModeState.CLOSED
        assert coordinator._snapshot is None
        assert host.isVisible() and host.is_visible
        assert not coordinator.controller.is_visible()
        assert not coordinator.controller._load_timer.isActive()
        assert host.settings.value("widget_mode_resume") == before_resume
        assert host.settings.value("overlay_instances") == before_overlays

        coordinator.enter("work")
        assert coordinator.state is WidgetModeState.ACTIVE
        assert coordinator.controller.is_visible()
        assert not host.isVisible()
        coordinator.return_to_main()
        assert coordinator.state is WidgetModeState.CLOSED
        assert host.isVisible()
    finally:
        coordinator.controller.prepare_shutdown()
        if coordinator.controller.widget is not None:
            coordinator.controller.widget.close()
            coordinator.controller.widget.deleteLater()
        host.close()
        host.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
