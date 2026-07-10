"""Shared CAN connection policy for production and desktop debugging."""

import os
import platform


CAN_FILTERS = [
    {"can_id": 0x7E8, "can_mask": 0x7FF},
    {"can_id": 0x7E9, "can_mask": 0x7FF},
    {"can_id": 0x340, "can_mask": 0x7FF},
    {"can_id": 0x335, "can_mask": 0x7FF},
    {"can_id": 0x38A, "can_mask": 0x7FF},
    {"can_id": 0x410, "can_mask": 0x7FF},
    {"can_id": 0x420, "can_mask": 0x7FF},
]


def slcan_debug_allowed(system_name=None):
    """SLCAN is a desktop debug transport, never an RPi/Linux fallback."""
    return (system_name or platform.system()) in {"Darwin", "Windows"}


def configured_slcan_port():
    return os.environ.get("QTDASHBOARD_SLCAN_PORT", "").strip() or None
