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

# Credentials embedded in the official Telegram Desktop client.
# Using these means the user only needs a phone number — no registration needed.
_BUILTIN_API_ID   = 2040
_BUILTIN_API_HASH = "b18441a1ff607e10a989891a5462e627"


class TelegramClientManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self.client: TelegramClient | None = None
        self.phone: str | None = None
        self._phone_code_hash: str | None = None
        self.export_tasks: dict[int, dict] = {}

    # ------------------------------------------------------------------ #
    #  Event loop
    # ------------------------------------------------------------------ #

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coro, timeout: int = 120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=timeout)

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

    def try_restore_session(self) -> bool:
        if not os.path.exists(f"{SESSION_FILE}.session"):
            return False  # no session file — skip network call entirely
        try:
            self.client = TelegramClient(
                SESSION_FILE, _BUILTIN_API_ID, _BUILTIN_API_HASH, loop=self.loop
            )
            self._run(self.client.connect(), timeout=15)
            return self.is_logged_in()
        except Exception:
            self.client = None
            return False

    def send_code(self, phone: str) -> dict:
        self.phone = phone
        self.client = TelegramClient(
            SESSION_FILE, _BUILTIN_API_ID, _BUILTIN_API_HASH, loop=self.loop
        )

        async def _send():
            await self.client.connect()
            result = await self.client.send_code_request(phone)
            self._phone_code_hash = result.phone_code_hash
            return {"success": True}

        try:
            return self._run(_send())
        except FloodWaitError as e:
            return {"success": False, "error": f"Слишком много попыток. Подождите {e.seconds} сек."}
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
            seen_ids: set[int] = set()

            async def collect(dialogs_iter):
                async for dialog in dialogs_iter:
                    entity = dialog.entity
                    if not isinstance(entity, (Channel, Chat)):
                        continue
                    if entity.id in seen_ids:
                        continue
                    seen_ids.add(entity.id)
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
        link = f"https://t.me/{username}" if username else None

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

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Telegram Chats\n\n",
            f"**Обновлено:** {timestamp}\n\n",
            f"**Всего:** {len(chats)}\n\n",
            "---\n\n",
        ]

        active_groups    = [c for c in chats if c["type"] == "group"   and not c["archived"]]
        active_channels  = [c for c in chats if c["type"] == "channel" and not c["archived"]]
        archived         = [c for c in chats if c["archived"]]

        def chat_line(c: dict) -> str:
            return f"- [{c['title']}]({c['link']})\n" if c["link"] else f"- {c['title']} *(приватный)*\n"

        if active_groups:
            lines.append(f"## Группы ({len(active_groups)})\n\n")
            lines += [chat_line(c) for c in active_groups]
            lines.append("\n")

        if active_channels:
            lines.append(f"## Каналы ({len(active_channels)})\n\n")
            lines += [chat_line(c) for c in active_channels]
            lines.append("\n")

        if archived:
            lines.append(f"## Архив ({len(archived)})\n\n")
            for c in archived:
                prefix = "📢" if c["type"] == "channel" else "👥"
                lines.append(f"{prefix} {chat_line(c).lstrip('- ')}")
            lines.append("\n")

        filepath = os.path.join(folder, "telegram_chats.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {"success": True, "file": filepath, "count": len(chats), "timestamp": timestamp}

    # ------------------------------------------------------------------ #
    #  Export chat history
    # ------------------------------------------------------------------ #

    def start_export(self, chat_id: int, folder: str, limit: int = 0) -> dict:
        if self.export_tasks.get(chat_id, {}).get("status") == "running":
            return {"success": False, "error": "Экспорт уже запущен"}

        self.export_tasks[chat_id] = {
            "status": "running", "progress": 0, "total": 0,
            "file": None, "error": None,
            "started_at": datetime.now().isoformat(),
        }
        asyncio.run_coroutine_threadsafe(
            self._export_async(chat_id, folder, limit), self.loop
        )
        return {"success": True}

    async def _export_async(self, chat_id: int, folder: str, limit: int):
        try:
            os.makedirs(folder, exist_ok=True)
            entity = await self.client.get_entity(chat_id)
            title = getattr(entity, "title", str(chat_id))
            safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
            filepath = os.path.join(folder, f"{safe_title}_{chat_id}.md")

            total = await self.client.get_messages(entity, limit=0)
            self.export_tasks[chat_id]["total"] = total.total

            count = 0
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# История чата: {title}\n\n")
                f.write(f"**Экспортировано:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")

                async for msg in self.client.iter_messages(entity, limit=limit or None, reverse=True):
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
                    if msg.media:
                        mtype = type(msg.media).__name__.replace("MessageMedia", "")
                        text = f"*[{mtype}]* {text}".strip()

                    if text:
                        f.write(f"**[{date_str}]** {sender_name}:\n{text}\n\n")

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
