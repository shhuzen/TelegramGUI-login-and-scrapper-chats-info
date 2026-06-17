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
from telethon.tl.types import Channel, Chat, User, ChannelForbidden, ChatForbidden

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
            self.client = None

        # Remove stale session file so the new login uses a fresh auth flow.
        # Without this, Telethon reuses an old session whose phone_code_hash no
        # longer matches the code Telegram just sent, causing PhoneCodeInvalidError.
        session_path = f"{SESSION_FILE}.session"
        if os.path.exists(session_path):
            try:
                os.remove(session_path)
            except OSError:
                pass

        # Create new client synchronously (must NOT be inside async function)
        self.client = self._make_client(SESSION_FILE, effective_api_id, effective_api_hash)

        async def _send():
            await self.client.connect()
            result = await self.client.send_code_request(phone)
            # Let Telethon manage the hash in its own internal dict.
            # We keep a copy only for logging.
            self._phone_code_hash = result.phone_code_hash
            code_type = type(result.type).__name__
            print(f"[AUTH] send_code ok  phone={phone}  type={code_type}  hash={self._phone_code_hash[:8]}...")
            if "App" in code_type:
                print("[AUTH] Code sent to TELEGRAM APP (not SMS) — check your Telegram messages")
            elif "Sms" in code_type:
                print("[AUTH] Code sent via SMS")
            return {"success": True, "code_type": code_type}

        try:
            return self._run(_send(), timeout=30)
        except FloodWaitError as e:
            return {"success": False, "error": f"Слишком много попыток. Подождите {e.seconds} сек."}
        except TimeoutError:
            return {"success": False, "error": "Не удаётся подключиться к Telegram. Проверьте интернет или попробуйте через VPN/прокси."}
        except Exception as e:
            print(f"[AUTH] send_code ERROR: {e}")
            return {"success": False, "error": str(e)}

    def verify_code(self, code: str) -> dict:
        async def _verify():
            # Do NOT pass phone_code_hash explicitly — Telethon uses its own
            # internal dict (_phone_code_hash[phone]) set by send_code_request.
            # Passing it explicitly can cause mismatches in some Telethon versions.
            print(f"[AUTH] verify_code  phone={self.phone}  code={code}")
            try:
                await self.client.sign_in(self.phone, code)
                print("[AUTH] verify_code SUCCESS — logged in")
                return {"success": True}
            except SessionPasswordNeededError:
                print("[AUTH] verify_code → need 2FA")
                return {"success": False, "need_2fa": True}
            except PhoneCodeInvalidError:
                print("[AUTH] verify_code → PhoneCodeInvalidError")
                return {"success": False, "error": "Неверный код"}
            except Exception as e:
                print(f"[AUTH] verify_code EXCEPTION: {type(e).__name__}: {e}")
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

    def get_full_export_status(self) -> dict:
        return self._full_export_status

    def start_full_export(self, chat_configs: list, md_folder: str, media_folder: str,
                          export_json: bool = False, export_html: bool = False) -> dict:
        if self._full_export_status.get("status") == "running":
            return {"success": False, "error": "Экспорт уже запущен"}
        self._full_export_status = {
            "status": "running",
            "current_chat_title": "",
            "current_chat_id": 0,
            "current_msg": 0,
            "current_total": 0,
            "current_media": 0,
            "chats_done": 0,
            "chats_total": len(chat_configs),
            "results": [],
            "error": "",
        }
        asyncio.run_coroutine_threadsafe(
            self._full_export_async(chat_configs, md_folder, media_folder, export_json, export_html),
            self.loop,
        )
        return {"success": True}

    async def _full_export_async(self, chat_configs: list, md_folder: str, media_folder: str,
                                  export_json: bool = False, export_html: bool = False):
        import json as _json
        from datetime import datetime, timezone
        from telethon.tl.types import (
            MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
            MessageMediaGeo, MessageMediaPoll, MessageMediaContact,
            DocumentAttributeVideo, DocumentAttributeAudio,
            DocumentAttributeSticker, DocumentAttributeAnimated,
            DocumentAttributeFilename,
        )

        for cfg in chat_configs:
            chat_id = int(cfg["id"])
            title = cfg.get("title", str(chat_id))

            self._full_export_status.update({
                "current_chat_title": title,
                "current_chat_id": chat_id,
                "current_msg": 0,
                "current_total": 0,
                "current_media": 0,
            })

            # Preserve Unicode (Cyrillic etc.), strip only filesystem-unsafe chars
            safe_title = re.sub(r'[/\\:*?"<>|\x00]', '', title).strip().strip('.')[:80] or str(chat_id)
            # If only Markdown is requested, save chat.md directly into md_folder
            # (no per-chat subfolder). A subfolder is only needed to hold extra
            # files (chat.json / chat.html) alongside the .md.
            needs_subfolder = export_json or export_html
            md_root = os.path.abspath(md_folder)
            chat_md_dir = os.path.join(md_root, safe_title) if needs_subfolder else md_root
            # Media files always go into media_folder/safe_title/
            chat_media_dir = os.path.join(os.path.abspath(media_folder), safe_title)

            result = {
                "id": chat_id,
                "title": title,
                "status": "running",
                "messages": 0,
                "media_files": 0,
                "md_folder": chat_md_dir,
                "media_folder": chat_media_dir,
                "folder": chat_md_dir,   # kept for backward-compat with "open folder" button
                "error": "",
            }
            self._full_export_status["results"].append(result)

            try:
                os.makedirs(chat_md_dir, exist_ok=True)

                # create media subdirectories inside chat_media_dir
                media_dirs: dict[str, str] = {}
                for d in ("photos", "videos", "voice", "audio", "stickers", "gif", "documents", "other"):
                    p = os.path.join(chat_media_dir, d)
                    os.makedirs(p, exist_ok=True)
                    media_dirs[d] = p

                entity = await self.client.get_entity(chat_id)
                username = getattr(entity, "username", None)
                link = f"https://t.me/{username}" if username else None

                count_r = await self.client.get_messages(entity, limit=0)
                total_msgs = count_r.total
                self._full_export_status["current_total"] = total_msgs

                # range parameters
                range_type = cfg.get("range_type", "all")
                date_from_dt = None
                date_to_dt = None
                last_n = None

                if range_type == "last_n":
                    last_n = max(1, int(cfg.get("last_n", 1000)))
                elif range_type == "date_range":
                    for key, var_name in (("date_from", "date_from_dt"), ("date_to", "date_to_dt")):
                        val = cfg.get(key, "")
                        if val:
                            try:
                                dt = datetime.fromisoformat(val[:10])
                                if var_name == "date_from_dt":
                                    date_from_dt = dt.replace(tzinfo=timezone.utc)
                                else:
                                    date_to_dt = dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                            except Exception:
                                pass

                md_path = os.path.join(chat_md_dir, f"{safe_title}.md")
                msg_cache: dict = {}
                count = 0
                media_count = 0
                messages_data = []   # for JSON/HTML export

                export_start = cfg.get("date_from", "") or ""
                export_end   = cfg.get("date_to",   "") or datetime.now().strftime("%Y-%m-%d")
                if range_type == "all":
                    export_start = "начало"
                    export_end   = datetime.now().strftime("%Y-%m-%d")

                with open(md_path, "w", encoding="utf-8") as f:
                    # ── Header ──────────────────────────────────────
                    f.write(f"# {title}\n\n")
                    if link:
                        f.write(f"**Ссылка:** {link}\n\n")
                    f.write(f"**ID чата:** `{chat_id}`\n\n")
                    f.write(f"**Дата начала экспорта:** {export_start}\n\n")
                    f.write(f"**Дата окончания экспорта:** {export_end}\n\n")
                    f.write(f"**Сообщений в чате:** {total_msgs}\n\n")
                    f.write("---\n\n")

                    # ── Message iterator ─────────────────────────────
                    async def _iter():
                        if last_n:
                            msgs = []
                            async for m in self.client.iter_messages(entity, limit=last_n):
                                msgs.append(m)
                            for m in reversed(msgs):
                                yield m
                        else:
                            async for m in self.client.iter_messages(entity, limit=None, reverse=True):
                                yield m

                    async for msg in _iter():
                        # date range filter
                        if msg.date:
                            mdt = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)
                            if date_from_dt and mdt < date_from_dt:
                                continue
                            if date_to_dt and mdt > date_to_dt:
                                continue

                        count += 1
                        self._full_export_status["current_msg"] = count

                        # sender name
                        sender_name = "Неизвестно"
                        if msg.sender:
                            if isinstance(msg.sender, User):
                                parts = [msg.sender.first_name or "", msg.sender.last_name or ""]
                                sender_name = " ".join(p for p in parts if p) or "Пользователь"
                            else:
                                sender_name = getattr(msg.sender, "title", "Канал")

                        date_str = msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else ""

                        fwd_name = ""
                        if msg.fwd_from:
                            fwd_name = getattr(msg.fwd_from, "from_name", None) or ""
                            if not fwd_name and msg.forward and msg.forward.sender:
                                s = msg.forward.sender
                                if isinstance(s, User):
                                    parts = [s.first_name or "", s.last_name or ""]
                                    fwd_name = " ".join(p for p in parts if p)
                                else:
                                    fwd_name = getattr(s, "title", "")

                        reply_snippet = ""
                        if msg.reply_to and hasattr(msg.reply_to, "reply_to_msg_id"):
                            reply_id = msg.reply_to.reply_to_msg_id
                            cached = msg_cache.get(reply_id)
                            if cached:
                                reply_snippet = cached["text"][:150].replace("\n", " ")
                                if len(cached["text"]) > 150:
                                    reply_snippet += "…"

                        text = msg.text or ""

                        media_line = ""
                        media_abs_path = None
                        if msg.media:
                            media_line, media_abs_path = await self._export_media_line(msg, media_dirs, msg.id)
                            if media_line:
                                media_count += 1
                                self._full_export_status["current_media"] = media_count

                        # ── write MD ─────────────────────────────────
                        f.write(f"## {sender_name}\n\n")
                        f.write(f"Дата: {date_str}\n\n")
                        if fwd_name:
                            f.write(f"> Переслано от: {fwd_name}\n\n")
                        if reply_snippet:
                            f.write(f"> Ответ на сообщение:\n> {reply_snippet}\n\n")
                        elif msg.reply_to and hasattr(msg.reply_to, "reply_to_msg_id"):
                            f.write("> Ответ на сообщение\n\n")
                        if text:
                            f.write(f"{text}\n\n")
                        if media_line:
                            f.write(media_line)
                        f.write("---\n\n")

                        # ── accumulate data for JSON/HTML ─────────────
                        if export_json or export_html:
                            messages_data.append({
                                "id": msg.id,
                                "date": date_str,
                                "sender": sender_name,
                                "forwarded_from": fwd_name or None,
                                "reply_to_snippet": reply_snippet or None,
                                "text": text,
                                "media": os.path.basename(media_abs_path) if media_abs_path else None,
                                "media_abs": media_abs_path,
                            })

                        # update reply cache
                        msg_cache[msg.id] = {
                            "sender": sender_name,
                            "text": text or ("[медиа]" if msg.media else ""),
                        }
                        if len(msg_cache) > 5000:
                            msg_cache.pop(next(iter(msg_cache)))

                # ── JSON export ───────────────────────────────────────
                if export_json:
                    json_path = os.path.join(chat_md_dir, f"{safe_title}.json")
                    json_messages = [{k: v for k, v in m.items() if k != "media_abs"} for m in messages_data]
                    with open(json_path, "w", encoding="utf-8") as jf:
                        _json.dump({
                            "id": chat_id,
                            "title": title,
                            "link": link,
                            "total": total_msgs,
                            "exported": count,
                            "messages": json_messages,
                        }, jf, ensure_ascii=False, indent=2)

                # ── HTML export ───────────────────────────────────────
                if export_html:
                    html_path = os.path.join(chat_md_dir, f"{safe_title}.html")
                    self._write_export_html(html_path, title, link, chat_id, total_msgs, export_start, export_end, messages_data)

                result.update({"status": "done", "messages": count, "media_files": media_count})

            except Exception as e:
                result.update({"status": "error", "error": str(e)})

            self._full_export_status["chats_done"] += 1

        self._full_export_status["status"] = "done"
        import notifications
        done  = sum(1 for r in self._full_export_status["results"] if r["status"] == "done")
        errs  = sum(1 for r in self._full_export_status["results"] if r["status"] == "error")
        notifications.notify("Экспорт завершён", f"Готово: {done}  •  Ошибок: {errs}")

    def _write_export_html(self, html_path: str, title: str, link, chat_id: int,
                           total_msgs: int, export_start: str, export_end: str,
                           messages_data: list):
        import html as _html
        css = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1c2026;color:#e8ecf1;margin:0;padding:0;}
.header{background:#242d38;padding:20px 32px;border-bottom:1px solid #2e3a46;}
.header h1{margin:0 0 6px;font-size:22px;} .header .meta{color:#8a9bac;font-size:13px;}
.header a{color:#5288c1;text-decoration:none;}
.messages{max-width:800px;margin:0 auto;padding:24px 16px;}
.msg{background:#242d38;border-radius:10px;padding:14px 16px;margin-bottom:12px;}
.msg-header{display:flex;justify-content:space-between;margin-bottom:6px;}
.sender{font-weight:600;color:#5288c1;font-size:14px;}
.date{color:#8a9bac;font-size:12px;}
.fwd{color:#8a9bac;font-size:12px;font-style:italic;margin-bottom:6px;}
.reply{background:#1c2026;border-left:3px solid #5288c1;padding:6px 10px;border-radius:4px;font-size:12px;color:#8a9bac;margin-bottom:8px;}
.text{white-space:pre-wrap;word-break:break-word;font-size:14px;line-height:1.55;}
.media img{max-width:100%;border-radius:8px;margin-top:8px;}
.media video,.media audio{max-width:100%;margin-top:8px;}
.media a{color:#5288c1;}
"""
        def esc(s): return _html.escape(s or "")

        html_dir = os.path.dirname(html_path)

        rows = []
        for m in messages_data:
            fwd = f'<div class="fwd">Переслано от: {esc(m["forwarded_from"])}</div>' if m.get("forwarded_from") else ""
            reply = f'<div class="reply">↩ {esc(m["reply_to_snippet"])}</div>' if m.get("reply_to_snippet") else ""
            text  = f'<div class="text">{esc(m["text"])}</div>' if m.get("text") else ""
            media = ""
            if m.get("media_abs"):
                mp = esc(os.path.relpath(m["media_abs"], html_dir).replace("\\", "/"))
                if mp.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                    media = f'<div class="media"><img src="{mp}" loading="lazy" /></div>'
                elif mp.endswith((".mp4", ".webm")):
                    media = f'<div class="media"><video controls><source src="{mp}"></video></div>'
                elif mp.endswith((".ogg", ".mp3", ".m4a")):
                    media = f'<div class="media"><audio controls><source src="{mp}"></audio></div>'
                else:
                    media = f'<div class="media"><a href="{mp}">📄 {mp}</a></div>'
            rows.append(f"""<div class="msg">
  <div class="msg-header"><span class="sender">{esc(m["sender"])}</span><span class="date">{esc(m["date"])}</span></div>
  {fwd}{reply}{text}{media}
</div>""")

        html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{css}</style></head>
<body>
<div class="header">
  <h1>{esc(title)}</h1>
  <div class="meta">
    {'<a href="' + esc(link) + '">' + esc(link) + '</a> · ' if link else ''}
    ID: {chat_id} · {total_msgs} сообщений · Период: {esc(export_start)} — {esc(export_end)}
  </div>
</div>
<div class="messages">
{''.join(rows)}
</div>
</body></html>"""
        with open(html_path, "w", encoding="utf-8") as hf:
            hf.write(html_content)

    async def _export_media_line(self, msg, media_dirs: dict, msg_id: int):
        """Download media from msg and return (markdown_line, absolute_file_path).

        Uses Obsidian's wiki-link embed syntax `![[filename]]` for media so the
        note resolves the file by name anywhere in the vault — this keeps links
        working even when the .md file and the media folder live in different
        directories (since a plain relative-path markdown link would break).
        """
        from telethon.tl.types import (
            MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
            MessageMediaGeo, MessageMediaPoll, MessageMediaContact,
            DocumentAttributeVideo, DocumentAttributeAudio,
            DocumentAttributeSticker, DocumentAttributeAnimated,
            DocumentAttributeFilename,
        )

        media = msg.media

        async def _download(file_path: str):
            """Download to file_path unless it's already there (re-export friendly)."""
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                return
            await self.client.download_media(msg, file=file_path)

        if isinstance(media, MessageMediaWebPage):
            web = getattr(media, "webpage", None)
            url = getattr(web, "url", None) if web else None
            return (f"🔗 {url}\n\n" if url else ""), None

        if isinstance(media, MessageMediaGeo):
            geo = getattr(media, "geo", None)
            return (f"📍 Геопозиция: {geo.lat}, {geo.long}\n\n" if geo else ""), None

        if isinstance(media, MessageMediaContact):
            name = f"{getattr(media,'first_name','')} {getattr(media,'last_name','')}".strip()
            phone = getattr(media, "phone_number", "")
            return f"👤 Контакт: **{name}**{' · ' + phone if phone else ''}\n\n", None

        if isinstance(media, MessageMediaPoll):
            poll = getattr(media, "poll", None)
            if poll:
                q = getattr(poll.question, "text", None) or str(poll.question)
                return f"📊 Опрос: **{q}**\n\n", None
            return "", None

        if isinstance(media, MessageMediaPhoto):
            filename = f"{msg_id:08d}.jpg"
            full_path = os.path.join(media_dirs["photos"], filename)
            try:
                await _download(full_path)
                return f"![[{filename}]]\n\n", full_path
            except Exception:
                return "📷 *[фото — ошибка загрузки]*\n\n", None

        if isinstance(media, MessageMediaDocument):
            doc = media.document
            if not doc:
                return "", None
            attrs = doc.attributes or []
            mime  = (doc.mime_type or "").lower()

            is_sticker  = any(isinstance(a, DocumentAttributeSticker)  for a in attrs)
            is_animated = any(isinstance(a, DocumentAttributeAnimated) for a in attrs)
            is_video    = any(isinstance(a, DocumentAttributeVideo)    for a in attrs)
            is_round    = any(isinstance(a, DocumentAttributeVideo) and getattr(a, "round_message", False) for a in attrs)
            is_audio    = any(isinstance(a, DocumentAttributeAudio)    for a in attrs)
            is_voice    = any(isinstance(a, DocumentAttributeAudio) and getattr(a, "voice", False) for a in attrs)
            orig_fn     = next((a.file_name for a in attrs if isinstance(a, DocumentAttributeFilename)), None)

            if is_sticker:
                ext = ".webp" if "webp" in mime else (".tgs" if "tgs" in mime else ".webp")
                fn = f"{msg_id:08d}{ext}"
                fp = os.path.join(media_dirs["stickers"], fn)
                try:
                    await _download(fp)
                    return f"![[{fn}]]\n\n", fp
                except Exception:
                    return "🎭 *[стикер — ошибка]*\n\n", None

            if is_animated or "gif" in mime:
                fn = f"{msg_id:08d}.gif" if "gif" in mime else f"{msg_id:08d}.mp4"
                fp = os.path.join(media_dirs["gif"], fn)
                try:
                    await _download(fp)
                    return f"![[{fn}]]\n\n", fp
                except Exception:
                    return "🎞 *[GIF — ошибка]*\n\n", None

            if is_video or is_round:
                fn = f"{msg_id:08d}.mp4"
                fp = os.path.join(media_dirs["videos"], fn)
                try:
                    await _download(fp)
                    return f"![[{fn}]]\n\n", fp
                except Exception:
                    return "🎥 *[видео — ошибка]*\n\n", None

            if is_voice:
                fn = f"{msg_id:08d}.ogg"
                fp = os.path.join(media_dirs["voice"], fn)
                try:
                    await _download(fp)
                    return f"![[{fn}]]\n\n", fp
                except Exception:
                    return "🎙 *[голосовое — ошибка]*\n\n", None

            if is_audio:
                _, ext = os.path.splitext(orig_fn or ".mp3")
                fn = f"{msg_id:08d}{ext or '.mp3'}"
                fp = os.path.join(media_dirs["audio"], fn)
                try:
                    await _download(fp)
                    return f"![[{fn}]]\n\n", fp
                except Exception:
                    return "🎵 *[аудио — ошибка]*\n\n", None

            # generic document — use an aliased wiki-link (resolved by filename,
            # not embedded, since arbitrary doc types can't be previewed inline)
            if orig_fn:
                safe_fn = re.sub(r"[^\w\s._\-]", "", orig_fn).strip()[:80] or "file"
                fn = f"{msg_id:08d}_{safe_fn}"
            else:
                ext = ("." + mime.split("/")[-1]) if "/" in mime else ".bin"
                fn  = f"{msg_id:08d}{ext}"
            fp = os.path.join(media_dirs["documents"], fn)
            try:
                await _download(fp)
                display = orig_fn or fn
                return f"[[{fn}|📄 {display}]]\n\n", fp
            except Exception:
                return f"📄 *[документ {orig_fn or ''} — ошибка]*\n\n", None

        return "", None

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

    # ------------------------------------------------------------------ #
    #  Blocked chats (kicked / restricted by Telegram)
    # ------------------------------------------------------------------ #

    _unsub_status: dict = {"status": "idle", "done": 0, "total": 0, "results": [], "entries": []}

    _full_export_status: dict = {
        "status": "idle",
        "current_chat_title": "",
        "current_chat_id": 0,
        "current_msg": 0,
        "current_total": 0,
        "current_media": 0,
        "chats_done": 0,
        "chats_total": 0,
        "results": [],
        "error": "",
    }

    def get_blocked_chats(self) -> dict:
        async def _scan():
            forbidden = []
            restricted = []
            seen: set[int] = set()

            for archived in (False, True):
                async for dialog in self.client.iter_dialogs(archived=archived, limit=None):
                    entity = dialog.entity
                    eid = getattr(entity, "id", None)
                    if eid is None or eid in seen:
                        continue
                    seen.add(eid)

                    if isinstance(entity, ChannelForbidden):
                        forbidden.append({
                            "id": eid,
                            "access_hash": getattr(entity, "access_hash", 0) or 0,
                            "title": getattr(entity, "title", None) or "Без названия",
                            "type": "channel",
                            "is_forbidden": True,
                            "reason": "Нет доступа (кикнули)",
                        })
                    elif isinstance(entity, ChatForbidden):
                        forbidden.append({
                            "id": eid,
                            "access_hash": 0,
                            "title": getattr(entity, "title", None) or "Без названия",
                            "type": "group",
                            "is_forbidden": True,
                            "reason": "Нет доступа (кикнули)",
                        })
                    elif isinstance(entity, Channel) and getattr(entity, "restricted", False):
                        reasons = [r.reason for r in getattr(entity, "restriction_reason", []) or []]
                        username = getattr(entity, "username", None)
                        restricted.append({
                            "id": eid,
                            "access_hash": getattr(entity, "access_hash", 0) or 0,
                            "title": dialog.name or "Без названия",
                            "type": "channel" if getattr(entity, "broadcast", False) else "group",
                            "username": username,
                            "url": f"https://t.me/{username}" if username else None,
                            "is_forbidden": False,
                            "reason": ", ".join(reasons) or "restricted",
                        })

            return {"forbidden": forbidden, "restricted": restricted}

        return self._run(_scan(), timeout=300)

    def get_unsubscribe_status(self) -> dict:
        return self._unsub_status

    def start_unsubscribe(self, entries: list[dict], batch_size: int = 0,
                          sub_delay_seconds: int = 0,
                          batch_delay_min_seconds: int = 0,
                          batch_delay_max_seconds: int = 0) -> dict:
        if self._unsub_status.get("status") in ("running", "waiting_sub", "waiting_batch"):
            return {"success": False, "error": "Отписка уже запущена"}

        self._unsub_status = {
            "status": "running",
            "done": 0,
            "total": len(entries),
            "results": [],
            "wait_type": "",
            "wait_remaining": 0,
            "wait_total": 0,
            "next_batch_wait": 0,
            "entries": entries,
        }
        asyncio.run_coroutine_threadsafe(
            self._unsubscribe_async(entries, batch_size, sub_delay_seconds,
                                    batch_delay_min_seconds, batch_delay_max_seconds),
            self.loop,
        )
        return {"success": True}

    async def _unsubscribe_async(self, entries: list[dict], batch_size: int = 0,
                                 sub_delay_seconds: int = 0,
                                 batch_delay_min_seconds: int = 0,
                                 batch_delay_max_seconds: int = 0):
        import random
        from telethon.tl.functions.channels import LeaveChannelRequest
        from telethon.tl.functions.messages import DeleteHistoryRequest
        from telethon.errors import FloodWaitError as FW
        import asyncio as aio

        results = self._unsub_status["results"]

        async def _countdown(wait_type: str, seconds: int):
            self._unsub_status["wait_type"] = wait_type
            self._unsub_status["wait_total"] = seconds
            self._unsub_status["wait_remaining"] = seconds
            for remaining in range(seconds, 0, -1):
                self._unsub_status["wait_remaining"] = remaining
                await aio.sleep(1)
            self._unsub_status["wait_type"] = ""
            self._unsub_status["wait_remaining"] = 0
            self._unsub_status["wait_total"] = 0
            self._unsub_status["next_batch_wait"] = 0

        def _random_batch_delay() -> int:
            lo = batch_delay_min_seconds
            hi = max(batch_delay_max_seconds, lo)
            return int(random.uniform(lo, hi))

        for idx, entry in enumerate(entries):
            if batch_size > 0 and batch_delay_min_seconds > 0 and idx > 0 and idx % batch_size == 0:
                wait_sec = _random_batch_delay()
                self._unsub_status["status"] = "waiting_batch"
                if idx + batch_size < len(entries):
                    self._unsub_status["next_batch_wait"] = _random_batch_delay()
                await _countdown("batch", wait_sec)
                self._unsub_status["status"] = "running"
            elif sub_delay_seconds > 0 and idx > 0:
                self._unsub_status["status"] = "waiting_sub"
                await _countdown("sub", sub_delay_seconds)
                self._unsub_status["status"] = "running"

            result = {"id": entry["id"], "title": entry["title"], "status": "", "error": ""}

            try:
                if entry.get("is_forbidden"):
                    # Kicked/banned: just delete the dialog from history
                    from telethon.tl.types import InputPeerChannel, InputPeerChat
                    if entry.get("type") == "group" and entry.get("access_hash", 0) == 0:
                        peer = InputPeerChat(entry["id"])
                    else:
                        peer = InputPeerChannel(entry["id"], entry.get("access_hash", 0))
                    await self.client(DeleteHistoryRequest(peer=peer, max_id=0, just_clear=False, revoke=False))
                else:
                    entity = await self.client.get_entity(entry["id"])
                    if isinstance(entity, Channel):
                        await self.client(LeaveChannelRequest(entity))
                    else:
                        from telethon.tl.functions.messages import DeleteChatUserRequest
                        await self.client(DeleteChatUserRequest(entry["id"], "me"))
                result["status"] = "left"
            except FW as e:
                result["status"] = "error"
                result["error"] = f"FloodWait {e.seconds}с"
                await aio.sleep(min(e.seconds, 300))
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)

            results.append(result)
            self._unsub_status["done"] += 1

        self._unsub_status["status"] = "done"

        import notifications
        left   = sum(1 for r in results if r["status"] == "left")
        errors = sum(1 for r in results if r["status"] == "error")
        notifications.notify(
            "Отписка завершена",
            f"Отписан: {left}  •  Ошибок: {errors}",
        )
