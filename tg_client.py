import asyncio
import logging
import os
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import socks
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    PasswordHashInvalidError,
    FloodWaitError,
)
from telethon.tl.types import Channel, Chat, User

# Suppress Telethon's internal "Attempt N at connecting failed" messages
logging.getLogger("telethon").setLevel(logging.ERROR)

SESSION_FILE = "telegram_session"

_BUILTIN_API_ID   = 2040
_BUILTIN_API_HASH = "b18441a1ff607e10a989891a5462e627"


def detect_system_proxy() -> tuple | None:
    """Read Windows system proxy and return (socks_type, host, port) or None."""
    try:
        proxies = urllib.request.getproxies()
        url = proxies.get("https") or proxies.get("http")
        if not url:
            return None
        p = urlparse(url)
        scheme = (p.scheme or "http").lower()
        host, port = p.hostname, p.port or 8080
        if "socks5" in scheme:
            return (socks.SOCKS5, host, port)
        if "socks4" in scheme:
            return (socks.SOCKS4, host, port)
        return (socks.HTTP, host, port)
    except Exception:
        return None


def parse_proxy_string(proxy_str: str) -> tuple | None:
    """Parse a user-supplied proxy string like socks5://127.0.0.1:1080."""
    try:
        proxy_str = proxy_str.strip()
        if not proxy_str:
            return None
        if "://" not in proxy_str:
            proxy_str = "http://" + proxy_str
        p = urlparse(proxy_str)
        scheme = (p.scheme or "http").lower()
        host, port = p.hostname, p.port or 8080
        if "socks5" in scheme:
            return (socks.SOCKS5, host, port)
        if "socks4" in scheme:
            return (socks.SOCKS4, host, port)
        return (socks.HTTP, host, port)
    except Exception:
        return None


class TelegramClientManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self.client: TelegramClient | None = None
        self.phone: str | None = None
        self._phone_code_hash: str | None = None
        self.export_tasks: dict[int, dict] = {}
        self.manual_proxy: str = ""   # set from UI settings

    # ------------------------------------------------------------------ #
    #  Event loop
    # ------------------------------------------------------------------ #

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coro, timeout: int = 120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=timeout)

    # ------------------------------------------------------------------ #
    #  Proxy helpers
    # ------------------------------------------------------------------ #

    def _get_proxy(self) -> tuple | None:
        """Return proxy tuple for Telethon: manual setting → system proxy → None."""
        if self.manual_proxy:
            proxy = parse_proxy_string(self.manual_proxy)
            if proxy:
                return proxy
        return detect_system_proxy()

    def _make_client(self, session: str, api_id: int, api_hash: str) -> TelegramClient:
        return TelegramClient(
            session, api_id, api_hash,
            loop=self.loop,
            proxy=self._get_proxy(),
            connection_retries=1,
            timeout=10,
        )

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
        session_path = f"{SESSION_FILE}.session"
        if not os.path.exists(session_path):
            return False  # no session file — skip entirely
        try:
            self.client = self._make_client(SESSION_FILE, _BUILTIN_API_ID, _BUILTIN_API_HASH)
            self._run(self.client.connect(), timeout=15)
            if self.is_logged_in():
                return True
            # connected but not authorised — stale session file, remove it
            self.client = None
            os.remove(session_path)
            return False
        except Exception:
            self.client = None
            # remove the file so we don't retry on every startup
            try:
                os.remove(session_path)
            except OSError:
                pass
            return False

    def send_code(self, phone: str, api_id: int | None = None, api_hash: str | None = None) -> dict:
        self.phone = phone
        effective_api_id   = int(api_id)   if api_id   else _BUILTIN_API_ID
        effective_api_hash = api_hash       if api_hash else _BUILTIN_API_HASH
        self.client = self._make_client(SESSION_FILE, effective_api_id, effective_api_hash)

        async def _send():
            await self.client.connect()
            result = await self.client.send_code_request(phone)
            self._phone_code_hash = result.phone_code_hash
            return {"success": True}

        try:
            return self._run(_send(), timeout=30)  # максимум 30 сек на весь запрос
        except FloodWaitError as e:
            return {"success": False, "error": f"Слишком много попыток. Подождите {e.seconds} сек."}
        except TimeoutError:
            return {"success": False, "error": "Не удаётся подключиться к Telegram. Проверьте интернет или попробуйте через VPN/прокси."}
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
