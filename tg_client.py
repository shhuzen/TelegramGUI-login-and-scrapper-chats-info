import asyncio
import logging
import os
import re
import sys
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

def _data_path(name: str) -> str:
    if getattr(sys, "frozen", False):
        import pathlib
        return str(pathlib.Path(sys.executable).parent / name)
    return name

SESSION_FILE = _data_path("telegram_session")

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

    def reconnect(self) -> dict:
        """Disconnect and reconnect the existing client — useful after VPN toggle."""
        if self.client is None:
            return {"success": False, "error": "Нет активного клиента"}
        try:
            self._run(self.client.disconnect(), timeout=10)
        except Exception:
            pass
        try:
            self._run(self.client.connect(), timeout=20)
            if self._run(self.client.is_user_authorized(), timeout=10):
                return {"success": True}
            return {"success": False, "error": "Подключились, но авторизация потеряна"}
        except Exception as e:
            return {"success": False, "error": str(e)}

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

        # Disconnect old client synchronously before making a new one
        if self.client is not None:
            try:
                self._run(self.client.disconnect(), timeout=5)
            except Exception:
                pass

        # Create new client synchronously (must NOT be inside async function)
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
                "is_premium": getattr(me, "premium", False),
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
        is_archived = bool(getattr(dialog, "archived", False) or
                          getattr(getattr(dialog, "dialog", None), "folder_id", 0) == 1)

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

    def save_chats_to_md(self, folder: str, filename: str = "telegram_chats.md") -> dict:
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

        filepath = os.path.join(folder, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {"success": True, "file": filepath, "count": len(chats), "timestamp": timestamp}

    def get_chats_csv(self, folder: str) -> str:
        import csv, io
        chats = self.get_chats()
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, "telegram_chats.csv")
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "type", "username", "link", "members_count", "archived"])
            writer.writeheader()
            for c in chats:
                writer.writerow({k: c.get(k, "") for k in writer.fieldnames})
        return filepath

    def get_chats_xlsx(self, folder: str) -> str:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        chats = self.get_chats()
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, "telegram_chats.xlsx")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Telegram Chats"

        headers = ["Название", "Тип", "Username", "Ссылка", "Участников", "Архив"]
        keys    = ["title",    "type", "username", "link",   "members_count", "archived"]

        header_fill = PatternFill("solid", fgColor="2b91d1")
        header_font = Font(bold=True, color="FFFFFF")
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        col_widths = [40, 10, 25, 45, 12, 8]
        for col, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w

        for row_i, c in enumerate(chats, 2):
            for col_i, key in enumerate(keys, 1):
                val = c.get(key, "")
                if isinstance(val, bool):
                    val = "Да" if val else "Нет"
                ws.cell(row=row_i, column=col_i, value=val or "")

        wb.save(filepath)
        return filepath

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

    # ------------------------------------------------------------------ #
    #  Subscribe from MD file
    # ------------------------------------------------------------------ #

    def check_subscribed(self, entries: list[dict]) -> list[dict]:
        """For each entry return subscribed=True/False/None (None = private link, can't check)."""
        async def _collect():
            usernames: set[str] = set()
            for archived in (False, True):
                async for dialog in self.client.iter_dialogs(archived=archived, limit=None):
                    u = getattr(dialog.entity, "username", None)
                    if u:
                        usernames.add(u.lower())
            return usernames

        try:
            usernames = self._run(_collect(), timeout=120)
        except Exception:
            return [{**e, "subscribed": None} for e in entries]

        result = []
        for e in entries:
            url: str = e["url"]
            if "/+" in url or "/joinchat/" in url:
                result.append({**e, "subscribed": None})
            else:
                username = url.rstrip("/").split("/")[-1].lower()
                result.append({**e, "subscribed": username in usernames})
        return result

    def parse_md_file(self, path: str) -> list[dict]:
        """Extract channel/group entries from a backup MD file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Файл не найден: {path}")

        entries = []
        # Match markdown links: [Title](url)
        link_re = re.compile(r'\[([^\]]+)\]\((https?://t\.me/[^\)]+)\)')

        with open(path, encoding="utf-8") as f:
            for line in f:
                for m in link_re.finditer(line):
                    title, url = m.group(1), m.group(2)
                    entries.append({"title": title, "url": url})

        seen = set()
        unique = []
        for e in entries:
            if e["url"] not in seen:
                seen.add(e["url"])
                unique.append(e)
        return unique

    def parse_md_content(self, text: str) -> list[dict]:
        """Same as parse_md_file but takes a string directly (for drag & drop)."""
        entries = []
        link_re = re.compile(r'\[([^\]]+)\]\((https?://t\.me/[^\)]+)\)')
        for line in text.splitlines():
            for m in link_re.finditer(line):
                entries.append({"title": m.group(1), "url": m.group(2)})
        seen = set()
        return [e for e in entries if e["url"] not in seen and not seen.add(e["url"])]

    # subscribe_tasks: list of result dicts, status dict
    _sub_status: dict = {"status": "idle", "done": 0, "total": 0, "results": []}

    def get_subscribe_status(self) -> dict:
        return self._sub_status

    def start_subscribe(self, entries: list[dict], batch_size: int = 0,
                        sub_delay_seconds: int = 0,
                        batch_delay_min_seconds: int = 0,
                        batch_delay_max_seconds: int = 0,
                        timeout_seconds: int = 60) -> dict:
        if self._sub_status.get("status") in ("running", "waiting_sub", "waiting_batch"):
            return {"success": False, "error": "Подписка уже запущена"}

        self._sub_status = {
            "status": "running",
            "done": 0,
            "total": len(entries),
            "results": [],
            "wait_type": "",
            "wait_remaining": 0,
            "wait_total": 0,
            "next_batch_wait": 0,   # секунд в следующей паузе (показывается заранее)
            "entries": entries,
        }
        asyncio.run_coroutine_threadsafe(
            self._subscribe_async(entries, batch_size, sub_delay_seconds,
                                  batch_delay_min_seconds, batch_delay_max_seconds,
                                  timeout_seconds),
            self.loop,
        )
        return {"success": True}

    async def _subscribe_async(self, entries: list[dict], batch_size: int = 0,
                               sub_delay_seconds: int = 0,
                               batch_delay_min_seconds: int = 0,
                               batch_delay_max_seconds: int = 0,
                               timeout_seconds: int = 60):
        import random
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.tl.functions.messages import ImportChatInviteRequest
        from telethon.errors import (
            UserAlreadyParticipantError, InviteHashExpiredError,
            ChannelPrivateError, FloodWaitError as FW,
        )
        import asyncio as aio

        results = self._sub_status["results"]

        async def _countdown(wait_type: str, seconds: int):
            self._sub_status["wait_type"] = wait_type
            self._sub_status["wait_total"] = seconds
            self._sub_status["wait_remaining"] = seconds
            for remaining in range(seconds, 0, -1):
                self._sub_status["wait_remaining"] = remaining
                await aio.sleep(1)
            self._sub_status["wait_type"] = ""
            self._sub_status["wait_remaining"] = 0
            self._sub_status["wait_total"] = 0
            self._sub_status["next_batch_wait"] = 0

        def _random_batch_delay() -> int:
            lo = batch_delay_min_seconds
            hi = max(batch_delay_max_seconds, lo)
            return int(random.uniform(lo, hi))

        for idx, entry in enumerate(entries):
            # Batch pause before each batch (except first)
            if batch_size > 0 and batch_delay_min_seconds > 0 and idx > 0 and idx % batch_size == 0:
                wait_sec = _random_batch_delay()
                self._sub_status["status"] = "waiting_batch"
                # Pre-compute next batch delay for display after this one
                if idx + batch_size < len(entries):
                    self._sub_status["next_batch_wait"] = _random_batch_delay()
                await _countdown("batch", wait_sec)
                self._sub_status["status"] = "running"

            # Per-subscription delay (skip very first)
            elif sub_delay_seconds > 0 and idx > 0:
                self._sub_status["status"] = "waiting_sub"
                await _countdown("sub", sub_delay_seconds)
                self._sub_status["status"] = "running"

            url: str = entry["url"]
            title: str = entry["title"]
            result = {"title": title, "url": url, "status": "", "error": ""}

            try:
                async def _join():
                    if "/+" in url or "/joinchat/" in url:
                        hash_part = url.split("/+")[-1] if "/+" in url else url.split("/joinchat/")[-1]
                        await self.client(ImportChatInviteRequest(hash_part))
                    else:
                        username = url.rstrip("/").split("/")[-1]
                        entity = await self.client.get_entity(username)
                        await self.client(JoinChannelRequest(entity))

                await aio.wait_for(_join(), timeout=float(timeout_seconds))
                result["status"] = "joined"

            except aio.TimeoutError:
                result["status"] = "error"
                result["error"] = f"Таймаут ({timeout_seconds}с)"
            except UserAlreadyParticipantError:
                result["status"] = "already"
            except (ChannelPrivateError, InviteHashExpiredError):
                result["status"] = "error"
                result["error"] = "Приватный / ссылка устарела"
            except FW as e:
                result["status"] = "error"
                result["error"] = f"FloodWait {e.seconds}с"
                await aio.sleep(min(e.seconds, 300))
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)

            results.append(result)
            self._sub_status["done"] += 1

        self._sub_status["status"] = "done"

        import notifications
        joined  = sum(1 for r in results if r["status"] == "joined")
        already = sum(1 for r in results if r["status"] == "already")
        errors  = sum(1 for r in results if r["status"] == "error")
        notifications.notify(
            "Подписка завершена",
            f"Новых: {joined}  •  Уже был: {already}  •  Ошибок: {errors}",
        )
