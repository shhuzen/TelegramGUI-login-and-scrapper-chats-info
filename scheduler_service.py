from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import notifications

if TYPE_CHECKING:
    from tg_client import TelegramClientManager

logger = logging.getLogger(__name__)

JOB_ID = "backup_chats"


class BackupScheduler:
    def __init__(self, tg: "TelegramClientManager"):
        self.tg = tg
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._last_run: str | None = None
        self._last_result: dict | None = None

    def start(self, config: dict):
        self.scheduler.start()
        self._apply_schedule(config)

    def reschedule(self, config: dict):
        if self.scheduler.get_job(JOB_ID):
            self.scheduler.remove_job(JOB_ID)
        self._apply_schedule(config)

    def _apply_schedule(self, config: dict):
        if not config.get("auto_backup_enabled", True):
            logger.info("Auto-backup disabled in config — not scheduling")
            return

        folder   = config.get("save_folder", "backups")
        filename = config.get("backup_filename", "telegram_chats.md")
        mode     = config.get("update_mode", "interval")

        if mode == "daily":
            time_str = config.get("update_daily_time", "03:00")
            hour, minute = (int(x) for x in time_str.split(":"))
            trigger = CronTrigger(hour=hour, minute=minute)
        else:
            hours = int(config.get("update_interval_hours", 24))
            trigger = IntervalTrigger(hours=hours)

        self.scheduler.add_job(
            self._do_backup,
            trigger=trigger,
            id=JOB_ID,
            args=[folder, filename],
            replace_existing=True,
        )
        logger.info("Backup scheduled: mode=%s config=%s", mode, config)

    def _do_backup(self, folder: str, filename: str = "telegram_chats.md"):
        if not self.tg.is_logged_in():
            logger.warning("Backup skipped: not logged in")
            return
        self._last_run = datetime.now().isoformat()
        result = self.tg.save_chats_to_md(folder, filename)
        self._last_result = result
        logger.info("Backup result: %s", result)
        if result.get("success"):
            notifications.notify(
                "Бэкап завершён",
                f"Сохранено {result.get('count', '?')} чатов → {result.get('file', '')}",
            )
        else:
            notifications.notify("Ошибка бэкапа", result.get("error", "Неизвестная ошибка"))

    def trigger_now(self, folder: str, filename: str = "telegram_chats.md") -> dict:
        if not self.tg.is_logged_in():
            return {"success": False, "error": "Не авторизован в Telegram"}
        self._last_run = datetime.now().isoformat()
        result = self.tg.save_chats_to_md(folder, filename)
        self._last_result = result
        if result.get("success"):
            notifications.notify(
                "Бэкап завершён",
                f"Сохранено {result.get('count', '?')} чатов → {result.get('file', '')}",
            )
        else:
            notifications.notify("Ошибка бэкапа", result.get("error", "Неизвестная ошибка"))
        return result

    def get_status(self) -> dict:
        job = self.scheduler.get_job(JOB_ID)
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
        return {
            "last_run": self._last_run,
            "last_result": self._last_result,
            "next_run": next_run,
            "running": self.scheduler.running,
        }

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
