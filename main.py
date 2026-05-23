import json
import os
import sys
import atexit
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from tg_client import TelegramClientManager
from scheduler_service import BackupScheduler

# ------------------------------------------------------------------ #
#  Path helpers (work both in normal mode and inside PyInstaller exe)
# ------------------------------------------------------------------ #

def _bundle_path(*parts) -> str:
    """Path to bundled read-only assets (templates etc.)."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base).joinpath(*parts))

def _data_path(*parts) -> str:
    """Path for user data (config, session) — always next to the exe / script."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return str(base.joinpath(*parts))

# Change working directory to data path so session/config land next to exe
os.chdir(_data_path())

app = Flask(
    "",
    static_url_path="",
    static_folder=_bundle_path("templates", "static"),
    template_folder=_bundle_path("templates"),
)
tg = TelegramClientManager()
scheduler = BackupScheduler(tg)

CONFIG_FILE = _data_path("config.json")
DEFAULT_CONFIG = {
    "save_folder": "backups",
    "backup_filename": "telegram_chats.md",
    "export_folder": "exports",
    "update_mode": "interval",
    "update_interval_hours": 24,
    "update_daily_time": "03:00",
    "proxy": "",
    "subscribe_md_path": "",
    "auto_backup_enabled": True,
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ #
#  Startup
# ------------------------------------------------------------------ #

def _apply_proxy(cfg: dict):
    tg.manual_proxy = cfg.get("proxy", "")


def _startup():
    cfg = load_config()
    _apply_proxy(cfg)
    try:
        if tg.try_restore_session():
            print("✓ Restored Telegram session")
    except Exception as e:
        print(f"Could not restore session: {e}")
    scheduler.start(cfg)
    atexit.register(scheduler.shutdown)


_startup()

# ------------------------------------------------------------------ #
#  Main page
# ------------------------------------------------------------------ #


@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------------ #
#  Auth
# ------------------------------------------------------------------ #


@app.route("/api/auth/status")
def auth_status():
    logged_in = tg.is_logged_in()
    me = tg.get_me() if logged_in else None
    return jsonify({"logged_in": logged_in, "user": me})


@app.route("/api/auth/send-code", methods=["POST"])
def send_code():
    data = request.json or {}
    phone    = (data.get("phone")    or "").strip()
    api_id   = (data.get("api_id")   or "").strip()
    api_hash = (data.get("api_hash") or "").strip()
    if not phone or not api_id or not api_hash:
        return jsonify({"success": False, "error": "Заполните все поля"}), 400
    return jsonify(tg.send_code(phone, api_id, api_hash))


@app.route("/api/auth/verify-code", methods=["POST"])
def verify_code():
    data = request.json or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"success": False, "error": "Введите код"}), 400
    return jsonify(tg.verify_code(code))


@app.route("/api/auth/verify-2fa", methods=["POST"])
def verify_2fa():
    data = request.json or {}
    password = data.get("password") or ""
    if not password:
        return jsonify({"success": False, "error": "Введите пароль"}), 400
    return jsonify(tg.verify_2fa(password))


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    return jsonify(tg.logout())


# ------------------------------------------------------------------ #
#  Chats
# ------------------------------------------------------------------ #


@app.route("/api/chats")
def get_chats():
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    try:
        chats = tg.get_chats()
        return jsonify({"chats": chats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chats/export-csv")
def export_chats_csv():
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    try:
        cfg = load_config()
        filepath = tg.get_chats_csv(cfg.get("export_folder", "exports"))
        return send_file(filepath, as_attachment=True,
                         download_name=Path(filepath).name, mimetype="text/csv")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chats/export-xlsx")
def export_chats_xlsx():
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    try:
        cfg = load_config()
        filepath = tg.get_chats_xlsx(cfg.get("export_folder", "exports"))
        return send_file(filepath, as_attachment=True,
                         download_name=Path(filepath).name,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------ #
#  Export
# ------------------------------------------------------------------ #


@app.route("/api/export/<int:chat_id>/start", methods=["POST"])
def start_export(chat_id: int):
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    cfg = load_config()
    data = request.json or {}
    limit = int(data.get("limit", 0))
    return jsonify(tg.start_export(chat_id, cfg.get("export_folder", "exports"), limit))


@app.route("/api/export/<int:chat_id>/status")
def export_status(chat_id: int):
    return jsonify(tg.get_export_status(chat_id))


@app.route("/api/export/<int:chat_id>/download")
def download_export(chat_id: int):
    task = tg.get_export_status(chat_id)
    if task["status"] != "done" or not task["file"]:
        return jsonify({"error": "Файл не готов"}), 404
    filepath = task["file"]
    if not os.path.exists(filepath):
        return jsonify({"error": "Файл не найден"}), 404
    return send_file(
        filepath,
        as_attachment=True,
        download_name=Path(filepath).name,
        mimetype="text/markdown",
    )


# ------------------------------------------------------------------ #
#  Settings
# ------------------------------------------------------------------ #


@app.route("/api/proxy/detected")
def proxy_detected():
    from tg_client import detect_system_proxy
    proxy = detect_system_proxy()
    if proxy:
        type_name = {1: "SOCKS4", 2: "SOCKS5", 3: "HTTP"}.get(proxy[0], "?")
        return jsonify({"found": True, "info": f"{type_name} {proxy[1]}:{proxy[2]}"})
    return jsonify({"found": False})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(load_config())


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json or {}
    cfg = load_config()
    for key in {"save_folder", "backup_filename", "export_folder", "update_mode", "update_interval_hours", "update_daily_time", "proxy", "auto_backup_enabled"}:
        if key in data:
            cfg[key] = data[key]
    save_config(cfg)
    _apply_proxy(cfg)
    scheduler.reschedule(cfg)
    return jsonify({"success": True})


# ------------------------------------------------------------------ #
#  Autostart (Windows registry)
# ------------------------------------------------------------------ #

_APP_NAME = "TelegramManager"


def _autostart_entry() -> str:
    """Command stored in registry — uses the same Python that's running now (venv-aware)."""
    # sys.executable already points to venv\Scripts\python.exe when inside venv
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    python  = Path(sys.executable)
    exe = pythonw if pythonw.exists() else python   # pythonw.exe = no console window
    script = Path(__file__).resolve()
    return f'"{exe}" "{script}"'


def _get_autostart() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _set_autostart(enable: bool):
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    if enable:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _autostart_entry())
    else:
        try:
            winreg.DeleteValue(key, _APP_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)


@app.route("/api/autostart", methods=["GET"])
def get_autostart():
    try:
        return jsonify({"enabled": _get_autostart()})
    except Exception as e:
        return jsonify({"enabled": False, "error": str(e)})


@app.route("/api/autostart", methods=["POST"])
def set_autostart():
    data = request.json or {}
    enable = bool(data.get("enabled", False))
    try:
        _set_autostart(enable)
        return jsonify({"success": True, "enabled": enable})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ------------------------------------------------------------------ #
#  Subscribe from MD
# ------------------------------------------------------------------ #


@app.route("/api/subscribe/preview", methods=["POST"])
def subscribe_preview():
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    data = request.json or {}
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify({"error": "Укажите путь к файлу"}), 400
    # Save path to config
    cfg = load_config()
    cfg["subscribe_md_path"] = path
    save_config(cfg)
    try:
        entries = tg.parse_md_file(path)
        return jsonify({"entries": entries, "count": len(entries)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/subscribe/check", methods=["POST"])
def subscribe_check():
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    data = request.json or {}
    entries = data.get("entries", [])
    try:
        result = tg.check_subscribed(entries)
        return jsonify({"entries": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscribe/start", methods=["POST"])
def subscribe_start():
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    data = request.json or {}
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"error": "Нет записей"}), 400
    batch_mode  = bool(data.get("batch_mode", False))
    batch_size  = int(data.get("batch_size", 3))
    batch_delay = int(data.get("batch_delay_minutes", 30))
    return jsonify(tg.start_subscribe(entries, batch_mode, batch_size, batch_delay))


@app.route("/api/subscribe/status")
def subscribe_status():
    return jsonify(tg.get_subscribe_status())


# ------------------------------------------------------------------ #
#  Backup
# ------------------------------------------------------------------ #


@app.route("/api/backup/now", methods=["POST"])
def backup_now():
    cfg = load_config()
    return jsonify(scheduler.trigger_now(cfg.get("save_folder", "backups"), cfg.get("backup_filename", "telegram_chats.md")))


@app.route("/api/backup/status")
def backup_status():
    return jsonify(scheduler.get_status())


# ------------------------------------------------------------------ #
#  Run
# ------------------------------------------------------------------ #

def _run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    # Flask runs in a background thread so the main thread is free for the tray
    flask_thread = threading.Thread(target=_run_flask, daemon=True)
    flask_thread.start()

    from tray import run_tray
    run_tray(tg, _get_autostart, _set_autostart, load_config, save_config, scheduler)

    # Tray exited — clean shutdown
    scheduler.shutdown()
    sys.exit(0)
