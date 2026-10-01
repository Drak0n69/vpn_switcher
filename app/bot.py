from __future__ import annotations

import logging
import secrets
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import Settings
from app.distributor import build_plan, distribute, format_plan
from app.storage import load_recipients, load_yaml_mapping, save_registration

LOGGER = logging.getLogger(__name__)


@dataclass
class PendingDistribution:
    token: str
    expires_at: datetime


class VpnDeliveryBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pending: dict[int, PendingDistribution] = {}

    def _is_admin(self, update: Update) -> bool:
        user = update.effective_user
        return bool(user and user.id in self.settings.admin_user_ids)

    async def _require_admin(self, update: Update) -> bool:
        if self._is_admin(update):
            return True
        if update.effective_message:
            await update.effective_message.reply_text("Команда доступна только администратору.")
        return False


    def _registration_errors(self, recipients) -> list[str]:
        registrations = load_yaml_mapping(self.settings.registrations_file, "registrations")
        errors: list[str] = []
        for recipient in recipients:
            registered = registrations.get(str(recipient.user_id))
            if not isinstance(registered, dict):
                errors.append(f"{recipient.name}: user_id {recipient.user_id} не зарегистрирован через /start")
                continue
            registered_chat_id = registered.get("chat_id")
            try:
                registered_chat_id = int(registered_chat_id)
            except (TypeError, ValueError):
                errors.append(f"{recipient.name}: в регистрации отсутствует корректный chat_id")
                continue
            if registered_chat_id != recipient.chat_id:
                errors.append(
                    f"{recipient.name}: chat_id в recipients.yml ({recipient.chat_id}) "
                    f"не совпадает с зарегистрированным ({registered_chat_id})"
                )
        return errors

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        user = update.effective_user
        chat = update.effective_chat
        message = update.effective_message
        if not user or not chat or not message:
            return
        if chat.type != "private":
            await message.reply_text("Для регистрации напишите боту /start в личном чате.")
            return
        save_registration(
            self.settings.registrations_file,
            user_id=user.id,
            chat_id=chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await message.reply_text(
            "Регистрация сохранена.\n"
            f"Ваш Telegram user_id: {user.id}\n\n"
            "Администратор привяжет к нему ваши VPN-конфигурации."
        )

    async def whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if update.effective_user and update.effective_message:
            await update.effective_message.reply_text(f"Ваш Telegram user_id: {update.effective_user.id}")

    async def registrations(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_admin(update):
            return
        registrations = load_yaml_mapping(self.settings.registrations_file, "registrations")
        if not registrations:
            await update.effective_message.reply_text("Пока никто не зарегистрировался.")
            return
        lines = ["Зарегистрированные пользователи:"]
        for user_id, item in sorted(registrations.items()):
            username = item.get("username") or "—"
            first = item.get("first_name") or ""
            last = item.get("last_name") or ""
            lines.append(f"• {user_id} | @{username} | {(first + ' ' + last).strip()}")
        await update.effective_message.reply_text("\n".join(lines)[:4000])

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_admin(update):
            return
        try:
            recipients = load_recipients(self.settings.recipients_file)
            registration_errors = self._registration_errors(recipients)
            plan = build_plan(
                self.settings.config_dir,
                recipients,
                self.settings.delivery_state_file,
                self.settings.skip_unchanged,
            )
            text = format_plan(plan, self.settings.config_dir)
            if registration_errors:
                text += "\n\nПроблемы регистрации:\n" + "\n".join(
                    f"  - {item}" for item in registration_errors[:20]
                )
            await update.effective_message.reply_text(text[:4000])
        except Exception as exc:
            LOGGER.exception("Status failed")
            await update.effective_message.reply_text(f"Ошибка проверки: {type(exc).__name__}: {exc}")

    async def distribute_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not await self._require_admin(update):
            return
        try:
            recipients = load_recipients(self.settings.recipients_file)
            registration_errors = self._registration_errors(recipients)
            plan = build_plan(
                self.settings.config_dir,
                recipients,
                self.settings.delivery_state_file,
                self.settings.skip_unchanged,
            )
            preview = format_plan(plan, self.settings.config_dir)
            if registration_errors:
                preview += "\n\nПроблемы регистрации:\n" + "\n".join(
                    f"  - {item}" for item in registration_errors[:20]
                )
                await update.effective_message.reply_text(
                    (preview + "\n\nРассылка заблокирована: исправьте регистрации/привязки.")[:4000]
                )
                return
            if plan.missing_count:
                await update.effective_message.reply_text(
                    (preview + "\n\nРассылка заблокирована: сначала устраните отсутствующие файлы.")[:4000]
                )
                return
            if plan.sendable_count == 0:
                await update.effective_message.reply_text((preview + "\n\nНовых файлов для отправки нет.")[:4000])
                return
            token = secrets.token_hex(3)
            admin_id = update.effective_user.id
            self.pending[admin_id] = PendingDistribution(
                token=token,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            await update.effective_message.reply_text(
                (preview + f"\n\nДля запуска: /confirm {token}\nПодтверждение действует 10 минут.")[:4000]
            )
        except Exception as exc:
            LOGGER.exception("Distribution preview failed")
            await update.effective_message.reply_text(f"Ошибка проверки: {type(exc).__name__}: {exc}")

    async def confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_admin(update):
            return
        admin_id = update.effective_user.id
        pending = self.pending.get(admin_id)
        if not pending:
            await update.effective_message.reply_text("Нет ожидающей рассылки. Сначала выполните /distribute.")
            return
        if datetime.now(timezone.utc) > pending.expires_at:
            self.pending.pop(admin_id, None)
            await update.effective_message.reply_text("Подтверждение истекло. Повторите /distribute.")
            return
        try:
            args = shlex.split(" ".join(context.args))
        except ValueError:
            args = context.args
        if len(args) != 1 or args[0] != pending.token:
            await update.effective_message.reply_text("Неверный код подтверждения.")
            return

        # Build the plan again so the confirmation cannot send stale files from the preview.
        try:
            recipients = load_recipients(self.settings.recipients_file)
            registration_errors = self._registration_errors(recipients)
            if registration_errors:
                await update.effective_message.reply_text(
                    "Рассылка отменена: регистрации изменились после preview. Выполните /status."
                )
                return
            plan = build_plan(
                self.settings.config_dir,
                recipients,
                self.settings.delivery_state_file,
                self.settings.skip_unchanged,
            )
            if plan.missing_count:
                await update.effective_message.reply_text("Рассылка отменена: после preview появились отсутствующие файлы.")
                return
            self.pending.pop(admin_id, None)
            await update.effective_message.reply_text(f"Начинаю персональную рассылку: {plan.sendable_count} файл(а/ов).")
            result = await distribute(
                context.bot,
                plan,
                config_dir=self.settings.config_dir,
                delivery_state_file=self.settings.delivery_state_file,
                send_delay_seconds=self.settings.send_delay_seconds,
            )
            lines = [
                "Рассылка завершена.",
                f"• отправлено: {result.sent}",
                f"• пропущено без изменений: {result.skipped_unchanged}",
                f"• ошибок: {len(result.failed)}",
            ]
            if result.failed:
                lines.append("\nОшибки:")
                lines.extend(f"  - {item}" for item in result.failed[:15])
                if len(result.failed) > 15:
                    lines.append(f"  ... ещё {len(result.failed) - 15}")
            await update.effective_message.reply_text("\n".join(lines)[:4000])
            if self.settings.announcement_chat_id is not None and result.sent > 0:
                try:
                    await context.bot.send_message(
                        chat_id=self.settings.announcement_chat_id,
                        text=(
                            "VPN-сервер обновлён. Свежие конфигурации отправлены пользователям "
                            "ботом в личные сообщения."
                        ),
                    )
                except Exception as announcement_exc:
                    LOGGER.exception("Announcement failed")
                    await update.effective_message.reply_text(
                        "Файлы разосланы, но не удалось отправить уведомление в общую группу: "
                        f"{type(announcement_exc).__name__}: {announcement_exc}"
                    )
        except Exception as exc:
            LOGGER.exception("Distribution failed")
            await update.effective_message.reply_text(f"Ошибка рассылки: {type(exc).__name__}: {exc}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.effective_message:
            return
        if self._is_admin(update):
            text = (
                "/start — зарегистрировать личный чат\n"
                "/whoami — показать свой Telegram user_id\n"
                "/registrations — список регистраций\n"
                "/status — проверить привязки и файлы\n"
                "/distribute — preview персональной рассылки\n"
                "/confirm CODE — подтвердить рассылку\n"
                "/help — помощь"
            )
        else:
            text = "/start — зарегистрироваться\n/whoami — показать свой Telegram user_id"
        await update.effective_message.reply_text(text)

    def build_application(self) -> Application:
        app = Application.builder().token(self.settings.bot_token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("whoami", self.whoami))
        app.add_handler(CommandHandler("registrations", self.registrations))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("distribute", self.distribute_request))
        app.add_handler(CommandHandler("confirm", self.confirm))
        app.add_handler(CommandHandler("help", self.help_command))
        return app
