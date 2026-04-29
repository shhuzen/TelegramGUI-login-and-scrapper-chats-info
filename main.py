import json
import os
import atexit
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, abort

from tg_client import TelegramClientManager
from scheduler_service import BackupScheduler

app = Flask("", static_url_path="", static_folder="templates/static")
tg = TelegramClientManager()
scheduler = BackupScheduler(tg)

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "api_id": "",
    "api_hash": "",
    "save_folder": "backups",
    "export_folder": "exports",
    "update_mode": "interval",
    "update_interval_hours": 24,
    "update_daily_time": "03:00",
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_CONFIG, **data}
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ #
#  Startup — try to reconnect with saved session
# ------------------------------------------------------------------ #

def _startup():
    cfg = load_config()
    try:
        ok = tg.try_restore_session(
            api_id=cfg.get("api_id") or None,
            api_hash=cfg.get("api_hash") or None,
        )
        if ok:
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


@app.route("/api/auth/default-tdata-path")
def default_tdata_path():
    from tg_client import DEFAULT_TDATA_PATH
    return jsonify({"path": DEFAULT_TDATA_PATH, "exists": os.path.isdir(DEFAULT_TDATA_PATH)})


@app.route("/api/auth/from-tdata", methods=["POST"])
def login_from_tdata():
    data = request.json or {}
    path = (data.get("tdata_path") or "").strip()
    if not path:
        from tg_client import DEFAULT_TDATA_PATH
        path = DEFAULT_TDATA_PATH
    result = tg.login_from_tdata(path)
    return jsonify(result)


@app.route("/api/auth/send-code", methods=["POST"])
def send_code():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    api_id = (data.get("api_id") or "").strip()
    api_hash = (data.get("api_hash") or "").strip()

    if not phone or not api_id or not api_hash:
        return jsonify({"success": False, "error": "Заполните все поля"}), 400

    # Save credentials to config
    cfg = load_config()
    cfg["api_id"] = api_id
    cfg["api_hash"] = api_hash
    save_config(cfg)

    result = tg.send_code(phone, api_id, api_hash)
    return jsonify(result)


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


# ------------------------------------------------------------------ #
#  Export
# ------------------------------------------------------------------ #


@app.route("/api/export/<int:chat_id>/start", methods=["POST"])
def start_export(chat_id: int):
    if not tg.is_logged_in():
        return jsonify({"error": "Не авторизован"}), 401
    cfg = load_config()
    folder = cfg.get("export_folder", "exports")
    data = request.json or {}
    limit = int(data.get("limit", 0))
    return jsonify(tg.start_export(chat_id, folder, limit))


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


@app.route("/api/settings", methods=["GET"])
def get_settings():
    cfg = load_config()
    # Don't expose api_hash in full; mask it
    safe = dict(cfg)
    if safe.get("api_hash"):
        safe["api_hash_masked"] = safe["api_hash"][:4] + "****"
    return jsonify(safe)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json or {}
    cfg = load_config()
    allowed = {
        "save_folder", "export_folder",
        "update_mode", "update_interval_hours", "update_daily_time",
        "api_id", "api_hash",
    }
    for key in allowed:
        if key in data:
            cfg[key] = data[key]
    save_config(cfg)
    scheduler.reschedule(cfg)
    return jsonify({"success": True})


# ------------------------------------------------------------------ #
#  Backup
# ------------------------------------------------------------------ #


@app.route("/api/backup/now", methods=["POST"])
def backup_now():
    cfg = load_config()
    return jsonify(scheduler.trigger_now(cfg.get("save_folder", "backups")))


@app.route("/api/backup/status")
def backup_status():
    return jsonify(scheduler.get_status())


# ------------------------------------------------------------------ #
#  Run
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
