import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
from bot.handlers.dashboard import dashboard_callback, mypackages_command
from bot.handlers.track import handle_text_message, track_command
from core.poller import poll_all_active_packages
from db.session import test_connection

logger = logging.getLogger(__name__)

POLL_INTERVAL_HOURS = int(os.environ.get("POLL_INTERVAL_HOURS", "4"))


async def start_command(update, context):
    await update.message.reply_text(
        "Hey there! 👋 I'm **TrackWithThem**.\n\n"
        "Send me a tracking number and I'll keep an eye on your package for you. "
        "I work with DHL, FedEx, UPS, USPS, China Post, and more.\n\n"
        "Just paste a tracking number, or use /track <number>.\n"
        "Use /mypackages to see everything you're tracking.",
        parse_mode="Markdown",
    )


async def _startup_health_check(app: Application) -> None:
    bot_user = await app.bot.get_me()
    db_ok = await test_connection()

    logger.info(
        "TrackWithThem started — bot: @%s (id: %s), "
        "poll interval: %d hours, DB: %s",
        bot_user.username or bot_user.first_name,
        bot_user.id,
        POLL_INTERVAL_HOURS,
        "connected" if db_ok else "FAILED",
    )

    if not db_ok:
        logger.error(
            "Database connection failed on startup — "
            "check DATABASE_URL and ensure Postgres is running."
        )


def main() -> None:
    config.setup_logging()

    token = config.BOT_TOKEN
    app = (
        Application.builder()
        .token(token)
        .post_init(_startup_health_check)
        .build()
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        poll_all_active_packages,
        trigger="interval",
        hours=POLL_INTERVAL_HOURS,
        args=[app.bot],
        id="poll_packages",
        replace_existing=True,
    )
    scheduler.start()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("mypackages", mypackages_command))

    app.add_handler(CallbackQueryHandler(dashboard_callback, pattern="^dash_"))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
