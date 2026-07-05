import os
import sys
import time
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.modules.setdefault("serial", types.SimpleNamespace())

from PyQt6.QtWidgets import QApplication

from ui.trip_card import TripInfoCardWide

_APP = None


def _app():
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def test_trip_info_speed_update_does_not_accumulate_distance():
    _app()
    card = TripInfoCardWide()
    card.trip_distance = 1.23
    card.last_speed = 40.0
    card.last_update_time = time.monotonic() - 1.0

    card.update_from_speed(80.0)

    assert card.trip_distance == 1.23


def test_trip_info_distance_accumulates_only_through_add_distance():
    _app()
    card = TripInfoCardWide()

    card.update_from_speed(80.0)
    card.add_distance(0.25)

    assert card.trip_distance == 0.25
