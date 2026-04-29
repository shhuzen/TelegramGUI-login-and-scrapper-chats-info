import asyncio
import os
import threading
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    PasswordHashInvalidError,
    FloodWaitError,
)
from telethon.tl.types import Channel, Chat, User

SESSION_FILE = "telegram_session"
TDATA_SESSION_FILE = "tdata_session"

# Default tdata path on Windows
DEFAULT_TDATA_PATH = os.path.join(
    os.environ.get("APPDATA", ""), "Telegram Desktop", "tdata"
)


class TelegramClientManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self.client: TelegramClient | None = None
        self.phone: str | None = None
        self.api_id: int | None = None
        self.api_hash: str | None = None
        self._phone_code_hash: str | None = None

        # export progress tracking: chat_id -> dict
        self.export_tasks: dict[int, dict] = {}

    # ------------------------------------------------------------------ #
    #  Event loop helpers
    # ------------------------------------------------------------------ #

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coro, timeout: int = 120):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------ #
    #  Auth
    # ------------------------------------------------------------------ #

    def is_logged_in(self) -> bool:
        if self.client is None:
            return False
        try:
            return self._run(self.client.is_user_authorized(), timeout=10)
        except Exception:
            return False

    def try_restore_session(self, api_id: int | None = None, api_hash: str | None = None) -> bool:
        """Reconnect using an existing session file (tdata-derived or MTProto)."""
        # Try tdata-derived session first (no api_id/hash needed)
        if os.path.exists(f"{TDATA_SESSION_FILE}.session"):
            try:
                from opentele.api import API
                creds = API.TelegramDesktop
                self.client = TelegramClient(
                    TDATA_SESSION_FILE, creds.api_id, creds.api_hash, loop=self.loop
                )
                self._run(self.client.connect())
                if self.is_logged_in():
                    return True
            except Exception:
                pass

        # Fall back to MTProto session
        if api_id and api_hash and os.path.exists(f"{SESSION_FILE}.session"):
            try:
                self.api_id = int(api_id)
                self.api_hash = api_hash
                self.client = TelegramClient(SESSION_FILE, self.api_id, self.api_hash, loop=self.loop)
                self._run(self.client.connect())
                return self.is_logged_in()
            except Exception:
                pass

        return False

    def login_from_tdata(self, tdata_path: str) -> dict:
        """Create a session from Telegram Desktop tdata folder — no API keys needed."""
        if not os.path.isdir(tdata_path):
            return {"success": False, "error": f"Папка не найдена: {tdata_path}"}

        async def _convert():
            from opentele.td import TDesktop
            from opentele.api import API, CreateNewSession

            tdesk = TDesktop(tdata_path)
            if not tdesk.isLoaded():
                return {"success": False, "error": "Не удалось прочитать tdata. Убедитесь что Telegram Desktop закрыт."}

            client = await tdesk.ToTelethon(
                session=TDATA_SESSION_FILE,
                flag=CreateNewSession,
                api=API.TelegramDesktop,
            )
            await client.connect()
            self.client = client
            return {"success": True}

        try:
            return self._run(_convert(), timeout=60)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_code(self, phone: str, api_id: int, api_hash: str) -> dict:
        self.phone = phone
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.client = TelegramClient(SESSION_FILE, self.api_id, self.api_hash, loop=self.loop)

        async def _send():
            await self.client.connect()
            result = await self.client.send_code_request(phone)
            self._phone_code_hash = result.phone_code_hash
            return {"success": True}

        try:
            return self._run(_send())
        except FloodWaitError as e:
            return {"success": False, "error": f"Flood wait: retry after {e.seconds}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def verify_code(self, code: str) -> dict:
        async def _verify():
            try:
                await self.client.sign_in(
                    self.phone, code, phone_code_hash=self._phone_code_hash
                )
                return {"success": True}
            except SessionPasswordNeededError:
                return {"success": False, "need_2fa": True}
            except PhoneCodeInvalidError:
                return {"success": False, "error": "Неверный код"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return self._run(_verify())

    def verify_2fa(self, password: str) -> dict:
        async def _verify():
            try:
                await self.client.sign_in(password=password)
                return {"success": True}
            except PasswordHashInvalidError:
                return {"success": False, "error": "Неверный пароль 2FA"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return self._run(_verify())

    def logout(self) -> dict:
        async def _logout():
            await self.client.log_out()
            return {"success": True}

        try:
            result = self._run(_logout())
            self.client = None
            self.phone = None
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_me(self) -> dict | None:
        if not self.is_logged_in():
            return None

        async def _me():
            me = await self.client.get_me()
            return {
                "id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username,
                "phone": me.phone,
            }

        try:
            return self._run(_me())
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Chats
    # ------------------------------------------------------------------ #

    def get_chats(self) -> list[dict]:
        async def _get():
            chats = []
            seen_ids = set()

            async def collect(dialogs_iter):
                async for dialog in dialogs_iter:
                    entity = dialog.entity
                    if not isinstance(entity, (Channel, Chat)):
                        continue
                    eid = entity.id
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    chats.append(self._format_chat(entity, dialog))

            await collect(self.client.iter_dialogs(archived=False, limit=None))
            await collect(self.client.iter_dialogs(archived=True, limit=None))
            return chats

        return self._run(_get(), timeout=180)

    def _format_chat(self, entity, dialog) -> dict:
        is_channel = isinstance(entity, Channel) and getattr(entity, "broadcast", False)
        chat_type = "channel" if is_channel else "group"
        is_archived = getattr(dialog.folder, "id", None) == 1 if dialog.folder else False

        username = getattr(entity, "username", None)
        if username:
            link = f"https://t.me/{username}"
        else:
            link = None  # private — no public link

        return {
            "id": entity.id,
            "title": dialog.name or "Без названия",
            "type": chat_type,
            "username": username,
            "link": link,
            "members_count": getattr(entity, "participants_count", None),
            "archived": is_archived,
        }

    # ------------------------------------------------------------------ #
    #  Backup to Markdown
    # ------------------------------------------------------------------ #

    def save_chats_to_md(self, folder: str) -> dict:
        os.makedirs(folder, exist_ok=True)
        try:
            chats = self.get_chats()
        except Exception as e:
            return {"success": False, "error": str(e)}

        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"# Telegram Chats\n\n",
            f"**Обновлено:** {timestamp}\n\n",
            f"**Всего:** {len(chats)}\n\n",
            "---\n\n",
        ]

        active_groups = [c for c in chats if c["type"] == "group" and not c["archived"]]
        active_channels = [c for c in chats if c["type"] == "channel" and not c["archived"]]
        archived = [c for c in chats if c["archived"]]

        def chat_line(c: dict) -> str:
            link = c["link"]
            title = c["title"]
            if link:
                return f"- [{title}]({link})\n"
            return f"- {title} *(приватный)*\n"

        if active_groups:
            lines.append(f"## Группы ({len(active_groups)})\n\n")
            for c in active_groups:
                lines.append(chat_line(c))
            lines.append("\n")

        if active_channels:
            lines.append(f"## Каналы ({len(active_channels)})\n\n")
            for c in active_channels:
                lines.append(chat_line(c))
            lines.append("\n")

        if archived:
            lines.append(f"## Архив ({len(archived)})\n\n")
            for c in archived:
                prefix = "📢" if c["type"] == "channel" else "👥"
                line = chat_line(c)
                lines.append(f"{prefix} {line.lstrip('- ')}")
            lines.append("\n")

        filepath = os.path.join(folder, "telegram_chats.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {
            "success": True,
            "file": filepath,
            "count": len(chats),
            "timestamp": timestamp,
        }

    # ------------------------------------------------------------------ #
    #  Export chat history
    # ------------------------------------------------------------------ #

    def start_export(self, chat_id: int, folder: str, limit: int = 0) -> dict:
        if chat_id in self.export_tasks and self.export_tasks[chat_id]["status"] == "running":
            return {"success": False, "error": "Экспорт уже запущен"}

        self.export_tasks[chat_id] = {
            "status": "running",
            "progress": 0,
            "total": 0,
            "file": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        }

        def _run_export():
            asyncio.run_coroutine_threadsafe(
                self._export_async(chat_id, folder, limit), self.loop
            )

        threading.Thread(target=_run_export, daemon=True).start()
        return {"success": True}

    async def _export_async(self, chat_id: int, folder: str, limit: int):
        try:
            os.makedirs(folder, exist_ok=True)
            entity = await self.client.get_entity(chat_id)
            title = getattr(entity, "title", str(chat_id))
            safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
            filename = f"{safe_title}_{chat_id}.md"
            filepath = os.path.join(folder, filename)

            # count messages
            total = await self.client.get_messages(entity, limit=0)
            self.export_tasks[chat_id]["total"] = total.total

            count = 0
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# История чата: {title}\n\n")
                f.write(f"**Экспортировано:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")

                async for msg in self.client.iter_messages(
                    entity, limit=limit or None, reverse=True
                ):
                    count += 1
                    self.export_tasks[chat_id]["progress"] = count

                    sender_name = "Неизвестно"
                    if msg.sender:
                        if isinstance(msg.sender, User):
                            parts = [msg.sender.first_name or "", msg.sender.last_name or ""]
                            sender_name = " ".join(p for p in parts if p) or "Пользователь"
                        else:
                            sender_name = getattr(msg.sender, "title", "Канал")

                    date_str = msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else ""
                    text = msg.text or ""

                    if msg.media and not text:
                        media_type = type(msg.media).__name__.replace("MessageMedia", "")
                        text = f"*[{media_type}]*"
                    elif msg.media and text:
                        media_type = type(msg.media).__name__.replace("MessageMedia", "")
                        text = f"*[{media_type}]* {text}"

                    if text:
                        f.write(f"**[{date_str}]** {sender_name}:\n")
                        f.write(f"{text}\n\n")

            self.export_tasks[chat_id]["status"] = "done"
            self.export_tasks[chat_id]["file"] = filepath

        except Exception as e:
            self.export_tasks[chat_id]["status"] = "error"
            self.export_tasks[chat_id]["error"] = str(e)

    def get_export_status(self, chat_id: int) -> dict:
        return self.export_tasks.get(
            chat_id,
            {"status": "not_started", "progress": 0, "total": 0, "file": None, "error": None},
        )
