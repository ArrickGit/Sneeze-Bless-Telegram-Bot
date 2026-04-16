from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from telegram import BotCommand, ForceReply, InputFile, Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackContext,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from blessyou_bot.config import Settings
from blessyou_bot.constants import HELP_TEXT
from blessyou_bot.models import Actor, Participant
from blessyou_bot.parsing import ParseError, parse_bless_text, parse_unbless_text
from blessyou_bot.storage import MongoStorage

LOGGER = logging.getLogger(__name__)

BLESS_INPUT = 1
UNBLESS_INPUT = 2
AUDIO_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "Faaah.m4a"


class UpdateDispatcher:
    def __init__(self, application: Application) -> None:
        self._application = application
        self._queue: asyncio.Queue[Update] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    async def enqueue(self, update: Update) -> None:
        if self._closed:
            raise RuntimeError("Update dispatcher is shut down")

        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

        self._queue.put_nowait(update)

    async def shutdown(self) -> None:
        self._closed = True
        await self._queue.join()

        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker

    async def _run(self) -> None:
        while True:
            update = await self._queue.get()
            try:
                await self._application.process_update(update)
            except Exception:
                LOGGER.exception("Failed to process queued update")
            finally:
                self._queue.task_done()


def create_application(settings: Settings, storage: MongoStorage) -> Application:
    application = (
        Application.builder()
        .token(settings.bot_token)
        .rate_limiter(AIORateLimiter(max_retries=3))
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["storage"] = storage
    application.add_handler(MessageHandler(filters.ALL, remember_seen_users), group=-1)

    bless_flow = ConversationHandler(
        entry_points=[CommandHandler("bless", bless_entry)],
        states={
            BLESS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bless_reply)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )

    unbless_flow = ConversationHandler(
        entry_points=[CommandHandler("unbless", unbless_entry)],
        states={
            UNBLESS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, unbless_reply)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("hardreset", hard_reset))
    application.add_handler(CommandHandler("blessme", bless_me))
    application.add_handler(CommandHandler("faaaah", faaaah))
    application.add_handler(bless_flow)
    application.add_handler(unbless_flow)
    application.add_handler(CommandHandler("scoreboard", scoreboard))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("addrule", add_rule))
    application.add_handler(CommandHandler("removerule", remove_rule))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_error_handler(error_handler)
    return application


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Bless You Sneeze Bot is ready.\n\n"
        "Use /help to see commands, or head to your group chat and try /bless."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


async def faaaah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not AUDIO_FILE_PATH.exists():
        LOGGER.error("Faaah audio file is missing at %s", AUDIO_FILE_PATH)
        await update.effective_message.reply_text("The faaah is temporarily unavailable.")
        return

    with AUDIO_FILE_PATH.open("rb") as audio_file:
        await update.effective_message.reply_audio(
            audio=InputFile(audio_file, filename=AUDIO_FILE_PATH.name),
            title="Faaah",
        )


async def bless_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_group_chat(update):
        return

    if context.args:
        await update.effective_message.reply_text("Usage: /blessme")
        return

    user = update.effective_user
    if user is None or not user.username:
        await update.effective_message.reply_text(
            "You need a Telegram username before you can use /blessme."
        )
        return

    storage = get_storage(context)
    actor = build_actor(update)
    participant = Participant(key=user.username.lower(), handle=f"@{user.username.lower()}")
    results = await storage.bless(update.effective_chat.id, [participant], 2, actor)
    result = results[0]

    await update.effective_message.reply_text(
        f"Self bless recorded: {result['handle']} +2 (now {result['points']})"
    )


async def bless_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_group_chat(update):
        return ConversationHandler.END

    if context.args:
        await process_bless(update, context, " ".join(context.args))
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "Reply with 1 or 2 Telegram handles, with an optional amount at the end.\n\n"
        "Examples:\n@alice @bob\n@alice\n@alice 100000\n@alice @bob 100000",
        reply_markup=ForceReply(selective=True),
    )
    return BLESS_INPUT


async def bless_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    success = await process_bless(update, context, update.effective_message.text)
    return ConversationHandler.END if success else BLESS_INPUT


async def process_bless(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> bool:
    storage = get_storage(context)
    chat_id = update.effective_chat.id

    try:
        parsed = parse_bless_text(raw_text)
    except ParseError as exc:
        await update.effective_message.reply_text(str(exc))
        return False

    if not await validate_group_participants(update, context, parsed.participants):
        return False

    actor = build_actor(update)
    results = await storage.bless(chat_id, parsed.participants, parsed.amount, actor)

    lines = ["Bless recorded!"]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result['handle']} +{parsed.amount} (now {result['points']})")
    if len(results) == 1:
        lines.append("No second blesser recorded this round.")

    await update.effective_message.reply_text("\n".join(lines))
    return True


async def unbless_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_group_chat(update):
        return ConversationHandler.END

    if context.args:
        await process_unbless(update, context, " ".join(context.args))
        return ConversationHandler.END

    settings = get_settings(context)
    await update.effective_message.reply_text(
        "Reply with the penalty details.\n\nExamples:\n"
        f"@alice\n@alice {settings.default_unbless_penalty}\n"
        "@alice -2 early blessing during a sneeze streak\n"
        "@alice 2 early blessing during a sneeze streak",
        reply_markup=ForceReply(selective=True),
    )
    return UNBLESS_INPUT


async def unbless_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    success = await process_unbless(update, context, update.effective_message.text)
    return ConversationHandler.END if success else UNBLESS_INPUT


async def process_unbless(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> bool:
    storage = get_storage(context)
    settings = get_settings(context)
    chat_id = update.effective_chat.id

    try:
        parsed = parse_unbless_text(raw_text, settings.default_unbless_penalty)
    except ParseError as exc:
        await update.effective_message.reply_text(str(exc))
        return False

    if not await validate_group_participants(update, context, [parsed.participant]):
        return False

    actor = build_actor(update)
    result = await storage.unbless(
        chat_id=chat_id,
        participant=parsed.participant,
        amount=parsed.amount,
        actor=actor,
        reason=parsed.reason,
    )

    message = f"Penalty recorded: {result['handle']} -{parsed.amount} (now {result['points']})"
    if parsed.reason:
        message = f"{message}\nReason: {parsed.reason}"
    await update.effective_message.reply_text(message)
    return True


async def scoreboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_group_chat(update):
        return

    storage = get_storage(context)
    settings = get_settings(context)
    rows = await storage.get_scoreboard(update.effective_chat.id, settings.scoreboard_limit)

    if not rows:
        await update.effective_message.reply_text("No bless points yet. Someone needs to sneeze first.")
        return

    lines = ["Bless You Scoreboard"]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row['handle']} - {row['points']}")
    await update.effective_message.reply_text("\n".join(lines))


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_group_chat(update):
        return

    storage = get_storage(context)
    rules_list = await storage.list_rules(update.effective_chat.id)
    lines = ["Bless You rules:"]
    for index, rule in enumerate(rules_list, start=1):
        lines.append(f"{index}. {rule}")
    await update.effective_message.reply_text("\n".join(lines))


async def add_rule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_group_chat(update):
        return

    if not await require_admin(update, context):
        return

    rule_text = " ".join(context.args).strip()
    if not rule_text:
        await update.effective_message.reply_text("Usage: /addrule Your new rule here")
        return

    storage = get_storage(context)
    rules_list = await storage.add_rule(update.effective_chat.id, rule_text)
    await update.effective_message.reply_text(f"Rule added. There are now {len(rules_list)} rules.")


async def remove_rule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_group_chat(update):
        return

    if not await require_admin(update, context):
        return

    if not context.args:
        await update.effective_message.reply_text("Usage: /removerule 3")
        return

    try:
        index = int(context.args[0]) - 1
    except ValueError:
        await update.effective_message.reply_text("Please provide a rule number, like /removerule 3")
        return

    storage = get_storage(context)
    try:
        rules_list = await storage.remove_rule(update.effective_chat.id, index)
    except IndexError:
        await update.effective_message.reply_text("That rule number does not exist.")
        return

    await update.effective_message.reply_text(f"Rule removed. {len(rules_list)} rules remain.")


async def hard_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner_private_chat(update, context):
        return

    if len(context.args) != 1 or context.args[0].strip().lower() != "confirm":
        await update.effective_message.reply_text(
            "This will wipe all bless scores, events, and custom rules across every chat.\n\n"
            "If you really want to do it, send:\n/hardreset confirm"
        )
        return

    storage = get_storage(context)
    counts = await storage.hard_reset()
    await update.effective_message.reply_text(
        "Hard reset complete.\n"
        f"Deleted {counts['scores']} score rows, {counts['events']} event rows, "
        f"and {counts['rules']} rule documents.\n"
        "Known users were kept."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Canceled.")
    return ConversationHandler.END


async def require_group_chat(update: Update) -> bool:
    chat = update.effective_chat
    if chat and chat.type in {"group", "supergroup"}:
        return True

    await update.effective_message.reply_text("This command is meant for a Telegram group chat.")
    return False


async def remember_seen_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = get_storage(context)
    users: dict[int, tuple[str | None, str]] = {}

    effective_user = update.effective_user
    if effective_user is not None:
        users[effective_user.id] = (effective_user.username, effective_user.full_name)

    message = update.effective_message
    if message is not None:
        reply_to_message = message.reply_to_message
        if reply_to_message and reply_to_message.from_user is not None:
            reply_user = reply_to_message.from_user
            users[reply_user.id] = (reply_user.username, reply_user.full_name)

        for member in message.new_chat_members or []:
            users[member.id] = (member.username, member.full_name)

    for user_id, (username, full_name) in users.items():
        await storage.remember_user(user_id, username, full_name)


async def validate_group_participants(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    participants: list,
) -> bool:
    storage = get_storage(context)
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return False

    for participant in participants:
        known_user = await storage.find_user_by_username(participant.key)
        if known_user is None:
            await message.reply_text(
                f"I can't verify {participant.handle} yet.\n"
                "Ask that person to message the bot once, or use a bot command once, so I can confirm them."
            )
            return False

        try:
            member = await context.bot.get_chat_member(chat.id, known_user["user_id"])
        except TelegramError:
            await message.reply_text(f"{participant.handle} is not a valid member of this group.")
            return False

        if member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}:
            await message.reply_text(f"{participant.handle} is not currently in this group.")
            return False

    return True


async def require_owner_private_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = get_settings(context)
    chat = update.effective_chat
    user = update.effective_user

    if chat is None or user is None:
        return False

    if chat.type != "private":
        await update.effective_message.reply_text("This command only works in a private chat with the bot.")
        return False

    if settings.owner_user_id is None:
        await update.effective_message.reply_text("OWNER_USER_ID is not configured for this bot.")
        return False

    if user.id != settings.owner_user_id:
        await update.effective_message.reply_text("You are not allowed to use this command.")
        return False

    return True


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
        return True

    await update.effective_message.reply_text("Only chat admins can change the rules.")
    return False


def build_actor(update: Update) -> Actor:
    user = update.effective_user
    if not user:
        return Actor(user_id=None, username=None, full_name="Unknown user")
    return Actor(user_id=user.id, username=user.username, full_name=user.full_name)


def get_storage(context: CallbackContext) -> MongoStorage:
    return context.application.bot_data["storage"]


def get_settings(context: CallbackContext) -> Settings:
    return context.application.bot_data["settings"]


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Unhandled exception while processing update", exc_info=context.error)


async def configure_application(application: Application, settings: Settings) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("bless", "Award points to blessers"),
            BotCommand("blessme", "Bless yourself for +2 points"),
            BotCommand("faaaah", "Play the faaah audio"),
            BotCommand("unbless", "Deduct points for a rule break"),
            BotCommand("scoreboard", "Show the current rankings"),
            BotCommand("rules", "Show the chat rules"),
            BotCommand("addrule", "Add a rule (admins only)"),
            BotCommand("removerule", "Remove a rule (admins only)"),
            BotCommand("help", "Show command help"),
        ]
    )


async def run_polling(settings: Settings) -> None:
    storage = MongoStorage(settings.mongodb_uri, settings.database_name)
    application = create_application(settings, storage)

    await storage.connect()
    await storage.ensure_indexes()
    LOGGER.info("Connected to MongoDB and ensured indexes")
    await application.initialize()
    await configure_application(application, settings)
    await application.bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates_on_polling)
    await application.start()

    if application.updater is None:
        raise RuntimeError("Polling requires an updater")

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=settings.drop_pending_updates_on_polling,
    )
    LOGGER.info("Bless You Sneeze Bot is running in polling mode")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await storage.close()


def create_web_app() -> FastAPI:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    storage = MongoStorage(settings.mongodb_uri, settings.database_name)
    application = create_application(settings, storage)
    dispatcher = UpdateDispatcher(application)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await storage.connect()
        await storage.ensure_indexes()
        LOGGER.info("Connected to MongoDB and ensured indexes")
        await application.initialize()
        await configure_application(application, settings)
        await application.start()
        await application.bot.set_webhook(
            url=settings.webhook_url,
            secret_token=settings.webhook_secret,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=settings.drop_pending_updates_on_webhook_start,
        )
        LOGGER.info("Webhook configured at %s", settings.webhook_url)
        try:
            yield
        finally:
            LOGGER.info("Shutting down webhook worker without deleting Telegram webhook")
            await dispatcher.shutdown()
            await application.stop()
            await application.shutdown()
            await storage.close()

    web_app = FastAPI(title="Bless You Sneeze Bot", lifespan=lifespan)

    @web_app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @web_app.post(settings.webhook_path)
    async def telegram_webhook(request: Request) -> dict[str, bool]:
        if settings.webhook_secret:
            provided_secret = request.headers.get("x-telegram-bot-api-secret-token")
            if provided_secret != settings.webhook_secret:
                raise HTTPException(status_code=401, detail="Invalid webhook secret")

        payload = await request.json()
        update = Update.de_json(payload, application.bot)
        await dispatcher.enqueue(update)
        return {"ok": True}

    return web_app


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    if settings.bot_mode == "webhook":
        raise SystemExit("BOT_MODE=webhook is meant for `uvicorn asgi:web_app`")

    asyncio.run(run_polling(settings))
