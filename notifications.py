"""Thin wrapper around pystray balloon notifications."""
from __future__ import annotations

_icon = None   # set by tray.py once the icon is running


def set_icon(icon) -> None:
    global _icon
    _icon = icon


def notify(title: str, message: str) -> None:
    """Show a system-tray balloon notification (Windows). Silently ignored elsewhere."""
    if _icon is None:
        return
    try:
        _icon.notify(message, title)   # pystray: notify(message, title)
    except Exception:
        pass
