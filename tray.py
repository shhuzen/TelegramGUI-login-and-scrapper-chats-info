"""System tray icon for TelegramManager."""
import sys
import webbrowser
import threading
import pystray
from PIL import Image
from pathlib import Path


PORT = 5000


def _load_icon() -> Image.Image:
    # Try icon.ico next to exe first, fall back to generating one
    ico_path = Path(sys.executable).parent / "icon.ico" if getattr(sys, "frozen", False) \
               else Path(__file__).parent / "icon.ico"
    if ico_path.exists():
        return Image.open(ico_path)
    # Inline fallback — blue 64x64 square
    img = Image.new("RGBA", (64, 64), "#2b91d1")
    return img


def run_tray(tg_client, get_autostart_fn, set_autostart_fn):
    """
    Start pystray in the current thread (must be main thread on Windows).
    Flask should already be running in a background thread before calling this.
    """

    icon_img = _load_icon()

    def open_browser(icon, item):
        webbrowser.open(f"http://localhost:{PORT}")

    def toggle_autostart(icon, item):
        current = get_autostart_fn()
        set_autostart_fn(not current)
        icon.update_menu()

    def autostart_checked(item):
        return get_autostart_fn()

    def status_title(item):
        return "● Подключён" if tg_client.is_logged_in() else "○ Не авторизован"

    def on_exit(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(status_title, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Открыть в браузере", open_browser, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Запуск с Windows", toggle_autostart, checked=autostart_checked),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", on_exit),
    )

    icon = pystray.Icon("TelegramManager", icon_img, "Telegram Manager", menu)

    # Auto-open browser on first launch
    threading.Thread(
        target=lambda: (
            __import__("time").sleep(1),
            webbrowser.open(f"http://localhost:{PORT}"),
        ),
        daemon=True,
    ).start()

    icon.run()          # blocks until on_exit() calls icon.stop()
