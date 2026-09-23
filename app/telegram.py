from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import Settings
from app.healthcheck import check_host
from app.switcher import load_state, save_state, switch_all
from app.vpn_config import VpnConfigError, normalize_host

LOGGER = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, settings: Settings) -> None:
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self.settings = settings
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self.client = httpx.AsyncClient(timeout=35)
        self.offset = 0

    async def close(self) -> None:
        await self.client.aclose()

    async def _api(self, method: str, **payload: Any) -> dict:
        response = await self.client.post(f"{self.base_url}/{method}", json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body.get('description', 'unknown error')}")
        return body

    async def send(self, chat_id: int, text: str) -> None:
        await self._api("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)

    def _chat_allowed(self, chat_id: int) -> bool:
        expected = self.settings.telegram_chat_id
        return expected is not None and chat_id == expected

    def _admin_allowed(self, user_id: int) -> bool:
        admins = self.settings.telegram_admin_user_ids
        return bool(admins) and user_id in admins

    async def _handle_message(self, message: dict) -> None:
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return

        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = int(chat.get("id"))
        user_id = int(sender.get("id"))
        command, *args = text.split()
        command = command.split("@", 1)[0].lower()

        if command == "/chatid":
            await self.send(chat_id, f"chat_id={chat_id}\nuser_id={user_id}")
            return

        if self.settings.telegram_chat_id is None:
            await self.send(
                chat_id,
                "TELEGRAM_CHAT_ID ещё не настроен. Выполни /chatid, внеси значение в .env и перезапусти контейнер.",
            )
            return

        if not self._chat_allowed(chat_id):
            LOGGER.warning("Ignoring command from unauthorized chat_id=%s user_id=%s", chat_id, user_id)
            return

        if command in {"/help", "/start"}:
            await self.send(
                chat_id,
                "Команды:\n"
                "/status — текущее состояние\n"
                "/switch <ip|host> — переключить endpoint во всех .vpn\n"
                "/chatid — показать chat_id и user_id",
            )
            return

        if command == "/status":
            state = load_state(self.settings.state_file)
            config_count = len(list(self.settings.vpn_config_dir.glob("*.vpn")))
            if state:
                await self.send(
                    chat_id,
                    f"Текущий endpoint: {state.get('host')}\n"
                    f"Последнее переключение: {state.get('updated_at')}\n"
                    f"Исходных конфигов: {config_count}",
                )
            else:
                await self.send(chat_id, f"Переключений ещё не было. Исходных конфигов: {config_count}")
            return

        if command == "/switch":
            if not self._admin_allowed(user_id):
                await self.send(
                    chat_id,
                    "Команда /switch запрещена для этого user_id. Добавь его в TELEGRAM_ADMIN_USER_IDS.",
                )
                return
            if len(args) != 1:
                await self.send(chat_id, "Использование: /switch <новый-ip-или-hostname>")
                return

            try:
                new_host = normalize_host(args[0])
            except VpnConfigError as exc:
                await self.send(chat_id, f"Некорректный endpoint: {exc}")
                return

            ok, check_message = await check_host(
                new_host,
                self.settings.healthcheck_mode,
                self.settings.healthcheck_timeout_seconds,
            )
            if not ok:
                await self.send(chat_id, f"Переключение отменено: health check не прошёл ({check_message}).")
                return

            try:
                summary, _ = await asyncio.to_thread(
                    switch_all,
                    self.settings.vpn_config_dir,
                    self.settings.vpn_output_dir,
                    new_host,
                )
                await asyncio.to_thread(save_state, self.settings.state_file, summary)
            except (FileNotFoundError, VpnConfigError, OSError) as exc:
                LOGGER.exception("Switch failed")
                await self.send(chat_id, f"Ошибка переключения: {exc}")
                return

            await self.send(
                chat_id,
                f"VPN endpoint переключён на {summary.host}.\n"
                f"Обновлено конфигов: {summary.files}; полей: {summary.changes}.\n"
                f"Новые .vpn сохранены на сервере в {self.settings.vpn_output_dir}.\n"
                "Содержимое конфигов в Telegram не отправляю: в них есть клиентские ключи.",
            )
            return

        await self.send(chat_id, "Неизвестная команда. /help")

    async def run(self) -> None:
        LOGGER.info("Telegram bot started")
        while True:
            try:
                body = await self._api(
                    "getUpdates",
                    offset=self.offset,
                    timeout=30,
                    allowed_updates=["message"],
                )
                for update in body.get("result", []):
                    self.offset = max(self.offset, int(update["update_id"]) + 1)
                    message = update.get("message")
                    if message:
                        await self._handle_message(message)
            except httpx.HTTPError:
                LOGGER.exception("Telegram HTTP error")
                await asyncio.sleep(3)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected bot error")
                await asyncio.sleep(3)
